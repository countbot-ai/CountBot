"""外部编程工具会话与历史辅助函数。"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

from backend.modules.external_agents.base import ExternalAgentProfile


def normalize_session_mode(value: str | None) -> str:
    """规范化会话模式。"""
    mode = str(value or "").strip().lower()
    if mode in {"native", "history", "stateless"}:
        return mode
    return "history"


def profile_supports_native_session(profile: ExternalAgentProfile) -> bool:
    """判断当前 profile 是否可稳定使用原生会话。"""
    command_name = Path(profile.command or "").name.lower()
    profile_name = profile.name.strip().lower()
    return command_name == "claude" or profile_name == "claude"


def resolve_effective_session_mode(profile: ExternalAgentProfile) -> str:
    """返回真正生效的会话模式。"""
    mode = normalize_session_mode(profile.session_mode)
    if mode == "native" and not profile_supports_native_session(profile):
        return "history"
    return mode


def sanitize_history_message_count(value: int | None) -> int:
    """限制历史消息条数，避免 prompt 失控。"""
    if value is None:
        return 10
    return max(1, min(50, int(value)))


def build_history_prompt(
    task: str,
    history_messages: Sequence[Mapping[str, str]] | None,
    history_message_count: int,
) -> str:
    """把最近历史消息拼到当前任务里。"""
    current_task = str(task or "").strip()
    if not current_task:
        return ""

    messages = [
        {
            "role": str(item.get("role") or "").strip().lower(),
            "content": str(item.get("content") or "").strip(),
        }
        for item in (history_messages or [])
    ]
    messages = [
        item
        for item in messages
        if item["role"] in {"user", "assistant", "system"} and item["content"]
    ]

    if not messages:
        return current_task

    trimmed = messages[-sanitize_history_message_count(history_message_count):]
    lines = ["下面是最近对话历史，请结合上下文继续处理。", "", "最近历史："]
    for item in trimmed:
        role = {
            "user": "用户",
            "assistant": "助手",
            "system": "系统",
        }.get(item["role"], item["role"])
        lines.append(f"[{role}] {item['content']}")

    lines.extend(["", "当前用户最新要求：", current_task])
    return "\n".join(lines)
