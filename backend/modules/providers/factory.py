"""Provider 工厂 — 根据配置自动选择合适的 Provider"""

from typing import Any, Optional
from loguru import logger
from .base import LLMProvider
from .anthropic_provider import AnthropicProvider
from .openai_provider import OpenAIProvider
from .registry import get_provider_metadata


def create_provider(
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    default_model: Optional[str] = None,
    timeout: float = 600.0,
    max_retries: int = 3,
    provider_id: Optional[str] = None,
    **kwargs: Any
) -> LLMProvider:
    """创建 LLM Provider
    
    根据 provider_id 或 api_base 自动选择合适的 Provider 实现
    
    Args:
        api_key: API 密钥
        api_base: API 基础 URL
        default_model: 默认模型
        timeout: 超时时间
        max_retries: 最大重试次数
        provider_id: Provider ID（优先级最高）
        **kwargs: 其他参数
    
    Returns:
        LLMProvider 实例
    """
    # 获取 provider 元数据
    metadata = get_provider_metadata(provider_id) if provider_id else None
    
    # 确定使用哪个 Provider 实现
    if metadata and metadata.id == "anthropic":
        provider_class = AnthropicProvider
        logger.debug(f"Using AnthropicProvider for {provider_id}")
    elif metadata and metadata.id in ["minimax", "custom_anthropic"]:
        # MiniMax 和自定义 Anthropic 兼容接口
        provider_class = AnthropicProvider
        logger.debug(f"Using AnthropicProvider (compatible) for {provider_id}")
    else:
        # 默认使用 OpenAI Provider（兼容大多数服务）
        provider_class = OpenAIProvider
        logger.debug(f"Using OpenAIProvider for {provider_id or 'default'}")
    
    # 如果有元数据，使用元数据中的默认值
    if metadata:
        if not default_model and metadata.default_model:
            default_model = metadata.default_model
        if not api_base and metadata.default_api_base:
            api_base = metadata.default_api_base
    
    return provider_class(
        api_key=api_key,
        api_base=api_base,
        default_model=default_model,
        timeout=timeout,
        max_retries=max_retries,
        provider_id=provider_id,
        **kwargs
    )
