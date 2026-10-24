"""chat API 的特征测试（characterization test）

先把当前可观察行为钉住，再拆分。重点是三类：

1. 路由表——23 条路由容易被漏挂载
2. 全局状态单例语义——`_global_subagent_manager` 是模块级 `global` 变量，
   拆到多模块会变成多个互不相干的单例，这是本次拆分最大的风险点
3. 模型与辅助函数的契约
"""

import pytest

import backend.api.chat as chat_api


# ---------------------------------------------------------------------------
# 路由表
# ---------------------------------------------------------------------------

EXPECTED_ROUTES = {
    ("/api/chat/sessions", ("GET",)),
    ("/api/chat/sessions", ("POST",)),
    ("/api/chat/sessions/{session_id}", ("GET",)),
    ("/api/chat/sessions/{session_id}", ("PUT",)),
    ("/api/chat/sessions/{session_id}", ("DELETE",)),
    ("/api/chat/sessions/{session_id}/messages", ("GET",)),
    ("/api/chat/sessions/{session_id}/messages", ("DELETE",)),
    ("/api/chat/sessions/{session_id}/messages/{message_id}", ("DELETE",)),
    ("/api/chat/sessions/{session_id}/messages/{message_id}/tool-calls", ("GET",)),
    ("/api/chat/tool-calls/{tool_call_id}", ("GET",)),
    ("/api/chat/sessions/{session_id}/export", ("GET",)),
    ("/api/chat/sessions/{session_id}/summary", ("PUT",)),
    ("/api/chat/sessions/{session_id}/summary", ("DELETE",)),
    ("/api/chat/sessions/{session_id}/summarize", ("POST",)),
    ("/api/chat/sessions/{session_id}/config", ("GET",)),
    ("/api/chat/sessions/{session_id}/config", ("PUT",)),
    ("/api/chat/sessions/{session_id}/config", ("DELETE",)),
    ("/api/chat/sessions/{session_id}/attachments", ("POST",)),
    ("/api/chat/sessions/{session_id}/attachments/{attachment_path:path}", ("GET",)),
    ("/api/chat/sessions/{session_id}/workspace/{file_path:path}", ("GET",)),
    ("/api/chat/workspace/{file_path:path}", ("GET",)),
    ("/api/chat/send", ("POST",)),
    ("/api/chat/preview", ("POST",)),
}


def test_route_table_unchanged():
    actual = {
        (route.path, tuple(sorted(route.methods)))
        for route in chat_api.router.routes
    }
    assert actual == EXPECTED_ROUTES
    assert len(actual) == 23


def test_router_prefix():
    assert chat_api.router.prefix == "/api/chat"


def test_no_duplicate_routes():
    keys = [
        (route.path, tuple(sorted(route.methods)))
        for route in chat_api.router.routes
    ]
    assert len(keys) == len(set(keys))


# ---------------------------------------------------------------------------
# 全局状态单例语义（拆分最大风险）
# ---------------------------------------------------------------------------


def test_subagent_manager_roundtrip():
    """set 后 get 必须拿到同一个对象。"""
    original = chat_api.get_global_subagent_manager()
    sentinel = object()
    try:
        chat_api.set_global_subagent_manager(sentinel)
        assert chat_api.get_global_subagent_manager() is sentinel
    finally:
        chat_api.set_global_subagent_manager(original)


def test_subagent_manager_is_module_level_shared():
    """状态必须挂在模块上，跨调用共享同一个引用。

    如果拆分后出现两个独立单例，本测试以外的场景（app.py 启动时设置、
    api/tasks.py 与 api/tools.py 读取）会读到 None。
    """
    original = chat_api.get_global_subagent_manager()
    try:
        chat_api.set_global_subagent_manager(None)
        assert chat_api.get_global_subagent_manager() is None
    finally:
        chat_api.set_global_subagent_manager(original)


def test_external_consumers_share_same_state():
    """app.py / tasks.py / tools.py 读到的必须是同一份状态。

    它们通过 ``from backend.api.chat import get_global_subagent_manager``
    拿到的是同一个函数对象，因此读同一份模块级变量。
    """
    from backend.api.chat import get_global_subagent_manager as imported_getter

    sentinel = object()
    original = chat_api.get_global_subagent_manager()
    try:
        chat_api.set_global_subagent_manager(sentinel)
        assert imported_getter() is sentinel
        assert imported_getter is chat_api.get_global_subagent_manager
    finally:
        chat_api.set_global_subagent_manager(original)


# ---------------------------------------------------------------------------
# 模型契约
# ---------------------------------------------------------------------------


def test_send_message_request_fields():
    fields = set(chat_api.SendMessageRequest.model_fields)
    assert fields == {"session_id", "message", "attachments"}


def test_preview_request_fields():
    fields = set(chat_api.PreviewRequest.model_fields)
    assert fields == {"session_id", "message", "attachments", "channel"}


def test_session_response_fields():
    fields = set(chat_api.SessionResponse.model_fields)
    assert "id" in fields and "name" in fields


def test_update_session_request_requires_name():
    assert set(chat_api.UpdateSessionRequest.model_fields) == {"name"}
    assert chat_api.UpdateSessionRequest.model_fields["name"].is_required()


def test_message_response_fields():
    fields = set(chat_api.MessageResponse.model_fields)
    assert {"id", "role", "content"}.issubset(fields)


# ---------------------------------------------------------------------------
# 纯函数契约
# ---------------------------------------------------------------------------


def test_validate_message_keeps_original_not_stripped():
    """返回的是原文（不做 strip），只做非空校验。"""
    assert chat_api._validate_message_or_attachments("  padded  ", None) == "  padded  "


def test_validate_message_accepts_attachments_only():
    assert chat_api._validate_message_or_attachments("", ["a.png"]) == ""


def test_validate_message_rejects_both_empty():
    with pytest.raises(Exception):
        chat_api._validate_message_or_attachments("   ", None)


def test_truncate_text_returns_tuple():
    """返回 (文本, 是否截断)。"""
    text, truncated = chat_api._truncate_text("abc", 10)
    assert text == "abc" and truncated is False


def test_truncate_text_cuts_and_marks():
    text, truncated = chat_api._truncate_text("abcdefghij", 4)
    assert truncated is True
    assert text.startswith("abcd")
    assert text.endswith("...")


def test_truncate_text_none_passthrough():
    assert chat_api._truncate_text(None, 10) == (None, False)


def test_normalize_api_mode_returns_chat_completions():
    """系统只支持 chat_completions（schema 为 Literal）。"""
    for value in ["responses", "unknown", None, "chat_completions"]:
        assert chat_api._normalize_api_mode(value) == "chat_completions"


@pytest.mark.parametrize(
    "raw,expected",
    [
        (50, 120),      # 低于下限被抬到 120
        (120, 120),
        (1200, 1200),
        (99999, 8000),  # 高于上限被压到 MAX_TOOL_PREVIEW_LIMIT
    ],
)
def test_clamp_tool_preview_limit(raw, expected):
    assert chat_api._clamp_tool_preview_limit(raw) == expected


# ---------------------------------------------------------------------------
# 导出符号
# ---------------------------------------------------------------------------


def test_public_symbols_present():
    required = {
        "router",
        "send_message",
        "preview_request",
        "get_agent_loop",
        "list_sessions",
        "create_session",
        "get_session",
        "update_session",
        "delete_session",
        "get_session_messages",
        "delete_single_message",
        "clear_session_messages",
        "export_session_context",
        "get_session_config",
        "update_session_config",
        "reset_session_config",
        "set_global_subagent_manager",
        "get_global_subagent_manager",
    }
    missing = required - set(dir(chat_api))
    assert not missing, f"缺少对外符号: {missing}"
