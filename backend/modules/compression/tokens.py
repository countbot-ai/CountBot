"""token 体积估算（非 CJK 按 UTF-8 字节数 / 4，CJK 等按 1 token/字符，仅作量级判断）。"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Sequence

# 每 token 对应的 ASCII 字符数，是所有「N tokens ≈ N*4 chars」换算的唯一来源
CHARS_PER_TOKEN = 4

# token 密度高的码点区间：谚文字母（含扩展 A）、CJK 部首与表意文字（含兼容区）、
# 谚文音节、兼容汉字、全角/半角形式
_DENSE_RE = re.compile(
    "[\u1100-\u11ff\u2e80-\u9fff\ua960-\ua97f\uac00-\ud7af\uf900-\ufaff\uff00-\uffef]"
)

# 图片类内容块：按「张」计价，不按 base64 长度
_IMAGE_PART_TYPES = frozenset({"image", "image_url", "input_image"})

# 仅最新 assistant 轮计费的思考字段：非回显链路只发送最新一轮的思考内容
_STALE_THINKING_KEYS = ("reasoning", "reasoning_content")

# 不参与估算的字段：仅用于持久化/展示的元数据，计入会污染量级判断
_PERSISTENCE_ONLY_FIELDS = frozenset(
    {
        "_db_persisted",
        "_compaction_tail",
        "created_at",
        "updated_at",
        "display_metadata",
        "message_id",
        "id",
    }
)

# 由提供商自行计价的密文类字段，按字节估算会严重高估（单块可达数百万字符）
_OPAQUE_FIELDS = frozenset({"encrypted_content"})


def estimate_tokens(text: Any) -> int:
    """估算一段文本的 token 数。

    全 ASCII 走 O(1) 快路径；含非 ASCII 时先剥离高密度字符，其余按字节估算。
    ``errors="replace"`` 保证孤立代理项（工具输出里常见）不抛异常。
    """
    if not text:
        return 0
    value = str(text)
    if value.isascii():
        return (len(value) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN
    stripped = _DENSE_RE.sub("", value)
    dense = len(value) - len(stripped)
    return dense + (len(stripped.encode("utf-8", "replace")) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN


def content_text(content: Any) -> str:
    """取出消息内容的纯文本，多模态只取文本块。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
                elif isinstance(item.get("content"), str):
                    parts.append(item["content"])
        return "\n".join(parts)
    if isinstance(content, dict):
        # 多模态信封：正文在 text_summary，图片另计
        summary = content.get("text_summary")
        if isinstance(summary, str):
            return summary
        return content_text(content.get("content"))
    return str(content or "")


def _count_parts(parts: Any, types: frozenset) -> int:
    if not isinstance(parts, list):
        return 0
    return sum(
        1 for part in parts if isinstance(part, dict) and part.get("type") in types
    )


def count_images(message: Dict[str, Any]) -> int:
    """统计消息中的图片块数量。"""
    if not isinstance(message, dict):
        return 0
    content = message.get("content")
    count = _count_parts(content, _IMAGE_PART_TYPES)
    if isinstance(content, dict) and content.get("_multimodal"):
        count += _count_parts(content.get("content"), _IMAGE_PART_TYPES)
    count += _count_parts(message.get("output"), _IMAGE_PART_TYPES)
    return count


def _wire_shadow(message: Dict[str, Any]) -> Dict[str, Any]:
    """只保留真正上网的部分，供估算使用。

    图片载荷替换为占位（按张计价）；仅持久化的元数据字段剔除；密文按空串处理，
    由提供商自己的计数计价，不由字节数计价。
    """
    shadow: Dict[str, Any] = {}
    for key, value in message.items():
        if key in _OPAQUE_FIELDS:
            shadow[key] = ""
        elif key in _PERSISTENCE_ONLY_FIELDS:
            continue
        elif key == "content" and isinstance(value, list):
            shadow[key] = [
                {**part, "image": "[stripped]"}
                if isinstance(part, dict) and part.get("type") in _IMAGE_PART_TYPES
                else part
                for part in value
            ]
        elif key == "content" and isinstance(value, dict) and value.get("_multimodal"):
            shadow[key] = value.get("text_summary", "")
        else:
            shadow[key] = value
    return shadow


def _message_text_tokens(message: Dict[str, Any]) -> int:
    """消息的文本 token 数（图片另计）。"""
    return estimate_tokens(json.dumps(_wire_shadow(message), ensure_ascii=False, default=str))


def estimate_message_tokens(
    message: Dict[str, Any],
    *,
    image_token_cost: int = 1_000,
    charge_stale_thinking: bool = True,
) -> int:
    """估算单条消息的 token 数。

    Args:
        message: 单条消息
        image_token_cost: 单张图片的 token 成本
        charge_stale_thinking: 是否计入非最新轮的思考内容。非回显链路上过期思考
            不再上网，计入会使压缩触发与实际体积脱节
    """
    if not isinstance(message, dict):
        return estimate_tokens(str(message))

    if not charge_stale_thinking and message.get("role") == "assistant":
        message = {
            key: value
            for key, value in message.items()
            if key not in _STALE_THINKING_KEYS
        }

    total = _message_text_tokens(message) + 4
    calls = message.get("tool_calls")
    if isinstance(calls, list):
        for call in calls:
            function = (call or {}).get("function") or {}
            total += estimate_tokens(function.get("name"))
            total += estimate_tokens(function.get("arguments"))
            total += 4
    return total + count_images(message) * image_token_cost


# 逐消息估算的缓存：键为消息值的指纹。
#
# 会话历史每轮重新组装（浅拷贝外层 dict，共享内容字符串），而估算在长会话中每轮被
# 多次调用。字符串以 ``id()`` 为键并强引用，使其地址不被复用；字符串不可变，故
# id 相等即值相等。其他类型按结构展开；无法指纹化的值放弃缓存，只影响性能。
_MESSAGE_TOKENS_CACHE: Dict[Any, tuple] = {}
_MESSAGE_TOKENS_CACHE_MAX = 4096


def _fingerprint(value: Any, pins: List[str]) -> Any:
    if value is None or value is True or value is False:
        return value
    kind = type(value)
    if kind is str:
        pins.append(value)
        return ("s", id(value))
    if kind is int or kind is float:
        return ("n", kind.__name__, value)
    if kind is dict:
        return (
            "d",
            tuple((_fingerprint(k, pins), _fingerprint(v, pins)) for k, v in value.items()),
        )
    if kind is list or kind is tuple:
        return ("l" if kind is list else "t", tuple(_fingerprint(v, pins) for v in value))
    raise ValueError("unfingerprintable message value")


def estimate_message_tokens_cached(
    message: Any, *, image_token_cost: int, charge_stale_thinking: bool
) -> int:
    """带缓存的单条估算，语义与 :func:`estimate_message_tokens` 相同。"""
    def compute() -> tuple:
        stripped = (
            message
            if not (not charge_stale_thinking and isinstance(message, dict) and message.get("role") == "assistant")
            else {k: v for k, v in message.items() if k not in _STALE_THINKING_KEYS}
        )
        return _message_text_tokens(stripped), count_images(stripped)

    try:
        pins: List[str] = []
        key = _fingerprint(
            {k: v for k, v in message.items() if k not in _PERSISTENCE_ONLY_FIELDS}
            if type(message) is dict
            else message,
            pins,
        )
        hash(key)
    except Exception:
        text, images = compute()
        return text + images * image_token_cost + 4

    # 计费标志决定思考字段是否计入，须并入缓存键，否则两种口径互相命中
    cache_key = (key, bool(charge_stale_thinking))
    cached = _MESSAGE_TOKENS_CACHE.get(cache_key)
    if cached is not None:
        return cached[1] + cached[2] * image_token_cost + 4

    text, images = compute()
    _MESSAGE_TOKENS_CACHE[cache_key] = (pins, text, images)
    while len(_MESSAGE_TOKENS_CACHE) > _MESSAGE_TOKENS_CACHE_MAX:
        try:
            _MESSAGE_TOKENS_CACHE.pop(next(iter(_MESSAGE_TOKENS_CACHE)))
        except (StopIteration, KeyError, RuntimeError):
            break
    return text + images * image_token_cost + 4


def estimate_messages_tokens(
    messages: Sequence[Dict[str, Any]],
    *,
    image_token_cost: int = 1_000,
    charge_stale_thinking: bool = True,
) -> int:
    """估算整段历史的 token 数。

    ``charge_stale_thinking`` 关闭时只对最新 assistant 轮计入思考内容，
    与尾部预算走查的口径保持一致，避免思考密集的会话反复触发压缩。
    """
    newest_assistant = -1
    if not charge_stale_thinking:
        for index in range(len(messages) - 1, -1, -1):
            if messages[index].get("role") == "assistant":
                newest_assistant = index
                break
    total = 0
    for index, message in enumerate(messages):
        total += estimate_message_tokens_cached(
            message,
            image_token_cost=image_token_cost,
            charge_stale_thinking=charge_stale_thinking or index == newest_assistant,
        )
    return total


def forget_message_token_cache(messages: Any, *, keep: Any = None) -> int:
    """释放缓存中固定了 ``messages`` 长字符串的条目，返回释放数量。

    缓存对指纹用的字符串持有强引用以保持 ``id()`` 键可靠，长驻进程会因此
    保留已关闭会话的消息正文。驱逐不改变任何估算结果（后续查询会重算）。
    """
    def long_string_ids(value: Any) -> set:
        ids: set = set()
        stack = [value]
        while stack:
            current = stack.pop()
            kind = type(current)
            if kind is dict:
                stack.extend(current.values())
            elif kind is list or kind is tuple:
                stack.extend(current)
            elif kind is str and len(current) > 64:
                ids.add(id(current))
        return ids

    owned = long_string_ids(messages)
    if owned and keep is not None:
        owned -= long_string_ids(keep)
    if not owned:
        return 0
    stale = [
        key
        for key, (pins, _text, _images) in list(_MESSAGE_TOKENS_CACHE.items())
        if any(id(pin) in owned for pin in pins)
    ]
    for key in stale:
        _MESSAGE_TOKENS_CACHE.pop(key, None)
    return len(stale)


def estimate_tools_tokens(tools: Optional[Sequence[Dict[str, Any]]]) -> int:
    """估算工具 schema 的 token 数。

    工具描述与参数占绝大部分体积，按主要字段求和，比完整序列化更贴近实际上网体积。
    """
    if not tools:
        return 0
    total_chars = 0
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        function = tool.get("function")
        source = function if isinstance(function, dict) else tool
        params = source.get("parameters") or {}
        total_chars += sum(
            len(value)
            for value in (source.get("name") or "", source.get("description") or "")
            if isinstance(value, str)
        )
        try:
            total_chars += len(
                json.dumps(params, ensure_ascii=False, separators=(",", ":"))
            )
        except Exception:
            total_chars += len(str(params))
    return (total_chars + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN


def estimate_request_tokens(
    messages: Sequence[Dict[str, Any]],
    *,
    system_prompt: str = "",
    tools: Optional[Sequence[Dict[str, Any]]] = None,
    image_token_cost: int = 1_000,
    charge_stale_thinking: bool = True,
) -> int:
    """估算一次完整请求的 token 数：系统提示 + 消息 + 工具 schema。

    仅估算消息会低估整体体积：数十个工具的 schema 本身即上万 token。
    """
    total = estimate_tokens(system_prompt) if system_prompt else 0
    if messages:
        total += estimate_messages_tokens(
            messages,
            image_token_cost=image_token_cost,
            charge_stale_thinking=charge_stale_thinking,
        )
    total += estimate_tools_tokens(tools)
    return total
