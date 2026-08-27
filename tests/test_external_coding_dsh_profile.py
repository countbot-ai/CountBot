"""外部编码工具 dsh profile 回归测试。

覆盖：新工作区默认配置自动带出 dsh（默认禁用）；dsh 走通用 CLI 适配器
（history 模式、不注入 --session-id）；别名解析；禁用态保护。
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.modules.external_agents.adapters.cli import CliExternalAgentAdapter
from backend.modules.external_agents.base import ExternalAgentRequest
from backend.modules.external_agents.conversation import (
    profile_supports_native_session,
    resolve_effective_session_mode,
)
from backend.modules.external_agents.registry import ExternalAgentRegistry


def _load_dsh_profile(tmp_path):
    """在新工作区创建 registry（会写出默认配置），返回解析后的 dsh profile。"""
    registry = ExternalAgentRegistry(workspace=tmp_path)
    return registry, registry._load_profiles()["dsh"]


def test_default_config_contains_dsh_profile(tmp_path):
    """新工作区首次生成的 external_coding_tools.json 自动带出 dsh（默认禁用）。"""
    registry = ExternalAgentRegistry(workspace=tmp_path)
    config = json.loads(
        (tmp_path / ExternalAgentRegistry.CONFIG_FILENAME).read_text(encoding="utf-8")
    )
    profiles = {item["name"]: item for item in config["profiles"]}
    dsh = profiles.get("dsh")
    assert dsh is not None
    assert dsh["enabled"] is False
    assert dsh["type"] == "cli"
    assert dsh["command"] == "dsh"
    assert dsh["args"] == ["--profile", "headless", "{prompt}"]
    assert dsh["session_mode"] == "history"
    assert "stdin_template" not in dsh  # dsh 从 argv 读任务，不走 stdin
    assert dsh["timeout"] == 900
    assert dsh["inherit_env"] == ["DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DSH_HOME"]


def test_dsh_profile_uses_history_session_mode(tmp_path):
    """dsh 解析为 history 模式，且不会启用 native 会话。"""
    _, profile = _load_dsh_profile(tmp_path)
    assert profile.type == "cli"
    assert resolve_effective_session_mode(profile) == "history"
    assert profile_supports_native_session(profile) is False


def test_dsh_aliases_resolve_to_canonical_name(tmp_path):
    """dsh 及其别名均可解析到规范名。"""
    registry, _ = _load_dsh_profile(tmp_path)
    assert registry.resolve_profile_name("dsh") == "dsh"
    assert registry.resolve_profile_name("deepseek-harness") == "dsh"
    assert registry.resolve_profile_name("dsh-headless") == "dsh"


def test_dsh_argv_does_not_inject_session_id(tmp_path):
    """dsh 的 argv 形如 dsh --profile headless <prompt>，不注入 --session-id。"""
    registry, profile = _load_dsh_profile(tmp_path)
    adapter = CliExternalAgentAdapter()
    request = ExternalAgentRequest(
        task="hello",
        prompt="hello",
        workspace=tmp_path,
        working_dir=tmp_path,
        session_id="session-1",  # 即使携带 session_id，history 模式也不注入
    )
    argv = adapter._build_argv(
        "dsh", profile, request, adapter._build_template_variables(request)
    )
    assert argv == ["dsh", "--profile", "headless", "hello"]
    assert "--session-id" not in argv


def test_disabled_dsh_profile_is_rejected(tmp_path):
    """dsh 默认禁用：未启用时 resolve_profile 应明确拒绝。"""
    registry, _ = _load_dsh_profile(tmp_path)
    with pytest.raises(ValueError, match="disabled"):
        registry.resolve_profile("dsh")
