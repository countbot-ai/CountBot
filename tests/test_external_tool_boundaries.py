"""Deterministic PR3 coverage for externally side-effecting Tool producers."""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.modules.external_agents.base import ExternalAgentProfile, ExternalAgentResult
from backend.modules.tools.execution import (
    ErrorCategory,
    ExecutionState,
    RetrySafety,
    SideEffectState,
)
from backend.modules.tools.external_coding_agent import ExternalCodingAgentTool
from backend.modules.tools.registry import ToolRegistry
from backend.modules.tools.send_media import SendMediaTool
from backend.modules.tools.xiaozhi_message import XiaozhiMessageTool


def _canonical(tool, arguments, *, operation_id=None):
    registry = ToolRegistry()
    registry.register(tool)
    return asyncio.run(
        registry.execute_outcome(
            tool.name,
            arguments,
            operation_id=operation_id,
        )
    )


class _ExternalRegistry:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = 0
        self.profile = ExternalAgentProfile(
            name="fake",
            type="cli",
            enabled=True,
            command="fake-agent",
        )

    def resolve_profile(self, profile_name=None):
        if isinstance(self.error, ValueError):
            raise self.error
        return self.profile

    async def execute(self, request, profile_name=None):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result


def _external_result(tmp_path: Path, *, exit_code=0, timed_out=False, cancelled=False):
    return ExternalAgentResult(
        profile_name="fake",
        adapter_type="cli",
        command=["fake-agent"],
        working_dir=tmp_path,
        exit_code=exit_code,
        stdout="completed output",
        timed_out=timed_out,
        cancelled=cancelled,
        success_exit_codes=[0],
    )


def test_external_coding_pre_start_failure_is_not_attempted(tmp_path: Path):
    tool = ExternalCodingAgentTool(tmp_path)
    fake = _ExternalRegistry(error=ValueError("profile is unavailable"))
    tool.registry = fake

    outcome = _canonical(tool, {"task": "inspect the repository"})

    assert fake.calls == 0
    assert outcome.state is ExecutionState.FAILED
    assert outcome.error_category is ErrorCategory.VALIDATION
    assert outcome.retry_safety is RetrySafety.UNSAFE
    assert outcome.side_effect_state is SideEffectState.NOT_ATTEMPTED


def test_external_coding_success_is_completed_once(tmp_path: Path):
    tool = ExternalCodingAgentTool(tmp_path)
    fake = _ExternalRegistry(result=_external_result(tmp_path))
    tool.registry = fake

    outcome = _canonical(tool, {"task": "inspect the repository"})

    assert fake.calls == 1
    assert outcome.state is ExecutionState.SUCCEEDED
    assert outcome.retry_safety is RetrySafety.UNSAFE
    assert outcome.side_effect_state is SideEffectState.COMMITTED


@pytest.mark.parametrize(
    ("result_kwargs", "category"),
    [
        ({"timed_out": True, "exit_code": -1}, ErrorCategory.TIMEOUT),
        ({"cancelled": True, "exit_code": -1}, ErrorCategory.CANCELLATION),
        ({"exit_code": 2}, ErrorCategory.EXECUTION),
    ],
)
def test_external_coding_post_start_non_success_keeps_uncertainty(
    tmp_path: Path,
    result_kwargs,
    category,
):
    tool = ExternalCodingAgentTool(tmp_path)
    fake = _ExternalRegistry(result=_external_result(tmp_path, **result_kwargs))
    tool.registry = fake

    outcome = _canonical(tool, {"task": "modify the repository"})

    assert fake.calls == 1
    assert outcome.state is ExecutionState.UNKNOWN_OUTCOME
    assert outcome.error_category is category
    assert outcome.retry_safety is RetrySafety.UNSAFE
    assert outcome.side_effect_state is SideEffectState.UNKNOWN


class _DirectChannel:
    def __init__(self, error=None):
        self.error = error
        self.calls = 0

    async def send(self, message):
        self.calls += 1
        if self.error is not None:
            raise self.error


class _ChannelManager:
    def __init__(self, channel):
        self.channel = channel
        self.queue_calls = 0

    def get_channel(self, channel, account_id=None):
        return self.channel

    async def send_message(self, message):
        self.queue_calls += 1


def _media_tool(tmp_path: Path, channel):
    tool = SendMediaTool(
        channel_manager=_ChannelManager(channel),
        workspace=tmp_path,
    )

    async def session_info():
        return "telegram", "chat-1", {}

    tool._parse_session_info = session_info
    return tool


def test_media_validation_failure_stays_before_dispatch(tmp_path: Path):
    channel = _DirectChannel()
    tool = _media_tool(tmp_path, channel)

    outcome = _canonical(tool, {"file_paths": [str(tmp_path / "missing.png")]})

    assert channel.calls == 0
    assert outcome.state is ExecutionState.FAILED
    assert outcome.error_category is ErrorCategory.VALIDATION
    assert outcome.side_effect_state is SideEffectState.NOT_ATTEMPTED


def test_media_normal_send_return_is_not_false_committed_delivery(tmp_path: Path):
    media = tmp_path / "image.png"
    media.write_bytes(b"png")
    channel = _DirectChannel()
    tool = _media_tool(tmp_path, channel)

    outcome = _canonical(tool, {"file_paths": [str(media)]})

    assert channel.calls == 1
    assert outcome.state is ExecutionState.UNKNOWN_OUTCOME
    assert outcome.error_category is ErrorCategory.DEPENDENCY
    assert outcome.retry_safety is RetrySafety.UNSAFE
    assert outcome.side_effect_state is SideEffectState.UNKNOWN
    assert "无法确认" in outcome.display_text


def test_media_local_queue_admission_is_still_unknown_delivery(tmp_path: Path):
    media = tmp_path / "image.png"
    media.write_bytes(b"png")
    manager = _ChannelManager(None)
    tool = SendMediaTool(channel_manager=manager, workspace=tmp_path)

    async def session_info():
        return "telegram", "chat-1", {}

    tool._parse_session_info = session_info

    outcome = _canonical(tool, {"file_paths": [str(media)]})

    assert manager.queue_calls == 1
    assert outcome.state is ExecutionState.UNKNOWN_OUTCOME
    assert outcome.retry_safety is RetrySafety.UNSAFE
    assert outcome.side_effect_state is SideEffectState.UNKNOWN


def test_media_response_loss_after_dispatch_keeps_uncertainty(tmp_path: Path):
    media = tmp_path / "image.png"
    media.write_bytes(b"png")
    channel = _DirectChannel(ConnectionResetError("response lost"))
    tool = _media_tool(tmp_path, channel)

    outcome = _canonical(tool, {"file_paths": [str(media)]})

    assert channel.calls == 1
    assert outcome.state is ExecutionState.UNKNOWN_OUTCOME
    assert outcome.error_category is ErrorCategory.DEPENDENCY
    assert outcome.retry_safety is RetrySafety.UNSAFE
    assert outcome.side_effect_state is SideEffectState.UNKNOWN


def test_xiaozhi_producer_normalizes_text_and_message_without_channel_effects():
    text_outcome = _canonical(
        XiaozhiMessageTool(),
        {"text": "  hello from text  "},
        operation_id="xiaozhi-text",
    )
    alias_outcome = _canonical(
        XiaozhiMessageTool(),
        {"message": "hello from alias"},
        operation_id="xiaozhi-alias",
    )

    for outcome, expected in (
        (text_outcome, "hello from text"),
        (alias_outcome, "hello from alias"),
    ):
        assert outcome.state is ExecutionState.SUCCEEDED
        assert outcome.output == expected
        assert outcome.retry_safety is RetrySafety.SAFE
        assert outcome.side_effect_state is SideEffectState.NOT_APPLICABLE


def test_xiaozhi_empty_producer_input_is_explicit_failure():
    outcome = asyncio.run(XiaozhiMessageTool().execute_outcome(text="   "))

    assert outcome.state is ExecutionState.FAILED
    assert outcome.error_category is ErrorCategory.VALIDATION
    assert outcome.side_effect_state is SideEffectState.NOT_APPLICABLE
