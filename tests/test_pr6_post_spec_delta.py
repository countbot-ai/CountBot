"""Deterministic evidence for pre-attempt rejection and three-state readers."""

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backend.modules.tools.execution import (
    ErrorCategory, ExecutionState, OperationLedger, ToolExecutionRejected, ToolResult,
)
from backend.modules.tools.outcome_projection import (
    ProjectionState, conversation_succeeded, project_attempt, projection_state,
    project_child_disposition, read_task_projection, task_read_view,
)
from backend.modules.tools.registry import ToolRegistry
from backend.modules.tools.file_audit_logger import FileAuditLogger
from backend.modules.tools.conversation_history import ToolConversationHistory
from test_pr5_consumer_outcomes import Probe, run_agent
from test_pr5_consumer_outcomes import (
    test_sse_direct_workflow_projects_child_outcome as exercise_sse,
)
from test_child_outcome_propagation import _Probe, _run_child


def rejected(operation_id="op", tool_name="probe"):
    return ToolExecutionRejected(
        operation_id=operation_id, reason="OPERATION_IDENTITY_CONFLICT",
        tool_name=tool_name, correlation_id=None,
        display_text="operation_id is already bound to another invocation",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("identity", ["different_tool", "different_arguments"])
@pytest.mark.parametrize("active", [False, True])
async def test_retained_identity_collision_has_no_physical_attempt(
    identity, active, tmp_path,
):
    class BlockingProbe(Probe):
        def __init__(self):
            super().__init__(ToolResult.success("done"))
            self.entered = asyncio.Event()
            self.release = asyncio.Event()

        async def execute_outcome(self, **kwargs):
            self.calls += 1
            self.entered.set()
            if active:
                await self.release.wait()
            return ToolResult.success("done")

    class OtherProbe(Probe):
        name = "other_probe"

    ledger = OperationLedger()
    registry = ToolRegistry(ledger=ledger)
    first_tool = BlockingProbe()
    remote = OtherProbe(ToolResult.success("remote"))
    registry.register(first_tool)
    registry.register(remote)
    first_task = asyncio.create_task(registry.execute_outcome(
        "probe", {"value": "A"}, operation_id="op",
    ))
    await first_tool.entered.wait()
    if not active:
        first = await first_task
    before = ledger.attempts_for_operation("op")
    incoming_tool = "other_probe" if identity == "different_tool" else "probe"
    collision = await registry.execute_outcome(
        incoming_tool, {"value": "B"}, operation_id="op",
    )
    assert isinstance(collision, ToolExecutionRejected)
    assert collision.reason == "OPERATION_IDENTITY_CONFLICT"
    for field in ("attempt_id", "attempt_ordinal", "state", "side_effect_state",
                  "error_category", "retryable", "retry_safety"):
        assert not hasattr(collision, field)
    assert ledger.attempts_for_operation("op") == before
    assert first_tool.calls == 1
    assert remote.calls == 0
    audit = FileAuditLogger(str(tmp_path))
    audit.set_enabled(True)
    with pytest.raises(TypeError):
        project_attempt(collision, source="direct_api")
    assert not any("projection" in row for row in audit.get_recent_logs())
    if active:
        assert before[0].state is ExecutionState.RUNNING
        first_tool.release.set()
        first = await first_task
    assert (await registry.execute_outcome("probe", {"value": "A"},
                                           operation_id="op")) == first
    assert len(ledger.attempts_for_operation("op")) == 1


@pytest.mark.asyncio
async def test_collision_before_mcp_wrapper_does_not_invoke_remote():
    from test_mcp_execution_boundaries import _ReadSession, _resource_wrapper

    session = _ReadSession([])
    wrapper = _resource_wrapper(session)
    registry = ToolRegistry()
    registry.register(Probe(ToolResult.success("local")))
    registry.register(wrapper)
    first = await registry.execute_outcome("probe", {}, operation_id="op")
    before = registry._operation_ledger.attempts_for_operation("op")
    collision = await registry.execute_outcome(wrapper.name, {}, operation_id="op")
    assert isinstance(collision, ToolExecutionRejected)
    assert session.calls == 0
    assert registry._operation_ledger.attempts_for_operation("op") == before
    assert (await registry.execute_outcome("probe", {}, operation_id="op")) == first


@pytest.mark.asyncio
async def test_agent_and_direct_api_rejection_never_retry_or_persist(monkeypatch, tmp_path):
    import backend.api.tools as api
    import backend.modules.tools.file_audit_logger as audit_module

    audit = FileAuditLogger(str(tmp_path))
    audit.set_enabled(True)
    monkeypatch.setattr(audit_module, "file_audit_logger", audit)
    registry = ToolRegistry()
    probe = Probe(ToolResult.success("must not run"))
    registry.register(probe)
    calls = []

    async def reject(*args, **kwargs):
        calls.append(kwargs)
        return rejected(kwargs.get("operation_id") or "op")

    monkeypatch.setattr(registry, "execute_outcome", reject)
    run = await run_agent(monkeypatch, None, registry=registry, retries=3)
    assert len(calls) == 1
    assert probe.calls == 0
    assert not any(kind == "tool_result" for kind, _ in run.events)
    assert any(kind == "tool_error" for kind, _ in run.events)
    assert run.history.records == []
    assert "attempt_id" not in run.events[-1][1]
    assert "execution_state" not in run.events[-1][1]
    assert run.events[-1][1]["rejection_reason"] == "OPERATION_IDENTITY_CONFLICT"
    assert not any("projection" in row for row in audit.get_recent_logs())

    monkeypatch.setattr(api, "get_tool_registry", lambda: registry)
    monkeypatch.setattr(api, "file_audit_logger", audit)
    response = await api.execute_tool(api.ExecuteToolRequest(tool="probe"))
    assert response.model_dump() == {
        "result": "", "success": False,
        "error": "operation_id is already bound to another invocation",
    }
    assert not any("projection" in row for row in audit.get_recent_logs())


@pytest.mark.asyncio
async def test_ws_and_xiaozhi_rejection_keep_error_envelopes(monkeypatch, tmp_path):
    import backend.app as app
    from backend.ws import events, tool_notifications as notifications
    from backend.modules.channels.xiaozhi import XiaozhiChannel
    import backend.modules.tools.file_audit_logger as audit_module

    audit = FileAuditLogger(str(tmp_path))
    audit.set_enabled(True)
    monkeypatch.setattr(audit_module, "file_audit_logger", audit)
    signals = []

    async def capture_start(self, value):
        signals.append("start")

    async def capture_complete(self, value):
        signals.append("complete")

    async def capture_error(self, value):
        signals.append("error")

    monkeypatch.setattr(notifications.ToolNotificationHandler, "notify_start", capture_start)
    monkeypatch.setattr(notifications.ToolNotificationHandler, "notify_complete", capture_complete)
    monkeypatch.setattr(notifications.ToolNotificationHandler, "notify_error", capture_error)
    registry = ToolRegistry()
    registry.register(Probe(ToolResult.success("must not run")))

    async def reject(*args, **kwargs):
        return rejected()

    monkeypatch.setattr(registry, "execute_outcome", reject)
    await events.handle_tool_execution("session", "probe", {},
                                       SimpleNamespace(execute_tool=registry.execute_outcome))
    assert signals == ["start", "error"]
    assert audit.get_recent_logs() == []

    monkeypatch.setattr(app, "get_tool_registry", lambda: registry)
    channel = XiaozhiChannel(SimpleNamespace(enable_conversation=False))
    sent = []

    async def send(message):
        sent.append(message)

    monkeypatch.setattr(channel, "_send_mcp", send)
    await channel._handle_tool_call(7, {"name": "probe", "arguments": {}})
    assert set(sent[0]) == {"jsonrpc", "id", "error"}
    assert sent[0]["error"]["code"] == -32002
    assert audit.get_recent_logs() == []


@pytest.mark.asyncio
async def test_child_rejection_keeps_disposition_separate_from_attempts(
    monkeypatch, tmp_path,
):
    import backend.modules.tools.registry as registry_module
    import backend.modules.tools.file_audit_logger as audit_module

    audit = FileAuditLogger(str(tmp_path / "audit"))
    audit.set_enabled(True)
    monkeypatch.setattr(audit_module, "file_audit_logger", audit)
    calls = []

    async def reject(self, *args, **kwargs):
        calls.append(kwargs)
        return rejected(kwargs["operation_id"])

    monkeypatch.setattr(registry_module.ToolRegistry, "execute_outcome", reject)
    probe = _Probe()
    manager, task = await _run_child(tmp_path, monkeypatch, probe)
    await asyncio.wait_for(task.done_event.wait(), 2)
    assert len(calls) == 1
    assert probe.invocations == 0
    assert task.tool_outcomes == []
    assert task.tool_call_records[0]["status"] == "rejected"
    assert "attempt_id" not in task.tool_call_records[0]
    assert task.outcome_projection()["attempts"] == []
    assert audit.get_recent_logs() == []


@pytest.mark.asyncio
async def test_sse_rejection_uses_error_event_without_attempt(monkeypatch, tmp_path):
    import backend.modules.tools.registry as registry_module
    import backend.modules.tools.file_audit_logger as audit_module

    audit = FileAuditLogger(str(tmp_path / "audit"))
    audit.set_enabled(True)
    monkeypatch.setattr(audit_module, "file_audit_logger", audit)
    calls = []

    async def reject(self, *args, **kwargs):
        calls.append(kwargs)
        return rejected(tool_name="workflow_run")

    monkeypatch.setattr(registry_module.ToolRegistry, "execute_outcome", reject)
    await exercise_sse(monkeypatch, ToolResult.failure(
        ErrorCategory.EXECUTION, "non-success",
    ), tmp_path)
    assert len(calls) == 1
    assert audit.get_recent_logs() == []


@pytest.mark.asyncio
async def test_workflow_bridge_marks_rejection_without_child_attempt():
    from backend.modules.agent.workflow import ChildOutcomeError, WorkflowEngine
    from backend.modules.tools.execution import SideEffectState

    class Manager:
        running_tasks = {}

        def create_task(self, **kwargs):
            self.callback = kwargs["event_callback"]
            return "child"

        async def execute_task(self, task_id):
            await self.callback("tool_call", "probe", {})
            await self.callback("tool_rejected", "probe", rejected())

        def get_task(self, task_id):
            return SimpleNamespace(outcome=ToolResult.failure(
                ErrorCategory.RESULT_CONTRACT, "request rejected",
                side_effect_state=SideEffectState.NOT_ATTEMPTED,
            ))

    events = []
    engine = WorkflowEngine(Manager())

    async def emit(name, **kwargs):
        events.append(name)

    engine._emit_ws = emit
    with pytest.raises(ChildOutcomeError):
        await engine._invoke_agent("task", agent_id="child")
    call = engine._execution_data["child"]["toolCalls"][0]
    assert call["status"] == "rejected"
    assert call["reason"] == "OPERATION_IDENTITY_CONFLICT"
    assert "attempt_id" not in call
    assert "workflow_agent_tool_result" not in events
    assert "workflow_agent_complete" not in events
    assert "workflow_agent_failed" in events


@pytest.mark.parametrize("projection,expected", [
    (None, ProjectionState.ABSENT),
    ("{malformed", ProjectionState.UNSUPPORTED),
])
def test_reader_state_absent_or_malformed(projection, expected):
    assert projection_state(projection) is expected
    assert conversation_succeeded(projection, None) is (expected is ProjectionState.ABSENT)


def test_reader_unknown_version_and_missing_fields_across_history_and_task():
    from test_pr6_outcome_projection import outcome

    good = project_attempt(outcome(), source="agent_initial")
    invalid = [
        {**good, "schema_version": 2},
        {key: value for key, value in good.items() if key != "side_effect_state"},
        "{malformed",
    ]
    history = ToolConversationHistory(use_db=False)
    for item in invalid:
        history.add_conversation("session", "probe", {}, result="legacy success",
                                 error=None, outcome_projection=item)
        assert projection_state(item) is ProjectionState.UNSUPPORTED
    assert asyncio.run(history.get_stats())["success_rate"] == 0
    assert len(asyncio.run(history.get_all())) == 3
    assert projection_state(good) is ProjectionState.RECOGNIZED
    disposition = {"disposition": None, "attempts": [good]}
    assert read_task_projection(disposition)[0] is ProjectionState.RECOGNIZED
    assert task_read_view("completed", None)[0] == "completed"
    assert task_read_view("completed", json.dumps(disposition))[0] == "unknown"
    for item in invalid:
        state, parsed = read_task_projection({"disposition": None, "attempts": [item]})
        assert state is ProjectionState.UNSUPPORTED
        assert parsed is None
    assert task_read_view("completed", "{malformed") == ("unknown", "unsupported", None)


@pytest.mark.asyncio
@pytest.mark.parametrize("variant,expected_state,web_status", [
    ("absent", "absent", "success"),
    ("v1", "recognized", "success"),
    ("unknown_version", "unsupported", "unknown"),
    ("missing_field", "unsupported", "unknown"),
    ("malformed", "unsupported", "unknown"),
    ("ordinal_zero", "unsupported", "unknown"),
    ("pending", "unsupported", "unknown"),
    ("running", "unsupported", "unknown"),
])
async def test_history_model_web_and_audit_readers_keep_three_states(
    variant, expected_state, web_status, tmp_path,
):
    from backend.api.chat import _build_tool_call_response
    from backend.models.tool_conversation import ToolConversation as DBConversation
    from test_pr6_outcome_projection import outcome

    v1 = project_attempt(outcome(), source="agent_initial")
    values = {
        "absent": None,
        "v1": v1,
        "unknown_version": {**v1, "schema_version": 2},
        "missing_field": {key: value for key, value in v1.items()
                          if key != "side_effect_state"},
        "malformed": "{malformed",
        "ordinal_zero": {**v1, "attempt_ordinal": 0},
        "pending": {**v1, "state": "PENDING"},
        "running": {**v1, "state": "RUNNING"},
    }
    value = values[variant]
    history = ToolConversationHistory(use_db=False)
    history.add_conversation("session", "probe", {}, error=None,
                             result="legacy looks successful", outcome_projection=value)
    assert (await history.get_stats())["success_rate"] == (
        100.0 if expected_state != "unsupported" else 0.0
    )
    stored = value if isinstance(value, str) or value is None else json.dumps(value)
    row = DBConversation(id="row", session_id="session", timestamp="now",
                         tool_name="probe", arguments="{}", result="legacy success",
                         error=None, outcome_projection=stored)
    assert row.to_dict()["outcome_projection_state"] == expected_state
    rendered = await _build_tool_call_response(tc=row, db=None, subagent_mgr=None)
    assert rendered.status == web_status

    audit = FileAuditLogger(str(tmp_path))
    audit.set_enabled(True)
    record = {"type": "call", "status": "success", "projection": value}
    (tmp_path / "audit_fixture.log").write_text(json.dumps(record) + "\n")
    stats = audit.get_stats()
    assert stats["success_count"] == (0 if expected_state == "unsupported" else 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("variant,expected_status,expected_state", [
    ("absent", "completed", "absent"),
    ("v1", "completed", "recognized"),
    ("unknown_version", "unknown", "unsupported"),
    ("missing_field", "unknown", "unsupported"),
    ("malformed", "unknown", "unsupported"),
    ("pending", "unknown", "unsupported"),
    ("running", "unknown", "unsupported"),
])
async def test_task_api_and_chat_detail_readers_keep_three_states(
    monkeypatch, tmp_path, variant, expected_status, expected_state,
):
    from datetime import datetime
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from backend.database import Base
    from backend.models.task import Task
    from backend.api import tasks as tasks_api, chat

    disposition = project_child_disposition("11111111-1111-1111-1111-111111111111",
                                            ToolResult.success("done"))
    v1 = {"disposition": disposition, "attempts": []}
    values = {
        "absent": None,
        "v1": json.dumps(v1),
        "unknown_version": json.dumps({"disposition": {**disposition, "schema_version": 2},
                                       "attempts": []}),
        "missing_field": json.dumps({"disposition": {key: value for key, value in
                                                    disposition.items() if key != "side_effect_state"},
                                     "attempts": []}),
        "malformed": "{malformed",
        "pending": json.dumps({"disposition": {**disposition, "state": "PENDING"},
                                "attempts": []}),
        "running": json.dumps({"disposition": {**disposition, "state": "RUNNING"},
                                "attempts": []}),
    }
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'task.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    task_id = "11111111-1111-1111-1111-111111111111"
    async with factory() as db:
        db.add(Task(id=task_id, label="child", message="task", status="completed",
                    progress=100, created_at=datetime.now(),
                    outcome_projection=values[variant]))
        await db.commit()
        monkeypatch.setattr(tasks_api, "require_subagent_manager",
                            lambda: SimpleNamespace(get_task=lambda _: None))
        response = await tasks_api.get_task(task_id, db)
        assert response.status == expected_status
        assert response.outcome_projection_state == expected_state
        detail = await chat._load_spawn_task_detail(
            tool_call_result=f"Child (ID: {task_id})", subagent_mgr=None, db=db,
        )
        assert detail["status"] == expected_status
        assert detail["outcome_projection_state"] == expected_state
    await engine.dispose()
