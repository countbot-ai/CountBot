"""OpenClaw 技能加载兼容性测试。"""

import shutil
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.modules.agent.skills import SkillsLoader


def write_skill(root: Path, name: str, description: str, extra_file: bool = False) -> Path:
    """创建一个最小技能目录。"""
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        f"---\ntitle: {name}\ndescription: {description}\n---\n\n# {name}\n",
        encoding="utf-8",
    )
    if extra_file:
        (skill_dir / "notes.txt").write_text("copied", encoding="utf-8")
    return skill_file


def test_priority_order_across_sources() -> None:
    """workspace > builtin > openclaw。"""
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        workspace = root / "workspace" / "skills"
        builtin = root / "builtin"
        openclaw = root / "openclaw"

        write_skill(workspace, "shared", "workspace version")
        write_skill(builtin, "shared", "builtin version")
        write_skill(openclaw, "shared", "openclaw version")
        write_skill(builtin, "builtin-first", "builtin wins")
        write_skill(openclaw, "builtin-first", "openclaw loses")
        write_skill(openclaw, "external-only", "external only")

        loader = SkillsLoader(
            skills_dir=workspace,
            builtin_skills_dir=builtin,
            external_skills_dirs=[openclaw],
        )

        shared = loader.get_skill("shared")
        assert shared is not None
        assert shared.source == "workspace"
        assert "workspace version" in shared.content

        builtin_first = loader.get_skill("builtin-first")
        assert builtin_first is not None
        assert builtin_first.source == "builtin"
        assert "builtin wins" in builtin_first.content

        external_only = loader.get_skill("external-only")
        assert external_only is not None
        assert external_only.source == "openclaw"
        assert external_only.enabled is False


def test_external_directory_order_and_default_disabled() -> None:
    """外部目录按传入顺序去重注册，且默认发现态禁用。"""
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        workspace = root / "workspace" / "skills"
        builtin = root / "builtin"
        primary = root / "openclaw-primary"
        secondary = root / "openclaw-secondary"

        write_skill(primary, "duplicate", "primary source")
        write_skill(secondary, "duplicate", "secondary source")

        loader = SkillsLoader(
            skills_dir=workspace,
            builtin_skills_dir=builtin,
            external_skills_dirs=[primary, secondary],
        )

        skill = loader.get_skill("duplicate")
        assert skill is not None
        assert skill.source == "openclaw"
        assert skill.enabled is False
        assert "primary source" in skill.content
        assert str(skill.path).startswith(str(primary))


def test_enable_imports_openclaw_skill_into_workspace() -> None:
    """启用 OpenClaw 技能时先导入 workspace，再变为启用状态。"""
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        workspace = root / "workspace" / "skills"
        builtin = root / "builtin"
        openclaw = root / "openclaw"

        write_skill(openclaw, "demo", "import me", extra_file=True)

        loader = SkillsLoader(
            skills_dir=workspace,
            builtin_skills_dir=builtin,
            external_skills_dirs=[openclaw],
        )

        discovered = loader.get_skill("demo")
        assert discovered is not None
        assert discovered.source == "openclaw"
        assert discovered.enabled is False

        assert loader.enable_skill("demo") is True

        imported = loader.get_skill("demo")
        assert imported is not None
        assert imported.source == "workspace"
        assert imported.enabled is True
        assert imported.path == workspace / "demo" / "SKILL.md"
        assert (workspace / "demo" / "notes.txt").exists()


def test_enable_returns_false_when_openclaw_source_disappears() -> None:
    """外部技能源目录丢失时应安全失败，而不是崩溃。"""
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        workspace = root / "workspace" / "skills"
        builtin = root / "builtin"
        openclaw = root / "openclaw"

        skill_file = write_skill(openclaw, "volatile", "vanish later")
        loader = SkillsLoader(
            skills_dir=workspace,
            builtin_skills_dir=builtin,
            external_skills_dirs=[openclaw],
        )

        shutil.rmtree(skill_file.parent)
        assert loader.enable_skill("volatile") is False


def main() -> int:
    tests = [
        ("source priority", test_priority_order_across_sources),
        ("external order", test_external_directory_order_and_default_disabled),
        ("import on enable", test_enable_imports_openclaw_skill_into_workspace),
        ("missing source handled safely", test_enable_returns_false_when_openclaw_source_disappears),
    ]

    failed = []
    for name, test_func in tests:
        try:
            test_func()
            print(f"✅ {name}")
        except Exception as exc:
            failed.append((name, exc))
            print(f"❌ {name}: {exc}")

    if failed:
        return 1

    print("\nOpenClaw skills loader tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())