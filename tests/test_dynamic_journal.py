"""Dynamic Workflow journal 的持久化与重放测试。"""

import pytest

from backend.modules.tools.execution import ExecutionState, ToolResult
from backend.modules.workflow.journal import WorkflowJournal, input_hash


@pytest.mark.asyncio
async def test_journal_persists_owner_and_replays_completed_ask():
    journal = WorkflowJournal.memory()
    await journal.init()
    await journal.create_run(
        run_id="run-1",
        owner_id="user-a",
        session_id="session-a",
        workspace="E:/workspace",
        program={"version": 1, "agents": [], "body": [], "args": {}},
        caps={"max_parallel_asks": 2},
    )
    await journal.create_actor(
        run_id="run-1",
        actor_id="worker",
        persona={"system": "worker"},
        model_ref={"provider": "own", "model": "model-a"},
    )

    assert await journal.completed_ask("run-1", "ask-1", 1, "research") is None
    await journal.begin_ask(
        run_id="run-1", site_id="ask-1", ordinal=1,
        actor_id="worker", instructions="research",
    )
    result = ToolResult.success({"approved": True})
    await journal.record_ask(
        run_id="run-1",
        site_id="ask-1",
        ordinal=1,
        actor_id="worker",
        instructions="research",
        result=result,
    )
    await journal.append_event(
        run_id="run-1", event_type="ask-settled", payload={"site_id": "ask-1"},
    )

    replay = await journal.completed_ask("run-1", "ask-1", 1, "research")

    assert replay.state is ExecutionState.SUCCEEDED
    assert replay.value == {"approved": True}
    with pytest.raises(ValueError, match="Input hash mismatch"):
        await journal.completed_ask("run-1", "ask-1", 1, "changed")


@pytest.mark.asyncio
async def test_reopen_run_preserves_resumed_from():
    journal = WorkflowJournal.memory()
    await journal.init()
    program = {"version": 1, "agents": [], "body": [], "args": {}}
    await journal.create_run(
        run_id="child", owner_id=None, session_id=None, workspace="E:/workspace",
        program=program, caps={}, resumed_from="parent",
    )

    await journal.reopen_run(
        run_id="child", owner_id=None, session_id=None, workspace="E:/workspace",
        program=program, caps={},
    )

    record = await journal.get_run("child", owner_id=None)
    assert record["resumed_from"] == "parent"
