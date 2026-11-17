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
# 错误分类（单一来源）：重试 / key 轮换 / 文案分发共享同一分类，
# provider 实现不得各自维护 hint 列表。
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


# 零宽字符：部分上游用它们给思考/正文占位，展开后就是一片空白
_INVISIBLE_CHARS = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff"), None)


def has_visible_text(text: Any) -> bool:
    """是否含可见内容；纯零宽/空白字符视为不可见，避免前端渲染出空块。"""
    return bool(str(text or "").translate(_INVISIBLE_CHARS).strip())


def format_upstream_detail(raw: str, *, limit: int = 300) -> str:
    """把上游原始错误压成单行文本，附在友好提示后，便于用户/排查看到真实原因。"""
    compact = " ".join(str(raw or "").split())
    if not compact:
        return ""
    if len(compact) > limit:
        compact = compact[:limit] + "…"
    return compact


def append_upstream_detail(message: str, raw: str) -> str:
    """拼接友好提示与上游原始返回；无原始内容时原样返回提示。"""
    detail = format_upstream_detail(raw)
    if not detail:
        return message
    return f"{message}\n\n上游原始返回：{detail}"


def read_usage_detail_int(details: Any, key: str) -> int:
    """读 usage 明细子对象里的整数字段（SDK 模型或原始 dict 都支持），取不到按 0。

    缓存命中与推理 token 都只在明细里（prompt_tokens_details.cached_tokens、
    input_tokens_details.cached_tokens、output_tokens_details.reasoning_tokens），
    顶层取不到；不显式带出来会被统一记成 0。
    """
    if details is None:
        return 0
    if isinstance(details, dict):
        value = details.get(key)
    else:
        value = getattr(details, key, None)
        if value is None:
            extra = getattr(details, "model_extra", None)
            value = extra.get(key) if isinstance(extra, dict) else None
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


# ======================================================================
# 工具参数解析失败哨兵 key（单一来源）。
# provider 层与 tools/registry 共用同一标识，避免出现两份字符串字面量漂移。
# ======================================================================
_TOOL_ARGUMENT_PARSE_ERROR_KEY = "__tool_argument_parse_error__"
_TOOL_ARGUMENT_RAW_KEY = "__tool_argument_raw__"
