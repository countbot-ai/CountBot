"""回归测试：频道会话命令支持 /al 全局列表与按最近列表范围切换。"""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import MethodType, SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.modules.channels.base import InboundMessage
from backend.modules.channels.handler import ChannelMessageHandler


def make_session(session_id: str, name: str) -> SimpleNamespace:
    now = datetime.now(timezone.utc)
    return SimpleNamespace(id=session_id, name=name, created_at=now, updated_at=now)


def make_message() -> InboundMessage:
    return InboundMessage(channel="feishu", sender_id="ou_test", chat_id="oc_chat", content="/cmd")


def build_handler() -> ChannelMessageHandler:
    handler = object.__new__(ChannelMessageHandler)
    handler._last_session_list_scope = {}
    handler._active_sessions = {}
    handler.replies = []

    async def fake_send_reply(self, msg, content):
        self.replies.append(content)

    handler._send_reply = MethodType(fake_send_reply, handler)
    return handler


async def test_list_all_sessions_updates_scope_and_prompt() -> bool:
    handler = build_handler()
    msg = make_message()
    sessions = [make_session("all-1", "web-session-1")]

    async def fake_load_recent_sessions(self, msg, include_all=False, limit=10):
        return sessions if include_all else []

    async def fake_load_session_message_counts(self, session_ids):
        return {"all-1": 3}

    handler._load_recent_sessions = MethodType(fake_load_recent_sessions, handler)
    handler._load_session_message_counts = MethodType(fake_load_session_message_counts, handler)

    await handler._handle_list_sessions_command(msg, include_all=True)
    reply = handler.replies[-1]
    checks = [
        (handler._get_last_session_list_scope(msg) == "all", "scope != all"),
        ("所有会话列表" in reply, "missing all sessions title"),
        ("使用 /l 查看当前聊天会话" in reply, "missing /l hint"),
    ]
    failed = [detail for ok, detail in checks if not ok]
    if failed:
        raise AssertionError("; ".join(failed))
    return True


async def test_switch_uses_last_all_scope_for_numeric_index() -> bool:
    handler = build_handler()
    msg = make_message()
    handler._remember_session_list_scope(msg, include_all=True)
    calls = []
    sessions = [make_session("all-1", "web-session-1"), make_session("all-2", "web-session-2")]

    async def fake_load_recent_sessions(self, msg, include_all=False, limit=10):
        calls.append(include_all)
        return sessions

    handler._load_recent_sessions = MethodType(fake_load_recent_sessions, handler)
    await handler._handle_switch_session_command(msg, "/s 2")

    reply = handler.replies[-1]
    checks = [
        (calls == [True], f"include_all calls={calls}"),
        (handler._active_sessions[handler._get_chat_key(msg)] == "all-2", "active session not switched"),
        ("来源: 所有会话" in reply, "missing all scope source line"),
    ]
    failed = [detail for ok, detail in checks if not ok]
    if failed:
        raise AssertionError("; ".join(failed))
    return True


async def test_switch_uses_chat_scope_by_default() -> bool:
    handler = build_handler()
    msg = make_message()
    calls = []
    sessions = [make_session("chat-1", "feishu:oc_chat:1")]

    async def fake_load_recent_sessions(self, msg, include_all=False, limit=10):
        calls.append(include_all)
        return sessions

    handler._load_recent_sessions = MethodType(fake_load_recent_sessions, handler)
    await handler._handle_switch_session_command(msg, "/s 1")

    if calls != [False]:
        raise AssertionError(f"default scope should be chat, got {calls}")
    if handler._active_sessions[handler._get_chat_key(msg)] != "chat-1":
        raise AssertionError("chat scope switch did not set active session")
    return True


async def test_help_mentions_all_sessions() -> bool:
    handler = build_handler()
    await handler._handle_help_command(make_message())
    reply = handler.replies[-1]
    if "/all (/al) - 查看所有会话" not in reply or "/al 查看所有会话" not in reply:
        raise AssertionError("help text missing /al usage")
    return True


async def main() -> int:
    tests = [
        ("list all sessions updates scope", test_list_all_sessions_updates_scope_and_prompt),
        ("switch uses all scope", test_switch_uses_last_all_scope_for_numeric_index),
        ("switch defaults to chat scope", test_switch_uses_chat_scope_by_default),
        ("help mentions /al", test_help_mentions_all_sessions),
    ]
    failed = []
    for name, test_func in tests:
        try:
            await test_func()
            print(f"✅ {name}")
        except Exception as exc:
            failed.append((name, exc))
            print(f"❌ {name}: {exc}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))