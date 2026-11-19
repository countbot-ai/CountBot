"""Dynamic Workflow 的执行、恢复与归属测试。"""

import pytest

from backend.modules.tools.execution import ExecutionState, ToolResult
from backend.modules.workflow.driver import DynamicWorkflowDriver
from backend.modules.workflow.engine import DynamicWorkflowEngine
from backend.modules.workflow.journal import WorkflowJournal


class _Actor:
    def __init__(self):
        self.calls = []

    async def ask(self, instructions, **kwargs):
        self.calls.append(instructions)
        return ToolResult.success({"answer": instructions})


def _program():
    return {
        "version": 1,
        "agents": [{"id": "worker", "persona": "worker"}],
        "body": [{
            "kind": "ask", "site_id": "research", "actor": "worker",
            "instructions": "first task", "assign": "answer",
        }, {
            "kind": "return", "site_id": "done", "value": {"kind": "var", "name": "answer"},
        }],
    }


@pytest.mark.asyncio
async def test_driver_journals_real_ask_and_replays_without_new_execution():
    actor = _Actor()
    journal = WorkflowJournal.memory()
    await journal.init()
    program = _program()
    await journal.create_run(
        run_id="run-1", owner_id="user-a", session_id="session-a",
        workspace="E:/workspace", program=program, caps={},
    )
    await journal.create_actor(run_id="run-1", actor_id="worker", persona={"system": "worker"})
    driver = DynamicWorkflowDriver(actors={"worker": actor}, journal=journal, run_id="run-1")

    first = await DynamicWorkflowEngine(program, driver).run()
    second = await DynamicWorkflowEngine(program, driver).run()

    assert first.state is ExecutionState.SUCCEEDED
    assert second.state is ExecutionState.SUCCEEDED
    assert second.output == first.output
    assert actor.calls == ["first task"]
