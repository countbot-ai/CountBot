"""SKILL.md frontmatter 解析回归测试。

核心场景：frontmatter 此前由手搓的 `split(":", 1)` 行循环解析，读不了 YAML 块标量。
`description: |` 会被解析成字面量 "|"，导致技能在系统提示词里没有任何触发语——
它显示为「已启用」，但模型永远不会激活它，且全程不报错。

除此之外还覆盖：allowed-tools / version / license 不再被丢弃、CRLF 兼容、
解析失败的降级路径、以及写入侧（build_frontmatter）与读取侧的往返一致性。
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.modules.agent.skills import (  # noqa: E402
    MAX_DESCRIPTION_LENGTH,
    Skill,
    SkillsLoader,
    build_frontmatter,
)


def make_skill(content: str, name: str = "demo") -> Skill:
    return Skill(name=name, path=Path(f"skills/{name}/SKILL.md"), content=content)


# ---------------------------------------------------------------------------
# 主回归：块标量 description
# ---------------------------------------------------------------------------

BLOCK_SCALAR_SKILL = """\
---
name: humanizer
version: 2.1.1
description: |
  Remove signs of AI-generated writing from text. Use when editing or reviewing
  text to make it sound more natural and human-written.
allowed-tools:
  - Read
  - Write
  - Edit
---

# Humanizer
"""


def test_block_scalar_description_is_parsed_not_truncated_to_pipe():
    """回归：旧解析器在这里返回字面量 "|"，技能因此永远不会被触发。"""
    skill = make_skill(BLOCK_SCALAR_SKILL, name="humanizer-1.0.0")

    desc = skill.metadata["description"]

    assert desc != "|"
    assert desc.startswith("Remove signs of AI-generated writing")
    # 触发语必须完整保留——它们才是模型判断何时用这个技能的依据
    assert "Use when editing or reviewing" in desc
    assert "human-written" in desc


def test_block_scalar_skill_reaches_the_model_prompt(tmp_path):
    """端到端：坏掉的 description 最终会进系统提示词，这里守住那条链路。"""
    skill_dir = tmp_path / "skills" / "humanizer-1.0.0"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(BLOCK_SCALAR_SKILL, encoding="utf-8")

    loader = SkillsLoader(
        skills_dir=tmp_path / "skills",
        builtin_skills_dir=tmp_path / "no-builtin",
        external_skills_dirs=[],
    )
    summary = loader.build_skills_summary()

    assert "humanizer-1.0.0" in summary          # 目录名 = 身份，模型据此拼 read_file 路径
    assert "Use when editing or reviewing" in summary
    assert ": |" not in summary


# ---------------------------------------------------------------------------
# 此前被解析后丢弃的开放标准字段
# ---------------------------------------------------------------------------

def test_allowed_tools_list_form_is_parsed():
    skill = make_skill(BLOCK_SCALAR_SKILL, name="humanizer-1.0.0")
    assert skill.metadata["allowed_tools"] == ["Read", "Write", "Edit"]


def test_allowed_tools_inline_comma_form_is_parsed():
    """Claude Code 生态里也有单行逗号分隔的写法，两种都要认。"""
    content = (
        "---\n"
        "name: agent-browser\n"
        "description: Browser automation.\n"
        "allowed-tools: Bash(npx agent-browser:*), Bash(agent-browser:*)\n"
        "---\n\n# Browser\n"
    )
    skill = make_skill(content, name="agent-browser")
    assert skill.metadata["allowed_tools"] == [
        "Bash(npx agent-browser:*)",
        "Bash(agent-browser:*)",
    ]


def test_version_and_license_are_parsed():
    content = (
        "---\n"
        "name: demo\n"
        "description: d\n"
        "version: 2.1.1\n"
        "license: MIT\n"
        "---\n\nbody\n"
    )
    skill = make_skill(content)
    assert skill.metadata["version"] == "2.1.1"
    assert skill.metadata["license"] == "MIT"


def test_version_is_not_coerced_to_float():
    """`version: 1.0` 在 YAML 里是 float，不能变成 '1.0' 以外的东西。"""
    content = "---\nname: demo\ndescription: d\nversion: 1.0\n---\n\nbody\n"
    skill = make_skill(content)
    assert skill.metadata["version"] == "1.0"


# ---------------------------------------------------------------------------
# 身份：目录名为准，frontmatter name 不一致时告警
# ---------------------------------------------------------------------------

def test_directory_name_remains_the_identity_and_mismatch_warns():
    """.skills_config.json / API 路由 / read_file 拦截都以目录名为键，不能改身份。"""
    skill = make_skill(BLOCK_SCALAR_SKILL, name="humanizer-1.0.0")

    assert skill.name == "humanizer-1.0.0"
    assert skill.metadata["name"] == "humanizer"
    assert any("不一致" in w for w in skill.metadata["warnings"])


def test_matching_name_produces_no_mismatch_warning():
    content = "---\nname: demo\ndescription: d\n---\n\nbody\n"
    skill = make_skill(content, name="demo")
    assert not any("不一致" in w for w in skill.metadata["warnings"])


def test_non_kebab_case_name_warns():
    content = "---\nname: Demo_Skill\ndescription: d\n---\n\nbody\n"
    skill = make_skill(content, name="Demo_Skill")
    assert any("kebab-case" in w for w in skill.metadata["warnings"])


# ---------------------------------------------------------------------------
# always / requires 的多种写法
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("always: true", True),
        ("always: false", False),
        ('always: "yes"', True),      # 手写字符串
        ("always: 1", True),
        ("always: no", False),
    ],
)
def test_always_accepts_bool_and_string_forms(raw, expected):
    content = f"---\nname: demo\ndescription: d\n{raw}\n---\n\nbody\n"
    skill = make_skill(content)
    assert skill.metadata["always"] is expected
    assert skill.auto_load is expected


def test_always_defaults_to_false_when_absent():
    skill = make_skill("---\nname: demo\ndescription: d\n---\n\nbody\n")
    assert skill.metadata["always"] is False


def test_legacy_metadata_json_string_still_works():
    """老写法：metadata 是一行 JSON 字符串。存量技能靠它，不能破坏。"""
    content = (
        "---\n"
        "name: demo\n"
        "description: d\n"
        'metadata: \'{"CountBot": {"always": true, "requires": {"bins": ["node"]}}}\'\n'
        "---\n\nbody\n"
    )
    skill = make_skill(content)
    assert skill.metadata["always"] is True
    assert skill.metadata["requires"] == {"bins": ["node"]}


def test_metadata_as_yaml_flow_mapping_works():
    """API 写出来的 `metadata: {"CountBot": {...}}` 恰好是合法的 YAML flow map。"""
    content = (
        "---\n"
        "name: demo\n"
        "description: d\n"
        'metadata: {"CountBot": {"always": true, "requires": {"bins": ["git"]}}}\n'
        "---\n\nbody\n"
    )
    skill = make_skill(content)
    assert skill.metadata["always"] is True
    assert skill.metadata["requires"] == {"bins": ["git"]}


def test_top_level_requires_is_supported_and_wins_over_nested():
    content = (
        "---\n"
        "name: demo\n"
        "description: d\n"
        "requires:\n"
        "  bins: [node]\n"
        "  env: [TOKEN]\n"
        'metadata: {"CountBot": {"requires": {"bins": ["ignored"]}}}\n'
        "---\n\nbody\n"
    )
    skill = make_skill(content)
    assert skill.metadata["requires"] == {"bins": ["node"], "env": ["TOKEN"]}


# ---------------------------------------------------------------------------
# 健壮性：坏输入不能让技能静默消失
# ---------------------------------------------------------------------------

def test_malformed_yaml_sets_parse_error_and_degrades_gracefully():
    """YAML 崩了也要捞回 description，并把错误显式暴露出去。"""
    content = (
        "---\n"
        "name: demo\n"
        "description: still readable\n"
        "bad: [unclosed\n"
        "---\n\nbody\n"
    )
    skill = make_skill(content)

    assert skill.metadata["parse_error"]                     # 不再静默
    assert skill.metadata["description"] == "still readable"  # 降级路径捞回来了


def test_frontmatter_that_is_not_a_mapping_sets_parse_error():
    content = "---\n- just\n- a\n- list\n---\n\nbody\n"
    skill = make_skill(content)
    assert "映射" in skill.metadata["parse_error"]


def test_missing_description_warns():
    skill = make_skill("---\nname: demo\n---\n\nbody\n")
    assert any("description" in w for w in skill.metadata["warnings"])


def test_overlong_description_warns_but_still_loads():
    long_desc = "x" * (MAX_DESCRIPTION_LENGTH + 1)
    content = f"---\nname: demo\ndescription: {long_desc}\n---\n\nbody\n"
    skill = make_skill(content)

    assert len(skill.metadata["description"]) == MAX_DESCRIPTION_LENGTH + 1  # 不截断
    assert any("超过开放标准上限" in w for w in skill.metadata["warnings"])


def test_no_frontmatter_yields_defaults():
    skill = make_skill("# Just a heading\n\nbody\n")
    assert skill.metadata["description"] == ""
    assert skill.metadata["title"] == "demo"
    assert skill.metadata["parse_error"] == ""


def test_empty_frontmatter_yields_defaults():
    skill = make_skill("---\n\n---\n\nbody\n")
    assert skill.metadata["description"] == ""
    assert skill.metadata["parse_error"] == ""


# ---------------------------------------------------------------------------
# CRLF：Windows 上编辑过的 SKILL.md
# ---------------------------------------------------------------------------

def test_crlf_frontmatter_is_parsed():
    """旧正则写死了 `^---\\n`，CRLF 文件会整段匹配不上 → 元数据全空。"""
    content = "---\r\nname: demo\r\ndescription: windows line endings\r\n---\r\n\r\n# Body\r\n"
    skill = make_skill(content)
    assert skill.metadata["description"] == "windows line endings"


def test_crlf_frontmatter_is_stripped_from_context_body(tmp_path):
    """always 技能会把全文注入提示词——frontmatter 必须被剥掉，否则 YAML 泄进 prompt。"""
    skill_dir = tmp_path / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\r\nname: demo\r\ndescription: d\r\n---\r\n\r\n# Real Body\r\n",
        encoding="utf-8",
    )

    loader = SkillsLoader(
        skills_dir=tmp_path / "skills",
        builtin_skills_dir=tmp_path / "no-builtin",
        external_skills_dirs=[],
    )
    body = loader.load_skills_for_context(["demo"])

    assert "# Real Body" in body
    assert "description:" not in body


# ---------------------------------------------------------------------------
# 写入侧：build_frontmatter 必须能被读取侧原样读回
# ---------------------------------------------------------------------------

def test_build_frontmatter_round_trips():
    content = build_frontmatter(
        name="demo",
        description="A demo skill.",
        auto_load=True,
        requirements=["node", "git"],
    ) + "# Body\n"

    skill = make_skill(content)
    assert skill.metadata["description"] == "A demo skill."
    assert skill.metadata["always"] is True
    assert skill.metadata["requires"] == {"bins": ["node", "git"]}
    assert skill.metadata["parse_error"] == ""


def test_build_frontmatter_survives_colon_in_description():
    """裸 f-string 拼接会在这里产出非法 YAML，让整个 frontmatter 解析失败。"""
    tricky = "Usage: run the tool. Note: it needs auth."
    skill = make_skill(build_frontmatter("demo", tricky) + "# Body\n")

    assert skill.metadata["parse_error"] == ""
    assert skill.metadata["description"] == tricky


@pytest.mark.parametrize(
    "tricky",
    [
        "# starts with a hash",
        "- starts with a dash",
        "multi\nline\ndescription",
        "中文描述：包含全角冒号与英文 colon: here",
        'has "double quotes" and \'single quotes\'',
        "{braces: like_yaml_flow}",
    ],
)
def test_build_frontmatter_survives_yaml_hostile_descriptions(tricky):
    skill = make_skill(build_frontmatter("demo", tricky) + "# Body\n")

    assert skill.metadata["parse_error"] == ""
    assert skill.metadata["description"] == tricky.strip()


def test_build_frontmatter_keeps_chinese_readable():
    """allow_unicode=True：中文不能被转义成 \\uXXXX，否则用户在编辑器里没法读。"""
    content = build_frontmatter("demo", "多智能体团队管理")
    assert "多智能体团队管理" in content
