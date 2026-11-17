"""工具结果瘦身：不调用模型，把旧工具结果正文替换为有界摘要。"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from backend.modules.compression.boundaries import role_of
from backend.modules.compression.summary_stub import summarize_tool_result
from backend.modules.compression.tokens import (
    content_text,
    estimate_message_tokens,
)

# 小于该长度的工具结果不瘦身，避免把有价值的短输出也抹掉
PRUNE_MIN_CHARS = 200

# 尾部压降时保留的最近消息条数：保证模型手头的直接上下文不被抽空
PRESSURE_KEEP_RECENT_MESSAGES = 3

# 尾部可超预算的比例上限（相对上下文窗口）；小窗口下超预算部分可能已占请求三分之一
TAIL_MAX_CONTEXT_FRACTION = 0.20

# 软上限倍数：允许整行保留，但不无限超支
TAIL_SOFT_CEILING_FACTOR = 1.5

# 尾部条数下限的硬上限：防止大量小消息把保护范围撑得过宽
MAX_TAIL_MESSAGE_FLOOR = 8

PRUNED_PLACEHOLDER = "[Old tool output cleared to save context space]"
DUPLICATE_PLACEHOLDER = "[Duplicate tool output — same content as a more recent call]"
SCREENSHOT_PREFIX = "[screenshot removed"
IMAGE_PLACEHOLDER = "[image removed to save context space]"


def is_placeholder(content: Any) -> bool:
    """该内容是否已被瘦身（幂等判定，避免重复处理）。"""
    if not isinstance(content, str):
        return False
    return (
        content == PRUNED_PLACEHOLDER
        or content.startswith(DUPLICATE_PLACEHOLDER)
        or content.startswith(SCREENSHOT_PREFIX)
    )


def tool_calls_by_id(messages: Sequence[Dict[str, Any]]) -> Dict[str, Tuple[str, str]]:
    """建立 ``tool_call_id -> (工具名, 参数原文)`` 索引，供工具结果反查来源。"""
    index: Dict[str, Tuple[str, str]] = {}
    for message in messages:
        if role_of(message) != "assistant":
            continue
        for tool_call in message.get("tool_calls") or []:
            if not isinstance(tool_call, dict):
                continue
            function = tool_call.get("function") or {}
            name = str(function.get("name") or tool_call.get("name") or "unknown")
            arguments = function.get("arguments")
            if not isinstance(arguments, str):
                try:
                    arguments = json.dumps(arguments or {}, ensure_ascii=False)
                except (TypeError, ValueError):
                    arguments = ""
            call_id = str(
                tool_call.get("id") or tool_call.get("call_id") or ""
            ).strip()
            if call_id:
                index[call_id] = (name, arguments)
    return index


def pending_tool_round(messages: Sequence[Dict[str, Any]]) -> Optional[range]:
    """模型已请求但尚未读取的工具结果所在区段。

    判定依据：从尾部向前，连续的 ``tool`` 结果属于其发起调用的 assistant，
    且该 assistant 之后没有新的 assistant 消息（有则说明模型已读过这一轮）。
    """
    total = len(messages)
    end = total
    start = total
    while start > 0 and role_of(messages[start - 1]) == "tool":
        start -= 1
    if start == 0:
        return None
    caller_index = start - 1
    if not (role_of(messages[caller_index]) == "assistant" and messages[caller_index].get("tool_calls")):
        return None
    for later in range(end, total):
        if role_of(messages[later]) == "assistant":
            return None
    return range(start, end)


def _has_images(content: Any) -> bool:
    if isinstance(content, list):
        return any(
            isinstance(part, dict) and part.get("type") in ("image", "image_url", "input_image")
            for part in content
        )
    if isinstance(content, dict) and content.get("_multimodal"):
        return _has_images(content.get("content"))
    return False


def _strip_images(message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """把消息里的图片替换为短占位；无图片时返回 None。"""
    content = message.get("content")
    if isinstance(content, list):
        replaced = [
            {"type": "text", "text": IMAGE_PLACEHOLDER}
            if isinstance(part, dict) and part.get("type") in ("image", "image_url", "input_image")
            else part
            for part in content
        ]
        new_message = {k: v for k, v in message.items() if k != "api_content"}
        new_message["content"] = replaced
        return new_message
    if isinstance(content, dict) and content.get("_multimodal"):
        if not _has_images(content.get("content")):
            return None
        new_message = {k: v for k, v in message.items() if k != "api_content"}
        new_message["content"] = content.get("text_summary") or IMAGE_PLACEHOLDER
        return new_message
    return None


def dedupe_tool_results(messages: List[Dict[str, Any]]) -> int:
    """第一道：相同内容的旧工具结果只保留最新一份，较早的替换为回指。"""
    seen: set = set()
    pruned = 0
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        content = message.get("content")
        if role_of(message) != "tool" or not isinstance(content, str):
            continue
        if len(content) < PRUNE_MIN_CHARS:
            continue
        digest = hashlib.md5(content.encode("utf-8", errors="replace")).hexdigest()[:12]
        if digest in seen:
            messages[index] = {**message, "content": DUPLICATE_PLACEHOLDER}
            pruned += 1
        seen.add(digest)
    return pruned


def demote_tool_result_at(
    messages: List[Dict[str, Any]],
    index: int,
    call_index: Dict[str, Tuple[str, str]],
    min_chars: int,
) -> bool:
    """把 ``index`` 处的工具结果替换为单行摘要，发生改动返回 True。"""
    message = messages[index]
    if role_of(message) != "tool":
        return False
    content = message.get("content")

    # 多模态结果：剥离图片载荷，正文按摘要处理
    if isinstance(content, list) or (isinstance(content, dict) and content.get("_multimodal")):
        stripped = _strip_images(message)
        if stripped is not None:
            messages[index] = stripped
            return True
        return False

    if (
        not isinstance(content, str)
        or not content
        or is_placeholder(content)
        or len(content) <= min_chars
    ):
        return False

    tool_name, tool_args = call_index.get(
        str(message.get("tool_call_id") or ""), ("unknown", "")
    )
    messages[index] = {
        **message,
        "content": summarize_tool_result(tool_name, tool_args, content),
    }
    return True


def tail_soft_ceiling(token_budget: int, context_length: int) -> int:
    """尾部软上限：允许超预算一定倍数，但不超过窗口的固定比例。"""
    ceiling = int(token_budget * TAIL_SOFT_CEILING_FACTOR)
    if context_length > 0:
        ceiling = min(ceiling, int(context_length * TAIL_MAX_CONTEXT_FRACTION))
    return max(ceiling, token_budget)


def _tail_boundary(
    messages: Sequence[Dict[str, Any]],
    protect_tail_count: int,
    protect_tail_tokens: Optional[int],
) -> int:
    """受保护尾部的起始下标；给出 token 预算时预算优先于条数下限。"""
    if not protect_tail_tokens or protect_tail_tokens <= 0:
        return len(messages) - protect_tail_count
    floor = min(protect_tail_count, len(messages), MAX_TAIL_MESSAGE_FLOOR)
    accumulated = 0
    boundary = len(messages)
    for index in range(len(messages) - 1, -1, -1):
        tokens = estimate_message_tokens(messages[index])
        if accumulated + tokens > protect_tail_tokens and (len(messages) - index) >= floor:
            break
        accumulated += tokens
        boundary = index
    # 条数下限在索引空间取 min 会反向（索引越小保护越多），故用长度相减
    return min(boundary, len(messages) - floor)


def pressure_demote_tail(
    messages: List[Dict[str, Any]],
    boundary: int,
    protect_tail_tokens: int,
    call_index: Dict[str, Tuple[str, str]],
    min_chars: int,
    spared: Optional[range],
    context_length: int,
) -> int:
    """第四道：受保护尾部自身超软上限时，逐级压降其中的工具结果正文。

    先压降较早的结果；仍超限则保留最新一条、其余全部压降；最后手段是压降
    最新一条本身（一处 200KB 的读取单独就能超限），除非它属于待读轮次。
    """
    ceiling = tail_soft_ceiling(protect_tail_tokens, context_length)
    start = max(0, boundary)
    demote_end = len(messages) - min(PRESSURE_KEEP_RECENT_MESSAGES, len(messages))

    def region_tokens() -> int:
        return sum(estimate_message_tokens(messages[i]) for i in range(start, len(messages)))

    if demote_end <= boundary or region_tokens() <= ceiling:
        return 0

    spared_set = set(spared) if spared else set()

    def shrink_at(index: int) -> bool:
        if index in spared_set:
            return False
        return demote_tool_result_at(messages, index, call_index, min_chars)

    demoted = 0
    for index in range(start, demote_end):
        if shrink_at(index):
            demoted += 1
        if region_tokens() <= ceiling:
            break

    if region_tokens() > ceiling:
        newest_tool = next(
            (i for i in range(len(messages) - 1, -1, -1) if role_of(messages[i]) == "tool"),
            None,
        )
        for index in range(start, len(messages)):
            if index == newest_tool:
                continue
            if shrink_at(index):
                demoted += 1
        if (
            newest_tool is not None
            and newest_tool not in spared_set
            and newest_tool >= boundary
            and region_tokens() > ceiling
            and demote_tool_result_at(messages, newest_tool, call_index, min_chars)
        ):
            demoted += 1

    return demoted


def prune_tool_results(
    messages: Sequence[Dict[str, Any]],
    *,
    protect_tail_count: int,
    protect_tail_tokens: Optional[int] = None,
    min_prune_chars: int = PRUNE_MIN_CHARS,
    context_length: int = 0,
) -> Tuple[List[Dict[str, Any]], int]:
    """按规定顺序对旧工具结果瘦身，返回 ``(新消息列表, 改动数)``。"""
    if not messages:
        return list(messages), 0

    result = [dict(message) for message in messages]
    call_index = tool_calls_by_id(result)
    boundary = _tail_boundary(result, protect_tail_count, protect_tail_tokens)

    # 待读轮次是模型已请求但未读取的输出：替换成摘要会让它重跑（含副作用）或盲答
    spared = pending_tool_round(result)
    if spared:
        boundary = min(boundary, spared.start)

    pruned = dedupe_tool_results(result)
    pruned += sum(
        1
        for index in range(max(0, boundary))
        if demote_tool_result_at(result, index, call_index, min_prune_chars)
    )

    # 第三道：受保护尾部内的历史图片退役，最新的图片保留（模型正在据此推理）
    pruned += _retire_tail_images(result, spared)

    if protect_tail_tokens and protect_tail_tokens > 0 and result:
        pruned += pressure_demote_tail(
            result,
            boundary,
            protect_tail_tokens,
            call_index,
            min_prune_chars,
            spared,
            context_length,
        )

    return result, pruned


def _retire_tail_images(
    messages: List[Dict[str, Any]], spared: Optional[range]
) -> int:
    """第三道：尾部内的历史图片替换为占位，最新一张与待读轮次除外。"""
    spared_set = set(spared) if spared else set()
    newest_image_index = -1
    for index in range(len(messages) - 1, -1, -1):
        if role_of(messages[index]) == "tool" and _has_images(messages[index].get("content")):
            newest_image_index = index
            break

    retired = 0
    for index, message in enumerate(messages):
        if index == newest_image_index or index in spared_set:
            continue
        if role_of(message) != "tool":
            continue
        stripped = _strip_images(message)
        if stripped is not None:
            messages[index] = stripped
            retired += 1
    return retired
