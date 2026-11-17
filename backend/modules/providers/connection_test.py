"""模型连通性探测：流式读取与错误判定，管理员与用户级接口共用。

Provider 的构造方式因配置来源而异（全局配置、用户私有配置、共享模型运行时），
构造留给调用方；探测本身必须走 chat_stream，与实际对话保持同一条链路。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from loguru import logger

from backend.modules.providers.base import LLMProvider


async def run_connection_test(
    provider: LLMProvider,
    *,
    provider_id: str,
    model: str,
    max_tokens: int = 0,
    temperature: Optional[float] = None,
    thinking_enabled: Optional[bool] = None,
) -> tuple[bool, str]:
    """发起一次最小流式请求，返回（是否成功，成功摘要或失败原因）。"""
    try:
        request_kwargs: Dict[str, Any] = {
            "messages": [{"role": "user", "content": "Hello"}],
            "tools": None,
            "model": model,
            "max_tokens": max_tokens,
        }
        if temperature is not None and temperature > 0:
            request_kwargs["temperature"] = temperature
        if thinking_enabled is not None:
            request_kwargs["thinking_enabled"] = thinking_enabled

        response_received = False
        error_message: Optional[str] = None
        response_content = ""

        async for chunk in provider.chat_stream(**request_kwargs):
            if chunk.error:
                error_message = chunk.error
                logger.error(f"Provider returned error: {chunk.error}")
                break
            if chunk.content:
                response_content += chunk.content
                response_received = True
            if chunk.finish_reason:
                response_received = True
                break

        if error_message:
            return False, error_message
        if response_received:
            message = f"Successfully connected to {provider_id}"
            if response_content:
                message += f", received response: {response_content[:50]}"
            return True, message
        return False, "No response received from provider"
    except Exception as exc:
        logger.exception(f"Connection test failed: {exc}")
        return False, str(exc) or type(exc).__name__
