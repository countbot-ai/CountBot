"""Shared helpers for explicit /team command parsing and replies."""

from typing import List, Optional

from loguru import logger


def get_available_team_names(
    context_builder: object | None,
    *,
    log_scope: str = "team command",
) -> List[str]:
    """Load active team names from the context builder."""
    team_name_getter = getattr(context_builder, "_get_active_team_names", None)
    if not callable(team_name_getter):
        return []

    try:
        raw_team_names = team_name_getter() or []
    except Exception as exc:
        logger.warning(f"Failed to load active team names for {log_scope}: {exc}")
        return []

    team_names: List[str] = []
    seen: set[str] = set()
    for name in raw_team_names:
        normalized = str(name or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        team_names.append(normalized)
    return team_names


def build_team_command_overview(
    context_builder: object | None,
    *,
    log_scope: str = "team command",
) -> str:
    """Build the reply for `/team` without a task."""
    team_names = get_available_team_names(context_builder, log_scope=log_scope)
    if not team_names:
        return "当前没有可用团队，请先在团队管理中启用团队。"

    lines = ["可用团队名称:"]
    lines.extend(f"- {team_name}" for team_name in team_names)
    lines.append("")
    lines.append("用法: /team 团队名 任务描述")
    return "\n".join(lines)


def build_team_goal_usage(team_name: str) -> str:
    """Build the reply when a team is selected but the goal is missing."""
    return f"已识别团队: {team_name}\n用法: /team {team_name} 任务描述"


def resolve_explicit_team_command(
    context_builder: object | None,
    message: str,
    *,
    log_scope: str = "team command",
) -> Optional[tuple[str, str]]:
    """Resolve `/team <team_name> <goal>` into a deterministic workflow request."""
    stripped = message.strip()
    if stripped == "/team":
        return ("", "")

    if not stripped.startswith("/team "):
        return None

    remainder = stripped[len("/team "):].strip()
    if not remainder:
        return ("", "")

    team_names = get_available_team_names(context_builder, log_scope=log_scope)
    if not team_names:
        return None

    for team_name in sorted(team_names, key=len, reverse=True):
        if remainder == team_name:
            return (team_name, "")
        if remainder.startswith(team_name):
            suffix = remainder[len(team_name):]
            if suffix[:1].isspace():
                return (team_name, suffix.strip())

    return ("", "")
