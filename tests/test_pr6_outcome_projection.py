"""PR6 projection, persistence compatibility, and completion evidence."""

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backend.database import Base, _apply_schema_compatibility_migrations
from backend.models.task import Task
from backend.models.tool_conversation import ToolConversation as DBToolConversation
from backend.modules.agent.subagent import SubagentManager, SubagentTask
from backend.modules.tools.conversation_history import ToolConversationHistory
from backend.modules.tools.execution import (
    ErrorCategory, ExecutionState, RetrySafety, SideEffectState,
    ToolExecutionInProgress, ToolExecutionOutcome, ToolResult,
    ToolExecutionRejected,
)
from backend.modules.tools.file_audit_logger import FileAuditLogger
from backend.modules.tools.outcome_projection import (
    ATTEMPT_KIND, CHILD_DISPOSITION_KIND, conversation_succeeded,
    project_attempt, project_child_disposition, read_projection, read_stored_projection,
    ProjectionState, projection_state, read_task_projection, task_read_view,
)
from backend.modules.tools.registry import ToolRegistry
from test_pr5_consumer_outcomes import (
    Probe, run_agent,
    test_sse_direct_workflow_projects_child_outcome as _exercise_sse,
    test_xiaozhi_direct_tool_call_reports_non_success as _exercise_xiaozhi,
)
from test_mcp_execution_boundaries import _ReadSession, _resource_wrapper


def outcome(state=ExecutionState.SUCCEEDED, *, attempt="attempt-a", ordinal=1):
    return ToolExecutionOutcome(
        operation_id="operation", attempt_id=attempt, attempt_ordinal=ordinal,
        tool_name="probe", state=state,
        display_text="SECRET_DISPLAY", duration_ms=12,
        output="SECRET_OUTPUT" if state is ExecutionState.SUCCEEDED else None,
        error_category=None if state is ExecutionState.SUCCEEDED else ErrorCategory.TIMEOUT,
        retryable=state is ExecutionState.FAILED,
        retry_safety=RetrySafety.SAFE,
        side_effect_state=(
            SideEffectState.UNKNOWN if state is ExecutionState.UNKNOWN_OUTCOME
            else SideEffectState.NOT_APPLICABLE
        ),
        correlation_id="tool-call",
    )


def test_projection_is_versioned_complete_and_redacted():
    projected = project_attempt(outcome(), source="agent_initial", session_id="session")
    assert projected["kind"] == ATTEMPT_KIND
    assert projected["schema_version"] == 1
    assert projected["operation_id"] == "operation"
    assert projected["attempt_id"] == "attempt-a"
    assert projected["state"] == "SUCCEEDED"
    assert projected["retry_safety"] == "SAFE"
    assert projected["side_effect_state"] == "NOT_APPLICABLE"
    assert projected["correlation_id"] == "tool-call"
    assert projected["duration_ms"] == 12
    assert read_projection(projected) == projected
    payload = json.dumps(projected)
    for secret in ("SECRET_DISPLAY", "SECRET_OUTPUT", "password", "raw prompt"):
        assert secret not in payload


def test_legacy_and_unknown_versions_never_become_canonical_defaults():
    legacy = {"result": "nonempty", "status": "success", "error": None}
    assert read_projection(legacy) is None
    projected = project_attempt(outcome(), source="direct_api")
    assert read_projection({**projected, "schema_version": 2}) is None
    assert read_projection({key: value for key, value in projected.items()
                            if key != "side_effect_state"}) is None
    assert read_stored_projection("{malformed") is None
    assert projection_state(None) is ProjectionState.ABSENT
    assert projection_state(projected) is ProjectionState.RECOGNIZED
    assert projection_state({**projected, "schema_version": 2}) is ProjectionState.UNSUPPORTED
    assert projection_state("{malformed") is ProjectionState.UNSUPPORTED
    assert conversation_succeeded({**projected, "schema_version": 2}, None) is False
    assert conversation_succeeded("{malformed", None) is False
    assert conversation_succeeded(None, None) is True  # legacy display compatibility
    assert conversation_succeeded(project_attempt(
        outcome(ExecutionState.FAILED), source="agent_initial"), None) is False


@pytest.mark.parametrize("change", [
    {"attempt_ordinal": 0},
    {"state": "PENDING"},
    {"state": "RUNNING"},
    {"error_category": "EXECUTION"},
    {"side_effect_state": "UNKNOWN"},
])
def test_current_version_attempt_with_impossible_semantics_is_unsupported(change):
    invalid = {**project_attempt(outcome(), source="direct_api"), **change}
    assert read_projection(invalid) is None
    assert projection_state(invalid) is ProjectionState.UNSUPPORTED
    assert conversation_succeeded(invalid, None) is False


@pytest.mark.parametrize("state", ["PENDING", "RUNNING"])
def test_current_version_child_disposition_must_be_terminal(state):
    disposition = project_child_disposition("child", ToolResult.success("done"))
    invalid = {**disposition, "state": state}
    assert read_projection(invalid, kind=CHILD_DISPOSITION_KIND) is None
    task_projection = {"disposition": invalid, "attempts": []}
    assert read_task_projection(task_projection) == (ProjectionState.UNSUPPORTED, None)
    assert task_read_view("completed", task_projection) == ("unknown", "unsupported", None)


def test_current_version_unknown_outcome_requires_unknown_effect_certainty():
    invalid = {**project_attempt(outcome(ExecutionState.UNKNOWN_OUTCOME), source="child"),
               "side_effect_state": "NOT_APPLICABLE"}
    assert projection_state(invalid) is ProjectionState.UNSUPPORTED


@pytest.mark.parametrize("state", [
    ExecutionState.SUCCEEDED, ExecutionState.FAILED,
    ExecutionState.CANCELLED, ExecutionState.UNKNOWN_OUTCOME,
])
def test_history_uses_canonical_state_not_text(state):
    history = ToolConversationHistory(use_db=False)
    projected = project_attempt(outcome(state), source="agent_initial")
    history.add_conversation(
        "session", "probe", {"secret": "legacy argument"},
        result="nonempty display", error=None, outcome_projection=projected,
    )
    record = asyncio.run(history.get_all())[0]
    assert record["outcome_projection"]["state"] == state.value
    stats = asyncio.run(history.get_stats())
    assert stats["success_rate"] == (100.0 if state is ExecutionState.SUCCEEDED else 0.0)


def test_audit_retry_and_replay_preserve_physical_identity(tmp_path):
    logger = FileAuditLogger(str(tmp_path))
    logger.set_enabled(True)
    first = outcome(ExecutionState.FAILED)
    second = outcome(attempt="attempt-b", ordinal=2)
    assert logger.record_outcome(first, source="mcp_safe_retry") is True
    assert logger.record_outcome(second, source="mcp_safe_retry") is True
    assert logger.record_outcome(second, source="mcp_safe_retry") is False
    records = [row["projection"] for row in logger.get_recent_logs()]
    assert len(records) == 2
    assert {item["attempt_id"] for item in records} == {"attempt-a", "attempt-b"}
    assert {item["operation_id"] for item in records} == {"operation"}
    assert {item["attempt_ordinal"] for item in records} == {1, 2}
    assert {item["source"] for item in records} == {"mcp_safe_retry"}
    reopened = FileAuditLogger(str(tmp_path))
    reopened.set_enabled(True)
    assert reopened.record_outcome(second, source="mcp_safe_retry") is False
    assert len(reopened.get_recent_logs()) == 2


def test_mixed_legacy_audit_remains_readable_and_canonical_stats_use_state(tmp_path):
    audit = FileAuditLogger(str(tmp_path))
    audit.set_enabled(True)
    audit.record_call("legacy", "probe", {"old": "payload"}, "session")
    audit.update_result("legacy", "display", "success")
    audit.record_outcome(
        outcome(ExecutionState.UNKNOWN_OUTCOME), source="direct_api",
    )
    records = audit.get_recent_logs()
    assert any(record.get("id") == "legacy" for record in records)
    assert any(record.get("projection", {}).get("state") == "UNKNOWN_OUTCOME"
               for record in records)
    stats = audit.get_stats()
    assert stats["success_count"] == 1
    assert stats["error_count"] == 1


@pytest.mark.asyncio
async def test_registry_completed_replay_does_not_create_audit_attempt(tmp_path):
    registry = ToolRegistry()
    probe = Probe(ToolResult.success("sensitive output"))
    registry.register(probe)
    audit = FileAuditLogger(str(tmp_path))
    audit.set_enabled(True)
    first = await registry.execute_outcome("probe", {}, operation_id="replayed")
    replay = await registry.execute_outcome("probe", {}, operation_id="replayed")
    assert first == replay
    assert probe.calls == 1
    assert audit.record_outcome(first, source="direct_api") is True
    assert audit.record_outcome(replay, source="direct_api") is False
    assert len([row for row in audit.get_recent_logs() if "projection" in row]) == 1


@pytest.mark.asyncio
async def test_mcp_safe_remote_reexecution_has_two_projected_attempts(tmp_path):
    session = _ReadSession([
        ConnectionResetError("transient"),
        SimpleNamespace(contents=[SimpleNamespace(text="SECRET_RESOURCE_BODY")]),
    ])
    wrapper = _resource_wrapper(session)
    registry = ToolRegistry()
    registry.register(wrapper)
    audit = FileAuditLogger(str(tmp_path))
    audit.set_enabled(True)
    first = await registry.execute_outcome(wrapper.name, {}, operation_id="remote-read")
    second = await registry.execute_outcome(
        wrapper.name, {}, operation_id="remote-read", retry_authorized=True,
    )
    assert session.calls == 2
    assert first.state is ExecutionState.FAILED
    assert second.state is ExecutionState.SUCCEEDED
    assert audit.record_outcome(first, source="agent_initial")
    assert audit.record_outcome(second, source="mcp_safe_retry")
    projections = [row["projection"] for row in audit.get_recent_logs()
                   if "projection" in row]
    assert {item["operation_id"] for item in projections} == {"remote-read"}
    assert {item["attempt_id"] for item in projections} == {
        first.attempt_id, second.attempt_id,
    }
    assert {item["source"] for item in projections} == {
        "agent_initial", "mcp_safe_retry",
    }
    assert "SECRET_RESOURCE_BODY" not in json.dumps(projections)


@pytest.mark.asyncio
async def test_agent_retry_records_both_attempts_and_final_history(monkeypatch, tmp_path):
    import backend.modules.tools.file_audit_logger as audit_module

    audit = FileAuditLogger(str(tmp_path))
    audit.set_enabled(True)
    monkeypatch.setattr(audit_module, "file_audit_logger", audit)
    run = await run_agent(monkeypatch, Probe(
        ToolResult.failure(ErrorCategory.DEPENDENCY, "SECRET_FAILURE", retryable=True,
                           retry_safety=RetrySafety.SAFE),
        ToolResult.success("SECRET_SUCCESS"),
    ))
    records = [row["projection"] for row in audit.get_recent_logs()
               if "projection" in row]
    assert len(records) == 2
    assert {
        record["attempt_ordinal"]: record["state"] for record in records
    } == {1: "FAILED", 2: "SUCCEEDED"}
    assert records[0]["operation_id"] == records[1]["operation_id"]
    assert records[0]["attempt_id"] != records[1]["attempt_id"]
    assert run.history.records[0]["outcome_projection"]["state"] == "SUCCEEDED"
    assert "SECRET_FAILURE" not in json.dumps(records)
    assert "SECRET_SUCCESS" not in json.dumps(records)


def test_child_disposition_and_attempts_are_distinct():
    task = SubagentTask("task", "label", "message")
    task.outcome = ToolResult.unknown_outcome(ErrorCategory.TIMEOUT, "SECRET_CHILD")
    task.tool_outcomes.append(outcome(ExecutionState.FAILED))
    projected = task.outcome_projection()
    assert projected["disposition"]["kind"] == CHILD_DISPOSITION_KIND
    assert projected["disposition"]["state"] == "UNKNOWN_OUTCOME"
    assert "attempt_id" not in projected["disposition"]
    assert projected["attempts"][0]["state"] == "FAILED"
    assert "SECRET_CHILD" not in json.dumps(projected)
    task.tool_outcomes.clear()
    assert task.outcome_projection()["attempts"] == []


def test_additive_migration_keeps_legacy_rows(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE tool_conversations (id TEXT PRIMARY KEY, error TEXT)"
        )
        connection.exec_driver_sql("INSERT INTO tool_conversations VALUES ('legacy', NULL)")
        connection.exec_driver_sql("CREATE TABLE tasks (id TEXT PRIMARY KEY, status TEXT)")
        connection.exec_driver_sql("INSERT INTO tasks VALUES ('child', 'failed')")
        _apply_schema_compatibility_migrations(connection)
        _apply_schema_compatibility_migrations(connection)
        assert connection.exec_driver_sql(
            "SELECT id, outcome_projection FROM tool_conversations"
        ).one() == ("legacy", None)
        assert connection.exec_driver_sql(
            "SELECT id, outcome_projection FROM tasks"
        ).one() == ("child", None)
        assert connection.exec_driver_sql("SELECT id, error FROM tool_conversations").one() == (
            "legacy", None,
        )
    assert "outcome_projection" in {
        column["name"] for column in inspect(engine).get_columns("tasks")
    }
    engine.dispose()


@pytest.mark.asyncio
async def test_history_and_child_task_columns_persist_structured_state(monkeypatch, tmp_path):
    import backend.database as database_module

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'new.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def get_db():
        async with factory() as session:
            yield session

    monkeypatch.setattr(database_module, "get_db", get_db)
    history = ToolConversationHistory(use_db=True)
    projected = project_attempt(outcome(ExecutionState.UNKNOWN_OUTCOME), source="agent_initial")
    history.add_conversation(
        "session", "probe", {}, result="looks successful", error=None,
        outcome_projection=projected,
    )
    await asyncio.gather(*history._pending_db_tasks)
    saved_history = await history.get_all()
    assert saved_history[0]["outcome_projection"]["state"] == "UNKNOWN_OUTCOME"
    assert (await history.get_stats())["success_rate"] == 0.0

    task = SubagentTask("child", "label", "message")
    task.outcome = ToolResult.unknown_outcome(ErrorCategory.TIMEOUT, "uncertain")
    task.tool_outcomes.append(outcome(ExecutionState.FAILED))
    manager = SubagentManager(None, tmp_path, "model", db_session_factory=factory)
    await manager._save_task_to_db(task)
    async with factory() as session:
        saved = await session.get(Task, "child")
        projection = json.loads(saved.outcome_projection)
        assert projection["disposition"]["state"] == "UNKNOWN_OUTCOME"
        assert projection["attempts"][0]["state"] == "FAILED"
        assert saved.status == "pending"  # legacy status never overwrites projection
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_result,expected", [
    (ToolResult.success("display"), "SUCCEEDED"),
    (ToolResult.failure(ErrorCategory.EXECUTION, "display"), "FAILED"),
    (ToolResult.unknown_outcome(ErrorCategory.TIMEOUT, "display"), "UNKNOWN_OUTCOME"),
])
async def test_direct_api_response_and_audit_agree(monkeypatch, tmp_path, tool_result, expected):
    import backend.api.tools as tools_api

    registry = ToolRegistry()
    registry.register(Probe(tool_result))
    audit = FileAuditLogger(str(tmp_path))
    audit.set_enabled(True)
    monkeypatch.setattr(tools_api, "get_tool_registry", lambda: registry)
    monkeypatch.setattr(tools_api, "file_audit_logger", audit)
    response = await tools_api.execute_tool(tools_api.ExecuteToolRequest(tool="probe"))
    records = [row["projection"] for row in audit.get_recent_logs()]
    assert len(records) == 1
    assert records[0]["state"] == expected
    assert response.success is (expected == "SUCCEEDED")
    assert response.result == ("display" if expected == "SUCCEEDED" else "")


@pytest.mark.asyncio
@pytest.mark.parametrize("consumer,state", [
    ("sse", ExecutionState.UNKNOWN_OUTCOME),
    ("xiaozhi", ExecutionState.FAILED),
    ("websocket", ExecutionState.SUCCEEDED),
])
async def test_pr5_direct_consumers_write_matching_projection(
    monkeypatch, tmp_path, consumer, state,
):
    import backend.modules.tools.file_audit_logger as audit_module

    audit = FileAuditLogger(str(tmp_path / "audit"))
    audit.set_enabled(True)
    monkeypatch.setattr(audit_module, "file_audit_logger", audit)
    result = (
        ToolResult.success("display") if state is ExecutionState.SUCCEEDED
        else ToolResult.unknown_outcome(ErrorCategory.TIMEOUT, "display")
        if state is ExecutionState.UNKNOWN_OUTCOME
        else ToolResult.failure(ErrorCategory.EXECUTION, "display")
    )
    if consumer == "sse":
        await _exercise_sse(monkeypatch, result, tmp_path)
    elif consumer == "xiaozhi":
        await _exercise_xiaozhi(monkeypatch, result)
    else:
        from backend.ws import events, tool_notifications

        registry = ToolRegistry()
        registry.register(Probe(result))

        async def no_notification(*args, **kwargs):
            pass

        monkeypatch.setattr(tool_notifications.ToolNotificationHandler,
                            "notify_start", no_notification)
        monkeypatch.setattr(tool_notifications.ToolNotificationHandler,
                            "notify_complete", no_notification)
        monkeypatch.setattr(tool_notifications.ToolNotificationHandler,
                            "notify_error", no_notification)
        await events.handle_tool_execution(
            "session", "probe", {},
            SimpleNamespace(execute_tool=registry.execute_outcome),
        )
    projections = [row["projection"] for row in audit.get_recent_logs()
                   if "projection" in row]
    assert len(projections) == 1
    assert projections[0]["state"] == state.value
    assert projections[0]["source"] == (
        "sse_workflow" if consumer == "sse" else consumer
    )


@pytest.mark.asyncio
async def test_websocket_in_progress_admission_has_no_attempt_record(monkeypatch, tmp_path):
    from backend.ws import events
    import backend.ws.tool_notifications as notifications
    import backend.modules.tools.file_audit_logger as audit_module

    audit = FileAuditLogger(str(tmp_path))
    audit.set_enabled(True)
    monkeypatch.setattr(audit_module, "file_audit_logger", audit)

    async def admission(**kwargs):
        return ToolExecutionInProgress(
            operation_id="operation", active_attempt_id="attempt-a",
            tool_name="probe", correlation_id=None, display_text="still running",
        )

    monkeypatch.setattr(notifications, "execute_tool_with_notifications", admission)
    await events.handle_tool_execution(
        "session", "probe", {}, SimpleNamespace(execute_tool=None),
    )
    assert audit.get_recent_logs() == []


def test_queue_fake_consumes_projection_without_ack_methods():
    class FutureQueueConsumer:
        def __init__(self):
            self.ack_calls = 0

        def consume(self, projection):
            parsed = read_projection(projection)
            return parsed["state"], parsed["retryable"], parsed["retry_safety"]

        def mark_processed(self):
            self.ack_calls += 1

        def mark_failed(self):
            self.ack_calls += 1

    consumer = FutureQueueConsumer()
    assert consumer.consume(project_attempt(
        outcome(ExecutionState.UNKNOWN_OUTCOME), source="direct_api",
    )) == ("UNKNOWN_OUTCOME", False, "SAFE")
    assert consumer.ack_calls == 0
