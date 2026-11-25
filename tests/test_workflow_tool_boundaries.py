"""工作流工具入口的多用户归属与模型继承测试。"""

import json
from types import SimpleNamespace

import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models.agent_team import AgentTeam
from backend.modules.tools import workflow_tool as tool_module
from backend.modules.tools.workflow_tool import WorkflowTool
from backend.modules.tools.execution import ExecutionState


class _SessionStore:
    def __init__(self, teams):
        engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine, tables=[AgentTeam.__table__])
        self._factory = sessionmaker(bind=engine)
        with self._factory() as session:
            session.add_all(teams)
            session.commit()

    def __call__(self):
        return self._factory()


def _team(owner_id, *, model_config=None):
    return AgentTeam(
        id=f"team-{owner_id}",
        name="shared-name",
        owner_id=owner_id,
        mode="pipeline",
        agents=[{"id": "researcher", "role": "Researcher", "task": "research"}],
        cross_review=True,
        enable_skills=False,
        use_custom_model=model_config is not None,
        team_model_config=json.dumps(model_config) if model_config else None,
    )


def _successful_engine(monkeypatch):
    captured = {}

    class Engine:
        def __init__(self, manager, **kwargs):
            captured.update(kwargs)

        async def run_outcome(self, mode, goal, agents, **kwargs):
            captured["mode"] = mode
            captured["agents"] = agents
            return SimpleNamespace(state=ExecutionState.SUCCEEDED)

    monkeypatch.setattr(tool_module, "WorkflowEngine", Engine)
    return captured


@pytest.mark.asyncio
async def test_team_lookup_uses_the_callers_owner(monkeypatch):
    teams = [_team(None), _team("user-a")]
    monkeypatch.setattr(tool_module.database, "SessionLocal", _SessionStore(teams))
    captured = _successful_engine(monkeypatch)

    result = await WorkflowTool(object(), owner_id="user-a").execute_outcome(
        goal="research", team_name="shared-name",
    )

    assert result.state is ExecutionState.SUCCEEDED
    assert captured["team_model_config"] is None


@pytest.mark.asyncio
async def test_admin_does_not_read_a_regular_users_team(monkeypatch):
    teams = [_team("user-a")]
    monkeypatch.setattr(tool_module.database, "SessionLocal", _SessionStore(teams))
    _successful_engine(monkeypatch)

    result = await WorkflowTool(object(), owner_id=None).execute_outcome(
        goal="research", team_name="shared-name",
    )

    assert result.state is ExecutionState.FAILED
    assert "was not found" in result.display_text


@pytest.mark.asyncio
async def test_invalid_mode_is_rejected_before_engine_construction(monkeypatch):
    class UnexpectedEngine:
        def __init__(self, *args, **kwargs):
            raise AssertionError("invalid mode must not construct an engine")

    monkeypatch.setattr(tool_module, "WorkflowEngine", UnexpectedEngine)

    result = await WorkflowTool(object()).execute_outcome(
        mode="dag", goal="research", agents=[{"id": "a"}],
    )

    assert result.state is ExecutionState.FAILED
    assert "unknown workflow mode" in result.display_text


@pytest.mark.asyncio
async def test_team_model_and_session_stream_inheritance(monkeypatch):
    team = _team("user-a", model_config={
        "provider": "own-provider", "model": "own-model",
    })
    monkeypatch.setattr(tool_module.database, "SessionLocal", _SessionStore([team]))
    captured = _successful_engine(monkeypatch)
    tool = WorkflowTool(object(), owner_id="user-a")

    result = await tool.execute_outcome(goal="research", team_name="shared-name")
    assert result.state is ExecutionState.SUCCEEDED
    assert captured["team_model_config"]["model"] == "own-model"

    with tool_module.database.SessionLocal() as session:
        session.get(AgentTeam, "team-user-a").use_custom_model = False
        session.commit()

    tool.set_session_id("session-1")
    monkeypatch.setattr(tool, "_load_session_model_override", lambda: {
        "model": "session-model", "stream_enabled": False,
    })
    result = await tool.execute_outcome(goal="research", team_name="shared-name")
    assert result.state is ExecutionState.SUCCEEDED
    assert captured["team_model_config"] == {
        "model": "session-model", "stream_enabled": False,
    }
