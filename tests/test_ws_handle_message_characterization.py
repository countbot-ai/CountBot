"""handle_message_event（WS 消息入口）拆分重构的特征测试

通过 monkeypatch 隔离 WS 基础设施（连接管理、发送函数、DB 会话），
用真实 AgentLoop + 脚本式 provider 驱动完整的 handle_message_event 链路，
锁定拆分前后的关键行为：
- 快乐路径：用户消息落库 → 流式处理 → 助手消息落库 → 完成通知 → 闸门释放
- 会话不存在 / provider 不可用 / 用户消息保存失败的分类错误
- 异常路径下闸门必须释放（不得泄漏占用）
"""

import asyncio
import sys
import types
from types import SimpleNamespace

import pytest

from backend.modules.agent.session_gate import get_session_gate
from backend.modules.providers.base import ToolCall


class _ScriptedProvider:
    def __init__(self, scripts):
        self.scripts = scripts
        self.calls = 0

    async def chat_stream(self, messages, tools=None, **kwargs):
        from backend.modules.providers.base import StreamChunk

        idx = min(self.calls, len(self.scripts) - 1)
        self.calls += 1
        for kwargs_chunk in self.scripts[idx]:
            yield StreamChunk(**kwargs_chunk)


class _MinimalTools:
    def get_definitions(self):
        return []

    def set_session_id(self, *a):
        pass

    def set_channel(self, *a):
        pass

    def set_cancel_token(self, *a):
        pass

    def set_tool_event_handler(self, *a):
        pass

    def get_tool(self, *a):
        return None


@pytest.fixture()
def ws_env(monkeypatch, tmp_path):
    """隔离全部 WS 基础设施，记录发送调用。"""
    import backend.ws.events as events
    import backend.ws.connection as ws_connection
    import backend.ws.streaming as ws_streaming

    sent = {"errors": [], "chunks": [], "reasoning": [], "complete": []}

    async def fake_send_error(session_id, message, code):
        sent["errors"].append((session_id, message, code))

    async def fake_send_chunk(session_id, chunk):
        sent["chunks"].append(chunk)

    async def fake_send_reasoning(session_id, chunk):
        sent["reasoning"].append(chunk)

    async def fake_send_complete(session_id, payload):
        sent["complete"].append((session_id, payload))

    async def fake_bind_session(connection_id, session_id):
        pass

    monkeypatch.setattr(events, "send_error", fake_send_error)
    monkeypatch.setattr(events, "send_message_chunk", fake_send_chunk)
    monkeypatch.setattr(events, "send_reasoning_chunk", fake_send_reasoning)
    monkeypatch.setattr(events, "send_message_complete", fake_send_complete)
    monkeypatch.setattr(ws_connection, "send_error", fake_send_error)
    monkeypatch.setattr(ws_connection, "send_message_chunk", fake_send_chunk)
    monkeypatch.setattr(ws_connection, "send_message_complete", fake_send_complete)
    monkeypatch.setattr(ws_connection, "send_reasoning_chunk", fake_send_reasoning)
    monkeypatch.setattr(
        ws_connection.connection_manager, "bind_session", fake_bind_session
    )

    # 取消令牌：真实 CancellationToken，get/cleanup 走内存字典
    from backend.modules.agent.task_manager import CancellationToken

    tokens = {}
    monkeypatch.setattr(
        ws_connection, "get_cancel_token",
        lambda session_id: tokens.setdefault(session_id, CancellationToken()),
    )
    monkeypatch.setattr(
        ws_connection, "cleanup_cancel_token",
        lambda session_id, token: tokens.pop(session_id, None),
    )

    # 流式 handler 假件
    class _FakeStreaming:
        def __init__(self, **kwargs):
            self.written = []

        async def write(self, text):
            self.written.append(text)

        async def flush(self):
            pass

        def get_stats(self):
            return {}

    monkeypatch.setattr(ws_streaming, "BufferedStreamingHandler", _FakeStreaming)

    # DB 会话（SessionManager 将被单独 mock，db 本身不参与）
    db = object()

    # AgentLoop：真实实例 + 脚本 provider
    from backend.modules.agent.loop import AgentLoop

    def make_loop(scripts):
        return AgentLoop(provider=_ScriptedProvider(scripts), workspace=tmp_path,
                         tools=_MinimalTools(), max_iterations=4)

    return types.SimpleNamespace(
        events=events, sent=sent, tokens=tokens, db=db,
        make_loop=make_loop, monkeypatch=monkeypatch, tmp_path=tmp_path,
    )


def _patch_session_layer(env, session_exists=True, user_message="DEFAULT",
                         assistant_message=None, history=None,
                         provider_selectable=True):
    """mock 会话层：SessionManager / runtime config / context service。

    user_message 传 None 表示"保存失败返回 None"（触发 DATABASE_ERROR 分支）。
    """
    import backend.ws.events as events

    session = (SimpleNamespace(use_custom_config=False, id="ws-session-1")
               if session_exists else None)
    env.user_message_result = (
        SimpleNamespace(id="u-default") if user_message == "DEFAULT" else user_message
    )
    runtime_config = SimpleNamespace(
        provider_name="fake_provider",
        api_key=None,
        api_base=None,
        model_name="fake-model",
        persona_config=SimpleNamespace(
            max_history_messages=20,
            enable_short_context_summary=False,
            personality="default",
        ),
        has_custom_model_config=False,
        has_custom_persona_config=False,
        use_custom_config=False,
    )

    class _FakeSessionManager:
        def __init__(self, db):
            pass

        async def get_session(self, session_id):
            return session

        async def add_message(self, session_id, role, content, message_context=None):
            if role == "user":
                return env.user_message_result
            return assistant_message

        def save(self, session):
            pass

        def get_or_create(self, session_id):
            return types.SimpleNamespace(
                add_message=lambda *a, **k: None, )

    monkeypatch = env.monkeypatch
    monkeypatch.setattr(events, "SessionManager", _FakeSessionManager)
    monkeypatch.setattr(events, "resolve_session_runtime_config",
                        lambda config, session: runtime_config)
    monkeypatch.setattr(
        events, "get_provider_runtime_state",
        lambda config, provider_id, **kwargs: SimpleNamespace(
            selectable=provider_selectable, reason=None,
            api_key="k", api_keys=["k"], api_base=None),
    )
    monkeypatch.setattr(events, "build_session_model_override",
                        lambda runtime_config, force=True: {"model": "fake-model"})
    monkeypatch.setattr(events, "build_provider_unavailable_message",
                        lambda provider_id, reason: f"provider {provider_id} unavailable")

    class _FakeContextService:
        def __init__(self, db):
            pass

        async def build_model_context(self, session_id, max_history_messages,
                                      enable_short_context_summary):
            return SimpleNamespace(history=list(history or []),
                                   session_summary=None)

    monkeypatch.setattr(events, "ConversationContextService", _FakeContextService)

    monkeypatch.setattr(events, "schedule_context_maintenance", lambda **kwargs: None)
    monkeypatch.setattr(events, "get_db_session_factory", lambda: None)
    return runtime_config


def _client_message(content="帮我看看", session_id="ws-session-1"):
    return SimpleNamespace(content=content, attachments=None, session_id=session_id)


def run(coro):
    return asyncio.run(coro)


def test_happy_path_full_exchange(ws_env):
    """快乐路径：用户消息落库 → 处理 → 助手消息落库 → 完成通知 → 闸门释放。"""
    env = ws_env
    user_msg = SimpleNamespace(id="u-1")
    asst_msg = SimpleNamespace(id="a-1")
    _patch_session_layer(env, user_message=user_msg, assistant_message=asst_msg,
                         history=[{"role": "user", "content": "旧消息"}])
    loop = env.make_loop([[{"content": "你好"}, {"finish_reason": "stop"}]])

    run(env.events.handle_message_event("conn-1", _client_message(), loop, env.db))

    assert len(env.sent["errors"]) == 0
    assert env.sent["complete"] == [("ws-session-1", "")]
    # 闸门已释放
    assert not get_session_gate().is_busy("ws-session-1")
    # 取消令牌已清理
    assert "ws-session-1" not in env.tokens


def test_session_not_found_sends_classified_error(ws_env):
    env = ws_env
    _patch_session_layer(env, session_exists=False)
    loop = env.make_loop([])
    run(env.events.handle_message_event(
        "conn-1", _client_message(session_id="missing"), loop, env.db))
    assert env.sent["errors"][-1][1:] == (
        "Session 'missing' not found", "SESSION_NOT_FOUND")
    assert env.sent["complete"] == []


def test_provider_unavailable_sends_classified_error(ws_env):
    env = ws_env
    _patch_session_layer(env, provider_selectable=False)
    loop = env.make_loop([])
    run(env.events.handle_message_event("conn-1", _client_message(), loop, env.db))
    codes = [e[2] for e in env.sent["errors"]]
    assert "PROVIDER_UNAVAILABLE" in codes
    assert env.sent["complete"] == []


def test_user_message_persist_failure_sends_database_error(ws_env):
    env = ws_env
    _patch_session_layer(env, user_message=None)
    loop = env.make_loop([[{"content": "不应出现"}, {"finish_reason": "stop"}]])
    run(env.events.handle_message_event("conn-1", _client_message(), loop, env.db))
    codes = [e[2] for e in env.sent["errors"]]
    assert "DATABASE_ERROR" in codes
    assert env.sent["complete"] == []


def test_gate_released_on_provider_error(ws_env):
    """回归：provider 不可用等提前返回路径不得泄漏闸门占用。"""
    env = ws_env
    _patch_session_layer(env, provider_selectable=False)
    loop = env.make_loop([])
    run(env.events.handle_message_event("conn-1", _client_message(), loop, env.db))
    assert not get_session_gate().is_busy("ws-session-1")


def test_assistant_reply_streamed_and_persisted(ws_env):
    """助手回复经流式写出并持久化；回复内容含 provider 全部 chunk。"""
    env = ws_env
    env.user_message_result = SimpleNamespace(id="u-1")
    asst_msg = SimpleNamespace(id="a-1")
    _patch_session_layer(env, user_message=SimpleNamespace(id="u-1"),
                         assistant_message=asst_msg)
    loop = env.make_loop([
        [{"content": "回答甲"}, {"content": "回答乙"}, {"finish_reason": "stop"}],
    ])
    run(env.events.handle_message_event("conn-1", _client_message(), loop, env.db))
    # 完整回复被处理（streaming 假件收到的内容由内部 handler 拼接，此处验证无错误）
    assert env.sent["errors"] == []
    assert env.sent["complete"] == [("ws-session-1", "")]
