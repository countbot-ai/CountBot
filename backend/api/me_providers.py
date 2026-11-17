"""普通用户自有供应商与模型配置，复用管理员的清单规则与连通性探测。"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from pydantic import BaseModel, Field

from backend.api.me import _require_regular
from backend.api.settings.model_catalog import (
    ModelCatalogError,
    fetch_provider_models_with_key_failover,
)
from backend.api.settings.models import (
    AddProviderModelsRequest,
    ProviderConnectionTestResponse,
    ProviderMetadataResponse,
    ProviderModelCatalogEntry,
    ProviderModelCatalogResponse,
    ReasoningLevelsResponse,
    ReorderProviderModelsRequest,
    TestConnectionRequest,
    TestConnectionResponse,
    UpdateProviderModelRequest,
)
from backend.modules.config.loader import config_loader
from backend.modules.config.schema import ProviderConfig
from backend.modules.multiuser.identity import AuthUser
from backend.modules.multiuser.permissions import require_active_user
from backend.modules.multiuser.runtime import user_runtime_manager
from backend.modules.multiuser.ssrf import SsrfError, validate_outbound_url
from backend.modules.multiuser.user_config import (
    load_user_config,
    normalize_model_ref,
    save_user_config,
)
from backend.modules.providers import create_provider
from backend.modules.providers.connection_test import run_connection_test
from backend.modules.providers.factory import resolve_api_type
from backend.modules.providers.model_registry import (
    add_models,
    delete_model as delete_model_entry,
    reorder_models,
    update_model,
)
from backend.modules.providers.registry import get_all_providers
from backend.modules.providers.thinking_profiles import (
    KNOWN_REASONING_LEVELS,
    resolve_model_reasoning_levels,
)

router = APIRouter(
    prefix="/api/me/providers",
    tags=["me-providers"],
    dependencies=[Depends(require_active_user)],
)


class UpdateMeProvidersRequest(BaseModel):
    providers: Dict[str, Dict[str, Any]] = Field(default_factory=dict)


def _validated_api_base(value: Optional[str]) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return validate_outbound_url(text)
    except SsrfError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def _load(owner_id: str):
    raw = await load_user_config(owner_id)
    raw_providers = raw.get("providers")
    if not isinstance(raw_providers, dict):
        raw_providers = {}
        raw["providers"] = raw_providers

    configs: Dict[str, ProviderConfig] = {}
    for provider_id, value in raw_providers.items():
        if not isinstance(value, dict):
            continue
        try:
            configs[provider_id] = ProviderConfig.model_validate(value)
        except Exception:
            continue
    return raw, configs


def _is_valid_provider(value: Any) -> bool:
    """判断配置项能否反序列化为 ProviderConfig。"""
    if not isinstance(value, dict):
        return False
    try:
        ProviderConfig.model_validate(value)
    except Exception:
        return False
    return True


async def _persist(owner_id: str, raw: Dict[str, Any], configs: Dict[str, ProviderConfig]):
    # 反序列化失败的配置项原样保留，避免保存时丢失；展示层已跳过这些项
    merged = {
        provider_id: value
        for provider_id, value in (raw.get("providers") or {}).items()
        if not _is_valid_provider(value)
    }
    for provider_id, config in configs.items():
        merged[provider_id] = config.model_dump()
    raw["providers"] = merged
    await save_user_config(owner_id, raw)
    user_runtime_manager.invalidate(owner_id)


def _strip_sharing(config: ProviderConfig) -> None:
    """用户侧配置一律私有；共享动作只由管理员发起。"""
    for entry in config.models:
        entry.shared = False
        entry.shared_alias = None
        entry.shared_note = None
        entry.user_daily_limit = None


def _view(raw: Dict[str, Any], configs: Dict[str, ProviderConfig]) -> Dict[str, Any]:
    """返回与管理员 Settings 同形状的局部视图，供同一套前端组件消费。"""
    global_model = config_loader.config.model
    ref = normalize_model_ref(raw.get("model_ref"))
    return {
        "providers": {
            provider_id: config.model_dump()
            for provider_id, config in configs.items()
        },
        "model": {
            "provider": ref["provider"] if ref else "",
            "model": ref["model"] if ref else "",
            "api_mode": "chat_completions",
            "temperature": getattr(global_model, "temperature", 0),
            "max_tokens": getattr(global_model, "max_tokens", 0),
            "max_iterations": getattr(global_model, "max_iterations", 0),
            "thinking_enabled": bool(getattr(global_model, "thinking_enabled", False)),
            "stream_enabled": bool(getattr(global_model, "stream_enabled", True)),
            "reasoning_level": getattr(global_model, "reasoning_level", None),
            "supports_image": getattr(global_model, "supports_image", None),
        },
    }


def _provider_or_404(configs: Dict[str, ProviderConfig], provider_id: str) -> ProviderConfig:
    config = configs.get(provider_id)
    if config is None:
        raise HTTPException(status_code=404, detail=f"供应商 {provider_id} 不存在")
    return config


def _effective_connection(config: ProviderConfig, provider_id: str):
    keys = config.get_effective_api_keys()
    api_base = _validated_api_base(config.api_base)
    api_type = resolve_api_type(provider_id, config.api_type)
    return (keys[0] if keys else ""), api_base, api_type


# ---------------------------------------------------------------------------
# 静态路径先声明，避免被 /{provider_id} 捕获
# ---------------------------------------------------------------------------


@router.get("")
async def get_my_providers(
    user: AuthUser = Depends(require_active_user),
) -> Dict[str, Any]:
    owner_id = _require_regular(user)
    raw, configs = await _load(owner_id)
    return _view(raw, configs)


@router.put("")
async def update_my_providers(
    request: UpdateMeProvidersRequest,
    user: AuthUser = Depends(require_active_user),
) -> Dict[str, Any]:
    owner_id = _require_regular(user)
    raw, configs = await _load(owner_id)

    for provider_id, payload in request.providers.items():
        if not isinstance(payload, dict):
            continue
        data = dict(payload)
        if "api_base" in data:
            data["api_base"] = _validated_api_base(data.get("api_base"))
        try:
            config = ProviderConfig.model_validate(data)
        except Exception as exc:
            raise HTTPException(
                status_code=400, detail=f"供应商 {provider_id} 配置无效: {exc}"
            ) from exc
        _strip_sharing(config)
        configs[provider_id] = config

    await _persist(owner_id, raw, configs)
    return _view(raw, configs)


@router.get("/metadata", response_model=List[ProviderMetadataResponse])
async def get_my_provider_metadata(
    user: AuthUser = Depends(require_active_user),
) -> List[ProviderMetadataResponse]:
    """注册表元数据 + 用户已配置状态；自建供应商也补一条，保证已有配置可见。"""
    owner_id = _require_regular(user)
    _, configs = await _load(owner_id)

    result: List[ProviderMetadataResponse] = []
    for meta in get_all_providers().values():
        config = configs.get(meta.id)
        keys = config.get_effective_api_keys() if config else []
        enabled = config.enabled if config else True
        configured = bool(keys) or bool(config.models) if config else False
        requires_api_key = bool(getattr(meta, "requires_api_key", True))
        selectable = enabled and (configured or not requires_api_key)
        result.append(
            ProviderMetadataResponse(
                id=meta.id,
                name=meta.name,
                default_api_base=getattr(meta, "default_api_base", None),
                default_model=getattr(meta, "default_model", None),
                enabled=enabled,
                configured=configured,
                selectable=selectable,
                requires_api_key=requires_api_key,
                requires_api_base=bool(getattr(meta, "requires_api_base", False)),
                status="ready" if selectable else "disabled",
                reason="ready" if selectable else "disabled",
                provider_group=getattr(meta, "provider_group", "experimental"),
                thinking_control_tier=getattr(meta, "thinking_control_tier", "unsupported"),
            )
        )

    known = {item.id for item in result}
    for provider_id, config in configs.items():
        if provider_id in known:
            continue
        keys = config.get_effective_api_keys()
        configured = bool(keys) or bool(config.models)
        result.append(
            ProviderMetadataResponse(
                id=provider_id,
                name=config.name or provider_id,
                default_api_base=config.api_base,
                default_model=config.models[0].id if config.models else None,
                enabled=config.enabled,
                configured=configured,
                selectable=config.enabled and configured,
                requires_api_key=False,
                requires_api_base=False,
                status="ready" if configured else "disabled",
                reason="ready" if configured else "disabled",
                provider_group="custom",
                thinking_control_tier="unsupported",
            )
        )
    return result


@router.get("/reasoning-levels", response_model=ReasoningLevelsResponse)
async def get_my_reasoning_levels(model: str = "") -> ReasoningLevelsResponse:
    return ReasoningLevelsResponse(
        model=model,
        levels=resolve_model_reasoning_levels(model),
        known_levels=list(KNOWN_REASONING_LEVELS),
    )


@router.post("/test-connection", response_model=TestConnectionResponse)
async def test_my_connection(
    request: TestConnectionRequest,
    user: AuthUser = Depends(require_active_user),
) -> TestConnectionResponse:
    """按草稿参数或已保存的私有配置发起一次最小流式请求。"""
    owner_id = _require_regular(user)
    _, configs = await _load(owner_id)
    config = configs.get(request.provider)

    keys = config.get_effective_api_keys() if config else []
    api_key = str(request.api_key or "").strip() or (keys[0] if keys else "")
    api_base = _validated_api_base(request.api_base or (config.api_base if config else None))
    api_type = request.api_type or (config.api_type if config else "openai-chat-completions")

    model = str(request.model or "").strip()
    if not model and config:
        first_enabled = next((entry.id for entry in config.models if entry.enabled), "")
        model = first_enabled
    if not model:
        return TestConnectionResponse(success=False, error="请先填写模型名称，再测试连接。")

    entry = config.find_model(model) if config else None
    if request.stream_enabled is not None:
        stream_mode = bool(request.stream_enabled)
    elif entry is not None and entry.stream_enabled is not None:
        stream_mode = bool(entry.stream_enabled)
    else:
        stream_mode = bool(config_loader.config.model.stream_enabled)

    provider = create_provider(
        api_key=api_key,
        api_base=api_base,
        default_model=model,
        api_mode="chat_completions",
        api_type=api_type,
        timeout=30.0,
        max_retries=1,
        provider_id=request.provider,
        # 一次性探测不参与共享轮换，避免只测一个 Key 却改写全局轮换器
        enable_key_rotation=False,
        stream_enabled=stream_mode,
    )
    success, detail = await run_connection_test(
        provider,
        provider_id=request.provider,
        model=model,
        max_tokens=request.max_tokens or 0,
        temperature=request.temperature,
        thinking_enabled=request.thinking_enabled,
    )
    if success:
        return TestConnectionResponse(success=True, message=detail)
    return TestConnectionResponse(success=False, error=detail)


# ---------------------------------------------------------------------------
# 单个供应商下的模型清单
# ---------------------------------------------------------------------------


@router.get(
    "/{provider_id}/models/catalog",
    response_model=ProviderModelCatalogResponse,
)
async def get_my_model_catalog(
    provider_id: str,
    user: AuthUser = Depends(require_active_user),
) -> ProviderModelCatalogResponse:
    owner_id = _require_regular(user)
    _, configs = await _load(owner_id)
    config = _provider_or_404(configs, provider_id)
    _, api_base, api_type = _effective_connection(config, provider_id)
    keys = config.get_effective_api_keys()

    try:
        models, _ = await fetch_provider_models_with_key_failover(
            api_base=api_base,
            api_keys=keys,
            api_type=api_type,
        )
    except ModelCatalogError as exc:
        return ProviderModelCatalogResponse(
            success=False, provider=provider_id, error=str(exc)
        )

    return ProviderModelCatalogResponse(
        success=True,
        provider=provider_id,
        models=[
            ProviderModelCatalogEntry(
                id=entry[0],
                display_name=entry[1],
                owned_by=entry[2],
                context_window=entry[3] if len(entry) > 3 else None,
            )
            for entry in models
        ],
    )


@router.post("/{provider_id}/models")
async def add_my_models(
    provider_id: str,
    request: AddProviderModelsRequest,
    user: AuthUser = Depends(require_active_user),
) -> List[Dict[str, Any]]:
    owner_id = _require_regular(user)
    raw, configs = await _load(owner_id)
    config = configs.get(provider_id)
    if config is None:
        config = ProviderConfig()
        configs[provider_id] = config

    _, models = add_models(
        config,
        request,
        provider_id=provider_id,
        providers=configs,
        allow_shared=False,
    )
    await _persist(owner_id, raw, configs)
    return models


@router.put("/{provider_id}/models/order")
async def reorder_my_models(
    provider_id: str,
    request: ReorderProviderModelsRequest,
    user: AuthUser = Depends(require_active_user),
) -> List[Dict[str, Any]]:
    owner_id = _require_regular(user)
    raw, configs = await _load(owner_id)
    config = _provider_or_404(configs, provider_id)

    models = reorder_models(config, request.model_ids)
    await _persist(owner_id, raw, configs)
    return models


@router.put("/{provider_id}/models/{model_id}")
async def update_my_model(
    provider_id: str,
    model_id: str,
    request: UpdateProviderModelRequest,
    user: AuthUser = Depends(require_active_user),
) -> List[Dict[str, Any]]:
    owner_id = _require_regular(user)
    raw, configs = await _load(owner_id)
    config = _provider_or_404(configs, provider_id)

    models = update_model(
        config,
        model_id,
        request,
        provider_id=provider_id,
        providers=configs,
        allow_shared=False,
    )
    await _persist(owner_id, raw, configs)
    return models


@router.delete("/{provider_id}/models/{model_id}")
async def delete_my_model(
    provider_id: str,
    model_id: str,
    user: AuthUser = Depends(require_active_user),
) -> List[Dict[str, Any]]:
    owner_id = _require_regular(user)
    raw, configs = await _load(owner_id)
    config = _provider_or_404(configs, provider_id)

    models = delete_model_entry(config, model_id, provider_id=provider_id)
    current = normalize_model_ref(raw.get("model_ref"))
    if (
        current
        and current["source"] == "own"
        and current["provider"] == provider_id
        and current["model"] == model_id
    ):
        raw.pop("model_ref", None)

    await _persist(owner_id, raw, configs)
    return models


@router.post("/{provider_id}/test", response_model=ProviderConnectionTestResponse)
async def test_my_provider(
    provider_id: str,
    user: AuthUser = Depends(require_active_user),
) -> ProviderConnectionTestResponse:
    owner_id = _require_regular(user)
    _, configs = await _load(owner_id)
    config = _provider_or_404(configs, provider_id)
    _, api_base, api_type = _effective_connection(config, provider_id)
    keys = config.get_effective_api_keys()

    started = time.perf_counter()
    try:
        models, used_key_index = await fetch_provider_models_with_key_failover(
            api_base=api_base,
            api_keys=keys,
            api_type=api_type,
        )
    except ModelCatalogError as exc:
        return ProviderConnectionTestResponse(success=False, error=str(exc))

    if used_key_index > 0:
        logger.info(
            f"User provider {provider_id} catalog test succeeded with fallback key "
            f"#{used_key_index + 1}"
        )
    return ProviderConnectionTestResponse(
        success=True,
        latency_ms=int((time.perf_counter() - started) * 1000),
        model_count=len(models),
    )


@router.delete("/{provider_id}")
async def delete_my_provider(
    provider_id: str,
    user: AuthUser = Depends(require_active_user),
) -> Dict[str, Any]:
    owner_id = _require_regular(user)
    raw, configs = await _load(owner_id)
    _provider_or_404(configs, provider_id)
    configs.pop(provider_id, None)

    current = normalize_model_ref(raw.get("model_ref"))
    if current and current["source"] == "own" and current["provider"] == provider_id:
        raw.pop("model_ref", None)

    await _persist(owner_id, raw, configs)
    return _view(raw, configs)
