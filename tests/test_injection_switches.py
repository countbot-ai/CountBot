"""注入开关回归测试：context-injection 可控注入特性。

覆盖：
1. InjectionConfig 默认全开（向后兼容），None 与默认实例输出一致。
2. 各开关关闭后对应区块从 system prompt / user 消息中消失，最小身份保留。
3. disabled_tools 生效；sync_disabled_tools 让长连接无需重连即生效。
4. auto_memory_summary 控制后台记忆维护的 LLM 调用。
5. 相同开关配置下 system prompt 字节级稳定（prompt cache 前提）。
6. 子代理与主代理的注入开关保持一致。
"""

import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.modules.agent.context import ContextBuilder  # noqa: E402
from backend.modules.config.schema import AppConfig, InjectionConfig  # noqa: E402
from backend.modules.session import context_service as ctx_service_mod  # noqa: E402
from backend.modules.tools.setup import (  # noqa: E402
    register_all_tools,
    sync_disabled_tools,
)

SESSION_SUMMARY = "S1-summary-会话摘要"
PERSONA = SimpleNamespace(
    ai_name="小智",
    user_name="张总",
    user_address="上海",
    output_language="英文",
    personality="professional",
    custom_personality="",
)


class NoDBContextBuilder(ContextBuilder):
    """绕过 DB 访问的 ContextBuilder。"""

    def _get_personality_from_db(self, personality_id: str, custom_text: str = "") -> str:
        return f"性格描述:{personality_id}"

    def _get_active_teams_section(self) -> str:
        return "# Available Agent Teams\n\n**数据分析** (pipeline)\n  Members: 分析师 -> 写手"

    def _get_active_team_names(self):
        return ["数据分析"]


class FakeSkills:
    """最小 SkillsLoader 替身，避免依赖磁盘技能。"""

    def get_always_skills(self):
        return ["always-skill"]

    def load_skills_for_context(self, skill_names):
        return "### Skill: always-skill\n\nALWAYS-SKILL-FULL-TEXT"

    def build_skills_summary(self):
        return "- skill-a: 技能A描述"


def make_builder(tmp_path, injection_config=None) -> NoDBContextBuilder:
    return NoDBContextBuilder(
        workspace=Path(tmp_path),
        skills=FakeSkills(),
        injection_config=injection_config,
    )


def full_kwargs():
    return dict(
        history=[
            {"role": "user", "content": "上一轮问题"},
            {"role": "assistant", "content": "上一轮回答"},
        ],
        current_message="帮我总结本周工作进展 @数据分析",
        session_summary=SESSION_SUMMARY,
        media=["/tmp/ctx-attachment-notes.txt"],
        channel="feishu",
        chat_id="oc_12345",
        account_id="acc-999",
        persona_config=PERSONA,
    )


def all_off() -> InjectionConfig:
    return InjectionConfig(
        core_rules=False,
        external_coding_guidance=False,
        skills_always=False,
        skills_summary=False,
        agent_teams=False,
        dynamic_context=False,
        team_reminder=False,
        auto_memory_summary=False,
    )


# ---------------------------------------------------------------------------
# 1) 默认值与向后兼容
# ---------------------------------------------------------------------------

def test_defaults_all_enabled():
    config = InjectionConfig()
    assert all(
        [
            config.core_rules,
            config.external_coding_guidance,
            config.skills_always,
            config.skills_summary,
            config.agent_teams,
            config.dynamic_context,
            config.team_reminder,
            config.auto_memory_summary,
        ]
    )
    assert config.disabled_tools == []


def test_none_matches_default_instance(tmp_path):
    """injection_config=None（未接线）与 InjectionConfig() 输出完全一致。"""
    kwargs = full_kwargs()
    assert (
        make_builder(tmp_path, None).build_system_prompt()
        == make_builder(tmp_path, InjectionConfig()).build_system_prompt()
    )
    assert (
        make_builder(tmp_path, None).build_messages(**kwargs)
        == make_builder(tmp_path, InjectionConfig()).build_messages(**kwargs)
    )


def test_default_injection_keeps_all_sections(tmp_path):
    builder = make_builder(tmp_path, InjectionConfig())
    prompt = builder.build_system_prompt()
    for anchor in (
        "# Identity",
        "## Personality",
        "## CountBot Docs",
        "ALWAYS-SKILL-FULL-TEXT",
        "skill-a",
        "# Available Agent Teams",
        "External coding agent",
    ):
        assert anchor in prompt, anchor

    user_content = builder.build_messages(**full_kwargs())[-1]["content"]
    for anchor in ("Current time", SESSION_SUMMARY, "Team invocation detected", "/tmp/ctx-attachment-notes.txt"):
        assert anchor in user_content, anchor


# ---------------------------------------------------------------------------
# 2) 开关关闭后的行为
# ---------------------------------------------------------------------------

def test_all_off_leaves_minimal_identity_and_clean_user_message(tmp_path):
    builder = make_builder(tmp_path, all_off())
    prompt = builder.build_system_prompt()

    assert "# Identity" in prompt and "## Personality" in prompt
    for removed in (
        "## CountBot Docs",
        "## Safety",
        "ALWAYS-SKILL-FULL-TEXT",
        "skill-a",
        "# Available Agent Teams",
    ):
        assert removed not in prompt, removed

    messages = builder.build_messages(**full_kwargs())
    user_content = messages[-1]["content"]
    for removed in ("Current time", SESSION_SUMMARY, "Team invocation detected", "Channel: feishu"):
        assert removed not in user_content, removed
    # 原始内容与附件提示不受开关影响
    assert "帮我总结本周工作进展" in user_content
    assert "/tmp/ctx-attachment-notes.txt" in user_content
    assert messages[0]["role"] == "system"


def test_core_rules_off_keeps_identity_and_other_sections(tmp_path):
    prompt = make_builder(tmp_path, InjectionConfig(core_rules=False)).build_system_prompt()
    assert "# Identity" in prompt
    for removed in ("## CountBot Docs", "## Tools & Execution", "## Memory", "## Safety"):
        assert removed not in prompt
    assert "skill-a" in prompt and "# Available Agent Teams" in prompt


def test_external_coding_guidance_independent_switch(tmp_path):
    off = make_builder(
        tmp_path, InjectionConfig(external_coding_guidance=False)
    ).build_system_prompt()
    assert "## Tools & Execution" in off
    assert "External coding agent" not in off
    assert "External coding agent" in make_builder(tmp_path, InjectionConfig()).build_system_prompt()


def test_skills_switches(tmp_path):
    prompt = make_builder(
        tmp_path, InjectionConfig(skills_always=False, skills_summary=False)
    ).build_system_prompt()
    assert "ALWAYS-SKILL-FULL-TEXT" not in prompt
    assert "skill-a" not in prompt
    assert "# Available Skills" not in prompt
    assert "## CountBot Docs" in prompt


def test_agent_teams_off(tmp_path):
    prompt = make_builder(tmp_path, InjectionConfig(agent_teams=False)).build_system_prompt()
    assert "# Available Agent Teams" not in prompt
    assert "## CountBot Docs" in prompt


def test_dynamic_context_off(tmp_path):
    user_content = make_builder(
        tmp_path, InjectionConfig(dynamic_context=False)
    ).build_messages(**full_kwargs())[-1]["content"]
    for removed in ("Current time", SESSION_SUMMARY, "Channel: feishu"):
        assert removed not in user_content
    # team_reminder 是独立开关，仍然注入
    assert "Team invocation detected" in user_content


def test_team_reminder_off(tmp_path):
    user_content = make_builder(
        tmp_path, InjectionConfig(team_reminder=False)
    ).build_messages(**full_kwargs())[-1]["content"]
    assert "Team invocation detected" not in user_content
    assert "Current time" in user_content


# ---------------------------------------------------------------------------
# 3) 工具开关
# ---------------------------------------------------------------------------

def test_disabled_tools_removed_from_registry(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    baseline = register_all_tools(workspace=workspace)
    assert {"wiki", "screenshot"} <= set(baseline.list_tools())

    filtered = register_all_tools(
        workspace=workspace, disabled_tools=["screenshot", "wiki", "not-a-real-tool"]
    )
    names = set(filtered.list_tools())
    assert "screenshot" not in names and "wiki" not in names
    assert {"read_file", "exec"} <= names

    definition_names = {
        (d.get("function") or d).get("name") for d in filtered.get_definitions()
    }
    assert "screenshot" not in definition_names and "wiki" not in definition_names


def test_sync_disabled_tools_updates_live_registry(tmp_path):
    """长连接场景：改开关后无需重建注册表对象，下一次请求即生效。"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    registry = register_all_tools(workspace=workspace)
    original_defs = len(registry.get_definitions())

    assert sync_disabled_tools(registry, ["wiki"]) is True
    assert "wiki" not in registry.list_tools()
    assert len(registry.get_definitions()) == original_defs - 1

    # 重复同步同一配置不应重建
    assert sync_disabled_tools(registry, ["wiki"]) is False

    # 取消禁用后工具恢复
    assert sync_disabled_tools(registry, []) is True
    assert "wiki" in registry.list_tools()
    assert len(registry.get_definitions()) == original_defs


# ---------------------------------------------------------------------------
# 4) 后台记忆维护开关
# ---------------------------------------------------------------------------

class _FakeService:
    calls = None

    def __init__(self, db):
        pass

    async def refresh_short_summary_cache(self, **kwargs):
        self.calls["short"] += 1

    async def summarize_overflow_to_memory(self, **kwargs):
        self.calls["overflow"] += 1

    async def maybe_auto_summarize_to_memory(self, **kwargs):
        self.calls["whole"] += 1


class _FakeSessionFactory:
    def __call__(self):
        class _Ctx:
            async def __aenter__(self):
                return object()

            async def __aexit__(self, *args):
                return False

        return _Ctx()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "enabled,expected",
    [
        (False, {"short": 1, "overflow": 0, "whole": 0}),
        (True, {"short": 1, "overflow": 1, "whole": 1}),
    ],
)
async def test_auto_memory_summary_switch(monkeypatch, enabled, expected):
    calls = {"short": 0, "overflow": 0, "whole": 0}
    _FakeService.calls = calls
    monkeypatch.setattr(ctx_service_mod, "ConversationContextService", _FakeService)

    task = ctx_service_mod.schedule_context_maintenance(
        db_session_factory=_FakeSessionFactory(),
        session_id=f"session-{enabled}",
        max_history_messages=20,
        enable_short_context_summary=True,
        provider=object(),
        model="m",
        memory_store=None,
        enable_auto_memory_summary=enabled,
    )
    await task
    assert calls == expected


# ---------------------------------------------------------------------------
# 5) prompt cache 稳定性
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("injection", [InjectionConfig(), None])
def test_system_prompt_stable_across_time(tmp_path, monkeypatch, injection):
    import backend.modules.agent.context as ctx_mod

    builder = make_builder(tmp_path, injection)
    times = iter([datetime(2026, 9, 3, 10, 30, 5), datetime(2026, 9, 3, 11, 35, 5)])

    class FrozenDT:
        @staticmethod
        def now():
            return next(times)

    monkeypatch.setattr(ctx_mod, "datetime", FrozenDT)
    assert builder.build_system_prompt() == builder.build_system_prompt()


# ---------------------------------------------------------------------------
# 6) 配置集成与子代理一致性
# ---------------------------------------------------------------------------

def test_app_config_injection_roundtrip(tmp_path):
    workspace_arg = {"path": str(tmp_path)}
    config = AppConfig(workspace=workspace_arg)
    assert config.injection.core_rules is True

    dumped = config.model_dump()
    assert "injection" in dumped
    assert AppConfig(**dumped).injection.disabled_tools == []

    # 旧配置（无 injection 段）反序列化后取默认值
    legacy = AppConfig(**{k: v for k, v in dumped.items() if k != "injection"})
    assert legacy.injection.core_rules is True


def test_subagent_prompt_respects_skills_switch(tmp_path):
    from backend.modules.agent.subagent import SubagentManager

    class _Provider:
        timeout = 120.0
        max_retries = 3

    def make_manager(injection):
        config = AppConfig(workspace={"path": str(tmp_path)})
        if injection is not None:
            config.injection = injection
        return SubagentManager(
            provider=_Provider(),
            workspace=Path(tmp_path),
            model="m",
            config_loader=SimpleNamespace(config=config),
            skills=FakeSkills(),
        )

    assert "skill-a" in make_manager(None)._build_subagent_prompt("任务", enable_skills=True)
    assert (
        "skill-a"
        not in make_manager(InjectionConfig(skills_summary=False))._build_subagent_prompt(
            "任务", enable_skills=True
        )
    )
