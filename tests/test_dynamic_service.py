"""planner 的受限程序生成与运行控制测试。"""

import asyncio

import pytest

from backend.modules.tools.execution import ExecutionState, ToolResult
from backend.modules.workflow.driver import DynamicWorkflowDriver
from backend.modules.workflow.journal import WorkflowJournal
from backend.modules.workflow.service import DynamicWorkflowService


class _Actor:
    def __init__(self):
        self.calls = []

    async def ask(self, instructions, **kwargs):
        self.calls.append(instructions)
        return ToolResult.success("done")


class _Driver:
    def __init__(self):
        self.calls = []

    async def ask(self, **kwargs):
        self.calls.append(kwargs)
        return ToolResult.success("done")


def _program(**kwargs):
    return {
        "version": 1,
        "agents": [{"id": "worker", "persona": "worker"}],
        "limits": {"max_parallel_asks": 1},
        "body": [{
            "kind": "ask", "site_id": "task", "actor": "worker",
            "instructions": "work", "await": True,
        }, {"kind": "return", "site_id": "done", "value": "finished"}],
        **kwargs,
    }


@pytest.mark.asyncio
async def test_planner_compiles_and_executes_only_through_service():
    journal = WorkflowJournal.memory()
    await journal.init()
    drivers = []

    def factory(**kwargs):
        driver = DynamicWorkflowDriver(
            actors={"worker": _Actor()},
            journal=kwargs["journal"],
            run_id=kwargs["run_id"],
            lineage=kwargs.get("lineage", ()),
        )
        drivers.append(driver)
        return driver

    service = DynamicWorkflowService(factory, journal)
    program = _program()
    preview = service.compile(program)
    result = await service.start(
        run_id="run-1", owner_id="user-a", session_id="session-a",
        workspace="E:/workspace", program=program,
    )

    assert preview["static"] is True
    assert result.state is ExecutionState.SUCCEEDED
    assert result.output == "finished"
    assert len(drivers[0].actors["worker"].calls) == 1


@pytest.mark.asyncio
async def test_invalid_planner_program_creates_no_run():
    journal = WorkflowJournal.memory()
    await journal.init()
    service = DynamicWorkflowService(lambda **kwargs: _Driver(), journal)
    program = _program()
    program["body"][0]["actor"] = "someone-else"

    result = await service.start(
        run_id="invalid", owner_id="user-a", session_id=None,
        workspace="E:/workspace", program=program,
    )

    assert result.state is ExecutionState.FAILED
    assert result.error_category.value == "VALIDATION"
    assert service.runs == {}


@pytest.mark.asyncio
async def test_resume_requires_owner_and_reuses_finished_ask():
    journal = WorkflowJournal.memory()
    await journal.init()
    drivers = []

    def factory(**kwargs):
        driver = DynamicWorkflowDriver(
            actors={"worker": _Actor()},
            journal=kwargs["journal"],
            run_id=kwargs["run_id"],
            lineage=kwargs.get("lineage", ()),
        )
        drivers.append(driver)
        return driver

    service = DynamicWorkflowService(factory, journal)
    program = _program()
    await service.start(
        run_id="run-owner", owner_id="user-a", session_id=None,
        workspace="E:/workspace", program=program,
    )
    record = await service.get_run("run-owner", owner_id="user-a")
    record["status"] = "cancelled"
    from backend.models.workflow_run import WorkflowRun
    async with journal._sessions() as db:
        row = await db.get(WorkflowRun, "run-owner")
        row.status = "cancelled"
        await db.commit()

    forbidden = await service.resume(run_id="run-owner", owner_id="user-b")
    assert forbidden.state is ExecutionState.FAILED
    assert forbidden.error_category.value == "PERMISSION"

    result = await service.resume(run_id="run-owner", owner_id="user-a")

    assert result.state is ExecutionState.SUCCEEDED
    assert len(drivers) == 2
    assert drivers[0].actors["worker"].calls == ["work"]
    assert drivers[1].actors["worker"].calls == []


@pytest.mark.asyncio
async def test_template_save_and_get_is_owner_scoped():
    journal = WorkflowJournal.memory()
    await journal.init()
    service = DynamicWorkflowService(lambda **kwargs: None, journal)
    program = _program()

    saved = await service.save_template(
        template_id="template-1", owner_id="user-a", name="Review", program=program,
    )
    found = await service.get_template("template-1", owner_id="user-a")
    hidden = await service.get_template("template-1", owner_id="user-b")

    assert saved["preview"]["static"] is True
    assert found["name"] == "Review"
    assert hidden is None


@pytest.mark.asyncio
async def test_max_asks_budget_stops_before_next_call():
    journal = WorkflowJournal.memory()
    await journal.init()
    drivers = []

    def factory(**kwargs):
        driver = _Driver()
        drivers.append(driver)
        return driver

    service = DynamicWorkflowService(factory, journal)
    program = _program(limits={"max_asks": 1})
    program["body"].insert(1, {
        "kind": "ask", "site_id": "task-2", "actor": "worker", "instructions": "second",
    })

    result = await service.start(
        run_id="budget", owner_id="user-a", session_id=None,
        workspace="E:/workspace", program=program,
    )

    assert result.state is ExecutionState.UNKNOWN_OUTCOME
    assert "max_asks" in result.display_text
    assert len(drivers[0].calls) == 1
