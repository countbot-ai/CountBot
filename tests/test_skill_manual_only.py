"""技能「仅显式调用」状态测试

对应 pi 的 disable-model-invocation：技能可用但不进入模型可见清单。
"""

from pathlib import Path

from backend.modules.agent.skills import SkillsLoader


def _loader(tmp_path: Path) -> SkillsLoader:
    return SkillsLoader(
        skills_dir=tmp_path / "skills",
        builtin_skills_dir=tmp_path / "nonexistent-builtin",
        external_skills_dirs=[],
    )


def _write_skill(root: Path, name: str, frontmatter_extra: str = "", body: str = "body"):
    d = root / "skills" / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {name} description\n{frontmatter_extra}---\n{body}\n",
        encoding="utf-8",
    )


def test_manual_only_parsed_from_hyphen_form(tmp_path):
    _write_skill(tmp_path, "big-skill", "disable-model-invocation: true\n")
    loader = _loader(tmp_path)
    assert loader.get_skill("big-skill").manual_only is True


def test_manual_only_parsed_from_underscore_form(tmp_path):
    _write_skill(tmp_path, "big-skill", "disable_model_invocation: true\n")
    loader = _loader(tmp_path)
    assert loader.get_skill("big-skill").manual_only is True


def test_normal_skill_is_not_manual_only(tmp_path):
    _write_skill(tmp_path, "normal")
    loader = _loader(tmp_path)
    assert loader.get_skill("normal").manual_only is False


def test_manual_only_excluded_from_summary(tmp_path):
    _write_skill(tmp_path, "visible")
    _write_skill(tmp_path, "hidden-skill", "disable-model-invocation: true\n")
    loader = _loader(tmp_path)

    summary = loader.build_skills_summary()
    # 不进入正式清单
    assert "- hidden-skill:" not in summary
    assert "- visible:" in summary
    # 但要点名，避免用户以为技能消失
    assert "hidden-skill" in summary
    assert "仅在用户显式点名时使用" in summary


def test_manual_only_not_auto_injected_even_with_always(tmp_path):
    _write_skill(tmp_path, "both-flags", "always: true\ndisable-model-invocation: true\n")
    loader = _loader(tmp_path)

    assert loader.get_always_skills() == []
    assert loader.load_skills_for_context(["both-flags"]) != ""


def test_manual_only_skill_still_readable(tmp_path):
    _write_skill(tmp_path, "big-skill", "disable-model-invocation: true\n", body="SPECIAL_BODY")
    loader = _loader(tmp_path)

    content = loader.load_skills_for_context(["big-skill"])
    assert "SPECIAL_BODY" in content
