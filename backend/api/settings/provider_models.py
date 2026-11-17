"""供应商模型清单的读写接口（增删改排序）；切换当前模型仍走 PUT /api/settings 的 model 节。"""

import time
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from loguru import logger

from backend.modules.config.loader import config_loader
from backend.modules.config.schema import AppConfig, ProviderConfig
from backend.modules.providers.factory import resolve_api_type
from backend.modules.providers.model_registry import (
    add_models,
    delete_model as delete_model_entry,
    reorder_models,
    serialize_models,
    update_model,
)
from backend.modules.providers.registry import get_provider_metadata

from backend.api.settings._router import router
from backend.api.settings.model_catalog import (
    ModelCatalogError,
    fetch_provider_models_with_key_failover,
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
    ReorderProviderModelsRequest,
    UpdateProviderModelRequest,
)


@router.get("/reasoning-levels", response_model=ReasoningLevelsResponse)
async def get_reasoning_levels(model: str = "") -> ReasoningLevelsResponse:
    """思考档位内置建议，模型编辑弹窗用作初始勾选项。"""
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


async def _save_and_reload(config: AppConfig) -> None:
    """落盘并刷新运行时，保证新模型立刻可选。"""
    from backend.modules.config.loader import config_loader as loader

    await loader.save_config(config)


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
        models, _ = await fetch_provider_models_with_key_failover(
            api_base=_resolve_effective_api_base(provider_id, provider),
            api_keys=provider.get_effective_api_keys(),
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
    config = config_loader.config
    provider = _get_provider_or_404(config, provider_id)

    added, _ = add_models(
        provider,
        request,
        provider_id=provider_id,
        providers=config.providers,
        allow_shared=True,
    )

    config._migrate_provider_models()
    await _save_and_reload(config)
    logger.info(f"Added {added} models to provider {provider_id}")
    return serialize_models(config.providers[provider_id])


@router.put(
    "/providers/{provider_id}/models/order",
    response_model=List[Dict[str, Any]],
)
async def reorder_provider_models(
    provider_id: str,
    request: ReorderProviderModelsRequest,
) -> List[Dict[str, Any]]:
    """按传入顺序重排模型；未出现在列表里的模型保持相对顺序附在末尾。"""
    config = config_loader.config
    provider = _get_provider_or_404(config, provider_id)

    models = reorder_models(provider, request.model_ids)
    await _save_and_reload(config)
    return models


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
    config = config_loader.config
    provider = _get_provider_or_404(config, provider_id)

    models = update_model(
        provider,
        model_id,
        request,
        provider_id=provider_id,
        providers=config.providers,
        allow_shared=True,
    )
    await _save_and_reload(config)
    return models


@router.delete(
    "/providers/{provider_id}/models/{model_id}",
    response_model=List[Dict[str, Any]],
)
async def delete_provider_model(
    provider_id: str,
    model_id: str,
) -> List[Dict[str, Any]]:
    """删除单个模型；若删的是当前选中模型，则回落到清单首个可用模型。"""
    config = config_loader.config
    provider = _get_provider_or_404(config, provider_id)

    models = delete_model_entry(provider, model_id, provider_id=provider_id)

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
    logger.info(f"Deleted {model_id} from provider {provider_id}")
    return models


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
        models, used_key_index = await fetch_provider_models_with_key_failover(
            api_base=_resolve_effective_api_base(provider_id, provider),
            api_keys=provider.get_effective_api_keys(),
            api_type=api_type,
        )
    except ModelCatalogError as exc:
        return ProviderConnectionTestResponse(success=False, error=str(exc))

    latency_ms = int((time.perf_counter() - started) * 1000)
    if used_key_index > 0:
        logger.info(
            f"Provider {provider_id} catalog test succeeded with fallback key "
            f"#{used_key_index + 1}"
        )
    return ProviderConnectionTestResponse(
        success=True,
        latency_ms=latency_ms,
        model_count=len(models),
    )
