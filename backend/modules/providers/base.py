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
    raw_error: Optional[str] = None
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

    async def chat_completion(
        self,
        prompt: str,
        max_tokens: int = 2000,
        temperature: float = 0.3,
    ) -> str:
        """非流式便捷方法：包装 chat_stream，累积完整回答。

        Wiki 检索链路（grader / 查询改写 / 块级生成）等单轮调用使用此方法。
        prompt 会被包成单条 user 消息；流中出现的错误块（StreamChunk.error）
        以 RuntimeError 抛出，由调用方的降级逻辑兜底。
        """
        messages = [{"role": "user", "content": prompt}]
        parts: List[str] = []
        async for chunk in self.chat_stream(
            messages, max_tokens=max_tokens, temperature=temperature
        ):
            if chunk.is_error:
                raise RuntimeError(chunk.error)
            if chunk.content is not None:
                parts.append(chunk.content)
        return "".join(parts)

    @abstractmethod
    def get_default_model(self) -> str:
        """获取默认模型"""
        pass


# ======================================================================
# 错误分类（单一来源）：曾散落在 anthropic_provider / openai_provider /
# agent/loop / providers/runtime 共 5 处重复 hint 列表，统一收敛到此处，
# 重试 / key 轮换 / 文案分发共享同一分类。
# 注意：_format_error_message 的用户文案关键字不在合并范围（文案保持稳定）。
# ======================================================================

AUTH_ERROR_HINTS = (
    "401", "403", "unauthorized", "invalid api key", "invalid_api_key",
    "authentication", "invalid token", "token is unusable", "api key",
    "apikey", "access denied", "forbidden", "insufficient_quota",
    "account_deactivated",
)

RATE_LIMIT_HINTS = (
    "429", "rate limit", "rate_limit", "too many requests", "quota",
    "insufficient_quota", "capacity", "overloaded",
)


def _error_status_code(error: Exception) -> Optional[int]:
    code = getattr(error, "status_code", None)
    if not isinstance(code, int):
        response = getattr(error, "response", None)
        code = getattr(response, "status_code", None)
    return code if isinstance(code, int) else None


def _error_text(error: Exception) -> str:
    return f"{type(error).__name__} {error}".lower()


def is_auth_error(error: Exception) -> bool:
    """认证/密钥错误：不应在 Provider 内部重试，可触发 key 轮换。"""
    if _error_status_code(error) in (401, 403):
        return True
    text = _error_text(error)
    return any(hint in text for hint in AUTH_ERROR_HINTS)


def is_rate_limit_error(error: Exception) -> bool:
    """限流/配额错误：可退避重试或触发 key 轮换。"""
    if _error_status_code(error) == 429:
        return True
    text = _error_text(error)
    return any(hint in text for hint in RATE_LIMIT_HINTS)


# ======================================================================
# 工具参数解析失败哨兵 key（单一来源）。
# provider 层与 tools/registry 共用同一标识，避免出现两份字符串字面量漂移。
# ======================================================================
_TOOL_ARGUMENT_PARSE_ERROR_KEY = "__tool_argument_parse_error__"
_TOOL_ARGUMENT_RAW_KEY = "__tool_argument_raw__"
