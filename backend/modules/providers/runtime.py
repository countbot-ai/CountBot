"""Provider 运行态状态与校验辅助。"""

from dataclasses import dataclass
from typing import Optional

from backend.modules.providers.registry import get_all_providers, get_provider_metadata


LOCAL_PROVIDER_IDS = {"ollama", "vllm", "lm_studio"}
NO_API_KEY_PROVIDER_IDS = {"custom_openai", "custom_anthropic"}


def _normalized_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


@dataclass
class ProviderRuntimeState:
    """Provider 当前运行态状态。"""

    provider_id: str
    exists: bool
    enabled: bool
    configured: bool
    selectable: bool
    requires_api_key: bool
    requires_api_base: bool
    api_key: str
    api_base: Optional[str]
    status: str
    reason: str


def get_provider_runtime_state(
    app_config,
    provider_id: str,
    *,
    api_key_override: Optional[str] = None,
    api_base_override: Optional[str] = None,
) -> ProviderRuntimeState:
    """计算 provider 是否可被实际请求使用。"""

    provider_meta = get_provider_metadata(provider_id)
    provider_config = app_config.providers.get(provider_id) if app_config else None
    exists = provider_meta is not None

    enabled = bool(provider_config.enabled) if provider_config else False

    api_key = _normalized_text(api_key_override)
    if api_key is None:
        api_key = _normalized_text(provider_config.api_key if provider_config else "")

    api_base = _normalized_text(api_base_override)
    if api_base is None:
        api_base = _normalized_text(
            (provider_config.api_base if provider_config else None)
            or (provider_meta.default_api_base if provider_meta else None)
        )

    requires_api_key = (
        provider_id not in LOCAL_PROVIDER_IDS
        and provider_id not in NO_API_KEY_PROVIDER_IDS
    )
    requires_api_base = not bool(
        _normalized_text(provider_meta.default_api_base if provider_meta else None)
    )

    missing_api_key = requires_api_key and not api_key
    missing_api_base = requires_api_base and not api_base

    configured = exists and not missing_api_key and not missing_api_base
    selectable = enabled and configured

    if not exists:
        status = "unknown"
        reason = "unknown_provider"
    elif not enabled:
        status = "disabled"
        reason = "disabled"
    elif missing_api_key:
        status = "incomplete"
        reason = "missing_api_key"
    elif missing_api_base:
        status = "incomplete"
        reason = "missing_api_base"
    else:
        status = "ready"
        reason = "ready"

    return ProviderRuntimeState(
        provider_id=provider_id,
        exists=exists,
        enabled=enabled,
        configured=configured,
        selectable=selectable,
        requires_api_key=requires_api_key,
        requires_api_base=requires_api_base,
        api_key=api_key or "",
        api_base=api_base,
        status=status,
        reason=reason,
    )


def find_first_selectable_provider(app_config) -> Optional[ProviderRuntimeState]:
    """返回第一个可实际使用的 provider。"""

    for provider_id in get_all_providers():
        state = get_provider_runtime_state(app_config, provider_id)
        if state.selectable:
            return state
    return None


def build_provider_unavailable_message(
    provider_id: str,
    reason: str,
    *,
    compact: bool = False,
) -> str:
    """生成统一的 provider 不可用错误信息。"""

    if compact:
        compact_messages = {
            "disabled": f"Provider '{provider_id}' disabled / 提供商已禁用",
            "missing_api_key": (
                f"Provider '{provider_id}' missing API key / 缺少 API Key"
            ),
            "missing_api_base": (
                f"Provider '{provider_id}' missing API base / 缺少 API Base"
            ),
            "unknown_provider": f"Provider '{provider_id}' unknown / 提供商未注册",
        }
        return compact_messages.get(
            reason,
            f"Provider '{provider_id}' unavailable / 提供商不可用",
        )

    full_messages = {
        "disabled": (
            f"提供商 '{provider_id}' 已禁用，请前往“设置 -> 模型提供商”启用后再试。 / "
            f"Provider '{provider_id}' is disabled. "
            "Enable it in Settings -> Providers and try again."
        ),
        "missing_api_key": (
            f"提供商 '{provider_id}' 缺少 API Key，请前往“设置 -> 模型提供商”补全后再试。 / "
            f"Provider '{provider_id}' is missing an API key. "
            "Add it in Settings -> Providers and try again."
        ),
        "missing_api_base": (
            f"提供商 '{provider_id}' 缺少 API Base URL，请前往“设置 -> 模型提供商”补全后再试。 / "
            f"Provider '{provider_id}' is missing an API base URL. "
            "Fill it in Settings -> Providers and try again."
        ),
        "unknown_provider": (
            f"提供商 '{provider_id}' 未注册，请检查“设置 -> 模型提供商”和当前模型配置。 / "
            f"Provider '{provider_id}' is unknown. "
            "Check Settings -> Providers and the current model configuration."
        ),
    }
    return full_messages.get(
        reason,
        (
            f"提供商 '{provider_id}' 当前不可用，请检查“设置 -> 模型提供商”中的配置。 / "
            f"Provider '{provider_id}' is currently unavailable. "
            "Check its configuration in Settings -> Providers."
        ),
    )
