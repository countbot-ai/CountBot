"""canonical Tool execution contract 的 deterministic PR1 coverage。"""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.modules.tools.base import Tool
from backend.modules.tools.execution import (
    AttemptTransitionError,
    ErrorCategory,
    ExecutionState,
    OperationLedger,
    RetrySafety,
    SideEffectState,
    ToolExecutionInProgress,
    ToolExecutionRequest,
    ToolExecutionOutcome,
    ToolResult,
)
from backend.modules.tools.registry import ToolRegistry
from backend.modules.agent.task_manager import CancellationToken


class _ExplicitTool(Tool):
    name = "explicit"
    description = "Contract test Tool"

    def __init__(self, result: ToolResult, *, parameters=None) -> None:
        self.result = result
        self._parameters = parameters or {"type": "object", "properties": {}}
        self.body_invocations = 0
        self.effect_marker = False

    @property
    def parameters(self):
        return self._parameters

    async def execute(self, **kwargs):
        return "legacy path is not used by this test Tool"

    async def execute_outcome(self, **kwargs):
        self.body_invocations += 1
        self.effect_marker = True
        return self.result


class _LegacyStringTool(Tool):
    name = "legacy"
    description = "Returns an error-shaped legacy string"
    parameters = {"type": "object", "properties": {}}

    async def execute(self, **kwargs):
        return "Error: ordinary text that must not be parsed as execution state"


class _LegacyDictTool(_LegacyStringTool):
    name = "legacy_dict"

    async def execute(self, **kwargs):
        return {"error": "legacy dict must not be inferred as success"}


class _OtherExplicitTool(_ExplicitTool):
    name = "other_explicit"


class _SequencedExplicitTool(_ExplicitTool):
    def __init__(self, results):
        super().__init__(results[0])
        self._results = iter(results)

    async def execute_outcome(self, **kwargs):
        self.body_invocations += 1
        self.effect_marker = True
        return next(self._results)


class _BlockingExplicitTool(_ExplicitTool):
    def __init__(self, result: ToolResult) -> None:
        super().__init__(result)
        self.body_entered = asyncio.Event()
        self.release_body = asyncio.Event()

    async def execute_outcome(self, **kwargs):
        self.body_invocations += 1
        self.effect_marker = True
        self.body_entered.set()
        await self.release_body.wait()
        return self.result


class _RaisingExplicitTool(_ExplicitTool):
    async def execute_outcome(self, **kwargs):
        self.body_invocations += 1
        self.effect_marker = True
        raise RuntimeError("body exception after execution started")


class _CancelledExplicitTool(_ExplicitTool):
    async def execute_outcome(self, **kwargs):
        self.body_invocations += 1
        self.effect_marker = True
        raise asyncio.CancelledError()


class _ValidationErrorTool(_ExplicitTool):
    def validate_params(self, params):
        raise ValueError("broken schema")


def _run(coro):
    return asyncio.run(coro)


def test_registry_produces_machine_readable_success_outcome():
    registry = ToolRegistry()
    tool = _ExplicitTool(ToolResult.success("completed"))
    registry.register(tool)

    outcome = _run(registry.execute_outcome("explicit", {}))

    assert outcome.state is ExecutionState.SUCCEEDED
    assert outcome.output == "completed"
    assert outcome.error_category is None
    assert outcome.operation_id and outcome.attempt_id
    assert outcome.attempt_ordinal == 1
    assert tool.body_invocations == 1


def test_explicit_failure_keeps_error_dimensions_independent():
    registry = ToolRegistry()
    registry.register(
        _ExplicitTool(
            ToolResult.failure(
                ErrorCategory.DEPENDENCY,
                "Dependency is unavailable.",
                retryable=True,
                retry_safety=RetrySafety.UNSAFE,
            )
        )
    )

    outcome = _run(registry.execute_outcome("explicit", {}))

    assert outcome.state is ExecutionState.FAILED
    assert outcome.error_category is ErrorCategory.DEPENDENCY
    assert outcome.retryable is True
    assert outcome.retry_safety is RetrySafety.UNSAFE


def test_unknown_outcome_is_a_state_not_an_error_category():
    result = ToolResult.unknown_outcome(
        ErrorCategory.TIMEOUT,
        "Timed out after execution certainty was lost.",
        retryable=True,
        retry_safety=RetrySafety.UNKNOWN,
    )

    assert result.state is ExecutionState.UNKNOWN_OUTCOME
    assert result.error_category is ErrorCategory.TIMEOUT
    assert "UNKNOWN_OUTCOME" not in ErrorCategory._value2member_map_


def test_unknown_side_effect_certainty_requires_unknown_outcome():
    with pytest.raises(ValueError):
        ToolResult.failure(
            ErrorCategory.TIMEOUT,
            "Timeout certainty is unknown.",
            side_effect_state=SideEffectState.UNKNOWN,
        )
    with pytest.raises(ValueError):
        ToolExecutionOutcome(
            operation_id="operation-1",
            attempt_id="attempt-1",
            attempt_ordinal=1,
            tool_name="explicit",
            state=ExecutionState.FAILED,
            display_text="Contradictory outcome.",
            duration_ms=0,
            error_category=ErrorCategory.TIMEOUT,
            side_effect_state=SideEffectState.UNKNOWN,
        )
    with pytest.raises(ValueError):
        ToolResult(
            state=ExecutionState.UNKNOWN_OUTCOME,
            display_text="Missing uncertainty.",
            error_category=ErrorCategory.TIMEOUT,
            side_effect_state=SideEffectState.NOT_ATTEMPTED,
        )


def test_operation_can_have_distinct_physical_attempts():
    ledger = OperationLedger()
    request = ToolExecutionRequest.create(tool_name="explicit", arguments={"value": 1})

    first = ledger.create_attempt(request)
    ledger.start(first.attempt_id)
    ledger.finalize(first.attempt_id, ToolResult.success("first"), duration_ms=1)
    second = ledger.create_attempt(request)
    ledger.start(second.attempt_id)
    ledger.finalize(second.attempt_id, ToolResult.success("second"), duration_ms=1)

    assert first.operation_id == second.operation_id == request.operation_id
    assert first.attempt_id != second.attempt_id
    assert (first.attempt_ordinal, second.attempt_ordinal) == (1, 2)


def test_terminal_attempt_cannot_be_reopened_or_refinalized():
    ledger = OperationLedger()
    attempt = ledger.create_attempt(ToolExecutionRequest.create(tool_name="explicit", arguments={}))
    ledger.start(attempt.attempt_id)
    ledger.finalize(attempt.attempt_id, ToolResult.success("done"), duration_ms=1)

    with pytest.raises(AttemptTransitionError):
        ledger.start(attempt.attempt_id)
    with pytest.raises(AttemptTransitionError):
        ledger.finalize(
            attempt.attempt_id,
            ToolResult.failure(ErrorCategory.EXECUTION, "cannot overwrite"),
            duration_ms=1,
        )


def test_invalid_pending_to_success_transition_is_rejected():
    ledger = OperationLedger()
    attempt = ledger.create_attempt(ToolExecutionRequest.create(tool_name="explicit", arguments={}))

    with pytest.raises(AttemptTransitionError):
        ledger.finalize(attempt.attempt_id, ToolResult.success("too early"), duration_ms=0)


def test_validation_failure_happens_before_tool_body():
    registry = ToolRegistry()
    tool = _ExplicitTool(
        ToolResult.success("must not run"),
        parameters={
            "type": "object",
            "properties": {"required_value": {"type": "string"}},
            "required": ["required_value"],
        },
    )
    registry.register(tool)

    outcome = _run(registry.execute_outcome("explicit", {}))

    assert outcome.state is ExecutionState.FAILED
    assert outcome.error_category is ErrorCategory.VALIDATION
    assert outcome.side_effect_state is SideEffectState.NOT_ATTEMPTED
    assert tool.body_invocations == 0
    assert tool.effect_marker is False


def test_validation_exception_is_normalized_before_tool_body():
    registry = ToolRegistry()
    tool = _ValidationErrorTool(ToolResult.success("must not run"))
    registry.register(tool)

    outcome = _run(registry.execute_outcome("explicit", {}))

    assert outcome.state is ExecutionState.FAILED
    assert outcome.error_category is ErrorCategory.INTERNAL
    assert outcome.side_effect_state is SideEffectState.NOT_ATTEMPTED
    assert tool.body_invocations == 0
    assert tool.effect_marker is False


def test_legacy_return_is_result_contract_unknown_outcome_not_success():
    registry = ToolRegistry()
    registry.register(_LegacyStringTool())

    outcome = _run(registry.execute_outcome("legacy", {}))

    assert outcome.state is ExecutionState.UNKNOWN_OUTCOME
    assert outcome.error_category is ErrorCategory.RESULT_CONTRACT
    assert outcome.output is None
    assert outcome.side_effect_state is SideEffectState.UNKNOWN


def test_unexpected_legacy_dict_is_result_contract_unknown_outcome_not_success():
    registry = ToolRegistry()
    registry.register(_LegacyDictTool())

    outcome = _run(registry.execute_outcome("legacy_dict", {}))

    assert outcome.state is ExecutionState.UNKNOWN_OUTCOME
    assert outcome.error_category is ErrorCategory.RESULT_CONTRACT
    assert outcome.side_effect_state is SideEffectState.UNKNOWN


def test_overlapping_operation_returns_in_progress_without_creating_attempt():
    async def run_overlap():
        ledger = OperationLedger()
        registry = ToolRegistry(ledger=ledger)
        tool = _BlockingExplicitTool(ToolResult.success("completed"))
        registry.register(tool)

        first_task = asyncio.create_task(
            registry.execute_outcome(
                "explicit",
                {},
                operation_id="operation-1",
                correlation_id="correlation-1",
            )
        )
        await tool.body_entered.wait()

        active_attempt = ledger.attempts_for_operation("operation-1")[0]
        assert active_attempt.state is ExecutionState.RUNNING

        second = await registry.execute_outcome(
            "explicit",
            {},
            operation_id="operation-1",
            correlation_id="correlation-1",
        )

        assert isinstance(second, ToolExecutionInProgress)
        assert second.operation_id == "operation-1"
        assert second.active_attempt_id == active_attempt.attempt_id
        assert second.tool_name == "explicit"
        assert second.correlation_id == "correlation-1"
        assert len(ledger.attempts_for_operation("operation-1")) == 1
        assert ledger.get_attempt(active_attempt.attempt_id).state is ExecutionState.RUNNING
        assert tool.body_invocations == 1

        tool.release_body.set()
        first = await first_task
        replay = await registry.execute_outcome(
            "explicit",
            {},
            operation_id="operation-1",
            correlation_id="correlation-1",
        )

        assert first.state is ExecutionState.SUCCEEDED
        assert replay == first
        assert replay.attempt_id == active_attempt.attempt_id
        assert len(ledger.attempts_for_operation("operation-1")) == 1
        assert tool.body_invocations == 1

    _run(run_overlap())


def test_post_body_exception_preserves_unknown_effect_certainty():
    registry = ToolRegistry()
    tool = _RaisingExplicitTool(ToolResult.success("unused"))
    registry.register(tool)

    outcome = _run(registry.execute_outcome("explicit", {}))

    assert tool.body_invocations == 1
    assert tool.effect_marker is True
    assert outcome.state is ExecutionState.UNKNOWN_OUTCOME
    assert outcome.error_category is ErrorCategory.EXECUTION
    assert outcome.side_effect_state is SideEffectState.UNKNOWN
    assert outcome.retryable is False
    assert outcome.retry_safety is RetrySafety.UNKNOWN


def test_post_body_cancellation_preserves_unknown_effect_certainty():
    registry = ToolRegistry()
    tool = _CancelledExplicitTool(ToolResult.success("unused"))
    registry.register(tool)

    outcome = _run(registry.execute_outcome("explicit", {}))

    assert tool.body_invocations == 1
    assert tool.effect_marker is True
    assert outcome.state is ExecutionState.UNKNOWN_OUTCOME
    assert outcome.error_category is ErrorCategory.CANCELLATION
    assert outcome.side_effect_state is SideEffectState.UNKNOWN
    assert outcome.retry_safety is RetrySafety.UNKNOWN


def test_completed_operation_replay_is_deduplicated_without_running_body_again():
    registry = ToolRegistry()
    tool = _ExplicitTool(ToolResult.success("completed"))
    registry.register(tool)

    first = _run(registry.execute_outcome("explicit", {}, operation_id="operation-1"))
    replay = _run(registry.execute_outcome("explicit", {}, operation_id="operation-1"))

    assert replay == first
    assert tool.body_invocations == 1


def test_operation_id_collision_with_different_tool_is_rejected_before_body():
    registry = ToolRegistry()
    first_tool = _ExplicitTool(ToolResult.success("first"))
    wrong_tool = _OtherExplicitTool(ToolResult.success("wrong body must not run"))
    registry.register(first_tool)
    registry.register(wrong_tool)

    first = _run(registry.execute_outcome("explicit", {}, operation_id="operation-1"))
    collision = _run(
        registry.execute_outcome("other_explicit", {}, operation_id="operation-1")
    )

    assert first.state is ExecutionState.SUCCEEDED
    assert collision.state is ExecutionState.FAILED
    assert collision.error_category is ErrorCategory.VALIDATION
    assert collision.tool_name == "other_explicit"
    assert first_tool.body_invocations == 1
    assert wrong_tool.body_invocations == 0


def test_operation_id_collision_with_different_arguments_is_rejected_before_body():
    registry = ToolRegistry()
    tool = _ExplicitTool(ToolResult.success("first"))
    registry.register(tool)

    first = _run(
        registry.execute_outcome("explicit", {"value": "one"}, operation_id="operation-1")
    )
    collision = _run(
        registry.execute_outcome("explicit", {"value": "two"}, operation_id="operation-1")
    )

    assert first.state is ExecutionState.SUCCEEDED
    assert collision.state is ExecutionState.FAILED
    assert collision.error_category is ErrorCategory.VALIDATION
    assert tool.body_invocations == 1


def test_authorized_reexecution_creates_a_second_registry_attempt():
    registry = ToolRegistry()
    tool = _SequencedExplicitTool(
        [
            ToolResult.failure(
                ErrorCategory.DEPENDENCY,
                "Dependency is temporarily unavailable.",
                retryable=True,
                retry_safety=RetrySafety.SAFE,
            ),
            ToolResult.success("completed"),
        ]
    )
    registry.register(tool)

    first = _run(registry.execute_outcome("explicit", {}, operation_id="operation-1"))
    duplicate = _run(registry.execute_outcome("explicit", {}, operation_id="operation-1"))
    second = _run(
        registry.execute_outcome(
            "explicit",
            {},
            operation_id="operation-1",
            retry_authorized=True,
        )
    )

    assert duplicate == first
    assert first.state is ExecutionState.FAILED
    assert second.state is ExecutionState.SUCCEEDED
    assert first.operation_id == second.operation_id == "operation-1"
    assert first.attempt_id != second.attempt_id
    assert (first.attempt_ordinal, second.attempt_ordinal) == (1, 2)
    assert tool.body_invocations == 2


def test_successful_operation_cannot_be_reexecuted_even_when_retry_is_authorized():
    ledger = OperationLedger()
    registry = ToolRegistry(ledger=ledger)
    tool = _ExplicitTool(ToolResult.success("completed"))
    registry.register(tool)

    first = _run(registry.execute_outcome("explicit", {}, operation_id="operation-1"))
    second = _run(
        registry.execute_outcome(
            "explicit",
            {},
            operation_id="operation-1",
            retry_authorized=True,
        )
    )

    assert second == first
    assert second.attempt_id == first.attempt_id
    assert len(ledger.attempts_for_operation("operation-1")) == 1
    assert tool.body_invocations == 1


def test_unknown_outcome_does_not_reexecute_without_proven_safe_idempotency():
    registry = ToolRegistry()
    tool = _ExplicitTool(
        ToolResult.unknown_outcome(
            ErrorCategory.TIMEOUT,
            "Commit certainty is unknown.",
            retryable=True,
        )
    )
    registry.register(tool)

    first = _run(registry.execute_outcome("explicit", {}, operation_id="operation-1"))
    blocked = _run(
        registry.execute_outcome(
            "explicit",
            {},
            operation_id="operation-1",
            retry_authorized=True,
        )
    )

    assert blocked == first
    assert blocked.state is ExecutionState.UNKNOWN_OUTCOME
    assert tool.body_invocations == 1


def test_bounded_completed_operation_retention_expires_only_terminal_operations():
    ledger = OperationLedger(max_completed_operations=1)
    registry = ToolRegistry(ledger=ledger)
    tool = _ExplicitTool(ToolResult.success("completed"))
    registry.register(tool)

    _run(registry.execute_outcome("explicit", {}, operation_id="operation-1"))
    _run(registry.execute_outcome("explicit", {}, operation_id="operation-2"))
    replay_after_expiry = _run(
        registry.execute_outcome("explicit", {}, operation_id="operation-1")
    )

    assert replay_after_expiry.attempt_ordinal == 1
    assert tool.body_invocations == 3

    in_flight = ledger.create_attempt(
        ToolExecutionRequest.create(tool_name="explicit", arguments={}, operation_id="in-flight")
    )
    ledger.start(in_flight.attempt_id)
    completed = ledger.create_attempt(
        ToolExecutionRequest.create(tool_name="explicit", arguments={}, operation_id="complete-a")
    )
    ledger.start(completed.attempt_id)
    ledger.finalize(completed.attempt_id, ToolResult.success("done"), duration_ms=0)
    later_completed = ledger.create_attempt(
        ToolExecutionRequest.create(tool_name="explicit", arguments={}, operation_id="complete-b")
    )
    ledger.start(later_completed.attempt_id)
    ledger.finalize(later_completed.attempt_id, ToolResult.success("done"), duration_ms=0)

    assert ledger.get_attempt(in_flight.attempt_id).state is ExecutionState.RUNNING


def test_pre_execution_cancellation_does_not_run_body_or_mark_effect():
    registry = ToolRegistry()
    tool = _ExplicitTool(ToolResult.success("must not run"))
    registry.register(tool)
    cancellation = asyncio.Event()
    cancellation.set()

    outcome = _run(
        registry.execute_outcome(
            "explicit",
            {},
            cancellation_token=cancellation,
        )
    )

    assert outcome.state is ExecutionState.CANCELLED
    assert outcome.error_category is ErrorCategory.CANCELLATION
    assert outcome.side_effect_state is SideEffectState.NOT_ATTEMPTED
    assert tool.body_invocations == 0
    assert tool.effect_marker is False


def test_repository_cancellation_token_stops_before_tool_body():
    registry = ToolRegistry()
    tool = _ExplicitTool(ToolResult.success("must not run"))
    registry.register(tool)
    cancellation = CancellationToken()
    cancellation.cancel()

    outcome = _run(
        registry.execute_outcome("explicit", {}, cancellation_token=cancellation)
    )

    assert outcome.state is ExecutionState.CANCELLED
    assert outcome.error_category is ErrorCategory.CANCELLATION
    assert outcome.side_effect_state is SideEffectState.NOT_ATTEMPTED
    assert tool.body_invocations == 0
    assert tool.effect_marker is False


def test_circular_arguments_are_normalized_before_tool_body():
    registry = ToolRegistry()
    tool = _ExplicitTool(ToolResult.success("must not run"))
    registry.register(tool)
    arguments = {}
    arguments["self"] = arguments

    outcome = _run(registry.execute_outcome("explicit", arguments))

    assert outcome.state is ExecutionState.FAILED
    assert outcome.error_category is ErrorCategory.VALIDATION
    assert outcome.side_effect_state is SideEffectState.NOT_ATTEMPTED
    assert tool.body_invocations == 0
    assert tool.effect_marker is False
