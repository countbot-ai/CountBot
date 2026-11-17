"""Provider 工厂 — 根据配置自动选择合适的 Provider"""

from typing import Any, List, Optional
from loguru import logger
from .base import LLMProvider
from .anthropic_provider import AnthropicProvider
from .openai_provider import OpenAIProvider
from .openai_responses_provider import OpenAIResponsesProvider
from .registry import get_provider_metadata
from .runtime import KeyRotator, get_key_rotator


# 供应商级协议标识（与前端 ProviderConfig.api_type 同值）。
API_TYPE_ANTHROPIC_MESSAGES = "anthropic-messages"
API_TYPE_OPENAI_RESPONSES = "openai-responses"
API_TYPE_OPENAI_CHAT = "openai-chat-completions"

API_TYPES = (
    API_TYPE_OPENAI_CHAT,
    API_TYPE_OPENAI_RESPONSES,
    API_TYPE_ANTHROPIC_MESSAGES,
)


def resolve_api_type(
    provider_id: Optional[str],
    api_type: Optional[str] = None,
    *,
    explicit: bool = False,
) -> str:
    """解析供应商使用的协议。

    显式传入的 api_type 优先；未传时按 provider_id 回落到历史默认值，
    保证存量配置（没有 api_type 字段）行为不变。

    explicit=True 表示「用户确实选过这个值」：即使它恰好等于 schema 默认值
    （openai-chat-completions），也不再被 provider_id 的推断覆盖。
    """
    normalized = str(api_type or "").strip().lower()
    if normalized in API_TYPES and (explicit or normalized != API_TYPE_OPENAI_CHAT):
        return normalized

    metadata = get_provider_metadata(provider_id) if provider_id else None
    if metadata and metadata.id in ("anthropic", "minimax", "custom_anthropic"):
        return API_TYPE_ANTHROPIC_MESSAGES
    return API_TYPE_OPENAI_CHAT


def create_provider(
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    default_model: Optional[str] = None,
    api_mode: str = "chat_completions",
    timeout: float = 600.0,
    max_retries: int = 3,
    provider_id: Optional[str] = None,
    api_keys: Optional[List[str]] = None,
    api_type: Optional[str] = None,
    **kwargs: Any
) -> LLMProvider:
    """创建 LLM Provider
    
    根据 api_type（优先）或 provider_id 选择合适的 Provider 实现，
    并在配置了多个 API Key 时启用轮换。
    
    Args:
        api_key: API 密钥（主密钥）
        api_keys: API 密钥列表（用于轮换，优先于 api_key）
        api_base: API 基础 URL
        default_model: 默认模型
        api_mode: API 模式（历史字段，行为由 api_type 决定）
        timeout: 超时时间
        max_retries: 最大重试次数
        provider_id: Provider ID（优先级最高）
        api_type: 供应商协议，见 API_TYPES
        **kwargs: 其他参数
    
    Returns:
        LLMProvider 实例
    """
    resolved_api_type = resolve_api_type(provider_id, api_type)

    metadata = get_provider_metadata(provider_id) if provider_id else None

    effective_api_keys: List[str] = []
    if api_keys:
        seen: set[str] = set()
        for key in api_keys:
            trimmed = (key or "").strip()
            if trimmed and trimmed not in seen:
                seen.add(trimmed)
                effective_api_keys.append(trimmed)

    if not effective_api_keys and api_key and api_key.strip():
        effective_api_keys = [api_key.strip()]

    selected_key = api_key or ""
    if effective_api_keys and provider_id:
        rotator = get_key_rotator(provider_id, effective_api_keys)
        selected_key = rotator.next_key() or effective_api_keys[0]
        if rotator.count > 1:
            logger.debug(
                f"Key rotation enabled for {provider_id}: "
                f"{rotator.count} keys available, using key index {rotator._index}"
            )
    elif effective_api_keys:
        selected_key = effective_api_keys[0]
    
    if resolved_api_type == API_TYPE_ANTHROPIC_MESSAGES:
        provider_class = AnthropicProvider
        logger.debug(f"Using AnthropicProvider for {provider_id or 'default'}")
    elif resolved_api_type == API_TYPE_OPENAI_RESPONSES:
        provider_class = OpenAIResponsesProvider
        logger.debug(f"Using OpenAIResponsesProvider for {provider_id or 'default'}")
    else:
        provider_class = OpenAIProvider
        logger.debug(f"Using OpenAIProvider for {provider_id or 'default'}")
    
    if metadata:
        if not default_model and metadata.default_model:
            default_model = metadata.default_model
        if not api_base and metadata.default_api_base:
            api_base = metadata.default_api_base
    
    return provider_class(
        api_key=selected_key or None,
        api_base=api_base,
        default_model=default_model,
        api_mode=api_mode,
        timeout=timeout,
        max_retries=max_retries,
        provider_id=provider_id,
        **kwargs
    )
