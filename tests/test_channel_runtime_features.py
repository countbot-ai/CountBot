"""渠道运行时能力测试。

覆盖附件上限、统一运行时状态机、飞书投递诊断/熔断、群聊 @ 触发、
话题会话隔离以及飞书 SDK 延迟加载。
"""

import asyncio
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.modules.channels.base import BaseChannel, InboundMessage
from backend.modules.channels.feishu import (
    FeishuChannel,
    FeishuStreamPhase,
    FeishuStreamState,
)
from backend.modules.channels.inbound_utils import _resolve_session_route
from backend.modules.channels.media_utils import (
    MAX_INBOUND_ATTACHMENT_BYTES,
    download_to_temp,
    save_bytes_to_temp,
)


def _run(coro):
    return asyncio.run(coro)


class _DummyChannel(BaseChannel):
    name = "dummy"

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def send(self, msg) -> None:
        return None

    async def test_connection(self):
        return {"success": True, "message": "ok"}


def _feishu_channel() -> FeishuChannel:
    return FeishuChannel(
        SimpleNamespace(account_id="default", app_id="cli_test", app_secret="secret")
    )


# ---------------------------------------------------------------------------
# 附件上限
# ---------------------------------------------------------------------------


def test_save_bytes_rejects_oversized_attachment():
    with pytest.raises(ValueError):
        save_bytes_to_temp("test", b"x" * (MAX_INBOUND_ATTACHMENT_BYTES + 1))


def test_download_to_temp_streams_and_enforces_limit():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"0123456789")

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(ValueError):
                await download_to_temp(
                    "test",
                    "https://example.com/file.bin",
                    client=client,
                    max_bytes=5,
                )

    _run(scenario())


def test_handle_message_truncates_attachments_and_adds_default_prompt():
    channel = _DummyChannel(SimpleNamespace(account_id="default"))
    captured = {}

    async def callback(msg: InboundMessage):
        captured["msg"] = msg

    channel.set_message_callback(callback)
    _run(
        channel._handle_message(
            sender_id="user",
            chat_id="chat",
            content="",
            media=["a", "b", "c", "d", "e"],
        )
    )

    msg = captured["msg"]
    assert len(msg.media) == 4
    assert "请查看附件" in msg.content
    assert "忽略 1 个" in msg.content


# ---------------------------------------------------------------------------
# 运行时状态机
# ---------------------------------------------------------------------------


def test_runtime_state_snapshot():
    channel = _DummyChannel(SimpleNamespace(account_id="bot-1"))
    channel._running = True
    channel.set_runtime_state(
        BaseChannel.RUNTIME_RUNNING, reconnect_attempts=2
    )
    status = channel.get_runtime_status()
    assert status["state"] == "running"
    assert status["healthy_running"] is True
    assert status["reconnect_attempts"] == 2

    channel.set_runtime_state(BaseChannel.RUNTIME_FAILED, error="boom")
    status = channel.get_runtime_status()
    assert status["healthy_running"] is False
    assert status["last_error"] == "boom"


# ---------------------------------------------------------------------------
# 飞书投递诊断与熔断
# ---------------------------------------------------------------------------


class _FakeFeishuResponse:
    def __init__(self, code: int = 19001, status: int = 400):
        self.code = code
        self.msg = "invalid request"
        self.raw = SimpleNamespace(status_code=status)

    def success(self) -> bool:
        return False

    def get_log_id(self) -> str:
        return "log-123"


def test_feishu_delivery_error_detail():
    channel = _feishu_channel()
    detail = channel._record_delivery_error(
        "message.patch", response=_FakeFeishuResponse()
    )

    assert detail["code"] == 19001
    assert detail["status"] == 400
    assert detail["log_id"] == "log-123"
    assert channel.get_runtime_status()["delivery_error"]["operation"] == "message.patch"

    channel._clear_delivery_error()
    assert channel.get_runtime_status()["delivery_error"] is None


def test_feishu_stream_circuit_opens_after_threshold():
    channel = _feishu_channel()
    state = FeishuStreamState(
        source_message_id="om_1",
        chat_key="chat_id:oc_1",
        reply_to="oc_1",
        receive_id_type="chat_id",
        phase=FeishuStreamPhase.STREAMING,
    )

    for _ in range(5):
        channel._register_stream_failure(state, "cardkit.stream", response=_FakeFeishuResponse())

    assert channel._is_circuit_open(state) is True
    channel._register_stream_success(state)
    assert channel._is_circuit_open(state) is False


def test_feishu_bot_mention_detection(monkeypatch):
    channel = _feishu_channel()

    async def fake_identity():
        return {"open_id": "ou_bot", "app_name": "CountBot"}

    monkeypatch.setattr(channel, "_get_bot_identity", fake_identity)

    assert _run(
        channel._is_bot_mentioned(
            {"mentions": [{"id": {"open_id": "ou_bot"}, "name": "CountBot"}]}
        )
    )
    assert not _run(
        channel._is_bot_mentioned(
            {
                "mentions": [
                    {"id": {"open_id": "ou_a"}},
                    {"id": {"open_id": "ou_b"}},
                ]
            }
        )
    )
    # 身份不可用时，仅一个 @ 视为在叫机器人。
    async def empty_identity():
        return {}

    monkeypatch.setattr(channel, "_get_bot_identity", empty_identity)
    assert _run(channel._is_bot_mentioned({"mentions": [{"id": {"open_id": "ou_a"}}]}))


def test_feishu_queue_notice_uses_topic_reply(monkeypatch):
    channel = _feishu_channel()
    calls = []

    async def fake_send_card(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(channel, "_send_card", fake_send_card)
    msg = InboundMessage(
        channel="feishu",
        sender_id="ou_user",
        chat_id="oc_chat",
        content="queued",
        metadata={
            "chat_type": "group",
            "thread_reply_message_id": "om_source",
        },
    )

    _run(channel.notify_queued(msg, position=2))

    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[0] == "oc_chat"
    assert "队列第 2 位" in args[1]
    assert kwargs["thread_message_id"] == "om_source"


# ---------------------------------------------------------------------------
# 飞书话题会话隔离
# ---------------------------------------------------------------------------


def test_feishu_topic_session_isolation():
    msg = InboundMessage(
        channel="feishu",
        sender_id="ou_user",
        chat_id="oc_chat",
        content="hello",
        metadata={"chat_type": "group", "thread_id": "th_1"},
    )
    route = _resolve_session_route(msg)
    assert route["group_chat_id"] == "oc_chat"
    assert route["session_chat_id"] == "oc_chat#topic:th_1"
    assert route["thread_id"] == "th_1"


def test_feishu_group_without_topic_uses_chat_session():
    msg = InboundMessage(
        channel="feishu",
        sender_id="ou_user",
        chat_id="oc_chat",
        content="hello",
        metadata={"chat_type": "group"},
    )
    route = _resolve_session_route(msg)
    assert route["session_chat_id"] == "oc_chat"
    assert route["thread_id"] is None


# ---------------------------------------------------------------------------
# SDK 延迟加载
# ---------------------------------------------------------------------------


def test_feishu_module_import_does_not_load_sdk():
    project_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import backend.modules.channels.feishu; "
            "print('lark_oapi' in sys.modules)",
        ],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "False"
