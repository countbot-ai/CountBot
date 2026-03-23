"""Helpers for explicit external coding agent routing."""

from __future__ import annotations

import re
from typing import Optional, Tuple


_EXPLICIT_EXTERNAL_AGENT_RE = re.compile(
    r"""
    ^\s*
    (?:
        (?:请帮我|请你|请|帮我|麻烦你|麻烦|能否帮我|可以帮我)\s*
    )?
    (?:
        (?:请\s*)?(?:用|使用|走|调用)\s*
        |
        (?:please\s+)?(?:use|with)\s+
    )
    (?P<profile>[a-zA-Z][a-zA-Z0-9_-]*)
    (?:
        \s*(?:[:：,，-]+)\s*
        |
        \s+(?:to\s+)?
    )?
    (?P<task>.*?)
    \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)


def extract_explicit_external_agent_request(
    message: str,
) -> Optional[Tuple[str, str]]:
    """Extract an explicit 'use claude/codex ...' style request.

    Returns:
        (profile_name, task) if the message clearly asks to use an external
        coding profile and still contains a task body; otherwise None.
    """

    content = str(message or "").strip()
    if not content:
        return None

    match = _EXPLICIT_EXTERNAL_AGENT_RE.match(content)
    if not match:
        return None

    profile_name = str(match.group("profile") or "").strip()
    task = str(match.group("task") or "").strip()
    if not profile_name or not task:
        return None

    return profile_name, task


def build_explicit_external_agent_system_message(
    profile_name: str,
    prepared_task: str,
) -> str:
    """Build a system reminder that forces tool-call flow instead of raw passthrough."""

    profile = str(profile_name or "").strip()
    task = str(prepared_task or "").strip()
    if not profile or not task:
        return ""

    return (
        "检测到用户明确要求使用外部编程代理。\n"
        f"本轮你必须优先调用 `external_coding_agent`，且 `profile` 必须使用 `{profile}`。\n"
        "不要直接跳过工具调用，也不要把这次请求当作普通闲聊回答。\n"
        "调用工具时，`task` 必须使用下面这段完整正文，不要改写、不要省略、不要再附加路由前缀：\n\n"
        f"{task}\n\n"
        "拿到工具结果后，再继续由你给用户生成最终回复："
        "可以整理、解释、提炼下一步，但不要在调用工具前就结束回答。"
    )
