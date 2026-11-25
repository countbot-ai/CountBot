"""通过 FastAPI 路由走真实 app 工厂的端到端测试。"""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.api import dynamic_workflow as api
from backend.app import _build_dynamic_driver_factory
from backend.modules.multiuser.identity import AuthUser
from backend.modules.tools.execution import ToolResult
from backend.modules.workflow.journal import WorkflowJournal
from backend.modules.workflow.service import DynamicWorkflowService


class _Driver:
    def __init__(self):
        self.asks = []

    async def ask(self, *, instructions, **kwargs):
        self.asks.append(instructions)
        return ToolResult.success("done")


class _AsyncFactory:
    def __init__(self, drivers, captured):
        self.drivers = drivers
        self.captured = captured

    async def build_dynamic_driver(self, **kwargs):
        self.captured.append(kwargs)
        driver = _Driver()
        self.drivers.append(driver)
        return driver


def _program(instructions="work"):
    return {
        "version": 1,
        "agents": [{"id": "worker", "persona": "worker"}],
        "body": [{
            "kind": "ask", "site_id": "task", "actor": "worker",
            "instructions": instructions,
        }, {"kind": "return", "site_id": "done", "value": "finished"}],
    }


async def _client(monkeypatch):
    journal = WorkflowJournal.memory()
    await journal.init()
    captured = []
    drivers = []
    factory = _build_dynamic_driver_factory(
        _AsyncFactory(drivers, captured), {"workspace": "E:/workspace"},
    )
    service = DynamicWorkflowService(factory, journal)
    monkeypatch.setattr(api, "_service", service)
    app = FastAPI()
    app.include_router(api.router)
    app.state.shared = {"workspace": "E:/workspace", "subagent_manager": None}
    user = AuthUser(id="", username="admin", role="admin")
    app.dependency_overrides[api.require_active_user] = lambda: user
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    return client, drivers, captured, user, journal


@pytest.mark.asyncio
async def test_post_runs_uses_real_app_factory(monkeypatch):
    client, drivers, captured, user, service_journal = await _client(monkeypatch)

    async with client:
        response = await client.post("/api/dynamic-workflow/runs", json={
            "program": _program(), "run_id": "api-run", "confirmed": True,
        })

    assert response.status_code == 200
    assert response.json()["state"] == "SUCCEEDED"
    assert captured[0]["user"] is user
    assert captured[0]["journal"] is service_journal
    assert captured[0]["runtime"]["workspace"] == "E:/workspace"
    assert drivers[0].asks == ["work"]


@pytest.mark.asyncio
async def test_post_amend_uses_new_program_without_old_lineage(monkeypatch):
    client, drivers, captured, _, _ = await _client(monkeypatch)

    async with client:
        await client.post("/api/dynamic-workflow/runs", json={
            "program": _program("old"), "run_id": "parent", "confirmed": True,
        })
        response = await client.post(
            "/api/dynamic-workflow/runs/parent/amend",
            json={"program": _program("new")},
        )

    assert response.status_code == 200
    assert response.json()["state"] == "SUCCEEDED"
    assert response.json()["run_id"] == captured[-1]["run_id"]
    assert captured[-1]["lineage"] == ()
    assert captured[-1]["run_id"].startswith("parent:amend-")
    assert drivers[-1].asks == ["new"]