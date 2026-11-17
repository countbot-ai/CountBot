"""用户有效配置解析：共享模型取全局配置，自有模型取用户配置，系统级配置不可覆盖。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from loguru import logger

from backend.modules.config.loader import config_loader
from backend.modules.config.schema import ModelConfig, PersonaConfig, ProviderConfig
from backend.modules.native_caps.types import normalize_native_capabilities
from backend.modules.multiuser.shared_access import (
    filter_shared_models_for_user,
    is_shared_model_allowed,
)
from backend.modules.multiuser.ssrf import SsrfError, assert_outbound_url_allowed
from backend.modules.multiuser.user_config import (
    load_user_config,
    normalize_model_ref,
    patch_user_config,
)


class ModelResolutionError(ValueError):
    """模型引用不可用。"""


@dataclass(frozen=True)
class ResolvedModel:
    """一次解析得到的模型运行时信息（含密钥，只在服务端使用）。"""

    source: str
    provider_id: str
    model_id: str
    alias: str
    provider_config: ProviderConfig


def resolved_stream_enabled(resolved: ResolvedModel, *, fallback: bool) -> bool:
    """用户模型条目的输出模式：未单独设置时回落到全局默认。"""
    entry = resolved.provider_config.find_model(resolved.model_id)
    if entry is not None and entry.stream_enabled is not None:
        return bool(entry.stream_enabled)
    return bool(fallback)


def _global_providers() -> Dict[str, ProviderConfig]:
    return config_loader.config.providers


# 普通用户视图中共享模型的统一展示名：真实供应商名与共享备注均不下发，
# 避免向上游用户暴露管理员的渠道来源。
SHARED_MODEL_DISPLAY_NAME = "内置模型"


def list_shared_models(anonymize: bool = False) -> List[Dict[str, Any]]:
    """管理员已共享的模型清单（不含任何密钥）。

    anonymize 面向普通用户视图：provider_name 固定为「内置模型」，
    共享备注置空；管理员总览保持真实供应商名。
    """
    items: List[Dict[str, Any]] = []
    for provider_id, provider_config in _global_providers().items():
        for entry in provider_config.models:
            if not entry.shared or not entry.enabled:
                continue
            items.append(
                {
                    "ref": f"shared:{provider_id}:{entry.id}",
                    "source": "shared",
                    "provider": provider_id,
                    "model": entry.id,
                    "alias": entry.resolved_alias(),
                    "note": "" if anonymize else (entry.shared_note or ""),
                    "daily_limit": entry.user_daily_limit,
                    "context_window": entry.context_window,
                    "supports_image": entry.supports_image,
                    "native_capabilities": entry.native_capabilities.model_dump(),
                    "provider_name": (
                        SHARED_MODEL_DISPLAY_NAME if anonymize
                        else provider_config.name or provider_id
                    ),
                    "available": True,
                }
            )
    return items


def _own_models(raw_config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """用户自建模型清单（同样不含密钥）。"""
    items: List[Dict[str, Any]] = []
    providers = raw_config.get("providers") or {}
    if not isinstance(providers, dict):
        return items

    for provider_id, provider_data in providers.items():
        if not isinstance(provider_data, dict):
            continue
        if provider_data.get("enabled") is False:
            continue
        for entry in provider_data.get("models") or []:
            if not isinstance(entry, dict):
                continue
            model_id = str(entry.get("id") or "").strip()
            if not model_id or entry.get("enabled") is False:
                continue
            alias = str(
                entry.get("display_name") or entry.get("alias") or model_id
            ).strip()
            items.append(
                {
                    "ref": f"own:{provider_id}:{model_id}",
                    "source": "own",
                    "provider": provider_id,
                    "model": model_id,
                    "alias": alias,
                    "note": "我的模型",
                    "daily_limit": None,
                    "context_window": entry.get("context_window"),
                    "supports_image": entry.get("supports_image"),
                    "native_capabilities": normalize_native_capabilities(
                        entry.get("native_capabilities")
                    ).model_dump(),
                    "provider_name": provider_data.get("name") or provider_id,
                    "available": True,
                }
            )
    return items


async def list_available_models(user) -> Dict[str, Any]:
    """返回某用户可用的模型分组与当前选中项。"""
    from backend.modules.multiuser.settings import load_settings

    settings = await load_settings()
    shared: List[Dict[str, Any]] = []
    own: List[Dict[str, Any]] = []

    # 普通用户（有 owner_id）的清单脱敏；管理员走本接口时保留真实供应商名
    is_regular = bool(getattr(user, "owner_id", None))
    if settings.mode == "shared" and settings.shared_providers:
        shared = list_shared_models(anonymize=is_regular)
        shared = filter_shared_models_for_user(shared, user)

    if getattr(user, "owner_id", None):
        raw = await load_user_config(user.owner_id)
        own = _own_models(raw)
        selected = normalize_model_ref(raw.get("model_ref"))
    else:
        # 管理员：展示全局默认，不下发到普通用户接口
        cfg = config_loader.config
        selected = {
            "source": "own",
            "provider": cfg.model.provider,
            "model": cfg.model.model,
            "alias": cfg.model.model,
        }

    selected_ref = None
    if selected:
        selected_ref = f"{selected['source']}:{selected['provider']}:{selected['model']}"

    # 选中的引用不在可用集合里时视为失效（管理员取消共享 / 删除模型）
    if selected_ref and not any(item["ref"] == selected_ref for item in shared + own):
        selected_ref = None

    return {
        "shared": shared,
        "own": own,
        "selected": selected_ref,
        "mode": settings.mode,
        "shared_enabled": settings.shared_providers,
    }


def assert_shared_model_allowed(user, provider_id: str, model_id: str) -> None:
    """共享模型解析前的统一授权门闩；未授权直接拒绝，不回落其他模型。"""
    if not is_shared_model_allowed(user, provider_id, model_id):
        raise ModelResolutionError("该共享模型未授权给当前用户")


def _from_shared(provider_id: str, model_id: str) -> ResolvedModel:
    provider_config = _global_providers().get(provider_id)
    if provider_config is None:
        raise ModelResolutionError("共享供应商已不存在")
    entry = provider_config.find_model(model_id)
    if entry is None or not entry.shared or not entry.enabled:
        raise ModelResolutionError("共享模型已被管理员取消共享")
    return ResolvedModel(
        source="shared",
        provider_id=provider_id,
        model_id=model_id,
        alias=entry.resolved_alias(),
        provider_config=provider_config,
    )


def _from_own(raw_config: Dict[str, Any], provider_id: str, model_id: str) -> ResolvedModel:
    providers = raw_config.get("providers") or {}
    provider_data = providers.get(provider_id) if isinstance(providers, dict) else None
    if not isinstance(provider_data, dict):
        raise ModelResolutionError("模型不存在")

    models = provider_data.get("models") or []
    entry = next(
        (m for m in models if isinstance(m, dict) and str(m.get("id")) == model_id),
        None,
    )
    if entry is None:
        raise ModelResolutionError("模型不存在")

    # 调用前重新校验 api_base，防止 DNS rebinding；仅限用户自建配置
    api_base = str(provider_data.get("api_base") or "").strip()
    if api_base:
        try:
            assert_outbound_url_allowed(api_base)
        except SsrfError as exc:
            raise ModelResolutionError(f"模型地址未通过安全校验: {exc}") from exc

    return ResolvedModel(
        source="own",
        provider_id=provider_id,
        model_id=model_id,
        alias=str(entry.get("display_name") or entry.get("alias") or model_id),
        provider_config=ProviderConfig.model_validate(provider_data),
    )


async def _ensure_default_model_ref(user) -> Optional[Dict[str, str]]:
    """用户未选择模型时，从可见清单中选定第一个并持久化。"""
    available = await list_available_models(user)
    pool = [*available["shared"], *available["own"]]
    if not pool:
        return None
    item = pool[0]
    ref = {
        "source": item["source"],
        "provider": item["provider"],
        "model": item["model"],
        "alias": item["alias"],
    }
    if getattr(user, "owner_id", None):
        await patch_user_config(user.owner_id, model_ref=ref)
    return ref


async def resolve_model_for_user(user) -> ResolvedModel:
    """解析当前用户实际使用的模型，无可用模型时抛错。"""
    from backend.modules.multiuser.settings import load_settings

    if getattr(user, "is_admin", False):
        cfg = config_loader.config
        provider_config = cfg.providers.get(cfg.model.provider)
        if provider_config is None:
            raise ModelResolutionError("全局供应商不存在")
        return ResolvedModel(
            source="own",
            provider_id=cfg.model.provider,
            model_id=cfg.model.model,
            alias=cfg.model.model,
            provider_config=provider_config,
        )

    raw = await load_user_config(user.owner_id) if user.owner_id else {}
    ref = normalize_model_ref(raw.get("model_ref"))
    if ref is None:
        ref = await _ensure_default_model_ref(user)
    if ref is None:
        raise ModelResolutionError("尚未选择可用模型")

    settings = await load_settings()
    if ref["source"] == "shared":
        if settings.mode != "shared" or not settings.shared_providers:
            raise ModelResolutionError("当前模式不允许使用共享模型")
        assert_shared_model_allowed(user, ref["provider"], ref["model"])
        return _from_shared(ref["provider"], ref["model"])

    return _from_own(raw, ref["provider"], ref["model"])


async def resolve_model_ref_for_user(user, provider: str, model: str) -> ResolvedModel:
    """解析普通用户显式选择的模型，只允许自有模型或管理员已共享的模型。"""
    from backend.modules.multiuser.settings import load_settings

    provider_id = (provider or "").strip()
    model_id = (model or "").strip()
    if not provider_id or not model_id:
        raise ModelResolutionError("模型引用格式不正确")

    raw = await load_user_config(user.owner_id) if getattr(user, "owner_id", None) else {}
    providers = raw.get("providers") if isinstance(raw.get("providers"), dict) else {}
    provider_data = providers.get(provider_id)
    if isinstance(provider_data, dict):
        models = provider_data.get("models") or []
        if any(
            isinstance(entry, dict) and str(entry.get("id")) == model_id
            for entry in models
        ):
            return _from_own(raw, provider_id, model_id)

    settings = await load_settings()
    if settings.mode == "shared" and settings.shared_providers:
        try:
            assert_shared_model_allowed(user, provider_id, model_id)
            return _from_shared(provider_id, model_id)
        except ModelResolutionError:
            pass
    raise ModelResolutionError("模型不可用或未共享给你")


async def validate_model_ref(user, source: str, provider: str, model: str) -> Dict[str, str]:
    """校验用户提交的模型引用是否可用，返回规范化结构。"""
    from backend.modules.multiuser.settings import load_settings

    source = (source or "").strip().lower()
    provider = (provider or "").strip()
    model = (model or "").strip()
    if source not in ("shared", "own") or not provider or not model:
        raise ModelResolutionError("模型引用格式不正确")

    if source == "shared":
        settings = await load_settings()
        if settings.mode != "shared" or not settings.shared_providers:
            raise ModelResolutionError("当前模式不允许使用共享模型")
        assert_shared_model_allowed(user, provider, model)
        resolved = _from_shared(provider, model)
        return {
            "source": "shared",
            "provider": provider,
            "model": model,
            "alias": resolved.alias,
        }

    raw = await load_user_config(user.owner_id) if user.owner_id else {}
    resolved = _from_own(raw, provider, model)
    return {
        "source": "own",
        "provider": provider,
        "model": model,
        "alias": resolved.alias,
    }


def build_provider(resolved: ResolvedModel, *, timeout: float = 120.0, max_retries: int = 3):
    """按解析结果构造 LLM Provider。"""
    from backend.modules.providers import create_provider
    from backend.modules.providers.factory import resolve_api_type
    from backend.modules.providers.runtime import get_provider_runtime_state

    provider_config = resolved.provider_config
    api_type = resolve_api_type(
        resolved.provider_id,
        provider_config.api_type,
        explicit=provider_config.api_type != "openai-chat-completions",
    )

    # 共享模式：沿用全局 provider 的运行时状态（含 Key 轮换与可用性判断）
    if resolved.source == "shared":
        state = get_provider_runtime_state(config_loader.config, resolved.provider_id)
        if not state.selectable:
            raise ModelResolutionError(state.reason or "共享模型当前不可用")
        return create_provider(
            api_key=state.api_key or None,
            api_keys=state.api_keys or None,
            api_base=state.api_base,
            default_model=resolved.model_id,
            api_mode=config_loader.config.model.api_mode,
            timeout=timeout,
            max_retries=max_retries,
            provider_id=resolved.provider_id,
            api_type=state.api_type,
            stream_enabled=resolved_stream_enabled(
                resolved, fallback=config_loader.config.model.stream_enabled
            ),
        )

    keys = provider_config.get_effective_api_keys()
    entry = provider_config.find_model(resolved.model_id)
    return create_provider(
        api_key=(keys[0] if keys else None),
        api_keys=keys or None,
        api_base=provider_config.api_base,
        default_model=resolved.model_id,
        api_mode=config_loader.config.model.api_mode,
        timeout=timeout,
        max_retries=max_retries,
        provider_id=resolved.provider_id,
        api_type=api_type,
        stream_enabled=resolved_stream_enabled(
            resolved, fallback=config_loader.config.model.stream_enabled
        ),
        native_capabilities=(
            entry.native_capabilities if entry is not None else None
        ),
    )


async def resolve_persona_for_user(user) -> PersonaConfig:
    """用户人设：共享全局默认值，但个人字段与主动问候只属于用户自己。"""
    base = config_loader.config.persona.model_dump()
    owner_id = getattr(user, "owner_id", None)
    if owner_id:
        defaults = PersonaConfig()
        base["user_name"] = defaults.user_name
        base["user_address"] = defaults.user_address
        base["heartbeat"] = defaults.heartbeat.model_dump()

        raw = await load_user_config(owner_id)
        persona_override = raw.get("persona")
        if isinstance(persona_override, dict):
            for key, value in persona_override.items():
                if key == "heartbeat" or value is None or key not in base:
                    continue
                base[key] = value
    try:
        return PersonaConfig(**base)
    except Exception as exc:
        logger.warning(f"Invalid persona for user {getattr(user, 'username', '?')}: {exc}")
        return PersonaConfig() if owner_id else config_loader.config.persona


def resolve_model_settings(user) -> ModelConfig:
    """生成参数永远取全局（用户不可调，避免绕过管理员的资源策略）。"""
    return config_loader.config.model


async def enforce_shared_daily_limit(user) -> None:
    """校验当前选中共享模型的每用户每日调用上限，超限抛错。"""
    if getattr(user, "is_admin", False) or not getattr(user, "owner_id", None):
        return

    try:
        resolved = await resolve_model_for_user(user)
    except ModelResolutionError:
        return
    await enforce_shared_daily_limit_for(user, resolved)


async def enforce_shared_daily_limit_for(user, resolved: ResolvedModel) -> None:
    """校验指定共享模型的每用户每日调用上限，超限抛错。"""
    if getattr(user, "is_admin", False) or not getattr(user, "owner_id", None):
        return
    if resolved.source != "shared":
        return

    entry = resolved.provider_config.find_model(resolved.model_id)
    limit = entry.user_daily_limit if entry else None
    if not limit:
        return

    from datetime import datetime, timezone

    from sqlalchemy import func, select

    from backend.database import AsyncSessionLocal
    from backend.models.model_usage import ModelUsage

    start_of_day = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    async with AsyncSessionLocal() as session:
        used = (
            await session.execute(
                select(func.count())
                .select_from(ModelUsage)
                .where(
                    ModelUsage.owner_id == user.owner_id,
                    ModelUsage.model == resolved.model_id,
                    ModelUsage.created_at >= start_of_day,
                )
            )
        ).scalar() or 0

    if int(used) >= int(limit):
        raise ModelResolutionError(
            f"今日共享模型调用次数已达上限（{limit} 次），请明天再试或使用自有模型"
        )
