"""原生能力解析入口：模型配置 + Provider 实例覆盖优先。"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .deepseek import build_request_overrides
from .registry import supports_native_capabilities
from .types import NativeCapabilities, normalize_native_capabilities


def load_model_capabilities(
    provider_id: Optional[str],
    model: Optional[str],
) -> NativeCapabilities:
    """从全局配置读取模型条目上的能力开关；读不到时返回全关。"""
    provider_key = str(provider_id or "").strip()
    model_key = str(model or "").strip()
    if not provider_key or not model_key:
        return NativeCapabilities()
    try:
        from backend.modules.config.loader import config_loader

        provider = config_loader.config.providers.get(provider_key)
        entry = provider.find_model(model_key) if provider else None
        if entry is None:
            return NativeCapabilities()
        return normalize_native_capabilities(getattr(entry, "native_capabilities", None))
    except Exception:
        return NativeCapabilities()


def capabilities_for_provider(
    provider: Any,
    model: Optional[str],
) -> NativeCapabilities:
    """Provider 实例上带的能力（用户私有配置）优先，其次回落到全局配置。"""
    provider_id = getattr(provider, "provider_id", None)
    override = getattr(provider, "native_capabilities", None)
    if override is not None:
        return normalize_native_capabilities(override)
    return load_model_capabilities(provider_id, model)


def resolve_native_capabilities(
    provider_id: Optional[str],
    model: Optional[str],
    override: Any = None,
) -> NativeCapabilities:
    if override is not None:
        return normalize_native_capabilities(override)
    return load_model_capabilities(provider_id, model)


def build_provider_overrides(
    *,
    provider_id: Optional[str],
    model: Optional[str],
    protocol: str,
    capabilities: Any = None,
    thinking_enabled: Optional[bool] = None,
) -> Dict[str, Any]:
    """Provider 组装请求时调用；未启用或不支持时返回空字典。"""
    if not supports_native_capabilities(provider_id, model):
        return {}
    return build_request_overrides(
        capabilities,
        protocol=protocol,
        provider_id=provider_id,
        model=model,
        thinking_enabled=thinking_enabled,
    )
