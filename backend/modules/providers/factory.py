"""Provider 工厂 — 根据配置自动选择合适的 Provider"""

from typing import Any, List, Optional
from loguru import logger
from .base import LLMProvider
from .anthropic_provider import AnthropicProvider
from .openai_provider import OpenAIProvider
from .registry import get_provider_metadata
from .runtime import KeyRotator, get_key_rotator


def create_provider(
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    default_model: Optional[str] = None,
    api_mode: str = "chat_completions",
    timeout: float = 600.0,
    max_retries: int = 3,
    provider_id: Optional[str] = None,
    api_keys: Optional[List[str]] = None,
    **kwargs: Any
) -> LLMProvider:
    """创建 LLM Provider
    
    根据 provider_id 或 api_base 自动选择合适的 Provider 实现，
    并在配置了多个 API Key 时启用轮换。
    
    Args:
        api_key: API 密钥（主密钥）
        api_keys: API 密钥列表（用于轮换，优先于 api_key）
        api_base: API 基础 URL
        default_model: 默认模型
        api_mode: API 模式
        timeout: 超时时间
        max_retries: 最大重试次数
        provider_id: Provider ID（优先级最高）
        **kwargs: 其他参数
    
    Returns:
        LLMProvider 实例
    """
    api_mode = "chat_completions"

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
    
    if metadata and metadata.id == "anthropic":
        provider_class = AnthropicProvider
        logger.debug(f"Using AnthropicProvider for {provider_id}")
    elif metadata and metadata.id in ["minimax", "custom_anthropic"]:
        provider_class = AnthropicProvider
        logger.debug(f"Using AnthropicProvider (compatible) for {provider_id}")
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
