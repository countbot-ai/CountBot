"""ChannelMessageHandler 特征测试（拆分重构的行为基线）

目的：在 handler.py 拆分重构前锁定关键行为，重构后逐一回归。
覆盖：
- 模块可导入 + 公开方法集合快照（拆分必须保持完全一致）
- 纯函数行为：错误友好化、会话路由解析、消息上下文编解码、模型输入格式化
- 入站内容清洗：@mention 剥离
- 命令分发表：每条命令必须路由到正确的处理器
"""

import asyncio
import types

import pytest

from backend.modules.channels.base import InboundMessage
from backend.modules.channels.handler import ChannelMessageHandler


def run(coro):
    """在独立事件循环中执行协程，避免污染 pytest 的默认循环。"""
    return asyncio.run(coro)


# ------------------------------------------------------------------
# 公开 API 快照：拆分（Mixin 化、函数搬家）后此集合必须逐项一致
# ------------------------------------------------------------------

EXPECTED_METHODS = {
    "_build_assistant_message_context",
    "_build_primary_group_session_route",
    "_build_session_channel_context",
    "_build_user_message_context",
    "_get_chat_key",
    "_get_last_session_list_scope",
    "_get_or_create_session",
    "_get_or_create_session_for_route",
    "_get_route_preference_key",
    "_get_routing_preferences",
    "_get_session_by_id",
    "_get_session_history",
    "_handle_clear_history_command",
    "_handle_coder_command",
    "_handle_direct_coding_message",
    "_handle_help_command",
    "_handle_list_sessions_command",
    "_handle_new_session_command",
    "_handle_personality_command",
    "_handle_provider_command",
    "_handle_route_command",
    "_handle_stop_command",
    "_handle_switch_session_command",
    "_handle_team_command",
    "_load_recent_sessions",
    "_load_session_message_counts",
    "_maybe_notify_queued",
    "_maybe_start_channel_typing",
    "_maybe_stop_channel_typing",
    "_mirror_group_exchange_to_primary_context",
    "_prepare_external_task",
    "_process_with_agent",
    "_promote_inbound_media",
    "_rebuild_tool_registry",
    "_reconcile_mcp_tools",
    "_register_stream_abort_callback",
    "_remember_session_list_scope",
    "_resolve_channel_account_config",
    "_resolve_explicit_external_coder",
    "_resolve_runtime_config_for_session",
    "_save_message",
    "_send_reply",
    "_should_mirror_to_primary_context",
    "cancel_task",
    "get_active_tasks",
    "get_queue_stats",
    "handle_message",
    "reload_config",
    "set_channel_manager",
    "start_processing",
}


def test_public_api_snapshot():
    """ChannelMessageHandler 的方法集合必须与拆分前基线完全一致。"""
    actual = {m for m in dir(ChannelMessageHandler) if not m.startswith("__")}
    assert actual == EXPECTED_METHODS, (
        f"API 变化: 新增={sorted(actual - EXPECTED_METHODS)}, "
        f"缺失={sorted(EXPECTED_METHODS - actual)}"
    )


# ------------------------------------------------------------------
# 纯函数：_friendly_channel_error
# ------------------------------------------------------------------

def test_friendly_channel_error_mappings():
    from backend.modules.channels.handler import _friendly_channel_error

    assert "额度不足" in _friendly_channel_error("HTTP 429 quota exceeded")
    assert "余额" in _friendly_channel_error("insufficient balance 余额不足")
    assert "认证失败" in _friendly_channel_error("401 unauthorized")
    assert "密钥" in _friendly_channel_error("invalid api_key")
    assert "网络连接异常" in _friendly_channel_error("connection timeout")
    assert "上下文过长" in _friendly_channel_error("context_length_exceeded")
    assert "/new" in _friendly_channel_error("context too long")
    assert "暂时不可用" in _friendly_channel_error("503 service unavailable")
    assert _friendly_channel_error("some unknown error") == "处理消息时出错，请稍后重试。"


# ------------------------------------------------------------------
# 纯函数：_resolve_session_route
# ------------------------------------------------------------------

def _wecom_group_msg(account_id: str = "default") -> InboundMessage:
    return InboundMessage(
        channel="wecom",
        sender_id="alice",
        chat_id="wr_group_1",
        content="hello",
        metadata={
            "chatid": "wr_group_1",
            "from": {"userid": "alice", "name": "Alice"},
            "account_id": account_id,
            "sender_name": "Alice",
        },
    )


def test_session_route_wecom_group_primary():
    from backend.modules.channels.handler import _resolve_session_route

    route = _resolve_session_route(_wecom_group_msg())
    assert route["is_group"] is True
    assert route["session_scope"] == "group_shared_primary"
    assert route["context_owner_account_id"] == "default"
    assert route["use_primary_group_context"] is True
    assert route["sender_name"] == "Alice"
    assert route["target_bot_label"] == "主机器人"
    assert route["session_chat_id"] == "wr_group_1"


def test_session_route_wecom_group_secondary_account():
    from backend.modules.channels.handler import _resolve_session_route

    route = _resolve_session_route(_wecom_group_msg(account_id="bot2"))
    # 非主账号的群聊走独立会话，但路由信息仍保留主账号标记
    assert route["session_scope"] == "group_independent"
    assert route["source_account_id"] == "bot2"
    assert route["context_owner_account_id"] == "bot2"
    assert route["use_primary_group_context"] is False


def test_session_route_private_message():
    from backend.modules.channels.handler import _resolve_session_route

    msg = InboundMessage(channel="telegram", sender_id="u1", chat_id="u1", content="hi")
    route = _resolve_session_route(msg)
    assert route["is_group"] is False
    assert route["session_scope"] == "private_independent"
    assert route["session_chat_id"] == "u1"


def test_session_route_feishu_group():
    from backend.modules.channels.handler import _resolve_session_route

    msg = InboundMessage(
        channel="feishu",
        sender_id="u1",
        chat_id="oc_group",
        content="hi",
        metadata={"chat_type": "group", "sender_name": "飞书用户"},
    )
    route = _resolve_session_route(msg)
    assert route["is_group"] is True
    assert route["session_scope"] == "group_shared_primary"
    assert route["sender_name"] == "飞书用户"


# ------------------------------------------------------------------
# 纯函数：消息上下文编解码与模型输入格式化
# ------------------------------------------------------------------

def test_message_context_encode_decode_roundtrip():
    from backend.modules.channels.handler import (
        _decode_message_context,
        _encode_message_context,
    )

    ctx = {"is_group": True, "sender_name": "Alice"}
    raw = _encode_message_context(ctx)
    assert raw is not None and _decode_message_context(raw) == ctx
    # 空值与异常输入
    assert _encode_message_context(None) is None
    assert _encode_message_context({}) is None
    assert _decode_message_context(None) == {}
    assert _decode_message_context("not json") == {}
    assert _decode_message_context('["a", "b"]') == {}


def test_format_message_for_model():
    from backend.modules.channels.handler import _format_message_for_model

    group_ctx = {
        "is_group": True,
        "sender_name": "Alice",
        "target_bot_label": "主机器人",
        "session_scope": "group_shared_primary",
    }
    out = _format_message_for_model("user", "你好", group_ctx)
    assert out.startswith("[群聊消息][主机器人群上下文][发送者:Alice][目标:主机器人]")
    assert out.endswith("你好")
    # assistant 历史必须保持纯文本（不复述机器人标签）
    assert _format_message_for_model("assistant", "回复", group_ctx) == "回复"
    # 非群聊不加前缀
    assert _format_message_for_model("user", "你好", None) == "你好"
    assert _format_message_for_model("user", "你好", {"is_group": False}) == "你好"


def test_build_history_message_strips_workflow_meta_and_restores_reasoning():
    from backend.modules.channels.handler import _build_history_message

    class FakeMessage:
        role = "assistant"
        content = "结果 <!--WORKFLOW_EXEC:secret:WORKFLOW_EXEC-->"
        message_context = '{"reasoning_content": "思考过程"}'

    entry = _build_history_message(FakeMessage())
    assert entry["role"] == "assistant"
    assert "WORKFLOW_EXEC" not in entry["content"]
    assert entry["content"].strip() == "结果"
    # message_context 必须以原始 JSON 字符串参与推理还原
    assert entry["reasoning_content"] == "思考过程"

    plain = types.SimpleNamespace(role="user", content="问题", message_context=None)
    entry2 = _build_history_message(plain)
    assert entry2 == {"role": "user", "content": "问题"}


# ------------------------------------------------------------------
# 纯函数：入站内容清洗
# ------------------------------------------------------------------

def test_normalize_inbound_strips_at_mentions():
    from backend.modules.channels.handler import _normalize_channel_inbound_content

    # 飞书 @_user_N 格式
    msg = InboundMessage(channel="feishu", sender_id="u1", chat_id="c1",
                         content="@_user_1 你好")
    assert _normalize_channel_inbound_content(msg) == "你好"
    # 企业微信 <at> 格式
    msg = InboundMessage(channel="wecom", sender_id="u1", chat_id="c1",
                         content='<at user_id="x">@SBot</at> 帮我查天气')
    assert _normalize_channel_inbound_content(msg) == "帮我查天气"


def test_normalize_inbound_leading_wakeup_mention_only_at_start():
    from backend.modules.channels.handler import _normalize_channel_inbound_content

    # 群消息开头的 "@SBot " 纯文本唤醒前缀要剥掉
    msg = InboundMessage(
        channel="wecom", sender_id="u1", chat_id="wr_group",
        content="@SBot 写个爬虫",
        metadata={"chatid": "wr_group", "from": {"userid": "u1"}},
    )
    assert _normalize_channel_inbound_content(msg) == "写个爬虫"
    # 正文中间的 @ 不应被误删
    msg2 = InboundMessage(
        channel="wecom", sender_id="u1", chat_id="wr_group",
        content="提醒 alice@example.com 开会",
        metadata={"chatid": "wr_group", "from": {"userid": "u1"}},
    )
    assert _normalize_channel_inbound_content(msg2) == "提醒 alice@example.com 开会"


# ------------------------------------------------------------------
# 命令分发表：handle_message 的命令路由
# ------------------------------------------------------------------

class _FakeToolRegistry:
    """命令分发路径需要的最小工具注册表。"""

    def get_tool(self, name):
        return None

    def set_message_context(self, ctx):
        pass

    def set_session_id(self, session_id):
        pass

    def set_channel(self, channel):
        pass

    def set_cancel_token(self, token):
        pass

    def execute(self, **kwargs):
        raise AssertionError("命令分发测试不应执行工具")


class _SentinelError(Exception):
    """用于在指定深度中断 handle_message 流程的哨兵异常。"""


def _make_dispatch_handler():
    """构造一个绕过 __init__ 的 handler，命令处理器全部替换为记录器。"""
    h = object.__new__(ChannelMessageHandler)
    h.rate_limiter = None
    h.context_builder = types.SimpleNamespace()  # 无 _find_mentioned_team
    h.tool_registry = _FakeToolRegistry()
    h._active_tasks = {}
    h._route_mode_overrides = {}
    h._coder_profile_overrides = {}

    calls = []

    def recorder(name):
        async def _record(*args, **kwargs):
            calls.append((name, args, kwargs))
        return _record

    for method in [
        "_handle_new_session_command",
        "_handle_list_sessions_command",
        "_handle_switch_session_command",
        "_handle_clear_history_command",
        "_handle_stop_command",
        "_handle_help_command",
        "_handle_route_command",
        "_handle_coder_command",
        "_handle_team_command",
        "_handle_provider_command",
        "_handle_personality_command",
    ]:
        setattr(h, method, recorder(method))

    async def _send_reply(msg, content):
        calls.append(("_send_reply", (msg, content), {}))

    async def _save_message(*args, **kwargs):
        calls.append(("_save_message", args, kwargs))

    async def _get_or_create_session(msg):
        calls.append(("_get_or_create_session", (msg,), {}))
        return "sess-dispatch-test"

    async def _resolve_runtime_config_for_session(session_id):
        # 落到 Agent 主流程的深度验证点：走到这里说明没有任何命令命中
        raise _SentinelError("reached-agent-path")

    h._send_reply = _send_reply
    h._save_message = _save_message
    h._get_or_create_session = _get_or_create_session
    h._resolve_runtime_config_for_session = _resolve_runtime_config_for_session
    return h, calls


def _dispatch(content: str):
    h, calls = _make_dispatch_handler()
    msg = InboundMessage(channel="telegram", sender_id="u1", chat_id="c1",
                         content=content)
    run(h.handle_message(msg))
    return h, calls


@pytest.mark.parametrize("content,expected_handler,expected_kwargs", [
    ("/new", "_handle_new_session_command", {}),
    ("/n", "_handle_new_session_command", {}),
    ("/newsession", "_handle_new_session_command", {}),
    ("/list", "_handle_list_sessions_command", {}),
    ("/l", "_handle_list_sessions_command", {}),
    ("/ls", "_handle_list_sessions_command", {}),
    ("/all", "_handle_list_sessions_command", {"include_all": True}),
    ("/al", "_handle_list_sessions_command", {"include_all": True}),
    ("/s 3", "_handle_switch_session_command", {}),
    ("/switch abc", "_handle_switch_session_command", {}),
    ("/clear", "_handle_clear_history_command", {}),
    ("/c", "_handle_clear_history_command", {}),
    ("/stop", "_handle_stop_command", {}),
    ("/cancel", "_handle_stop_command", {}),
    ("/help", "_handle_help_command", {}),
    ("/h", "_handle_help_command", {}),
    ("/?", "_handle_help_command", {}),
    ("/route ai", "_handle_route_command", {}),
    ("/rt direct", "_handle_route_command", {}),
    ("/coder codex", "_handle_coder_command", {}),
    ("/cdr default", "_handle_coder_command", {}),
    ("/team", "_handle_team_command", {}),
    ("/team 文档组 分析文档", "_handle_team_command", {}),
    ("/provider", "_handle_provider_command", {}),
    ("/m 1", "_handle_provider_command", {}),
    ("/m openai gpt-4", "_handle_provider_command", {}),
    ("/personality", "_handle_personality_command", {}),
    ("/p friendly", "_handle_personality_command", {}),
])
def test_command_dispatch(content, expected_handler, expected_kwargs):
    """每条命令必须且只能命中对应的处理器。"""
    h, calls = _dispatch(content)
    handler_calls = [c for c in calls if c[0] == expected_handler]
    assert len(handler_calls) == 1, f"{content} 应命中 {expected_handler}，实际: {calls}"
    assert len(calls) == 1, f"{content} 不应触发其他调用: {calls}"
    for key, value in expected_kwargs.items():
        assert handler_calls[0][2].get(key) == value


def test_plain_message_falls_through_to_agent_path():
    """普通消息不应命中任何命令，应进入会话解析与 Agent 流程。"""
    h, calls = _dispatch("今天天气怎么样")
    assert any(c[0] == "_get_or_create_session" for c in calls), \
        "普通消息应进入 _get_or_create_session"
    # _save_message 在 runtime 配置解析前被调用
    assert any(c[0] == "_save_message" for c in calls), \
        "普通消息应先落库再进入 Agent 流程"
    # 哨兵异常被转换为友好错误并发送
    replies = [c for c in calls if c[0] == "_send_reply"]
    assert replies and "处理消息时出错" in replies[0][1][1]


def test_team_command_receives_dispatch_context():
    """/team 命令的转发参数（session_route 等）必须完整传递。"""
    h, calls = _dispatch("/team 数据组 跑个报表")
    team_calls = [c for c in calls if c[0] == "_handle_team_command"]
    assert len(team_calls) == 1
    kwargs = team_calls[0][2]
    assert "session_route" in kwargs
    assert "user_message_context" in kwargs
    assert "cancel_token" in kwargs
    assert kwargs["session_route"]["channel"] == "telegram"


def test_team_command_releases_gate_when_registry_setup_fails():
    """回归：workflow_tool 曾在 try 中段才定义，工具注册表准备阶段抛异常时
    finally 会 UnboundLocalError，掩盖原异常并跳过 gate.release，
    导致会话被永久占用。修复后必须正常释放闸门。"""
    from backend.modules.agent.session_gate import get_session_gate
    from backend.modules.agent.task_manager import CancellationToken
    from backend.modules.channels.commands import ChannelCommandMixin

    h, calls = _make_dispatch_handler()
    # 还原真实的 _handle_team_command（dispatch 装置里它是记录器）
    h._handle_team_command = ChannelCommandMixin._handle_team_command.__get__(h)

    class _ExplodingRegistry(_FakeToolRegistry):
        def set_message_context(self, ctx):
            if ctx is not None:
                raise RuntimeError("registry setup boom")

    h.tool_registry = _ExplodingRegistry()

    msg = InboundMessage(channel="telegram", sender_id="u1", chat_id="c1",
                         content="/team 数据组 跑报表")
    session_id = "sess-dispatch-test"

    run(h._handle_team_command(
        msg,
        "/team 数据组 跑报表",
        session_route={"channel": "telegram"},
        user_message_context={},
        cancel_token=CancellationToken(),
    ))

    # finally 必须执行完整：闸门已释放（若回归则 is_busy 恒为 True）
    assert not get_session_gate().is_busy(session_id), (
        "工具注册表异常后 gate 未释放，会话将被永久占用"
    )
