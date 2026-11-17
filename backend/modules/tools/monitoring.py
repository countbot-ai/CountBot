"""Helpers for long-running tool execution monitoring."""

from __future__ import annotations

import asyncio
import re
import time
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional, TypeVar

from backend.modules.tools.execution_context import emit_tool_progress


MONITOR_PARAMETER_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "expected_duration_sec": {
            "type": "integer",
            "description": "Expected total runtime in seconds.",
            "minimum": 1,
            "maximum": 86400,
        },
        "notify_every_sec": {
            "type": "integer",
            "description": "Emit a progress update every N seconds.",
            "minimum": 1,
            "maximum": 86400,
            "default": 300,
        },
        "report_remaining": {
            "type": "boolean",
            "description": "Whether to include estimated remaining seconds in progress updates.",
            "default": True,
        },
    },
    "required": ["expected_duration_sec"],
    "additionalProperties": False,
}


@dataclass(slots=True)
class ToolMonitorConfig:
    """Normalized long-running execution monitor config."""

    expected_duration_sec: int
    notify_every_sec: int = 300
    report_remaining: bool = True


DETACHED_EXEC_PATTERNS = (
    r"\bnohup\b",
    r"\bdisown\b",
    r"\btmux\b.*(?:\s|^)-d(?:\s|$)",
    r"(?:^|[;&(])\s*setsid\b",
    r"&\s*(?:$|[;|])",
)


LIKELY_LONG_RUNNING_EXEC_PATTERNS = (
    r"\b(?:npm|pnpm|yarn|bun)\s+(?:install|add|update|upgrade|build|test|run\s+(?:build|dev|start|test|lint|type-check|e2e|watch))\b",
    r"\b(?:pip|pip3|uv|poetry)\s+(?:install|sync|update)\b",
    r"\b(?:pytest|playwright|vitest|jest|npx playwright|cargo test|cargo build|go test|go build|mvn test|mvn package|gradle test|gradle build|cmake --build)\b",
    r"\b(?:docker build|docker compose|docker-compose|kubectl|helm|terraform|ansible-playbook)\b",
    r"\b(?:git clone|git fetch|git pull|rsync|scp|curl\s+-O|curl\s+-o|wget|ffmpeg|nmap|ssh)\b",
    r"\b(?:tail\s+-f|watch\b|top\b|htop\b|tcpdump\b|journalctl\s+-f)\b",
    r"\bfor\b.*\bsleep\b",
    r"\btime\.sleep\s*\(",
    r"\bsleep\s+(?:[6-9]\d|\d{3,})\b",
    r"\bwhile\s+true\b",
)


def parse_monitor_config(raw: Any) -> Optional[ToolMonitorConfig]:
    """Parse the optional monitor configuration."""

    if raw in (None, False):
        return None

    if not isinstance(raw, dict):
        raise ValueError("monitor must be an object")

    expected_duration = int(raw.get("expected_duration_sec") or 0)
    notify_every = int(raw.get("notify_every_sec") or 300)
    report_remaining = bool(raw.get("report_remaining", True))

    if expected_duration <= 0:
        raise ValueError("monitor.expected_duration_sec must be greater than 0")
    if notify_every <= 0:
        raise ValueError("monitor.notify_every_sec must be greater than 0")

    return ToolMonitorConfig(
        expected_duration_sec=expected_duration,
        notify_every_sec=notify_every,
        report_remaining=report_remaining,
    )


def _normalize_text(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def is_detached_exec_command(command: str) -> bool:
    """Return True when the command is intended to detach immediately."""

    normalized = _normalize_text(command)
    if not normalized:
        return False

    return any(re.search(pattern, normalized) for pattern in DETACHED_EXEC_PATTERNS)


def looks_like_long_running_exec(command: str) -> bool:
    """Best-effort heuristic for commands that likely take noticeable time."""

    normalized = _normalize_text(command)
    if not normalized:
        return False

    return any(re.search(pattern, normalized) for pattern in LIKELY_LONG_RUNNING_EXEC_PATTERNS)


def _choose_expected_duration(timeout_sec: Optional[int]) -> Optional[int]:
    if timeout_sec is None:
        return 120

    if timeout_sec < 90:
        return None
    if timeout_sec >= 900:
        return 600
    if timeout_sec >= 600:
        return max(300, timeout_sec - 60)
    if timeout_sec >= 300:
        return max(180, timeout_sec - 60)
    if timeout_sec >= 180:
        return 120

    return max(60, timeout_sec - 30)


def _choose_notify_interval(expected_duration_sec: int) -> int:
    if expected_duration_sec >= 600:
        return 300
    if expected_duration_sec >= 300:
        return 120
    if expected_duration_sec >= 120:
        return 60
    return max(30, expected_duration_sec // 2)


def build_default_monitor_config(
    *,
    tool_name: str,
    timeout_sec: Optional[int] = None,
    command: str = "",
) -> Optional[ToolMonitorConfig]:
    """Build a conservative default monitor config when the caller omitted one."""

    if tool_name == "exec":
        if is_detached_exec_command(command):
            return None
        should_monitor = looks_like_long_running_exec(command) or (
            timeout_sec is not None and timeout_sec >= 300
        )
    elif tool_name == "external_coding_agent":
        should_monitor = timeout_sec is not None and timeout_sec >= 300
    else:
        should_monitor = False

    if not should_monitor:
        return None

    expected_duration_sec = _choose_expected_duration(timeout_sec)
    if expected_duration_sec is None:
        return None

    return ToolMonitorConfig(
        expected_duration_sec=expected_duration_sec,
        notify_every_sec=_choose_notify_interval(expected_duration_sec),
        report_remaining=True,
    )


def _build_progress_snapshot(config: ToolMonitorConfig, elapsed_sec: int) -> tuple[int, str, Dict[str, Any]]:
    capped_elapsed = max(1, int(elapsed_sec))
    expected = max(1, config.expected_duration_sec)
    remaining = max(expected - capped_elapsed, 0)
    overrun = max(capped_elapsed - expected, 0)

    progress = min(99, max(1, int((min(capped_elapsed, expected) / expected) * 100)))
    if config.report_remaining:
        if overrun > 0:
            message = f"执行中：已运行 {capped_elapsed} 秒，已超过预计 {overrun} 秒"
        else:
            message = f"执行中：已运行 {capped_elapsed} 秒，预计剩余 {remaining} 秒"
    else:
        message = f"执行中：已运行 {capped_elapsed} 秒"

    details = {
        "elapsed_sec": capped_elapsed,
        "expected_duration_sec": expected,
        "notify_every_sec": config.notify_every_sec,
        "report_remaining": config.report_remaining,
    }
    if config.report_remaining:
        details["remaining_sec"] = remaining
        if overrun > 0:
            details["overrun_sec"] = overrun

    return progress, message, details


async def _run_monitor_loop(done_event: asyncio.Event, config: ToolMonitorConfig) -> None:
    await _run_monitor_loop_with_details(done_event, config, None)


def _merge_monitor_details(
    base_details: Dict[str, Any],
    details_provider: Optional[Callable[[], Optional[Dict[str, Any]]]],
) -> Dict[str, Any]:
    details = dict(base_details)
    if details_provider is None:
        return details

    try:
        extra_details = details_provider() or {}
    except Exception:
        return details

    if isinstance(extra_details, dict):
        details.update(extra_details)
    return details


async def _run_monitor_loop_with_details(
    done_event: asyncio.Event,
    config: ToolMonitorConfig,
    details_provider: Optional[Callable[[], Optional[Dict[str, Any]]]],
) -> None:
    started_at = time.monotonic()

    while not done_event.is_set():
        try:
            await asyncio.wait_for(done_event.wait(), timeout=config.notify_every_sec)
            break
        except asyncio.TimeoutError:
            elapsed_sec = int(time.monotonic() - started_at)
            progress, message, details = _build_progress_snapshot(config, elapsed_sec)
            details = _merge_monitor_details(details, details_provider)
            await emit_tool_progress(progress=progress, message=message, details=details)


T = TypeVar("T")


async def run_with_monitoring(
    awaitable: Awaitable[T],
    monitor: Optional[ToolMonitorConfig],
    details_provider: Optional[Callable[[], Optional[Dict[str, Any]]]] = None,
) -> T:
    """Run an awaitable while periodically emitting estimated progress."""

    if monitor is None:
        return await awaitable

    done_event = asyncio.Event()
    monitor_task = asyncio.create_task(
        _run_monitor_loop_with_details(done_event, monitor, details_provider)
    )

    try:
        return await awaitable
    finally:
        done_event.set()
        with suppress(asyncio.CancelledError):
            await monitor_task
