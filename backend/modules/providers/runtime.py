"""Provider 运行态状态与校验辅助。"""

import threading
from dataclasses import dataclass, field
from typing import List, Optional

from backend.modules.providers.registry import get_all_providers, get_provider_metadata


LOCAL_PROVIDER_IDS = {"ollama", "vllm", "lm_studio"}
NO_API_KEY_PROVIDER_IDS = {"custom_openai", "custom_anthropic"}


def _normalized_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _collect_effective_api_keys(
    provider_config,
    *,
    api_key_override: Optional[str] = None,
) -> List[str]:
    """从 provider 配置中收集去重后的有效 API Key 列表。"""
    seen: set[str] = set()
    result: List[str] = []

    if api_key_override:
        trimmed = api_key_override.strip()
        if trimmed:
            seen.add(trimmed)
            result.append(trimmed)
            return result

    if hasattr(provider_config, "get_effective_api_keys"):
        for key in provider_config.get_effective_api_keys():
            if key not in seen:
                seen.add(key)
                result.append(key)
    else:
        primary = _normalized_text(getattr(provider_config, "api_key", ""))
        if primary:
            seen.add(primary)
            result.append(primary)

    return result


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
    api_keys: List[str] = field(default_factory=list)
    api_base: Optional[str] = None
    status: str = "disabled"
    reason: str = "disabled"


class KeyRotator:
    """线程安全的 API Key 轮换器，支持轮询和故障转移。"""

    def __init__(self, api_keys: List[str]):
        self._keys = [k for k in api_keys if k and k.strip()]
        self._index = 0
        self._lock = threading.Lock()

    @property
    def keys(self) -> List[str]:
        return list(self._keys)

    @property
    def count(self) -> int:
        return len(self._keys)

    def next_key(self) -> Optional[str]:
        """获取下一个 key（轮询策略）。"""
        with self._lock:
            if not self._keys:
                return None
            key = self._keys[self._index % len(self._keys)]
            self._index = (self._index + 1) % len(self._keys)
            return key

    def current_key(self) -> Optional[str]:
        """获取当前 key（不移动指针）。"""
        with self._lock:
            if not self._keys:
                return None
            return self._keys[self._index % len(self._keys)]

    def mark_key_failed(self, failed_key: str) -> Optional[str]:
        """标记某个 key 失败，返回下一个可用 key。"""
        with self._lock:
            if len(self._keys) <= 1:
                return None
            try:
                idx = self._keys.index(failed_key)
            except ValueError:
                return self.next_key()
            next_idx = (idx + 1) % len(self._keys)
            if self._keys[next_idx] == failed_key:
                return None
            self._index = next_idx
            return self._keys[self._index]

    def is_auth_error(self, error: Exception) -> bool:
        """判断错误是否为认证/密钥相关错误。"""
        error_text = f"{type(error).__name__} {str(error)}".lower()
        auth_hints = (
            "401", "unauthorized", "invalid api key", "invalid_api_key",
            "authentication", "invalid token", "token is unusable",
            "api key", "apikey", "access denied", "forbidden",
            "insufficient_quota", "account_deactivated",
        )
        return any(hint in error_text for hint in auth_hints)

    def is_rate_limit_error(self, error: Exception) -> bool:
        """判断错误是否为限流/配额错误。"""
        error_text = f"{type(error).__name__} {str(error)}".lower()
        rate_hints = (
            "429", "rate limit", "rate_limit", "quota", "too many requests",
            "insufficient_quota", "capacity", "overloaded",
        )
        return any(hint in error_text for hint in rate_hints)


_PROVIDER_KEY_ROTATORS: dict[str, KeyRotator] = {}
_ROTATOR_LOCK = threading.Lock()


def get_key_rotator(provider_id: str, api_keys: List[str]) -> KeyRotator:
    """获取或更新指定 provider 的 KeyRotator 实例。"""
    with _ROTATOR_LOCK:
        existing = _PROVIDER_KEY_ROTATORS.get(provider_id)
        if existing is not None and existing.keys == api_keys:
            return existing
        rotator = KeyRotator(api_keys)
        _PROVIDER_KEY_ROTATORS[provider_id] = rotator
        return rotator


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

    api_keys = _collect_effective_api_keys(
        provider_config,
        api_key_override=api_key_override,
    )

    api_key = api_keys[0] if api_keys else ""

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
        api_key=api_key,
        api_keys=api_keys,
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
