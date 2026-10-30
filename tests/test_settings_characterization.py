"""settings API 的特征测试（characterization test）

目的不是验证「行为是否正确」，而是把当前可观察行为钉住，使后续拆分/重构
一旦改变行为就能立刻发现。

覆盖三层：
1. 路由表——拆分时最容易漏挂载
2. 纯函数——校验与归一化逻辑，无需启动服务
3. 模型契约——请求/响应字段名与默认值
"""

import pytest

import backend.api.settings as settings_api


# ---------------------------------------------------------------------------
# 路由表：拆分后必须完全一致
# ---------------------------------------------------------------------------

# 基线：(path, methods)。注意实际路径带分组前缀（如 /workspace/info），
# 与函数名不一一对应，因此这里逐条钉住而不是靠命名推断。
EXPECTED_ROUTES = {
    ("/api/settings", ("GET",)),
    ("/api/settings", ("PUT",)),
    ("/api/settings/security/dangerous-patterns", ("GET",)),
    ("/api/settings/providers", ("GET",)),
    # provider 模型管理与连通性测试：随「模型目录/排序」功能加入
    ("/api/settings/providers/{provider_id}/models", ("POST",)),
    ("/api/settings/providers/{provider_id}/models/catalog", ("GET",)),
    ("/api/settings/providers/{provider_id}/models/order", ("PUT",)),
    ("/api/settings/providers/{provider_id}/models/{model_id}", ("PUT",)),
    ("/api/settings/providers/{provider_id}/models/{model_id}", ("DELETE",)),
    ("/api/settings/providers/{provider_id}/test", ("POST",)),
    ("/api/settings/reasoning-levels", ("GET",)),
    ("/api/settings/external-coding-tools", ("GET",)),
    ("/api/settings/external-coding-tools", ("PUT",)),
    ("/api/settings/external-coding-tools/check", ("POST",)),
    ("/api/settings/test-connection", ("POST",)),
    ("/api/settings/workspace/select-directory", ("POST",)),
    ("/api/settings/workspace/info", ("GET",)),
    ("/api/settings/workspace/clean-temp", ("POST",)),
    ("/api/settings/workspace/set-path", ("POST",)),
    ("/api/settings/export", ("GET",)),
    ("/api/settings/import", ("POST",)),
}


def test_route_table_unchanged():
    actual = {
        (route.path, tuple(sorted(route.methods)))
        for route in settings_api.router.routes
    }
    assert actual == EXPECTED_ROUTES


def test_no_duplicate_routes():
    keys = [
        (route.path, tuple(sorted(route.methods)))
        for route in settings_api.router.routes
    ]
    assert len(keys) == len(set(keys)), "存在重复注册的路由"


# ---------------------------------------------------------------------------
# 纯函数：校验与归一化
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    ["chat_completions", "responses", "CHAT_COMPLETIONS", "unknown-mode", None, ""],
)
def test_normalize_api_mode_always_chat_completions(raw):
    """系统只支持 chat_completions（schema 中为 Literal），任何输入都应归一到该值。"""
    assert settings_api._normalize_api_mode_value(raw) == "chat_completions"


@pytest.mark.parametrize(
    "raw,expected",
    [
        (True, True),
        (False, False),
        (1, True),
        (0, False),
        ("true", True),
        ("false", False),
        ("yes", True),
        ("no", False),
        ("on", True),
        ("off", False),
        ("1", True),
        ("0", False),
        ("  TRUE  ", True),
    ],
)
def test_coerce_boolean_value(raw, expected):
    assert settings_api._coerce_boolean_value(raw, field_name="x") is expected


@pytest.mark.parametrize("raw", ["unexpected", "maybe", 2, [], {}])
def test_coerce_boolean_value_rejects_ambiguous(raw):
    """模糊输入必须拒绝，不能默认成 False——否则用户以为关掉了其实没关。"""
    with pytest.raises(Exception):
        settings_api._coerce_boolean_value(raw, field_name="x")


def test_normalize_pattern_list_strips_and_dedupes():
    result = settings_api._normalize_pattern_list([" a ", "a", "", "  ", "b"])
    assert result == ["a", "b"]


def test_normalize_pattern_list_handles_none():
    assert settings_api._normalize_pattern_list(None) == []


def test_validate_regex_patterns_accepts_valid():
    settings_api._validate_regex_patterns_or_raise(["^abc$", "\\d+"], field_name="patterns")


def test_validate_regex_patterns_rejects_invalid():
    with pytest.raises(Exception):
        settings_api._validate_regex_patterns_or_raise(["(unclosed"], field_name="patterns")


def test_validate_cron_schedule_accepts_valid_and_returns_normalized():
    assert settings_api._validate_cron_schedule_or_raise(" 0 9 * * * ", field_name="s") == "0 9 * * *"


def test_validate_cron_schedule_rejects_invalid():
    with pytest.raises(Exception):
        settings_api._validate_cron_schedule_or_raise("not a cron", field_name="s")


def test_validate_cron_schedule_rejects_empty():
    with pytest.raises(Exception):
        settings_api._validate_cron_schedule_or_raise("", field_name="s")


def test_deep_merge_overrides_nested():
    base = {"a": 1, "b": {"x": 1, "y": 2}}
    override = {"b": {"y": 99, "z": 3}}
    merged = settings_api._deep_merge(base, override)
    assert merged == {"a": 1, "b": {"x": 1, "y": 99, "z": 3}}


def test_deep_merge_adds_new_keys():
    assert settings_api._deep_merge({}, {"k": 1}) == {"k": 1}


# ---------------------------------------------------------------------------
# 模型契约：字段名与默认值
# ---------------------------------------------------------------------------


def test_settings_response_fields():
    fields = set(settings_api.SettingsResponse.model_fields)
    assert fields == {
        "providers",
        "model",
        "workspace",
        "security",
        "persona",
        "injection",
        "workspace_migration",
    }


def test_update_settings_request_sections_optional():
    """所有分区可省略——部分更新依赖这一点。"""
    for name in ("providers", "model", "workspace", "security", "persona", "injection"):
        field = settings_api.UpdateSettingsRequest.model_fields[name]
        assert field.default is None


def test_test_connection_request_requires_provider():
    assert settings_api.TestConnectionRequest.model_fields["provider"].is_required()


def test_injection_config_response_fields():
    fields = set(settings_api.InjectionConfigResponse.model_fields)
    assert fields == {
        "core_rules",
        "external_coding_guidance",
        "skills_always",
        "skills_summary",
        "agent_teams",
        "dynamic_context",
        "team_reminder",
        "disabled_tools",
        "auto_memory_summary",
    }


def test_import_settings_request_fields():
    fields = set(settings_api.ImportSettingsRequest.model_fields)
    assert fields == {"version", "config", "merge", "sections"}
    assert settings_api.ImportSettingsRequest.model_fields["merge"].default is False


# ---------------------------------------------------------------------------
# 公开导出的符号（拆分需保持）
# ---------------------------------------------------------------------------


def test_public_symbols_present():
    required = {
        "router",
        "get_settings",
        "update_settings",
        "export_settings",
        "import_settings",
        "test_connection",
        "select_directory",
        "get_workspace_info",
        "set_workspace_path",
        "clean_temp_files",
        "get_available_providers",
        "get_dangerous_patterns",
        "get_external_coding_tools_config",
        "update_external_coding_tools_config",
        "check_external_coding_tool_profile",
    }
    missing = required - set(dir(settings_api))
    assert not missing, f"缺少对外符号: {missing}"
