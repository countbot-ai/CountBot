"""Dynamic Workflow 工具入口的受限执行测试。"""

from types import SimpleNamespace

import pytest

from backend.modules.tools.dynamic_workflow_tool import DynamicWorkflowTool
from backend.modules.tools.execution import ExecutionState, ToolResult
from backend.modules.workflow.journal import WorkflowJournal
from backend.modules.workflow.service import DynamicWorkflowService


@pytest.mark.asyncio
async def test_dynamic_tool_runs_json_program_not_python():
    journal = WorkflowJournal.memory()
    await journal.init()

    class Driver:
        async def ask(self, **kwargs):
            return SimpleNamespace(state=ExecutionState.SUCCEEDED, output="done")

    service = DynamicWorkflowService(lambda **kwargs: Driver(), journal)
    tool = DynamicWorkflowTool(service, owner_id="user-a", session_id="s1", workspace="E:/workspace")
    program = {
        "version": 1,
        "agents": [{"id": "worker", "persona": "worker"}],
        "body": [{"kind": "return", "site_id": "done", "value": {"kind": "literal", "value": "ok"}}],
    }

    result = await tool.execute_outcome(program=program, confirmed=True)

    assert result.state is ExecutionState.SUCCEEDED
    assert result.output["result"] == "ok"
    assert result.output["run_id"].startswith("dwf-")


@pytest.mark.asyncio
async def test_regular_user_tool_forwards_identity_to_service():
    from backend.modules.multiuser.identity import AuthUser

    journal = WorkflowJournal.memory()
    await journal.init()
    captured = {}

    async def fake_start(**kwargs):
        captured.update(kwargs)
        return ToolResult.success("ok")

    service = DynamicWorkflowService(lambda **kwargs: None, journal)
    service.start = fake_start
    user = AuthUser(id="user-b", username="bob", role="user")
    tool = DynamicWorkflowTool(
        service, owner_id=user.owner_id, session_id="s1",
        workspace="E:/workspace/user-b", user=user,
    )
    program = {
        "version": 1,
        "agents": [{"id": "worker", "persona": "worker"}],
        "body": [{"kind": "return", "site_id": "done", "value": "ok"}],
    }

    result = await tool.execute_outcome(program=program, confirmed=True)

    assert result.state is ExecutionState.SUCCEEDED
    assert captured["owner_id"] == "user-b"
    assert captured["user"] is user
    assert captured["workspace"] == "E:/workspace/user-b"


@pytest.mark.asyncio
async def test_dynamic_tool_rejects_arbitrary_code():
    service = DynamicWorkflowService(lambda **kwargs: None, WorkflowJournal.memory())
    tool = DynamicWorkflowTool(service, workspace="E:/workspace")

    result = await tool.execute_outcome(program={"version": 1, "agents": [], "body": "exec('danger')"})

    assert result.state is ExecutionState.FAILED
    assert result.error_category.value == "VALIDATION"
