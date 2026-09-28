"""将 canonical outcome 投影为带版本、且不含执行载荷的持久化元数据。"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any, Mapping, Optional

from backend.modules.tools.execution import (
    ErrorCategory, ExecutionState, RetrySafety, SideEffectState,
    ToolExecutionOutcome, ToolResult,
)


SCHEMA_VERSION = 1
ATTEMPT_KIND = "tool_execution_attempt"
CHILD_DISPOSITION_KIND = "child_task_disposition"

_ATTEMPT_FIELDS = frozenset({
    "kind", "schema_version", "operation_id", "attempt_id", "attempt_ordinal",
    "tool_name", "state", "error_category", "retryable", "retry_safety",
    "side_effect_state", "correlation_id", "duration_ms", "source",
    "session_id", "task_id",
})
_DISPOSITION_FIELDS = frozenset({
    "kind", "schema_version", "task_id", "state", "error_category",
    "retryable", "retry_safety", "side_effect_state",
})
_TERMINAL_PROJECTION_STATES = frozenset({
    ExecutionState.SUCCEEDED, ExecutionState.FAILED,
    ExecutionState.CANCELLED, ExecutionState.UNKNOWN_OUTCOME,
})


def project_attempt(
    outcome: ToolExecutionOutcome, *, source: str,
    session_id: Optional[str] = None, task_id: Optional[str] = None,
) -> dict[str, Any]:
    """按白名单复制契约字段；不读取 output 或 display_text。

    只有 Registry 返回的真实 terminal physical attempt 可使用该投影。
    """
    if not isinstance(outcome, ToolExecutionOutcome):
        raise TypeError("An immutable terminal ToolExecutionOutcome is required")
    if not outcome.attempt_id or outcome.attempt_ordinal < 1:
        raise ValueError("A real tracked physical attempt is required")
    return {
        "kind": ATTEMPT_KIND,
        "schema_version": SCHEMA_VERSION,
        "operation_id": outcome.operation_id,
        "attempt_id": outcome.attempt_id,
        "attempt_ordinal": outcome.attempt_ordinal,
        "tool_name": outcome.tool_name,
        "state": outcome.state.value,
        "error_category": outcome.error_category.value if outcome.error_category else None,
        "retryable": outcome.retryable,
        "retry_safety": outcome.retry_safety.value,
        "side_effect_state": outcome.side_effect_state.value,
        "correlation_id": outcome.correlation_id,
        "duration_ms": outcome.duration_ms,
        "source": source,
        "session_id": session_id,
        "task_id": task_id,
    }


def project_child_disposition(task_id: str, outcome: ToolResult) -> dict[str, Any]:
    """投影 child task 的最终处置；它不代表一条物理 Tool attempt。"""
    if not isinstance(outcome, ToolResult):
        raise TypeError("A structured child ToolResult is required")
    return {
        "kind": CHILD_DISPOSITION_KIND,
        "schema_version": SCHEMA_VERSION,
        "task_id": task_id,
        "state": outcome.state.value,
        "error_category": outcome.error_category.value if outcome.error_category else None,
        "retryable": outcome.retryable,
        "retry_safety": outcome.retry_safety.value,
        "side_effect_state": outcome.side_effect_state.value,
    }


def read_projection(value: Any, *, kind: str = ATTEMPT_KIND) -> Optional[dict[str, Any]]:
    """只读取当前版本的完整投影；legacy 或未知版本返回 None。

    缺少字段时不从旧 result、error 或 status 文本补造 canonical 事实。
    """
    if (not isinstance(value, Mapping)
            or type(value.get("schema_version")) is not int
            or value.get("schema_version") != SCHEMA_VERSION):
        return None
    if value.get("kind") != kind:
        return None
    fields = _ATTEMPT_FIELDS if kind == ATTEMPT_KIND else _DISPOSITION_FIELDS
    if kind not in (ATTEMPT_KIND, CHILD_DISPOSITION_KIND) or not fields.issuperset(value):
        return None
    if not fields.issubset(value):
        return None
    try:
        state = ExecutionState(value["state"])
        RetrySafety(value["retry_safety"])
        side_effect_state = SideEffectState(value["side_effect_state"])
        if value["error_category"] is not None:
            ErrorCategory(value["error_category"])
    except (ValueError, TypeError):
        return None
    if state not in _TERMINAL_PROJECTION_STATES:
        return None
    if (state is ExecutionState.SUCCEEDED) != (value["error_category"] is None):
        return None
    if (state is ExecutionState.UNKNOWN_OUTCOME) != (side_effect_state is SideEffectState.UNKNOWN):
        return None
    if type(value["retryable"]) is not bool:
        return None
    if kind == ATTEMPT_KIND:
        if not all(isinstance(value[field], str) and value[field] for field in
                   ("operation_id", "attempt_id", "tool_name", "source")):
            return None
        if (type(value["attempt_ordinal"]) is not int or value["attempt_ordinal"] < 1
                or type(value["duration_ms"]) is not int or value["duration_ms"] < 0):
            return None
    elif not isinstance(value["task_id"], str) or not value["task_id"]:
        return None
    return dict(value)


def read_stored_projection(value: Any, *, kind: str = ATTEMPT_KIND) -> Optional[dict[str, Any]]:
    """读取可空 JSON 列；旧数据或无效 JSON 保持为无 canonical 投影。"""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return None
    return read_projection(value, kind=kind)


class ProjectionState(str, Enum):
    ABSENT = "absent"
    RECOGNIZED = "recognized"
    UNSUPPORTED = "unsupported"


def projection_state(value: Any, *, kind: str = ATTEMPT_KIND) -> ProjectionState:
    """Keep absent legacy data distinct from present but unreadable data."""
    if value is None:
        return ProjectionState.ABSENT
    if read_stored_projection(value, kind=kind) is not None:
        return ProjectionState.RECOGNIZED
    return ProjectionState.UNSUPPORTED


def read_task_projection(value: Any) -> tuple[ProjectionState, Optional[dict[str, Any]]]:
    """Read child disposition and attempts as one versioned task projection."""
    if value is None:
        return ProjectionState.ABSENT, None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return ProjectionState.UNSUPPORTED, None
    if not isinstance(value, Mapping) or set(value) != {"disposition", "attempts"}:
        return ProjectionState.UNSUPPORTED, None
    disposition = value["disposition"]
    attempts = value["attempts"]
    if (disposition is not None and read_projection(disposition, kind=CHILD_DISPOSITION_KIND) is None):
        return ProjectionState.UNSUPPORTED, None
    if not isinstance(attempts, list) or any(read_projection(item) is None for item in attempts):
        return ProjectionState.UNSUPPORTED, None
    return ProjectionState.RECOGNIZED, dict(value)


def task_read_view(legacy_status: str, value: Any) -> tuple[str, str, Optional[dict[str, Any]]]:
    """Legacy status is authoritative only when the projection is absent."""
    state, parsed = read_task_projection(value)
    if state is ProjectionState.ABSENT:
        return legacy_status, state.value, None
    if state is ProjectionState.UNSUPPORTED:
        return "unknown", state.value, None
    disposition = parsed["disposition"]
    if disposition is None:
        # An active child may have prior attempts but no final disposition yet.
        lifecycle_status = legacy_status if legacy_status in ("pending", "running") else "unknown"
        return lifecycle_status, state.value, parsed
    canonical_status = (
        {"SUCCEEDED": "completed", "FAILED": "failed", "CANCELLED": "cancelled",
         "UNKNOWN_OUTCOME": "unknown"}[disposition["state"]]
    )
    return canonical_status, state.value, parsed


def conversation_succeeded(projection: Any, legacy_error: Any) -> bool:
    state = projection_state(projection)
    if state is ProjectionState.ABSENT:
        return legacy_error is None
    if state is ProjectionState.UNSUPPORTED:
        return False
    return read_stored_projection(projection)["state"] == "SUCCEEDED"
