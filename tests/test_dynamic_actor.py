"""Dynamic actor 的上下文连续性与结构化结果测试。"""

import asyncio
from types import SimpleNamespace

import pytest

from backend.modules.agent.subagent import SubagentManager
from backend.modules.providers.base import StreamChunk, ToolCall
from backend.modules.tools.registry import ToolRegistry
from backend.modules.workflow.actor import DynamicActor
from backend.modules.tools.execution import ExecutionState
from backend.modules.workflow.results import validate_result


class _Provider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def chat_stream(self, **kwargs):
        self.calls.append([dict(m) for m in kwargs["messages"]])
        for item in self.responses.pop(0):
            yield item


class _Manager(SubagentManager):
    def __init__(self, workspace):
        super().__init__(
            provider=None,
            workspace=workspace,
            model="model-a",
            config_loader=SimpleNamespace(
                config=SimpleNamespace(
                    security=SimpleNamespace(command_timeout=30, subagent_timeout=30),
                    model=SimpleNamespace(max_iterations=5),
                )
            ),
        )


def _actor(tmp_path, provider):
    return DynamicActor(
        actor_id="engineer",
        run_id="run-1",
        owner_id="user-a",
        session_id="session-a",
        persona="You are an engineer.",
        provider=provider,
        model="model-a",
        workspace=tmp_path,
        manager=_Manager(tmp_path),
        tools=ToolRegistry(workspace=tmp_path),
        gate=__import__("backend.modules.agent.session_gate", fromlist=["SessionTurnGate"]).SessionTurnGate(),
    )


@pytest.mark.asyncio
async def test_repeated_asks_share_assistant_and_tool_history(tmp_path):
    provider = _Provider([
        [StreamChunk(tool_call=ToolCall(id="read-1", name="read_file", arguments={"path": "note.txt"}))],
        [StreamChunk(content="first answer")],
        [StreamChunk(content="second answer")],
    ])
    actor = _actor(tmp_path, provider)
    (tmp_path / "note.txt").write_text("remember this", encoding="utf-8")

    first = await actor.ask("Read the note")
    second = await actor.ask("What did you read?")

    assert first.state is ExecutionState.SUCCEEDED
    assert second.state is ExecutionState.SUCCEEDED
    assert actor.next_ask_seq == 2
    second_messages = provider.calls[2]
    assert any(message["role"] == "assistant" and message.get("tool_calls") for message in second_messages)
    assert any(message["role"] == "tool" and "remember this" in message["content"] for message in second_messages)
    assert second_messages[-1] == {"role": "user", "content": "What did you read?"}


@pytest.mark.asyncio
async def test_structured_ask_uses_submit_tool_and_keeps_object(tmp_path):
    schema = {
        "type": "object",
        "properties": {"approved": {"type": "boolean"}, "feedback": {"type": "string"}},
        "required": ["approved", "feedback"],
        "additionalProperties": False,
    }
    provider = _Provider([
        [StreamChunk(tool_call=ToolCall(id="submit-1", name="submit_result", arguments={
            "result": {"approved": True, "feedback": "good"},
        }))],
    ])

    actor = _actor(tmp_path, provider)
    result = await actor.ask("Review", result_schema=schema)

    assert result.state is ExecutionState.SUCCEEDED
    assert result.value == {"approved": True, "feedback": "good"}


@pytest.mark.asyncio
async def test_structured_ask_repairs_invalid_result(tmp_path):
    schema = {"type": "object", "properties": {"approved": {"type": "boolean"}}, "required": ["approved"]}
    provider = _Provider([
        [StreamChunk(tool_call=ToolCall(id="bad", name="submit_result", arguments={"result": {"approved": "yes"}}))],
        [StreamChunk(tool_call=ToolCall(id="good", name="submit_result", arguments={"result": {"approved": True}}))],
    ])
    actor = _actor(tmp_path, provider)

    result = await actor.ask("Review", result_schema=schema)

    assert result.state is ExecutionState.SUCCEEDED
    assert result.value == {"approved": True}
    assert any("Correct it and call submit_result" in str(message.get("content")) for message in actor.messages)


def test_schema_rejects_boolean_as_integer_and_unknown_fields():
    errors = validate_result(
        {"count": True, "other": 1},
        {"type": "object", "properties": {"count": {"type": "integer"}}, "additionalProperties": False},
    )

    assert any("expected integer" in error for error in errors)
    assert any("unknown property" in error for error in errors)


@pytest.mark.asyncio
async def test_same_actor_is_fifo_and_different_actors_can_overlap(tmp_path):
    class GateProvider:
        def __init__(self):
            self.active = 0
            self.peak = 0
            self.events = []

        async def chat_stream(self, **kwargs):
            self.active += 1
            self.peak = max(self.peak, self.active)
            self.events.append(("enter", kwargs["messages"][-1]["content"]))
            await asyncio.sleep(0.02)
            self.events.append(("exit", kwargs["messages"][-1]["content"]))
            self.active -= 1
            yield StreamChunk(content=kwargs["messages"][-1]["content"])

    provider = GateProvider()
    actor = _actor(tmp_path, provider)
    other = _actor(tmp_path, provider)
    other.actor_id = "reviewer"

    await asyncio.gather(
        actor.ask("first"),
        actor.ask("second"),
        other.ask("other"),
    )

    actor_events = [event for event in provider.events if event[1] in {"first", "second"}]
    assert actor_events == [
        ("enter", "first"), ("exit", "first"),
        ("enter", "second"), ("exit", "second"),
    ]
    assert provider.peak == 2
    assert actor.next_ask_seq == 2


@pytest.mark.asyncio
async def test_structured_ask_repair_budget_is_enforced(tmp_path):
    provider = _Provider([
        [StreamChunk(tool_call=ToolCall(id="bad", name="submit_result", arguments={"result": {"approved": "no"}}))],
        [StreamChunk(tool_call=ToolCall(id="bad-2", name="submit_result", arguments={"result": {"approved": "still-no"}}))],
    ])
    actor = _actor(tmp_path, provider)

    result = await actor.ask(
        "Review",
        result_schema={"type": "object", "properties": {"approved": {"type": "boolean"}}},
        max_repairs=1,
        max_nudges=0,
    )

    assert result.state is ExecutionState.FAILED
    assert "Invalid structured result" in result.display_text
    assert len(provider.calls) == 2


@pytest.mark.asyncio
async def test_structured_ask_times_out_without_hanging(tmp_path):
    class HangingProvider:
        async def chat_stream(self, **kwargs):
            await asyncio.sleep(1)
            yield StreamChunk(content="late")

    actor = _actor(tmp_path, HangingProvider())
    actor.manager.config_loader.config.security.subagent_timeout = 0.01

    result = await actor.ask("Review", result_schema={"type": "boolean"})

    assert result.error_category.value == "TIMEOUT"
    assert "before tool execution" in result.display_text


@pytest.mark.asyncio
async def test_invalid_schema_is_rejected_before_creating_an_ask(tmp_path):
    actor = _actor(tmp_path, _Provider([]))

    with pytest.raises(ValueError, match="unsupported result schema"):
        await actor.ask("Review", result_schema={"type": "python"})

    assert actor.next_ask_seq == 0
