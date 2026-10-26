"""工具结果的有界摘要：按工具类型定制单行摘要，保留关键参数与结论。"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, Optional, Tuple

# 摘要上限：严格小于瘦身阈值，保证摘要本身不会被再次瘦身
SUMMARY_MAX_CHARS = 199

# 失败特征词：命中即在摘要中标注 FAILED，避免压缩后丢失失败信号
_FAILURE_RE = re.compile(
    r"\b(error|failed|failure|exception|traceback|timeout|timed out|fatal|denied|refused)\b",
    re.IGNORECASE,
)

_JSON_PREFIX = "{"
_ARG_KEYS_BY_TOOL: Dict[str, Tuple[str, ...]] = {
    "read_file": ("path", "file_path", "filename"),
    "write_file": ("path", "file_path", "filename"),
    "edit_file": ("path", "file_path", "filename"),
    "list_dir": ("path", "directory", "dir"),
    "exec": ("command", "cmd"),
    "execute_command": ("command", "cmd"),
    "web_fetch": ("url",),
    "web_search": ("query", "q"),
    "file_search": ("pattern", "query", "path"),
    "spawn": ("label", "task"),
    "send_media": ("path", "file"),
}


def _parse_args(raw: str) -> Dict[str, Any]:
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _first_arg(tool_name: str, args: Dict[str, Any]) -> str:
    """取该工具最具辨识度的参数值。"""
    keys = _ARG_KEYS_BY_TOOL.get(tool_name, ("path", "command", "query", "url", "name"))
    for key in keys:
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    # 未在映射内的工具：取第一个字符串参数，保证摘要仍有定位信息
    for value in args.values():
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def failure_suffix(content: str) -> str:
    """内容含失败特征时返回标注后缀，否则空串。"""
    return " FAILED" if _FAILURE_RE.search(content or "") else ""


def _line_count(content: str) -> int:
    return content.count("\n") + 1 if content else 0


def _truncate(text: str, limit: int = 120) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def summarize_read_file(target: str, content: str) -> str:
    return f"[read_file] {target} ({_line_count(content)} lines, {len(content)} chars)"


def summarize_write_file(target: str, content: str) -> str:
    return f"[write_file] {target} ({len(content)} chars written)"


def summarize_exec(target: str, content: str) -> str:
    head = _truncate(content, 100)
    return f"[exec] `{_truncate(target, 60)}` → {head}" if head else f"[exec] `{_truncate(target, 60)}`"


def summarize_search(target: str, content: str) -> str:
    hits = _line_count(content)
    return f"[search] {_truncate(target, 60)} ({hits} result line(s))"


def summarize_fetch(target: str, content: str) -> str:
    return f"[web_fetch] {_truncate(target, 80)} ({len(content)} chars fetched)"


def summarize_spawn(target: str, content: str) -> str:
    return f"[spawn] {_truncate(target, 60)} → {_truncate(content, 100)}"


def summarize_generic(tool_name: str, target: str, content: str) -> str:
    where = f" {_truncate(target, 60)}" if target else ""
    return f"[{tool_name}]{where} ({_line_count(content)} lines, {len(content)} chars)"


_BUILDERS: Dict[str, Callable[[str, str], str]] = {
    "read_file": summarize_read_file,
    "write_file": summarize_write_file,
    "edit_file": summarize_write_file,
    "list_dir": summarize_search,
    "exec": summarize_exec,
    "execute_command": summarize_exec,
    "web_fetch": summarize_fetch,
    "web_search": summarize_search,
    "file_search": summarize_search,
    "spawn": summarize_spawn,
}


def summarize_tool_result(tool_name: str, tool_args: str, content: str) -> str:
    """生成工具结果的单行摘要。

    Args:
        tool_name: 工具名
        tool_args: 调用参数原文（JSON 字符串）
        content: 工具结果正文

    Returns:
        不超过 ``SUMMARY_MAX_CHARS`` 的摘要文本
    """
    name = str(tool_name or "tool")
    text = content or ""
    target = _first_arg(name, _parse_args(tool_args))

    builder = _BUILDERS.get(name)
    summary = builder(target, text) if builder else summarize_generic(name, target, text)

    if not isinstance(text, str) or len(text) < 1:
        summary = f"[{name}]{(' ' + _truncate(target, 60)) if target else ''} (empty result)"
    elif text.lstrip().startswith(_JSON_PREFIX):
        # 结构化返回：正文形态对大模型价值不高，保留体量信息即可
        summary = f"[{name}]{(' ' + _truncate(target, 60)) if target else ''} (json, {len(text)} chars)"

    return (summary + failure_suffix(text))[:SUMMARY_MAX_CHARS]
