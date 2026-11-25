"""真实 Provider 下的 Dynamic actor 集成验证。"""

from types import SimpleNamespace

import pytest

from backend.modules.agent.session_gate import SessionTurnGate
from backend.modules.agent.subagent import SubagentManager
from backend.modules.providers.base import StreamChunk
from backend.modules.workflow.actor import DynamicActor


class _Provider:
    def __init__(self):
        self.messages = []

    async def chat_stream(self, **kwargs):
        self.messages.append(kwargs["messages"][-1]["content"])
        yield StreamChunk(content=kwargs["messages"][-1]["content"])


@pytest.mark.asyncio
async def test_real_subagent_manager_keeps_actor_history(tmp_path):
    provider = _Provider()
    manager = SubagentManager(
        provider=provider,
        workspace=tmp_path,
        model="model-a",
        config_loader=SimpleNamespace(config=SimpleNamespace(
            security=SimpleNamespace(command_timeout=10, subagent_timeout=10),
            model=SimpleNamespace(max_iterations=3),
        )),
    )
    actor = DynamicActor(
        actor_id="worker",
        run_id="run-1",
        owner_id="user-a",
        session_id="session-a",
        persona="worker",
        provider=provider,
        model="model-a",
        workspace=tmp_path,
        manager=manager,
        tools=None,
        gate=SessionTurnGate(),
    )

    first = await actor.ask("first")
    second = await actor.ask("second")

    assert first.output == "first"
    assert second.output == "second"
    assert actor.messages[0] == {"role": "system", "content": "worker"}
    assert actor.messages[-2] == {"role": "user", "content": "second"}
    assert actor.messages[-1] == {"role": "assistant", "content": "second"}
