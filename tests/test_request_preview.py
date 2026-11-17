"""请求预览测试

覆盖：system prompt 分节拼装与整段输出一致、注入开关的呈现、动态上下文的识别。
"""

from pathlib import Path
from types import SimpleNamespace

from backend.modules.agent.context import ContextBuilder
from backend.modules.agent.request_preview import build_request_preview
from backend.modules.config.schema import InjectionConfig


def _make_builder(tmp_path: Path, injection=None, persona=None) -> ContextBuilder:
    return ContextBuilder(
        workspace=tmp_path,
        memory=None,
        skills=None,
        persona_config=persona,
        injection_config=injection if injection is not None else InjectionConfig(),
    )


def _persona():
    return SimpleNamespace(
        ai_name="小C",
        user_name="主人",
        user_address="",
        output_language="中文",
        personality="blunt",
        custom_personality="",
    )


def test_sections_join_equals_full_prompt(tmp_path):
    """分节拼装结果必须与整段构建完全一致，重构不改变既有行为。"""
    builder = _make_builder(tmp_path)
    sections = builder.build_system_prompt_sections()
    joined = "\n\n---\n\n".join(item["content"].rstrip() for item in sections)
    assert joined == builder.build_system_prompt()


def test_sections_include_identity_and_rules(tmp_path):
    builder = _make_builder(tmp_path)
    names = [item["name"] for item in builder.build_system_prompt_sections()]
    assert names[0] == "identity"
    assert "rules" in names


def test_sections_drop_rules_when_disabled(tmp_path):
    builder = _make_builder(tmp_path, InjectionConfig(core_rules=False))
    names = [item["name"] for item in builder.build_system_prompt_sections()]
    assert "identity" in names
    assert "rules" not in names


def test_preview_reports_switch_ownership(tmp_path):
    """每个区块都应标注受哪个开关控制。"""
    builder = _make_builder(tmp_path, InjectionConfig(core_rules=False))
    preview = build_request_preview(builder, message="你好", persona_config=_persona())

    by_name = {item["name"]: item for item in preview["sections"]}

    # identity 是混合区块：名称恒注入、环境信息随 core_rules
    identity = by_name["identity"]
    assert identity["partial"] is True
    assert identity["controlled_by"] == ["core_rules"]
    assert identity["switch_states"]["always"] is True
    assert identity["switch_states"]["core_rules"] is False


def test_identity_chars_shrink_when_core_rules_disabled(tmp_path):
    """关闭 core_rules 时 identity 应实际变短，预览需如实反映。"""
    with_env = _make_builder(tmp_path, InjectionConfig(core_rules=True))
    without = _make_builder(tmp_path, InjectionConfig(core_rules=False))

    p1 = build_request_preview(with_env, message="hi", persona_config=_persona())
    p2 = build_request_preview(without, message="hi", persona_config=_persona())

    s1 = {s["name"]: s for s in p1["sections"]}["identity"]
    s2 = {s["name"]: s for s in p2["sections"]}["identity"]

    assert s2["chars"] < s1["chars"]


def test_preview_user_message_has_no_dynamic_context_when_disabled(tmp_path):
    """动态上下文关闭时，首条用户消息应只有用户原文。"""
    builder = _make_builder(tmp_path, InjectionConfig(dynamic_context=False))
    preview = build_request_preview(
        builder,
        message="我是谁",
        session_summary="之前的摘要内容",
        channel="web-chat",
        chat_id="c1",
        persona_config=_persona(),
    )
    assert preview["first_user_message"] == "我是谁"
    assert preview["dynamic_context"] == ""


def test_preview_user_message_contains_dynamic_context_when_enabled(tmp_path):
    """开启后动态上下文应出现在首条用户消息里，并被单独识别出来。"""
    builder = _make_builder(tmp_path, InjectionConfig(dynamic_context=True))
    preview = build_request_preview(
        builder,
        message="现在几点",
        session_summary="之前的摘要内容",
        channel="web-chat",
        chat_id="c1",
        persona_config=_persona(),
    )
    assert "Current time" in preview["first_user_message"]
    assert "主人" in preview["first_user_message"]
    assert "Current time" in preview["dynamic_context"]


def test_preview_lists_switch_states(tmp_path):
    injection = InjectionConfig(dynamic_context=False, disabled_tools=["wiki"])
    builder = _make_builder(tmp_path, injection)
    preview = build_request_preview(builder, message="hi", persona_config=_persona())

    assert preview["injection"]["dynamic_context"] is False
    assert preview["injection"]["core_rules"] is True
    assert preview["injection"]["disabled_tools"] == ["wiki"]


def test_preview_counts_tools(tmp_path):
    """传入工具注册表时应列出工具定义。"""
    class _Registry:
        def get_definitions(self):
            return [
                {
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "description": "read a file",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ]

    builder = _make_builder(tmp_path)
    preview = build_request_preview(
        builder,
        message="hi",
        persona_config=_persona(),
        tool_registry=_Registry(),
    )
    assert preview["tool_count"] == 1
    assert preview["tools"][0]["name"] == "read_file"
    assert preview["tool_chars"] > 0


def test_preview_survives_broken_registry(tmp_path):
    """工具注册表异常时预览仍应返回，不能整块 500。"""
    class _BrokenRegistry:
        def get_definitions(self):
            raise RuntimeError("registry down")

    builder = _make_builder(tmp_path)
    preview = build_request_preview(
        builder,
        message="hi",
        persona_config=_persona(),
        tool_registry=_BrokenRegistry(),
    )
    assert preview["tool_count"] == 0
    assert preview["system_prompt"]
