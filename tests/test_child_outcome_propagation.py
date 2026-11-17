"""PR4 child Tool attempt and parent bridge regression coverage."""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.modules.agent.subagent import SubagentManager, SubagentTask, TaskStatus
from backend.modules.agent.task_manager import CancellationToken
from backend.modules.agent.workflow import WorkflowEngine
from backend.modules.providers.base import StreamChunk, ToolCall
from backend.modules.tools.base import Tool
from backend.modules.tools.execution import (
    ErrorCategory, ExecutionState, SideEffectState, ToolExecutionOutcome, ToolResult,
)
from backend.modules.tools.registry import ToolRegistry
from backend.modules.tools.spawn import SpawnTool
from backend.modules.tools.workflow_tool import WorkflowTool


class _Provider:
    def __init__(self, tool_calls=1):
        self.calls = 0
        self.tool_calls = tool_calls

    async def chat_stream(self, **kwargs):
        self.calls += 1
        if self.calls <= self.tool_calls:
            yield StreamChunk(tool_call=ToolCall(
                id=f"call-{self.calls}", name="probe", arguments={},
            ))
        else:
            yield StreamChunk(content="human-readable child answer")


class _Probe(Tool):
    name = "probe"
    description = "PR4 probe"
    parameters = {"type": "object", "properties": {}}

    def __init__(self, results=None, block=False):
        self.results = iter(results or [ToolResult.success("done")])
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.block = block
        self.invocations = 0

    async def execute(self, **kwargs):
        raise AssertionError("child must use execute_outcome")

    async def execute_outcome(self, **kwargs):
        self.invocations += 1
        self.entered.set()
        if self.block:
            await self.release.wait()
        return next(self.results)


def _install_probe(monkeypatch, probe):
    import backend.modules.tools.registry as registry_module
    original = ToolRegistry

    def factory():
        registry = original()
        registry.register(probe)
        return registry

    monkeypatch.setattr(registry_module, "ToolRegistry", factory)


async def _run_child(tmp_path, monkeypatch, probe, *, provider=None, token=None,
                     timeout=360, task_timeout=10, handler=None):
    _install_probe(monkeypatch, probe)
    config = SimpleNamespace(config=SimpleNamespace(
        security=SimpleNamespace(command_timeout=timeout, subagent_timeout=task_timeout),
        model=SimpleNamespace(max_iterations=4, model="test", temperature=0,
                              max_tokens=100, thinking_enabled=False),
    ))
    manager = SubagentManager(provider or _Provider(), tmp_path, "test", config_loader=config)
    task_id = manager.create_task("test", "do work", cancel_token=token)
    manager.tasks[task_id].notification_handler = handler
    await manager.execute_task(task_id)
    return manager, manager.tasks[task_id]


@pytest.mark.asyncio
async def test_child_failed_attempt_remains_non_success_across_spawn(tmp_path, monkeypatch):
    probe = _Probe([ToolResult.failure(ErrorCategory.EXECUTION, "display failure")])
    manager, task = await _run_child(tmp_path, monkeypatch, probe)
    await asyncio.wait_for(task.done_event.wait(), 2)

    assert task.status is TaskStatus.COMPLETED
    assert task.outcome.state is ExecutionState.FAILED
    assert task.tool_outcomes[0].state is ExecutionState.FAILED
    assert task.tool_call_records[0]["state"] == "FAILED"
    assert task.tool_call_records[0]["operation_id"] == task.tool_outcomes[0].operation_id
    assert task.tool_call_records[0]["attempt_id"] == task.tool_outcomes[0].attempt_id
    assert "display failure" in task.tool_call_records[0]["result"]

    class ExistingManager:
        tasks = {task.task_id: task}

        def create_task(self, **kwargs):
            return task.task_id

        async def execute_task(self, task_id):
            pass

    spawn = SpawnTool(ExistingManager())
    result = await spawn.execute_outcome(task="do work")
    assert result.state is ExecutionState.FAILED
    assert "display failure" in result.display_text


@pytest.mark.asyncio
async def test_failed_child_notifies_failure_from_structured_disposition(tmp_path, monkeypatch):
    class Handler:
        def __init__(self):
            self.completed = []
            self.failed = []

        async def notify_status(self, *args):
            pass

        async def notify_tool_call(self, *args, **kwargs):
            pass

        async def notify_tool_result(self, *args, **kwargs):
            pass

        async def notify_complete(self, text):
            self.completed.append(text)

        async def notify_failed(self, text):
            self.failed.append(text)

    handler = Handler()
    probe = _Probe([ToolResult.failure(ErrorCategory.EXECUTION, "display failure")])
    manager, task = await _run_child(tmp_path, monkeypatch, probe, handler=handler)
    await asyncio.wait_for(task.done_event.wait(), 2)
    assert handler.completed == []
    assert handler.failed == ["display failure"]


@pytest.mark.asyncio
async def test_later_success_does_not_erase_failed_child_attempt(tmp_path, monkeypatch):
    probe = _Probe([
        ToolResult.failure(ErrorCategory.EXECUTION, "first failed"),
        ToolResult.success("recovered"),
    ])
    manager, task = await _run_child(tmp_path, monkeypatch, probe, provider=_Provider(2))
    await asyncio.wait_for(task.done_event.wait(), 2)
    assert [item.state for item in task.tool_outcomes] == [
        ExecutionState.FAILED, ExecutionState.SUCCEEDED,
    ]
    assert task.outcome.state is ExecutionState.FAILED
    assert task.status is TaskStatus.COMPLETED
    parent = await SpawnTool(_FakeManager(task)).execute_outcome(task="task")
    assert parent.state is ExecutionState.FAILED
    workflow = await WorkflowTool(_FakeManager(task)).execute_outcome(
        mode="pipeline", goal="goal", agents=[{"id": "one", "task": "do"}],
    )
    assert workflow.state is ExecutionState.FAILED
    assert task.result == "human-readable child answer"


@pytest.mark.asyncio
async def test_effect_started_timeout_preserves_unknown_outcome(tmp_path, monkeypatch):
    probe = _Probe(block=True)
    manager, task = await _run_child(tmp_path, monkeypatch, probe, timeout=0.05)
    await asyncio.wait_for(probe.entered.wait(), 2)
    await asyncio.wait_for(task.done_event.wait(), 2)
    assert probe.invocations == 1
    assert task.tool_outcomes[0].state is ExecutionState.UNKNOWN_OUTCOME
    assert task.outcome.state is ExecutionState.UNKNOWN_OUTCOME
    assert task.outcome.error_category is ErrorCategory.TIMEOUT
    assert task.outcome.side_effect_state is SideEffectState.UNKNOWN
    assert task.tool_call_records[0]["projection_error_category"] == "TIMEOUT"
    parent = await SpawnTool(_FakeManager(task)).execute_outcome(task="task")
    assert parent.state is ExecutionState.UNKNOWN_OUTCOME
    assert parent.error_category is ErrorCategory.TIMEOUT
    assert parent.side_effect_state is SideEffectState.UNKNOWN


@pytest.mark.asyncio
async def test_cancellation_before_and_during_child_execution(tmp_path, monkeypatch):
    before = CancellationToken()
    before.cancel()
    probe = _Probe()
    manager, task = await _run_child(tmp_path, monkeypatch, probe, token=before)
    await asyncio.wait_for(task.done_event.wait(), 2)
    assert probe.invocations == 0
    assert task.outcome.state is ExecutionState.CANCELLED
    assert task.outcome.side_effect_state is SideEffectState.NOT_ATTEMPTED

    during = CancellationToken()
    blocking = _Probe(block=True)
    manager, task = await _run_child(tmp_path, monkeypatch, blocking, token=during)
    await asyncio.wait_for(blocking.entered.wait(), 2)
    assert await manager.cancel_task(task.task_id)
    await asyncio.wait_for(task.done_event.wait(), 2)
    assert task.outcome.state is ExecutionState.UNKNOWN_OUTCOME
    assert task.outcome.side_effect_state is SideEffectState.UNKNOWN
    parent = await SpawnTool(_FakeManager(task)).execute_outcome(task="task")
    assert parent.state is ExecutionState.UNKNOWN_OUTCOME
    assert parent.side_effect_state is SideEffectState.UNKNOWN


@pytest.mark.asyncio
async def test_cancellation_after_tool_completion_keeps_prior_attempt(tmp_path, monkeypatch):
    class WaitingProvider(_Provider):
        def __init__(self):
            super().__init__()
            self.waiting = asyncio.Event()
            self.release = asyncio.Event()

        async def chat_stream(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                yield StreamChunk(tool_call=ToolCall(
                    id="call-1", name="probe", arguments={},
                ))
            else:
                self.waiting.set()
                await self.release.wait()
                yield StreamChunk(content="never reached")

    provider = WaitingProvider()
    token = CancellationToken()
    manager, task = await _run_child(
        tmp_path, monkeypatch, _Probe(), provider=provider, token=token,
    )
    await asyncio.wait_for(provider.waiting.wait(), 2)
    assert await manager.cancel_task(task.task_id)
    await asyncio.wait_for(task.done_event.wait(), 2)
    assert task.tool_outcomes[0].state is ExecutionState.SUCCEEDED
    assert task.outcome.state is ExecutionState.UNKNOWN_OUTCOME
    assert task.outcome.side_effect_state is SideEffectState.UNKNOWN


@pytest.mark.asyncio
async def test_whole_child_deadline_projects_timeout_after_tool_effect(tmp_path, monkeypatch):
    class WaitingProvider(_Provider):
        def __init__(self):
            super().__init__()
            self.waiting = asyncio.Event()

        async def chat_stream(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                yield StreamChunk(tool_call=ToolCall(
                    id="call-1", name="probe", arguments={},
                ))
            else:
                self.waiting.set()
                await asyncio.Event().wait()

    provider = WaitingProvider()
    manager, task = await _run_child(
        tmp_path, monkeypatch, _Probe(), provider=provider, task_timeout=0.05,
    )
    await asyncio.wait_for(provider.waiting.wait(), 2)
    await asyncio.wait_for(task.done_event.wait(), 2)
    assert task.tool_outcomes[0].state is ExecutionState.SUCCEEDED
    assert task.outcome.state is ExecutionState.UNKNOWN_OUTCOME
    assert task.outcome.error_category is ErrorCategory.TIMEOUT
    assert task.outcome.side_effect_state is SideEffectState.UNKNOWN
    parent = await SpawnTool(_FakeManager(task)).execute_outcome(task="task")
    assert parent.state is ExecutionState.UNKNOWN_OUTCOME
    assert parent.error_category is ErrorCategory.TIMEOUT


def _child_task(result):
    child = SubagentTask("child-id", "child", "task")
    child.outcome = result
    succeeded = result.state is ExecutionState.SUCCEEDED
    child.status = (
        TaskStatus.COMPLETED if succeeded else
        TaskStatus.CANCELLED if result.state is ExecutionState.CANCELLED else
        TaskStatus.FAILED
    )
    child.result = "child text" if succeeded else None
    child.error = None if succeeded else result.display_text
    child.done_event.set()
    return child


class _FakeManager:
    def __init__(self, child):
        self.child = child
        self.tasks = {child.task_id: child}
        self.running_tasks = {}

    def create_task(self, **kwargs):
        self.child.event_callback = kwargs.get("event_callback")
        return self.child.task_id

    async def execute_task(self, task_id):
        pass

    def get_task(self, task_id):
        return self.child


@pytest.mark.asyncio
@pytest.mark.parametrize("result", [
    ToolResult.failure(ErrorCategory.EXECUTION, "failed"),
    ToolResult.cancelled("cancelled"),
    ToolResult.unknown_outcome(ErrorCategory.TIMEOUT, "uncertain"),
])
async def test_spawn_maps_all_child_non_success_states(result):
    manager = _FakeManager(_child_task(result))
    spawn = SpawnTool(manager)
    parent = await spawn.execute_outcome(task="task")
    assert parent.state is result.state
    assert parent.side_effect_state is result.side_effect_state
    assert parent.error_category is result.error_category

    registry = ToolRegistry()
    registry.register(spawn)
    parent_attempt = await registry.execute_outcome("spawn", {"task": "task"})
    assert parent_attempt.state is result.state
    assert parent_attempt.side_effect_state is result.side_effect_state
    assert parent_attempt.attempt_id != "child-id"


@pytest.mark.asyncio
async def test_spawn_wait_timeout_does_not_finalize_child():
    child = _child_task(ToolResult.success("done"))
    child.status = TaskStatus.RUNNING
    child.outcome = None
    child.done_event.clear()
    manager = _FakeManager(child)
    spawn = SpawnTool(manager)
    spawn._get_timeout = lambda: 0.01
    result = await spawn.execute_outcome(task="task")
    assert result.state is ExecutionState.UNKNOWN_OUTCOME
    assert child.outcome is None
    assert child.status is TaskStatus.RUNNING


def _tool_attempt(result):
    return ToolExecutionOutcome(
        operation_id="operation", attempt_id="attempt", attempt_ordinal=1,
        tool_name="probe", state=result.state, display_text=result.display_text,
        duration_ms=1, output=result.output, error_category=result.error_category,
        retryable=result.retryable, retry_safety=result.retry_safety,
        side_effect_state=result.side_effect_state,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("child_result", [
    ToolResult.failure(ErrorCategory.EXECUTION, "nested failure"),
    ToolResult.cancelled("nested cancellation"),
    ToolResult.unknown_outcome(ErrorCategory.TIMEOUT, "nested uncertainty"),
])
async def test_workflow_nested_non_success_and_event_use_structured_state(child_result):
    child = _child_task(child_result)
    events = []

    async def capture(name, data):
        events.append((name, data))

    manager = _FakeManager(child)
    engine = WorkflowEngine(manager, event_callback=capture)

    async def execute_with_event(task_id):
        await child.event_callback("tool_call", "probe", {})
        await child.event_callback("tool_result", "probe", _tool_attempt(child_result))

    manager.execute_task = execute_with_event
    result = await engine.run_outcome("graph", "goal", [{"id": "one", "task": "do"}])
    expected_status = child_result.state.value.lower()
    assert result.state is child_result.state
    assert result.error_category is child_result.error_category
    assert result.side_effect_state is child_result.side_effect_state
    assert engine._execution_data["one"]["toolCalls"][0]["status"] == expected_status
    projected = [data for name, data in events if name == "workflow_agent_tool_result"]
    assert projected[0]["state"] == child_result.state.value
    assert projected[0]["status"] == expected_status
    assert projected[0]["error_category"] == child_result.error_category.value
    assert projected[0]["side_effect_state"] == child_result.side_effect_state.value
    assert projected[0]["operation_id"] == "operation"
    assert not any(name == "workflow_agent_complete" for name, _ in events)
    failed_events = [data for name, data in events if name == "workflow_agent_failed"]
    assert failed_events[0]["state"] == child_result.state.value
    assert failed_events[0]["status"] == expected_status
    assert failed_events[0]["side_effect_state"] == child_result.side_effect_state.value

    tool = WorkflowTool(manager)
    parent = await tool.execute_outcome(mode="graph", goal="goal",
                                        agents=[{"id": "one", "task": "do"}])
    assert parent.state is child_result.state
    assert parent.error_category is child_result.error_category
    assert parent.side_effect_state is child_result.side_effect_state

    registry = ToolRegistry()
    registry.register(tool)
    parent_attempt = await registry.execute_outcome(
        "workflow_run", {"mode": "graph", "goal": "goal",
                         "agents": [{"id": "one", "task": "do"}]}
    )
    assert parent_attempt.state is child_result.state
    assert parent_attempt.error_category is child_result.error_category
    assert parent_attempt.side_effect_state is child_result.side_effect_state


@pytest.mark.asyncio
async def test_successful_child_keeps_human_readable_spawn_and_workflow_output():
    manager = _FakeManager(_child_task(ToolResult.success("child text")))
    spawn = SpawnTool(manager)
    result = await spawn.execute_outcome(task="task", label="label")
    assert result.state is ExecutionState.SUCCEEDED
    assert result.display_text == "子 Agent [label] 已完成 (ID: child-id)。\n\nchild text"

    tool = WorkflowTool(manager)
    result = await tool.execute_outcome(mode="pipeline", goal="goal",
                                        agents=[{"id": "one", "task": "do"}])
    assert result.state is ExecutionState.SUCCEEDED
    assert "# Pipeline Workflow Results" in result.display_text
    assert "child text" in result.display_text
