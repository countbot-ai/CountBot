"""LLM Provider 基类 - 流式优先设计"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, AsyncIterator


@dataclass
class ToolCall:
    """工具调用数据"""
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class StreamChunk:
    """流式响应块"""
    content: str | None = None
    tool_call: ToolCall | None = None
    finish_reason: str | None = None
    usage: dict[str, int] | None = None
    error: str | None = None
    reasoning_content: str | None = None

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


class LLMProvider(ABC):
    """LLM Provider 抽象基类"""

    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        default_model: str | None = None,
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
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """流式聊天补全"""
        pass

    @abstractmethod
    def get_default_model(self) -> str:
        """获取默认模型"""
        pass

    async def transcribe(
        self,
        audio_file: bytes,
        model: str = "whisper-1",
        language: str | None = None,
        **kwargs: Any,
    ) -> str:
        """音频转文本（可选能力）"""
        raise NotImplementedError(f"{self.__class__.__name__} 不支持语音转录")
