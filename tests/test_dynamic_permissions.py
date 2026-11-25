"""Dynamic Workflow 用户运行时与模型授权边界测试。"""

from types import SimpleNamespace

import pytest

from backend.api.dynamic_workflow import _execution_context
from backend.modules.multiuser.identity import AuthUser
from backend.modules.workflow.factory import DynamicActorFactory


class _Manager:
    async def get(self, user):
        return SimpleNamespace(workspace="E:/users/alice", subagent_manager="user-manager")


@pytest.mark.asyncio
async def test_regular_user_uses_own_workspace_not_admin_shared():
    user = AuthUser(id="alice", username="alice", role="user")
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        shared={"workspace": "E:/admin"},
        user_runtime_manager=_Manager(),
    )))

    context = await _execution_context(request, user)

    assert context["workspace"] == "E:/users/alice"
    assert context["user"] is user


@pytest.mark.asyncio
async def test_actor_factory_uses_user_runtime_manager():
    user = AuthUser(id="alice", username="alice", role="user")
    runtime = SimpleNamespace(workspace="E:/users/alice", subagent_manager="user-manager")
    factory = DynamicActorFactory(
        subagent_manager="admin-manager",
        workspace="E:/admin",
        owner_id="alice",
        session_id=None,
    )
    from backend.modules.workflow import factory as factory_module
    async def fake_provider(*args):
        return SimpleNamespace(default_model="user-model")
    factory_module.provider_for_user = fake_provider
    user = None

    driver = await factory.build_dynamic_driver(
        run_id="run-1",
        program={"agents": [{"id": "worker", "persona": "worker"}]},
        journal=None,
        user=user,
        runtime=runtime,
    )

    assert driver.actors["worker"].workspace == "E:/users/alice"
    assert driver.actors["worker"].manager == "user-manager"
