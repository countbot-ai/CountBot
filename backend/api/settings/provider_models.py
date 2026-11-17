"""供应商模型清单的读写接口（增删改排序）；切换当前模型仍走 PUT /api/settings 的 model 节。"""

import time
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from loguru import logger

from backend.modules.config.loader import config_loader
from backend.modules.config.schema import AppConfig, ModelEntry, ProviderConfig
from backend.modules.providers.factory import resolve_api_type
from backend.modules.providers.registry import get_provider_metadata

from backend.api.settings._router import router
from backend.api.settings.model_catalog import (
    ModelCatalogError,
    fetch_provider_models,
)
from backend.modules.providers.thinking_profiles import (
    KNOWN_REASONING_LEVELS,
    resolve_model_reasoning_levels,
)

from backend.api.settings.models import (
    AddProviderModelsRequest,
    ReasoningLevelsResponse,
    ProviderConnectionTestResponse,
    ProviderModelCatalogEntry,
    ProviderModelCatalogResponse,
    ProviderModelPayload,
    ReorderProviderModelsRequest,
    UpdateProviderModelRequest,
)


_MODEL_SOURCES = ("builtin", "manual", "fetched")


@router.get("/reasoning-levels", response_model=ReasoningLevelsResponse)
async def get_reasoning_levels(model: str = "") -> ReasoningLevelsResponse:
    """思考档位内置建议：模型编辑弹窗用它作为初始勾选项。

    内置表只是默认值：用户可以在模型条目里自由增删档位，自定义模型同样可填，
    因此这里只做「建议」查询，不参与保存校验。
    """
    return ReasoningLevelsResponse(
        model=model,
        levels=resolve_model_reasoning_levels(model),
        known_levels=list(KNOWN_REASONING_LEVELS),
    )


def _get_provider_or_404(
    config: AppConfig,
    provider_id: str,
) -> ProviderConfig:
    """取供应商配置；未知 ID 直接 404，不隐式建条目。"""
    provider = config.providers.get(provider_id)
    if provider is not None:
        return provider

    if get_provider_metadata(provider_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"未知的供应商: {provider_id}",
        )

    # 注册表里有但配置里还没有：补一条默认条目，保持与 AppConfig 初始化一致
    provider = ProviderConfig(
        api_base=get_provider_metadata(provider_id).default_api_base
    )
    config.providers[provider_id] = provider
    return provider


def _resolve_effective_api_base(
    provider_id: str,
    provider: ProviderConfig,
) -> Optional[str]:
    metadata = get_provider_metadata(provider_id)
    return (provider.api_base or "").strip() or (
        metadata.default_api_base if metadata else None
    )


def _resolve_effective_api_key(provider: ProviderConfig) -> str:
    keys = provider.get_effective_api_keys()
    return keys[0] if keys else ""


async def _save_and_reload(config: AppConfig) -> None:
    """落盘并刷新运行时，保证新模型立刻可选。"""
    from backend.modules.config.loader import config_loader as loader

    await loader.save_config(config)


def _serialize_models(provider: ProviderConfig) -> List[Dict[str, Any]]:
    return [entry.model_dump() for entry in provider.models]


@router.get(
    "/providers/{provider_id}/models/catalog",
    response_model=ProviderModelCatalogResponse,
)
async def get_provider_model_catalog(provider_id: str) -> ProviderModelCatalogResponse:
    """拉取上游可用模型（不写配置，由前端多选后再提交）。"""
    config = config_loader.config
    provider = _get_provider_or_404(config, provider_id)
    api_type = resolve_api_type(provider_id, provider.api_type)

    try:
        models = await fetch_provider_models(
            api_base=_resolve_effective_api_base(provider_id, provider),
            api_key=_resolve_effective_api_key(provider),
            api_type=api_type,
        )
    except ModelCatalogError as exc:
        return ProviderModelCatalogResponse(
            success=False,
            provider=provider_id,
            error=str(exc),
        )

    return ProviderModelCatalogResponse(
        success=True,
        provider=provider_id,
        models=[
            ProviderModelCatalogEntry(
                id=entry[0],
                display_name=entry[1],
                owned_by=entry[2],
                # 兼容三元组形态（上游未提供窗口时省略第 4 项）
                context_window=entry[3] if len(entry) > 3 else None,
            )
            for entry in models
        ],
    )


@router.post(
    "/providers/{provider_id}/models",
    response_model=List[Dict[str, Any]],
)
async def add_provider_models(
    provider_id: str,
    request: AddProviderModelsRequest,
) -> List[Dict[str, Any]]:
    """批量添加模型；已存在的 ID 只更新来源与显式字段，不重复插入。"""
    # 就地修改而非 model_copy：save_config 会把它设为运行时配置，复制品会造成两份真相。
    config = config_loader.config
    provider = _get_provider_or_404(config, provider_id)

    added = 0
    for payload in request.models:
        model_id = (payload.id or "").strip()
        if not model_id:
            continue

        existing = provider.find_model(model_id)
        if existing is None:
            provider.models.append(_to_model_entry(payload, request.source))
            added += 1
            continue

        # 已存在：只补空字段，不覆盖用户改过的展示名与开关
        if payload.display_name and not existing.display_name:
            existing.display_name = payload.display_name.strip()
        if payload.context_window and not existing.context_window:
            existing.context_window = payload.context_window
        if payload.supports_image is not None and existing.supports_image is None:
            existing.supports_image = payload.supports_image
        if payload.reasoning_levels and not existing.reasoning_levels:
            existing.reasoning_levels = _normalize_reasoning_levels(payload.reasoning_levels)
        if payload.reasoning_level and not existing.reasoning_level:
            existing.reasoning_level = _normalize_single_level(payload.reasoning_level)

    config._migrate_provider_models()
    await _save_and_reload(config)
    logger.info(f"Added {added} models to provider {provider_id}")
    return _serialize_models(config.providers[provider_id])


@router.put(
    "/providers/{provider_id}/models/order",
    response_model=List[Dict[str, Any]],
)
async def reorder_provider_models(
    provider_id: str,
    request: ReorderProviderModelsRequest,
) -> List[Dict[str, Any]]:
    """按传入顺序重排模型；未出现在列表里的模型保持相对顺序附在末尾。"""
    # 就地修改而非 model_copy：save_config 会把它设为运行时配置，复制品会造成两份真相。
    config = config_loader.config
    provider = _get_provider_or_404(config, provider_id)

    order = [model_id for model_id in request.model_ids if model_id]
    by_id = {entry.id: entry for entry in provider.models}

    reordered: List[ModelEntry] = []
    used: set[str] = set()
    for model_id in order:
        entry = by_id.get(model_id)
        if entry is not None and model_id not in used:
            reordered.append(entry)
            used.add(model_id)
    for entry in provider.models:
        if entry.id not in used:
            reordered.append(entry)

    provider.models = reordered
    await _save_and_reload(config)
    return _serialize_models(config.providers[provider_id])


@router.put(
    "/providers/{provider_id}/models/{model_id}",
    response_model=List[Dict[str, Any]],
)
async def update_provider_model(
    provider_id: str,
    model_id: str,
    request: UpdateProviderModelRequest,
) -> List[Dict[str, Any]]:
    """更新单个模型（部分更新）。"""
    # 就地修改而非 model_copy：save_config 会把它设为运行时配置，复制品会造成两份真相。
    config = config_loader.config
    provider = _get_provider_or_404(config, provider_id)

    entry = provider.find_model(model_id)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"供应商 {provider_id} 下没有模型 {model_id}",
        )

    if request.clear_display_name:
        entry.display_name = None
    elif request.display_name is not None:
        entry.display_name = request.display_name.strip() or None

    if request.enabled is not None:
        entry.enabled = bool(request.enabled)

    if request.clear_context_window:
        entry.context_window = None
    elif request.context_window is not None:
        entry.context_window = request.context_window if request.context_window > 0 else None

    if request.clear_supports_image:
        entry.supports_image = None
    elif request.supports_image is not None:
        entry.supports_image = request.supports_image

    if request.reasoning_levels is not None:
        entry.reasoning_levels = _normalize_reasoning_levels(request.reasoning_levels)

    if request.clear_reasoning_level:
        entry.reasoning_level = None
    elif request.reasoning_level is not None:
        entry.reasoning_level = _normalize_single_level(request.reasoning_level)

    await _save_and_reload(config)
    return _serialize_models(config.providers[provider_id])


@router.delete(
    "/providers/{provider_id}/models/{model_id}",
    response_model=List[Dict[str, Any]],
)
async def delete_provider_model(
    provider_id: str,
    model_id: str,
) -> List[Dict[str, Any]]:
    """删除单个模型；若删的是当前选中模型，则回落到清单首个可用模型。"""
    # 就地修改而非 model_copy：save_config 会把它设为运行时配置，复制品会造成两份真相。
    config = config_loader.config
    provider = _get_provider_or_404(config, provider_id)

    before = len(provider.models)
    provider.models = [entry for entry in provider.models if entry.id != model_id]
    if len(provider.models) == before:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"供应商 {provider_id} 下没有模型 {model_id}",
        )

    if config.model.provider == provider_id and config.model.model == model_id:
        fallback_ids = provider.get_model_ids() or provider.get_model_ids(
            include_disabled=True
        )
        if fallback_ids:
            config.model.model = fallback_ids[0]
        else:
            config.model.model = ""
            config.model.provider = ""

    await _save_and_reload(config)
    logger.info(f"Deleted model {model_id} from provider {provider_id}")
    return _serialize_models(config.providers[provider_id])


@router.post(
    "/providers/{provider_id}/test",
    response_model=ProviderConnectionTestResponse,
)
async def test_provider_connection(provider_id: str) -> ProviderConnectionTestResponse:
    """供应商级连通性测试：只拉模型列表，不消耗对话 token。"""
    config = config_loader.config
    provider = _get_provider_or_404(config, provider_id)
    api_type = resolve_api_type(provider_id, provider.api_type)

    started = time.perf_counter()
    try:
        models = await fetch_provider_models(
            api_base=_resolve_effective_api_base(provider_id, provider),
            api_key=_resolve_effective_api_key(provider),
            api_type=api_type,
        )
    except ModelCatalogError as exc:
        return ProviderConnectionTestResponse(success=False, error=str(exc))

    latency_ms = int((time.perf_counter() - started) * 1000)
    return ProviderConnectionTestResponse(
        success=True,
        latency_ms=latency_ms,
        model_count=len(models),
    )


def _normalize_reasoning_levels(levels: Optional[List[str]]) -> List[str]:
    """档位列表归一化：小写去空白、去重、保序；非法值直接丢弃。

    不做「必须命中内置表」的校验——用户给自定义模型填自定义档位必须放行。
    """
    normalized: List[str] = []
    for raw in levels or []:
        level = str(raw or "").strip().lower()
        if not level or level in normalized:
            continue
        normalized.append(level)
    return normalized


def _normalize_single_level(level: Optional[str]) -> Optional[str]:
    normalized = str(level or "").strip().lower()
    return normalized or None


def _to_model_entry(payload: ProviderModelPayload, default_source: str) -> ModelEntry:
    # 条目自身显式给了来源就以它为准，否则跟随本次批量提交的来源
    explicit_source = str(payload.source or "").strip().lower()
    source = explicit_source if explicit_source in _MODEL_SOURCES else default_source
    if source not in _MODEL_SOURCES:
        source = "manual"
    return ModelEntry(
        id=payload.id.strip(),
        display_name=(payload.display_name or "").strip() or None,
        enabled=bool(payload.enabled),
        context_window=payload.context_window if (payload.context_window or 0) > 0 else None,
        supports_image=payload.supports_image,
        reasoning_levels=_normalize_reasoning_levels(payload.reasoning_levels or []),
        reasoning_level=_normalize_single_level(payload.reasoning_level),
        source=source,  # type: ignore[arg-type]
    )
