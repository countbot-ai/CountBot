"""Canonical, in-process Tool execution contract primitives.

This module deliberately contains no retry policy and no persisted storage.  It
provides the small process-local boundary used by ``ToolRegistry.execute_outcome``:
an operation may have several physical attempts, while each attempt is finalized
exactly once.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import time
import uuid
from collections import OrderedDict
from typing import Any, Dict, Mapping, Optional, Tuple


class ExecutionState(str, Enum):
    """Lifecycle states of one physical Tool execution attempt."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    UNKNOWN_OUTCOME = "UNKNOWN_OUTCOME"


class ErrorCategory(str, Enum):
    """Stable, domain-level failure categories for the execution boundary."""

    VALIDATION = "VALIDATION"
    PERMISSION = "PERMISSION"
    TIMEOUT = "TIMEOUT"
    CANCELLATION = "CANCELLATION"
    DEPENDENCY = "DEPENDENCY"
    EXECUTION = "EXECUTION"
    RESULT_CONTRACT = "RESULT_CONTRACT"
    INTERNAL = "INTERNAL"


class RetrySafety(str, Enum):
    """Safety of another execution of the same logical operation."""

    SAFE = "SAFE"
    UNSAFE = "UNSAFE"
    UNKNOWN = "UNKNOWN"


class SideEffectState(str, Enum):
    """What the execution boundary knows about a possible side effect."""

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
    """Raised when an attempt lifecycle transition would violate the contract."""


class OperationIdentityCollisionError(ValueError):
    """Raised when an operation ID is reused for a different invocation."""


def fingerprint_arguments(arguments: Mapping[str, Any]) -> str:
    """Return a stable fingerprint without retaining raw arguments in the ledger."""

    canonical = json.dumps(arguments, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ToolExecutionRequest:
    """Request metadata shared by all attempts of one logical operation."""

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
            # Do not leak an argument serialization exception through the
            # canonical boundary.  Registry turns this into a pre-body failure.
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
        """Compare only the fields that define a logical Tool invocation."""

        return (
            self.tool_name == other.tool_name
            and self.arguments_fingerprint == other.arguments_fingerprint
        )


@dataclass(frozen=True, slots=True)
class ToolResult:
    """Explicit result returned by a Tool to the registry-owned attempt runner.

    A ``ToolResult`` communicates facts to the runner; it does not mutate an
    attempt itself.  The runner owns the only finalization call to the ledger.
    ``UNKNOWN_OUTCOME`` remains an execution state, with an optional independent
    error category describing why certainty was lost.
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
    """Immutable, authoritative terminal outcome for one physical attempt."""

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
class ToolExecutionAttempt:
    """Read-only lifecycle view used for diagnostics and deterministic tests."""

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
    """Bounded, process-local attempt ledger.

    It intentionally offers no process-restart recovery or distributed
    idempotency.  Registry replay returns the existing terminal outcome rather
    than executing a completed operation again.
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
        """Return a same-invocation replay outcome within the retention boundary."""

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
        # Construct and validate the immutable outcome before changing state so
        # finalization cannot leave a terminal attempt without an outcome.
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
