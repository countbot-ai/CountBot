"""LLM Provider 基类 - 流式优先设计"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, List, Optional


@dataclass
class ToolCall:
    """工具调用数据"""
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class StreamChunk:
    """流式响应块"""
    content: Optional[str] = None
    tool_call: Optional[ToolCall] = None
    finish_reason: Optional[str] = None
    usage: Optional[Dict[str, int]] = None
    error: Optional[str] = None
    reasoning_content: Optional[str] = None
    provider_payload: Optional[Dict[str, Any]] = None

    @property
    def is_content(self) -> bool:
        return self.content is not None

    @property
    def is_tool_call(self) -> bool:
        return self.tool_call is not None

    @property
    def is_done(self) -> bool:
        return self.finish_reason is not None

    @property
    def is_error(self) -> bool:
        return self.error is not None

    @property
    def is_reasoning(self) -> bool:
        return self.reasoning_content is not None

    @property
    def has_provider_payload(self) -> bool:
        return self.provider_payload is not None


class LLMProvider(ABC):
    """LLM Provider 抽象基类"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        default_model: Optional[str] = None,
        timeout: float = 120.0,
        max_retries: int = 3,
    ):
        self.api_key = api_key
        self.api_base = api_base
        self.default_model = default_model
        self.timeout = timeout
        self.max_retries = max_retries

    @abstractmethod
    async def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """流式聊天补全"""
        pass

    @abstractmethod
    def get_default_model(self) -> str:
        """获取默认模型"""
        pass
