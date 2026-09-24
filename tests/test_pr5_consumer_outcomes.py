"""PR5 canonical consumer and fixed retry regression coverage."""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.modules.agent.loop import AgentLoop
from backend.modules.agent.subagent import SubagentTask, TaskStatus
from backend.modules.providers.base import StreamChunk, ToolCall
from backend.modules.tools.base import Tool
from backend.modules.tools.execution import (
    ErrorCategory,
    ExecutionState,
    RetrySafety,
    ToolExecutionInProgress,
    ToolResult,
)
from backend.modules.tools.registry import ToolRegistry
from backend.modules.tools.spawn import SpawnTool


class Probe(Tool):
    name = "probe"
    description = "PR5 probe"
    parameters = {"type": "object", "properties": {}}

    def __init__(self, *results):
        self.results = iter(results)
        self.calls = 0

    async def execute(self, **kwargs):
        raise AssertionError("legacy execution is forbidden")

    async def execute_outcome(self, **kwargs):
        self.calls += 1
        return next(self.results)


class Provider:
    def __init__(self, tool_name="probe", arguments=None):
        self.messages = []
        self.calls = 0
        self.tool_name = tool_name
        self.arguments = arguments or {}

    async def chat_stream(self, **kwargs):
        self.messages.append(kwargs["messages"])
        self.calls += 1
        if self.calls == 1:
            yield StreamChunk(tool_call=ToolCall(
                "llm-call-1", self.tool_name, self.arguments,
            ))
        else:
            yield StreamChunk(content="done")


class History:
    def __init__(self):
        self.records = []

    def add_conversation(self, **kwargs):
        self.records.append(kwargs)


async def run_agent(monkeypatch, tool, *, retries=3, registry=None, provider=None,
                    timeout=5):
    import backend.modules.agent.loop as loop_module
    import backend.ws.tool_notifications as notifications

    history = History()
    notices = []
    events = []

    async def notify(**kwargs):
        notices.append(kwargs)

    monkeypatch.setattr(loop_module, "get_conversation_history", lambda: history)
    monkeypatch.setattr(notifications, "notify_tool_execution", notify)
    if registry is None:
        registry = ToolRegistry()
    if tool is not None:
        registry.register(tool)
    provider = provider or Provider()
    agent = AgentLoop(provider, Path("/private/tmp"), registry, max_iterations=4,
                      max_retries=retries, retry_delay=0)
    agent._resolve_tool_timeout_seconds = lambda: timeout
    chunks = [
        chunk async for chunk in agent.process_message(
            "run", "session", tool_event_handler=lambda kind, value: events.append((kind, value)),
        )
    ]
    return SimpleNamespace(
        agent=agent, provider=provider, registry=registry, history=history,
        notices=notices, events=events, chunks=chunks,
    )


@pytest.mark.asyncio
async def test_agent_success_uses_canonical_success(monkeypatch):
    result = await run_agent(monkeypatch, Probe(ToolResult.success("finished")))
    assert result.history.records[0]["result"] == "finished"
    assert any(kind == "tool_result" for kind, _ in result.events)
    assert result.provider.messages[1][-1]["content"] == "finished"
    assert result.registry._operation_ledger.attempts_for_operation(
        next(iter(result.registry._operation_ledger._operation_attempt_ids))
    )[0].state is ExecutionState.SUCCEEDED


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_result,state", [
    (ToolResult.failure(ErrorCategory.EXECUTION, "nonempty failure"), ExecutionState.FAILED),
    (ToolResult.cancelled("cancelled"), ExecutionState.CANCELLED),
    (ToolResult.unknown_outcome(
        ErrorCategory.TIMEOUT, "timed out", retryable=True,
        retry_safety=RetrySafety.UNSAFE,
    ), ExecutionState.UNKNOWN_OUTCOME),
])
async def test_agent_normal_return_non_success_never_enters_success(
    monkeypatch, tool_result, state,
):
    probe = Probe(tool_result)
    result = await run_agent(monkeypatch, probe)
    assert probe.calls == 1
    assert result.history.records[0].get("result") is None
    assert result.history.records[0]["error"]
    assert not any(kind == "tool_result" for kind, _ in result.events)
    assert any(kind == "tool_error" for kind, _ in result.events)
    assert not any("result" in notice for notice in result.notices)
    if state is ExecutionState.UNKNOWN_OUTCOME:
        assert "side effects may have occurred" in result.provider.messages[1][-1]["content"]


@pytest.mark.asyncio
async def test_agent_retry_reuses_operation_and_creates_new_attempt(monkeypatch):
    probe = Probe(
        ToolResult.failure(
            ErrorCategory.DEPENDENCY, "safe transient", retryable=True,
            retry_safety=RetrySafety.SAFE,
        ),
        ToolResult.success("recovered"),
    )
    registry = ToolRegistry()
    calls = []
    original = registry.execute_outcome

    async def record(*args, **kwargs):
        outcome = await original(*args, **kwargs)
        calls.append((kwargs, outcome))
        return outcome

    monkeypatch.setattr(registry, "execute_outcome", record)
    result = await run_agent(monkeypatch, probe, registry=registry)
    assert probe.calls == 2
    assert len(calls) == 2
    first, second = (entry[1] for entry in calls)
    assert first.state is ExecutionState.FAILED
    assert second.state is ExecutionState.SUCCEEDED
    assert first.operation_id == second.operation_id
    assert first.operation_id != "llm-call-1"
    assert first.attempt_id != second.attempt_id
    assert first.correlation_id == second.correlation_id == "llm-call-1"
    assert calls[0][0]["retry_authorized"] is False
    assert calls[1][0]["retry_authorized"] is True
    assert [attempt.state for attempt in registry._operation_ledger.attempts_for_operation(
        first.operation_id
    )] == [ExecutionState.FAILED, ExecutionState.SUCCEEDED]
    assert result.history.records[0]["result"] == "recovered"


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary_error", [
    RuntimeError("second boundary unavailable"),
    asyncio.TimeoutError(),
])
async def test_retry_boundary_error_does_not_reuse_previous_attempt(
    monkeypatch, boundary_error,
):
    probe = Probe(ToolResult.failure(
        ErrorCategory.DEPENDENCY, "first safe failure",
        retryable=True, retry_safety=RetrySafety.SAFE,
    ))
    registry = ToolRegistry()
    boundary_calls = []
    original = registry.execute_outcome

    async def fail_second(*args, **kwargs):
        boundary_calls.append(kwargs)
        if len(boundary_calls) == 2:
            raise boundary_error
        return await original(*args, **kwargs)

    monkeypatch.setattr(registry, "execute_outcome", fail_second)
    result = await run_agent(monkeypatch, probe, registry=registry)

    assert len(boundary_calls) == 2  # 边界异常不能触发第三次尝试
    assert probe.calls == 1
    first = registry._operation_ledger.attempts_for_operation(
        boundary_calls[0]["operation_id"]
    )[0]
    assert first.state is ExecutionState.FAILED
    assert boundary_calls[1]["operation_id"] == first.operation_id
    assert result.history.records[0].get("result") is None
    current_error = result.history.records[0]["error"]
    assert "first safe failure" not in current_error
    assert (
        "second boundary unavailable" in current_error
        if isinstance(boundary_error, RuntimeError)
        else "timed out" in current_error
    )
    event = next(value for kind, value in result.events if kind == "tool_error")
    assert event["error"] == current_error
    assert event["execution_state"] is None
    assert event["attempt_id"] is None
    assert event["operation_id"] == first.operation_id
    assert not any(kind == "tool_result" for kind, _ in result.events)
    assert not any("result" in notice for notice in result.notices)
    assert current_error in result.provider.messages[1][-1]["content"]


@pytest.mark.asyncio
@pytest.mark.parametrize("safety", [RetrySafety.UNSAFE, RetrySafety.UNKNOWN])
async def test_unknown_outcome_never_auto_reexecutes(monkeypatch, safety):
    probe = Probe(ToolResult.unknown_outcome(
        ErrorCategory.TIMEOUT, "uncertain", retryable=True, retry_safety=safety,
    ))
    result = await run_agent(monkeypatch, probe)
    assert probe.calls == 1
    assert result.history.records[0].get("result") is None


@pytest.mark.asyncio
async def test_agent_malformed_raw_return_remains_unknown(monkeypatch):
    class Legacy(Probe):
        async def execute_outcome(self, **kwargs):
            self.calls += 1
            return "Error: this text has no authoritative state"

    probe = Legacy()
    result = await run_agent(monkeypatch, probe)
    assert probe.calls == 1
    assert result.history.records[0].get("result") is None
    assert any(kind == "tool_error" for kind, _ in result.events)
    assert "side effects may have occurred" in result.provider.messages[1][-1]["content"]


@pytest.mark.asyncio
async def test_agent_outer_timeout_preserves_canonical_unknown(monkeypatch):
    class Blocking(Probe):
        async def execute_outcome(self, **kwargs):
            self.calls += 1
            await asyncio.Event().wait()

    probe = Blocking()
    result = await run_agent(monkeypatch, probe, timeout=0.01)
    assert probe.calls == 1
    assert result.history.records[0].get("result") is None
    assert "side effects may have occurred" in result.provider.messages[1][-1]["content"]
    attempts = list(result.registry._operation_ledger._operation_attempt_ids)
    assert len(attempts) == 1
    assert result.registry._operation_ledger.attempts_for_operation(
        attempts[0]
    )[0].state is ExecutionState.UNKNOWN_OUTCOME


@pytest.mark.asyncio
@pytest.mark.parametrize("child_result", [
    ToolResult.failure(ErrorCategory.EXECUTION, "child failed"),
    ToolResult.cancelled("child cancelled"),
    ToolResult.unknown_outcome(ErrorCategory.TIMEOUT, "child uncertain"),
])
async def test_pr4_spawn_bridge_remains_non_success_for_agent_and_api(
    monkeypatch, child_result,
):
    import backend.api.tools as api

    child = SubagentTask("child-id", "child", "task")
    child.outcome = child_result
    child.status = (
        TaskStatus.CANCELLED
        if child_result.state is ExecutionState.CANCELLED else TaskStatus.FAILED
    )
    child.error = child_result.display_text
    child.done_event.set()

    class Manager:
        tasks = {child.task_id: child}
        running_tasks = {}

        def create_task(self, **kwargs):
            return child.task_id

        async def execute_task(self, task_id):
            pass

        def get_task(self, task_id):
            return child

    spawn = SpawnTool(Manager())
    result = await run_agent(
        monkeypatch, spawn,
        provider=Provider("spawn", {"task": "task"}),
    )
    assert result.history.records[0].get("result") is None
    assert any(kind == "tool_error" for kind, _ in result.events)
    assert not any("result" in notice for notice in result.notices)

    direct_registry = ToolRegistry()
    direct_registry.register(SpawnTool(Manager()))
    monkeypatch.setattr(api, "get_tool_registry", lambda: direct_registry)
    response = await api.execute_tool(api.ExecuteToolRequest(
        tool="spawn", arguments={"task": "task"},
    ))
    assert response.success is False
    assert response.result == ""


@pytest.mark.asyncio
async def test_registry_overlap_admission_preserves_running_attempt():
    class Blocking(Probe):
        def __init__(self):
            super().__init__(ToolResult.success("done"))
            self.entered = asyncio.Event()
            self.release = asyncio.Event()

        async def execute_outcome(self, **kwargs):
            self.calls += 1
            self.entered.set()
            await self.release.wait()
            return ToolResult.success("done")

    probe = Blocking()
    registry = ToolRegistry()
    registry.register(probe)
    first_task = asyncio.create_task(
        registry.execute_outcome("probe", {}, operation_id="same-operation")
    )
    await probe.entered.wait()
    admission = await registry.execute_outcome("probe", {}, operation_id="same-operation")
    assert isinstance(admission, ToolExecutionInProgress)
    assert probe.calls == 1
    assert len(registry._operation_ledger.attempts_for_operation("same-operation")) == 1
    assert registry._operation_ledger.attempts_for_operation("same-operation")[0].state is ExecutionState.RUNNING
    probe.release.set()
    first = await first_task
    assert first.attempt_id == admission.active_attempt_id
    assert first.state is ExecutionState.SUCCEEDED


@pytest.mark.asyncio
async def test_agent_in_progress_is_not_a_physical_terminal_result(monkeypatch):
    import backend.modules.agent.loop as loop_module
    import backend.ws.tool_notifications as notifications

    history = History()
    notices = []

    async def notify(**kwargs):
        notices.append(kwargs)

    monkeypatch.setattr(loop_module, "get_conversation_history", lambda: history)
    monkeypatch.setattr(notifications, "notify_tool_execution", notify)
    provider = Provider()
    agent = AgentLoop(provider, Path("/private/tmp"), ToolRegistry(), max_iterations=4)
    agent._resolve_tool_timeout_seconds = lambda: 5
    calls = []

    async def admission(*args, **kwargs):
        calls.append(kwargs)
        return ToolExecutionInProgress(
            operation_id=kwargs["operation_id"], active_attempt_id="active",
            tool_name="probe", correlation_id=kwargs["correlation_id"],
            display_text="Still running",
        )

    monkeypatch.setattr(agent, "execute_tool", admission)
    events = []
    async for _ in agent.process_message(
        "run", "session", tool_event_handler=lambda kind, value: events.append(kind),
    ):
        pass
    assert len(calls) == 1
    assert history.records == []
    assert events == ["tool_call"]
    assert not any("result" in item or "error" in item for item in notices)
    assert provider.messages[1][-1]["content"] == "Still running"


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_result,expected", [
    (ToolResult.success("ok"), True),
    (ToolResult.failure(ErrorCategory.EXECUTION, "failed"), False),
    (ToolResult.cancelled(), False),
    (ToolResult.unknown_outcome(ErrorCategory.TIMEOUT, "uncertain"), False),
])
async def test_direct_api_maps_canonical_state_without_schema_change(
    monkeypatch, tool_result, expected,
):
    import backend.api.tools as api
    registry = ToolRegistry()
    registry.register(Probe(tool_result))
    monkeypatch.setattr(api, "get_tool_registry", lambda: registry)
    response = await api.execute_tool(api.ExecuteToolRequest(tool="probe", arguments={}))
    assert set(response.model_dump()) == {"success", "result", "error"}
    assert response.success is expected
    assert response.result == ("ok" if expected else "")
    assert (response.error is None) is expected
    if tool_result.state is ExecutionState.UNKNOWN_OUTCOME:
        assert "side effects may have occurred" in response.error


@pytest.mark.asyncio
async def test_direct_api_in_progress_is_not_success(monkeypatch):
    import backend.api.tools as api

    class Registry:
        async def execute_outcome(self, **kwargs):
            return ToolExecutionInProgress("op", "attempt", "probe", None, "Still running")

    monkeypatch.setattr(api, "get_tool_registry", Registry)
    response = await api.execute_tool(api.ExecuteToolRequest(tool="probe"))
    assert response.model_dump() == {
        "result": "", "success": False, "error": "Still running",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_result", [
    ToolResult.success("workflow finished"),
    ToolResult.failure(ErrorCategory.EXECUTION, "child failed"),
    ToolResult.cancelled("child cancelled"),
    ToolResult.unknown_outcome(ErrorCategory.TIMEOUT, "child uncertain"),
])
async def test_sse_direct_workflow_projects_child_outcome(monkeypatch, tool_result, tmp_path):
    import backend.api.chat as chat
    import backend.modules.tools.conversation_history as history_module

    class WorkflowProbe(Probe):
        name = "workflow_run"
        parameters = {
            "type": "object",
            "properties": {
                "team_name": {"type": "string"},
                "goal": {"type": "string"},
            },
            "required": ["team_name", "goal"],
        }

    registry = ToolRegistry()
    registry.register(WorkflowProbe(tool_result))
    agent = SimpleNamespace(
        tools=registry, provider=None, context_builder=None,
    )

    class SessionManager:
        def __init__(self, db):
            pass

        async def add_message(self, **kwargs):
            return SimpleNamespace(id=1)

    class ContextService:
        def __init__(self, db):
            pass

        async def build_model_context(self, **kwargs):
            return SimpleNamespace(history=[], session_summary=None)

    async def require_session(*args):
        return SimpleNamespace(id="session")

    async def get_agent(*args, **kwargs):
        return agent

    async def backfill(*args, **kwargs):
        return None

    monkeypatch.setattr(chat, "_require_session", require_session)
    monkeypatch.setattr(chat, "get_agent_loop", get_agent)
    monkeypatch.setattr(chat, "SessionManager", SessionManager)
    monkeypatch.setattr(chat, "ConversationContextService", ContextService)
    monkeypatch.setattr(chat, "_resolve_active_workspace", lambda: tmp_path)
    monkeypatch.setattr(chat, "_resolve_explicit_external_tool_request", lambda *args: None)
    monkeypatch.setattr(chat, "_resolve_explicit_team_workflow_request",
                        lambda *args: ("team", "goal"))
    monkeypatch.setattr(chat, "schedule_context_maintenance", lambda **kwargs: None)
    monkeypatch.setattr(chat, "get_db_session_factory", lambda: None)
    monkeypatch.setattr(
        chat, "resolve_session_runtime_config",
        lambda *args: SimpleNamespace(persona_config=SimpleNamespace(
            max_history_messages=10, enable_short_context_summary=False,
        ), model_name="test"),
    )
    monkeypatch.setattr(
        history_module, "get_conversation_history",
        lambda: SimpleNamespace(backfill_message_id=backfill),
    )
    stream = await chat.send_message(
        chat.SendMessageRequest(session_id="session", message="/team team goal"),
        req=None, db=None,
    )
    payload = "".join([
        chunk.decode() if isinstance(chunk, bytes) else chunk
        async for chunk in stream.body_iterator
    ])
    if tool_result.state is ExecutionState.SUCCEEDED:
        assert "event: message" in payload
        assert "event: done" in payload
    else:
        assert "event: error" in payload
        assert "event: done" not in payload
        if tool_result.state is ExecutionState.UNKNOWN_OUTCOME:
            assert "side effects may have occurred" in payload


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_result", [
    ToolResult.failure(ErrorCategory.EXECUTION, "child FAILED"),
    ToolResult.unknown_outcome(ErrorCategory.TIMEOUT, "child uncertain"),
])
async def test_xiaozhi_direct_tool_call_reports_non_success(monkeypatch, tool_result):
    import backend.app as app
    from backend.modules.channels.xiaozhi import XiaozhiChannel

    registry = ToolRegistry()
    registry.register(Probe(tool_result))
    monkeypatch.setattr(app, "get_tool_registry", lambda: registry)
    channel = XiaozhiChannel(SimpleNamespace(enable_conversation=False))
    sent = []

    async def send(message):
        sent.append(message)

    monkeypatch.setattr(channel, "_send_mcp", send)
    await channel._handle_tool_call(7, {"name": "probe", "arguments": {}})
    assert sent[0]["result"]["isError"] is True
    assert sent[0]["result"]["content"][0]["text"]
    if tool_result.state is ExecutionState.UNKNOWN_OUTCOME:
        assert "side effects may have occurred" in sent[0]["result"]["content"][0]["text"]


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_result,should_complete", [
    (ToolResult.success("ok"), True),
    (ToolResult.failure(ErrorCategory.EXECUTION, "failed"), False),
    (ToolResult.unknown_outcome(ErrorCategory.TIMEOUT, "uncertain"), False),
])
async def test_ws_notification_uses_canonical_state(
    monkeypatch, tool_result, should_complete,
):
    from backend.ws import tool_notifications as notifications

    registry = ToolRegistry()
    registry.register(Probe(tool_result))
    signals = []

    async def capture_complete(self, value):
        signals.append(("complete", value))

    async def capture_error(self, value):
        signals.append(("error", value))

    async def capture_start(self, value):
        signals.append(("start", value))

    monkeypatch.setattr(notifications.ToolNotificationHandler, "notify_start", capture_start)
    monkeypatch.setattr(notifications.ToolNotificationHandler, "notify_complete", capture_complete)
    monkeypatch.setattr(notifications.ToolNotificationHandler, "notify_error", capture_error)
    outcome = await notifications.execute_tool_with_notifications(
        "session", "probe", {}, registry.execute_outcome,
    )
    assert outcome.state is tool_result.state
    assert ("complete" in [signal[0] for signal in signals]) is should_complete
    assert ("error" in [signal[0] for signal in signals]) is not should_complete
