"""压缩结果组装：保证拼装后的消息序列在模板层面合法。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from backend.modules.compression.boundaries import (
    last_template_visible_role,
    role_of,
    template_visible_role,
)
from backend.modules.compression.engine_prompt import (
    COMPRESSED_SUMMARY_HAS_USER_TURN_KEY,
    COMPRESSED_SUMMARY_METADATA_KEY,
    MERGED_PRIOR_CONTEXT_HEADER,
    MERGED_SUMMARY_DELIMITER,
    SUMMARY_END_MARKER,
    starts_with_summary_prefix,
)
from backend.modules.compression.tokens import content_text


def fresh_copy(message: Dict[str, Any]) -> Dict[str, Any]:
    """复制消息并剔除仅用于持久化的标记。

    标记若随压缩结果继续流转，会被写入库并被后续轮次误判为已落库消息。
    """
    copied = dict(message)
    copied.pop("_db_persisted", None)
    return copied


def is_summary_message(message: Any) -> bool:
    """该消息是否由压缩写入的摘要行。"""
    if not isinstance(message, dict):
        return False
    return bool(message.get(COMPRESSED_SUMMARY_METADATA_KEY)) or starts_with_summary_prefix(
        content_text(message.get("content"))
    )


def _append_text(content: Any, suffix: str, *, prepend: bool = False) -> Any:
    """在字符串或多模态内容上追加/前插文本。"""
    if isinstance(content, str):
        return suffix + content if prepend else content + suffix
    if isinstance(content, list):
        block = {"type": "text", "text": suffix}
        return ([block] + content) if prepend else (content + [block])
    return suffix


def strip_handoff_summary(message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """剥离消息中的历史交接摘要。

    仅当整条消息就是一份摘要时返回 None（调用方丢弃）；摘要与真实内容合并的消息
    保留，因为其中的用户文本有价值。
    """
    if is_summary_message(message):
        text = content_text(message.get("content"))
        if SUMMARY_END_MARKER in text:
            # 合并形态：保留结束标记之后的内容（即真正的当前上下文）
            _, _, remainder = text.rpartition(SUMMARY_END_MARKER)
            remainder = remainder.strip()
            if not remainder:
                return None
            stripped = dict(message)
            stripped["content"] = remainder
            for key in (COMPRESSED_SUMMARY_METADATA_KEY, COMPRESSED_SUMMARY_HAS_USER_TURN_KEY):
                stripped.pop(key, None)
            return stripped
        return None
    return message


def assemble_head(
    messages: Sequence[Dict[str, Any]],
    compress_start: int,
    compression_note: str = "",
) -> List[Dict[str, Any]]:
    """组装受保护头部；系统提示上追加压缩说明，历史交接摘要剥离。"""
    head: List[Dict[str, Any]] = []
    for index in range(compress_start):
        message = fresh_copy(messages[index])
        if index == 0 and role_of(message) == "system" and compression_note:
            existing = message.get("content")
            if compression_note not in content_text(existing):
                separator = "\n\n" if isinstance(existing, str) and existing else ""
                message["content"] = _append_text(existing, separator + compression_note)
        stripped = strip_handoff_summary(message)
        if stripped is not None:
            head.append(stripped)
    return head


def assemble_tail(
    messages: Sequence[Dict[str, Any]],
    compress_end: int,
    summary_indices: Optional[set] = None,
) -> List[Dict[str, Any]]:
    """组装受保护尾部；已被并入摘要的历史摘要不重复输出。"""
    tail: List[Dict[str, Any]] = []
    folded = summary_indices or set()
    for index in range(compress_end, len(messages)):
        if index in folded:
            continue
        stripped = strip_handoff_summary(fresh_copy(messages[index]))
        if stripped is not None:
            tail.append(stripped)
    return tail


def _has_visible_user_text(messages: Sequence[Dict[str, Any]]) -> bool:
    for message in messages:
        if role_of(message) != "user":
            continue
        if content_text(message.get("content")).strip():
            return True
    return False


def summary_placement(
    head: Sequence[Dict[str, Any]],
    tail: Sequence[Dict[str, Any]],
    compress_start: int,
) -> Tuple[str, bool, bool]:
    """决定摘要行的角色与放置方式。

    Returns:
        ``(角色, 是否并入尾部行, 是否强制以 user 引导)``
    """
    last_head_role: Optional[str] = "user"
    if head:
        last_head_role = last_template_visible_role(head)

    first_tail_role = next(
        (role for role in map(template_visible_role, tail) if role is not None),
        None,
    )

    # 头部只有 system、或序列中不存在带正文的用户消息时，摘要必须以 user 引导：
    # 前者是 Anthropic 的序列约束，后者是 OpenAI 兼容后端的要求（图片-only 不计入）
    force_user_leading = (
        compress_start == 0
        or last_head_role == "system"
        or not _has_visible_user_text(list(head) + list(tail))
    )

    summary_role = (
        "user"
        if last_head_role in {None, "assistant", "tool"} or force_user_leading
        else "assistant"
    )

    merge_into_tail = False
    if first_tail_role is not None and summary_role == first_tail_role:
        flipped = "assistant" if summary_role == "user" else "user"
        if flipped != last_head_role and last_head_role is not None and not force_user_leading:
            summary_role = flipped
        else:
            # 两种角色都非法时并入尾部首行，保证序列合法
            merge_into_tail = bool(tail)

    return summary_role, merge_into_tail, force_user_leading


def build_summary_row(summary: str, role: str) -> Dict[str, Any]:
    """构造独立的摘要消息行。"""
    return {
        "role": role,
        "content": summary,
        COMPRESSED_SUMMARY_METADATA_KEY: True,
        COMPRESSED_SUMMARY_HAS_USER_TURN_KEY: True,
    }


def merge_summary_into_row(
    message: Dict[str, Any], summary: str, *, force_user_leading: bool
) -> None:
    """把摘要并入已有尾部行（就地修改）。

    强制 user 引导时摘要置于正文之前（真实请求跟随结束标记）；否则保留原尾部内容
    作为带分隔的参考，摘要与结束标记在后。
    """
    old_content = message.get("content", "")
    if force_user_leading:
        message["content"] = _append_text(
            old_content,
            summary + "\n\n" + SUMMARY_END_MARKER + "\n\n",
            prepend=True,
        )
    else:
        suffix = (
            "\n\n" + MERGED_SUMMARY_DELIMITER + "\n\n" + summary + "\n\n" + SUMMARY_END_MARKER
        )
        merged = _append_text(old_content, suffix, prepend=False)
        message["content"] = _append_text(
            merged, MERGED_PRIOR_CONTEXT_HEADER + "\n", prepend=True
        )
    message[COMPRESSED_SUMMARY_METADATA_KEY] = True
    message[COMPRESSED_SUMMARY_HAS_USER_TURN_KEY] = True
    # 正文已改写，须丢弃旧 api_content，否则重放会发送改写前的字节
    message.pop("api_content", None)


def build_compressed(
    head: Sequence[Dict[str, Any]],
    tail: Sequence[Dict[str, Any]],
    summary: str,
    *,
    compress_start: int,
) -> List[Dict[str, Any]]:
    """按角色约束把头部、摘要、尾部拼装为最终消息列表。"""
    role, merge_into_tail, force_user_leading = summary_placement(head, tail, compress_start)
    compressed: List[Dict[str, Any]] = list(head)

    if merge_into_tail:
        merged_tail = [dict(message) for message in tail]
        merge_summary_into_row(
            merged_tail[0], summary, force_user_leading=force_user_leading
        )
        compressed.extend(merged_tail)
    else:
        compressed.append(build_summary_row(summary, role))
        compressed.extend(dict(message) for message in tail)

    return compressed
