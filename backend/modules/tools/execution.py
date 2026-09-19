"""进程内 Tool 执行契约的基础类型。

本模块刻意不包含重试策略或持久化存储。它为
``ToolRegistry.execute_outcome`` 提供最小的进程内边界：一个 operation 可以
包含多个 physical attempt，但每个 attempt 只能完成一次。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import time
import uuid
from collections import OrderedDict
from typing import Any, Dict, Mapping, Optional, Tuple, Union


class ExecutionState(str, Enum):
    """一次 physical Tool execution attempt 的生命周期状态。"""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    UNKNOWN_OUTCOME = "UNKNOWN_OUTCOME"


class ErrorCategory(str, Enum):
    """执行边界使用的稳定、领域级 failure category。"""

    VALIDATION = "VALIDATION"
    PERMISSION = "PERMISSION"
    TIMEOUT = "TIMEOUT"
    CANCELLATION = "CANCELLATION"
    DEPENDENCY = "DEPENDENCY"
    EXECUTION = "EXECUTION"
    RESULT_CONTRACT = "RESULT_CONTRACT"
    INTERNAL = "INTERNAL"


class RetrySafety(str, Enum):
    """再次执行同一 logical operation 的安全性。"""

    SAFE = "SAFE"
    UNSAFE = "UNSAFE"
    UNKNOWN = "UNKNOWN"


class SideEffectState(str, Enum):
    """执行边界对可能产生的 side effect 所掌握的状态。"""

    NOT_APPLICABLE = "NOT_APPLICABLE"
    NOT_ATTEMPTED = "NOT_ATTEMPTED"
    COMMITTED = "COMMITTED"
    UNKNOWN = "UNKNOWN"


_TERMINAL_STATES = frozenset(
    {
        ExecutionState.SUCCEEDED,
        ExecutionState.FAILED,
        ExecutionState.CANCELLED,
        ExecutionState.UNKNOWN_OUTCOME,
    }
)


class AttemptTransitionError(RuntimeError):
    """attempt 生命周期转换违反契约时抛出。"""


class OperationIdentityCollisionError(ValueError):
    """operation ID 被复用于不同 invocation 时抛出。"""


def fingerprint_arguments(arguments: Mapping[str, Any]) -> str:
    """生成稳定指纹，避免在 ledger 中保留原始 arguments。"""

    canonical = json.dumps(arguments, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ToolExecutionRequest:
    """同一 logical operation 的所有 attempt 共用的请求元数据。"""

    tool_name: str
    operation_id: str
    arguments_fingerprint: str
    correlation_id: Optional[str] = None
    retry_ceiling: int = 0
    fingerprint_error: Optional[str] = None

    @classmethod
    def create(
        cls,
        *,
        tool_name: str,
        arguments: Mapping[str, Any],
        operation_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        retry_ceiling: int = 0,
    ) -> "ToolExecutionRequest":
        try:
            arguments_fingerprint = fingerprint_arguments(arguments)
            fingerprint_error = None
        except (TypeError, ValueError) as exc:
            # 不让 arguments 序列化异常逃出 canonical boundary；Registry 会将其
            # 转换为进入 Tool body 前的失败 outcome。
            arguments_fingerprint = f"invalid:{type(exc).__name__}"
            fingerprint_error = type(exc).__name__

        return cls(
            tool_name=tool_name,
            operation_id=operation_id or str(uuid.uuid4()),
            arguments_fingerprint=arguments_fingerprint,
            correlation_id=correlation_id,
            retry_ceiling=retry_ceiling,
            fingerprint_error=fingerprint_error,
        )

    def matches_logical_invocation(self, other: "ToolExecutionRequest") -> bool:
        """仅比较定义一次 logical Tool invocation 的字段。"""

        return (
            self.tool_name == other.tool_name
            and self.arguments_fingerprint == other.arguments_fingerprint
        )


@dataclass(frozen=True, slots=True)
class ToolResult:
    """Tool 返回给 Registry-owned attempt runner 的显式结果。

``ToolResult`` 只向 runner 传递事实，不会直接修改 attempt。只有 runner 可以
调用 ledger finalization。``UNKNOWN_OUTCOME`` 仍是 execution state；可选的独立
error category 用于说明为什么无法确定结果。
"""

    state: ExecutionState
    display_text: str
    output: Optional[str] = None
    error_category: Optional[ErrorCategory] = None
    retryable: bool = False
    retry_safety: RetrySafety = RetrySafety.UNKNOWN
    side_effect_state: SideEffectState = SideEffectState.NOT_APPLICABLE

    def __post_init__(self) -> None:
        if self.state not in _TERMINAL_STATES:
            raise ValueError("ToolResult must describe a terminal execution state")
        self._validate_certainty()
        if self.state is ExecutionState.SUCCEEDED:
            if self.output is None:
                raise ValueError("Successful ToolResult requires output")
            if self.error_category is not None:
                raise ValueError("Successful ToolResult cannot have an error category")
        else:
            if self.output is not None:
                raise ValueError("Non-success ToolResult cannot have success output")
            if self.error_category is None:
                raise ValueError("Non-success ToolResult requires an error category")

    def _validate_certainty(self) -> None:
        if self.side_effect_state is SideEffectState.UNKNOWN:
            if self.state is not ExecutionState.UNKNOWN_OUTCOME:
                raise ValueError("Unknown side-effect certainty requires UNKNOWN_OUTCOME")
        elif self.state is ExecutionState.UNKNOWN_OUTCOME:
            raise ValueError("UNKNOWN_OUTCOME requires unknown side-effect certainty")

    @classmethod
    def success(
        cls,
        output: str,
        *,
        display_text: Optional[str] = None,
        retry_safety: RetrySafety = RetrySafety.UNKNOWN,
        side_effect_state: SideEffectState = SideEffectState.NOT_APPLICABLE,
    ) -> "ToolResult":
        return cls(
            state=ExecutionState.SUCCEEDED,
            output=output,
            display_text=display_text if display_text is not None else output,
            retry_safety=retry_safety,
            side_effect_state=side_effect_state,
        )

    @classmethod
    def failure(
        cls,
        error_category: ErrorCategory,
        display_text: str,
        *,
        retryable: bool = False,
        retry_safety: RetrySafety = RetrySafety.UNKNOWN,
        side_effect_state: SideEffectState = SideEffectState.NOT_APPLICABLE,
    ) -> "ToolResult":
        return cls(
            state=ExecutionState.FAILED,
            display_text=display_text,
            error_category=error_category,
            retryable=retryable,
            retry_safety=retry_safety,
            side_effect_state=side_effect_state,
        )

    @classmethod
    def cancelled(cls, display_text: str = "Tool execution cancelled before completion.") -> "ToolResult":
        return cls(
            state=ExecutionState.CANCELLED,
            display_text=display_text,
            error_category=ErrorCategory.CANCELLATION,
            side_effect_state=SideEffectState.NOT_ATTEMPTED,
        )

    @classmethod
    def unknown_outcome(
        cls,
        error_category: ErrorCategory,
        display_text: str,
        *,
        retryable: bool = False,
        retry_safety: RetrySafety = RetrySafety.UNKNOWN,
    ) -> "ToolResult":
        return cls(
            state=ExecutionState.UNKNOWN_OUTCOME,
            display_text=display_text,
            error_category=error_category,
            retryable=retryable,
            retry_safety=retry_safety,
            side_effect_state=SideEffectState.UNKNOWN,
        )


@dataclass(frozen=True, slots=True)
class ToolExecutionOutcome:
    """一个 physical attempt 不可变且 authoritative 的 terminal outcome。"""

    operation_id: str
    attempt_id: str
    attempt_ordinal: int
    tool_name: str
    state: ExecutionState
    display_text: str
    duration_ms: int
    output: Optional[str] = None
    error_category: Optional[ErrorCategory] = None
    retryable: bool = False
    retry_safety: RetrySafety = RetrySafety.UNKNOWN
    side_effect_state: SideEffectState = SideEffectState.NOT_APPLICABLE
    correlation_id: Optional[str] = None

    def __post_init__(self) -> None:
        if self.state not in _TERMINAL_STATES:
            raise ValueError("ToolExecutionOutcome must be terminal")
        if self.duration_ms < 0:
            raise ValueError("duration_ms cannot be negative")
        self._validate_certainty()
        if self.state is ExecutionState.SUCCEEDED:
            if self.output is None or self.error_category is not None:
                raise ValueError("Successful outcome requires output and no error category")
        else:
            if self.output is not None:
                raise ValueError("Non-success outcome cannot have success output")
            if self.error_category is None:
                raise ValueError("Non-success outcome requires an error category")

    def _validate_certainty(self) -> None:
        if self.side_effect_state is SideEffectState.UNKNOWN:
            if self.state is not ExecutionState.UNKNOWN_OUTCOME:
                raise ValueError("Unknown side-effect certainty requires UNKNOWN_OUTCOME")
        elif self.state is ExecutionState.UNKNOWN_OUTCOME:
            raise ValueError("UNKNOWN_OUTCOME requires unknown side-effect certainty")

    @property
    def succeeded(self) -> bool:
        return self.state is ExecutionState.SUCCEEDED


@dataclass(frozen=True, slots=True)
class ToolExecutionInProgress:
    """Read-only admission result for a matching operation already in flight.

    This is deliberately not a physical execution attempt or a terminal
    ``ToolExecutionOutcome``.  It lets a duplicate caller observe the real
    active attempt without creating, changing, or finalizing an attempt.
    """

    operation_id: str
    active_attempt_id: str
    tool_name: str
    correlation_id: Optional[str]
    display_text: str


CanonicalToolExecutionResult = Union[ToolExecutionOutcome, ToolExecutionInProgress]


@dataclass(frozen=True, slots=True)
class ToolExecutionAttempt:
    """供诊断和 deterministic test 使用的只读生命周期视图。"""

    operation_id: str
    attempt_id: str
    attempt_ordinal: int
    tool_name: str
    state: ExecutionState


@dataclass(slots=True)
class _LedgerAttempt:
    request: ToolExecutionRequest
    attempt_id: str
    attempt_ordinal: int
    state: ExecutionState = ExecutionState.PENDING
    started_at: Optional[float] = None
    outcome: Optional[ToolExecutionOutcome] = None


class OperationLedger:
    """有界的进程内 attempt ledger。

它刻意不提供进程重启恢复或 distributed idempotency。Registry replay 会返回已
保存的 terminal outcome，而不是再次执行已完成的 operation。
"""

    def __init__(self, *, max_completed_operations: int = 1024) -> None:
        if max_completed_operations < 0:
            raise ValueError("max_completed_operations cannot be negative")
        self._attempts: Dict[str, _LedgerAttempt] = {}
        self._operation_attempt_ids: Dict[str, list[str]] = {}
        self._completed_operation_ids: OrderedDict[str, None] = OrderedDict()
        self._max_completed_operations = max_completed_operations

    def create_attempt(self, request: ToolExecutionRequest) -> ToolExecutionAttempt:
        attempt_ids = self._operation_attempt_ids.setdefault(request.operation_id, [])
        if attempt_ids:
            bound_request = self._attempts[attempt_ids[0]].request
            if not bound_request.matches_logical_invocation(request):
                raise OperationIdentityCollisionError(
                    "operation_id is already bound to a different Tool invocation"
                )
        if any(self._attempts[attempt_id].state not in _TERMINAL_STATES for attempt_id in attempt_ids):
            raise AttemptTransitionError("Cannot create a second attempt while an operation is in flight")

        self._completed_operation_ids.pop(request.operation_id, None)

        attempt_id = str(uuid.uuid4())
        attempt = _LedgerAttempt(
            request=request,
            attempt_id=attempt_id,
            attempt_ordinal=len(attempt_ids) + 1,
        )
        self._attempts[attempt_id] = attempt
        attempt_ids.append(attempt_id)
        return self.get_attempt(attempt_id)

    def get_attempt(self, attempt_id: str) -> ToolExecutionAttempt:
        attempt = self._attempts[attempt_id]
        return ToolExecutionAttempt(
            operation_id=attempt.request.operation_id,
            attempt_id=attempt.attempt_id,
            attempt_ordinal=attempt.attempt_ordinal,
            tool_name=attempt.request.tool_name,
            state=attempt.state,
        )

    def attempts_for_operation(self, operation_id: str) -> Tuple[ToolExecutionAttempt, ...]:
        return tuple(
            self.get_attempt(attempt_id)
            for attempt_id in self._operation_attempt_ids.get(operation_id, [])
        )

    def completed_outcome(self, request: ToolExecutionRequest) -> Optional[ToolExecutionOutcome]:
        """在 retention boundary 内返回同一 invocation 的 replay outcome。"""

        attempt_ids = self._operation_attempt_ids.get(request.operation_id, [])
        if not attempt_ids:
            return None
        bound_request = self._attempts[attempt_ids[0]].request
        if not bound_request.matches_logical_invocation(request):
            raise OperationIdentityCollisionError(
                "operation_id is already bound to a different Tool invocation"
            )
        latest = self._attempts[attempt_ids[-1]]
        return latest.outcome

    def active_attempt_for_operation(
        self,
        request: ToolExecutionRequest,
    ) -> Optional[ToolExecutionAttempt]:
        """Return the matching non-terminal attempt without mutating the ledger."""

        attempt_ids = self._operation_attempt_ids.get(request.operation_id, [])
        if not attempt_ids:
            return None
        bound_request = self._attempts[attempt_ids[0]].request
        if not bound_request.matches_logical_invocation(request):
            raise OperationIdentityCollisionError(
                "operation_id is already bound to a different Tool invocation"
            )
        for attempt_id in reversed(attempt_ids):
            attempt = self._attempts[attempt_id]
            if attempt.state not in _TERMINAL_STATES:
                return self.get_attempt(attempt_id)
        return None

    def start(self, attempt_id: str) -> ToolExecutionAttempt:
        attempt = self._attempts[attempt_id]
        self._transition(attempt, ExecutionState.RUNNING)
        attempt.started_at = time.monotonic()
        return self.get_attempt(attempt_id)

    def finalize(
        self,
        attempt_id: str,
        result: ToolResult,
        *,
        duration_ms: int,
    ) -> ToolExecutionOutcome:
        attempt = self._attempts[attempt_id]
        self._validate_transition(attempt, result.state)
        outcome = ToolExecutionOutcome(
            operation_id=attempt.request.operation_id,
            attempt_id=attempt.attempt_id,
            attempt_ordinal=attempt.attempt_ordinal,
            tool_name=attempt.request.tool_name,
            state=result.state,
            display_text=result.display_text,
            duration_ms=duration_ms,
            output=result.output,
            error_category=result.error_category,
            retryable=result.retryable,
            retry_safety=result.retry_safety,
            side_effect_state=result.side_effect_state,
            correlation_id=attempt.request.correlation_id,
        )
        # 先构造并校验 immutable outcome，再修改 state，避免 finalization 留下
        # 已进入 terminal state 但缺少 outcome 的 attempt。
        attempt.state = result.state
        attempt.outcome = outcome
        self._remember_completed_operation(attempt.request.operation_id)
        return outcome

    @staticmethod
    def _transition(attempt: _LedgerAttempt, next_state: ExecutionState) -> None:
        OperationLedger._validate_transition(attempt, next_state)
        attempt.state = next_state

    @staticmethod
    def _validate_transition(attempt: _LedgerAttempt, next_state: ExecutionState) -> None:
        current = attempt.state
        if current in _TERMINAL_STATES:
            raise AttemptTransitionError(
                f"Attempt {attempt.attempt_id} is terminal ({current.value}) and cannot transition"
            )
        allowed = {
            ExecutionState.PENDING: {
                ExecutionState.RUNNING,
                ExecutionState.FAILED,
                ExecutionState.CANCELLED,
            },
            ExecutionState.RUNNING: _TERMINAL_STATES,
        }
        if next_state not in allowed[current]:
            raise AttemptTransitionError(
                f"Illegal attempt transition: {current.value} -> {next_state.value}"
            )

    def _remember_completed_operation(self, operation_id: str) -> None:
        self._completed_operation_ids.pop(operation_id, None)
        self._completed_operation_ids[operation_id] = None
        while len(self._completed_operation_ids) > self._max_completed_operations:
            expired_operation_id, _ = self._completed_operation_ids.popitem(last=False)
            attempt_ids = self._operation_attempt_ids.pop(expired_operation_id, [])
            for attempt_id in attempt_ids:
                self._attempts.pop(attempt_id, None)
