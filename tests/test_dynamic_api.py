"""planner、模板和 API 确认边界。"""

from types import SimpleNamespace

import pytest

from backend.api.dynamic_workflow import start_run, start_template_run
from backend.modules.multiuser.identity import AuthUser
from backend.modules.tools.execution import ExecutionState, ToolResult
from backend.modules.workflow.journal import WorkflowJournal
from backend.modules.workflow.service import DynamicWorkflowService


class _Actor:
    async def ask(self, instructions, **kwargs):
        return ToolResult.success(instructions)


def _program():
    return {
        "version": 1,
        "agents": [{"id": "worker", "persona": "worker"}],
        "body": [{"kind": "return", "site_id": "done", "value": "ok"}],
    }


@pytest.mark.asyncio
async def test_unconfirmed_free_program_does_not_execute(monkeypatch):
    journal = WorkflowJournal.memory()
    await journal.init()
    service = DynamicWorkflowService(lambda **kwargs: None, journal)
    import backend.api.dynamic_workflow as api
    monkeypatch.setattr(api, "_service", service)
    user = AuthUser(id="alice", username="alice", role="user")
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        user_runtime_manager=type("Manager", (), {
            "get": lambda self, user: _runtime(),
        })(),
    )))

    result = await start_run(
        SimpleNamespace(program=_program(), run_id="unconfirmed", confirmed=False),
        request,
        user,
    )

    assert result.state is ExecutionState.FAILED
    assert result.error_category.value == "PERMISSION"


async def _runtime():
    return SimpleNamespace(workspace="E:/users/alice", subagent_manager=None)


@pytest.mark.asyncio
async def test_saved_template_can_run_with_owner(monkeypatch):
    journal = WorkflowJournal.memory()
    await journal.init()
    service = DynamicWorkflowService(lambda **kwargs: None, journal)
    await service.save_template(
        template_id="review", owner_id="alice", name="Review", program=_program(),
    )
    import backend.api.dynamic_workflow as api
    monkeypatch.setattr(api, "_service", service)
    user = AuthUser(id="alice", username="alice", role="user")
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        user_runtime_manager=type("Manager", (), {"get": lambda self, user: _runtime()})(),
    )))

    result = await start_template_run(
        SimpleNamespace(template_id="review", run_id="template-run"), request, user,
    )

    assert result.state is ExecutionState.SUCCEEDED
    assert result.output == "ok"
