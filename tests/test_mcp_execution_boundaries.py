"""Deterministic PR3 coverage for MCP physical-execution boundaries."""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.modules.mcp.client import (
    MCPPromptWrapper,
    MCPResourceWrapper,
    MCPToolWrapper,
)
from backend.modules.tools.execution import (
    ErrorCategory,
    ExecutionState,
    RetrySafety,
    SideEffectState,
)
from backend.modules.tools.registry import ToolRegistry


class EndOfStream(Exception):
    pass


class _ToolSession:
    def __init__(self, actions):
        self.actions = iter(actions)
        self.calls = 0

    async def call_tool(self, name, arguments):
        self.calls += 1
        action = next(self.actions)
        if isinstance(action, BaseException):
            raise action
        return action


class _ReadSession:
    def __init__(self, actions):
        self.actions = iter(actions)
        self.calls = 0

    async def _next(self):
        self.calls += 1
        action = next(self.actions)
        if isinstance(action, BaseException):
            raise action
        return action

    async def read_resource(self, uri):
        return await self._next()

    async def get_prompt(self, name, arguments):
        return await self._next()


class _BlockingReadSession:
    def __init__(self):
        self.calls = 0
        self.dispatched = asyncio.Event()
        self.release = asyncio.Event()

    async def _block(self):
        self.calls += 1
        self.dispatched.set()
        await self.release.wait()

    async def read_resource(self, uri):
        return await self._block()

    async def get_prompt(self, name, arguments):
        return await self._block()


def _tool_wrapper(session):
    definition = SimpleNamespace(
        name="mutate",
        description="remote mutation",
        inputSchema={"type": "object", "properties": {}},
    )
    return MCPToolWrapper(session, "fake", definition, tool_timeout=30)


def _resource_wrapper(session):
    definition = SimpleNamespace(
        name="document",
        description="remote document",
        uri="fake://document",
    )
    return MCPResourceWrapper(session, "fake", definition, resource_timeout=30)


def _prompt_wrapper(session):
    definition = SimpleNamespace(
        name="template",
        description="remote template",
        arguments=[],
    )
    return MCPPromptWrapper(session, "fake", definition, prompt_timeout=30)


def _execute(tool, *, operation_id=None, retry_authorized=False):
    registry = ToolRegistry()
    registry.register(tool)
    return asyncio.run(
        registry.execute_outcome(
            tool.name,
            {},
            operation_id=operation_id,
            retry_authorized=retry_authorized,
        )
    )


@pytest.mark.parametrize(
    ("failure", "category"),
    [
        (ConnectionResetError("connection lost"), ErrorCategory.DEPENDENCY),
        (asyncio.TimeoutError(), ErrorCategory.TIMEOUT),
        (asyncio.CancelledError(), ErrorCategory.CANCELLATION),
        (EndOfStream("response stream lost"), ErrorCategory.DEPENDENCY),
    ],
)
def test_unsafe_mcp_failures_never_hide_a_second_remote_invocation(failure, category):
    session = _ToolSession([failure])

    outcome = _execute(_tool_wrapper(session))

    assert session.calls == 1
    assert outcome.attempt_ordinal == 1
    assert outcome.state is ExecutionState.UNKNOWN_OUTCOME
    assert outcome.error_category is category
    assert outcome.retry_safety is RetrySafety.UNKNOWN
    assert outcome.side_effect_state is SideEffectState.UNKNOWN


def test_real_task_cancellation_after_dispatch_keeps_uncertainty_and_one_call():
    class BlockingSession:
        def __init__(self):
            self.calls = 0
            self.dispatched = asyncio.Event()

        async def call_tool(self, name, arguments):
            self.calls += 1
            self.dispatched.set()
            await asyncio.Event().wait()

    async def scenario():
        session = BlockingSession()
        wrapper = _tool_wrapper(session)
        registry = ToolRegistry()
        registry.register(wrapper)
        task = asyncio.create_task(registry.execute_outcome(wrapper.name, {}))
        await session.dispatched.wait()
        task.cancel()
        outcome = await task
        return session, outcome

    session, outcome = asyncio.run(scenario())

    assert session.calls == 1
    assert outcome.state is ExecutionState.UNKNOWN_OUTCOME
    assert outcome.error_category is ErrorCategory.CANCELLATION
    assert outcome.side_effect_state is SideEffectState.UNKNOWN


@pytest.mark.parametrize("wrapper_factory", [_resource_wrapper, _prompt_wrapper])
def test_safe_read_internal_cancellation_is_cancelled_not_failed(wrapper_factory):
    session = _ReadSession([asyncio.CancelledError()])

    outcome = _execute(wrapper_factory(session))

    assert session.calls == 1
    assert outcome.state is ExecutionState.CANCELLED
    assert outcome.error_category is ErrorCategory.CANCELLATION
    assert outcome.retry_safety is RetrySafety.SAFE
    assert outcome.side_effect_state is SideEffectState.NOT_APPLICABLE


@pytest.mark.parametrize("wrapper_factory", [_resource_wrapper, _prompt_wrapper])
def test_safe_read_real_task_cancellation_is_cancelled_not_unknown(wrapper_factory):
    async def scenario():
        session = _BlockingReadSession()
        wrapper = wrapper_factory(session)
        registry = ToolRegistry()
        registry.register(wrapper)
        task = asyncio.create_task(registry.execute_outcome(wrapper.name, {}))
        await session.dispatched.wait()
        task.cancel()
        outcome = await task
        return session, outcome

    session, outcome = asyncio.run(scenario())

    assert session.calls == 1
    assert outcome.state is ExecutionState.CANCELLED
    assert outcome.error_category is ErrorCategory.CANCELLATION
    assert outcome.retry_safety is RetrySafety.SAFE
    assert outcome.side_effect_state is SideEffectState.NOT_APPLICABLE


def test_unknown_unsafe_mcp_attempt_cannot_be_reexecuted_by_retry_flag_alone():
    async def scenario():
        session = _ToolSession([ConnectionResetError("response lost")])
        wrapper = _tool_wrapper(session)
        registry = ToolRegistry()
        registry.register(wrapper)
        first = await registry.execute_outcome(
            wrapper.name,
            {},
            operation_id="unsafe-operation",
        )
        blocked = await registry.execute_outcome(
            wrapper.name,
            {},
            operation_id="unsafe-operation",
            retry_authorized=True,
        )
        return session, first, blocked

    session, first, blocked = asyncio.run(scenario())

    assert session.calls == 1
    assert blocked == first
    assert first.state is ExecutionState.UNKNOWN_OUTCOME
    assert first.retry_safety is RetrySafety.UNKNOWN


@pytest.mark.parametrize(
    ("wrapper_factory", "success_result"),
    [
        (
            _resource_wrapper,
            SimpleNamespace(contents=[SimpleNamespace(text="resource body")]),
        ),
        (
            _prompt_wrapper,
            SimpleNamespace(
                messages=[SimpleNamespace(content=SimpleNamespace(text="prompt body"))]
            ),
        ),
    ],
)
def test_safe_read_reexecution_uses_two_canonical_attempts(
    wrapper_factory,
    success_result,
):
    async def scenario():
        session = _ReadSession(
            [ConnectionResetError("first call lost"), success_result]
        )
        wrapper = wrapper_factory(session)
        registry = ToolRegistry()
        registry.register(wrapper)
        first = await registry.execute_outcome(
            wrapper.name,
            {},
            operation_id="safe-read-operation",
        )
        second = await registry.execute_outcome(
            wrapper.name,
            {},
            operation_id="safe-read-operation",
            retry_authorized=True,
        )
        return session, first, second

    session, first, second = asyncio.run(scenario())

    assert session.calls == 2
    assert first.state is ExecutionState.FAILED
    assert first.retry_safety is RetrySafety.SAFE
    assert first.side_effect_state is SideEffectState.NOT_APPLICABLE
    assert second.state is ExecutionState.SUCCEEDED
    assert first.operation_id == second.operation_id == "safe-read-operation"
    assert first.attempt_id != second.attempt_id
    assert (first.attempt_ordinal, second.attempt_ordinal) == (1, 2)


def test_mcp_error_and_malformed_result_are_not_false_successes():
    remote_error = SimpleNamespace(
        content=[SimpleNamespace(text="remote rejected the call")],
        isError=True,
    )
    error_outcome = _execute(_tool_wrapper(_ToolSession([remote_error])))
    malformed_outcome = _execute(_tool_wrapper(_ToolSession([SimpleNamespace()])))

    assert error_outcome.state is ExecutionState.UNKNOWN_OUTCOME
    assert error_outcome.error_category is ErrorCategory.EXECUTION
    assert malformed_outcome.state is ExecutionState.UNKNOWN_OUTCOME
    assert malformed_outcome.error_category is ErrorCategory.RESULT_CONTRACT
