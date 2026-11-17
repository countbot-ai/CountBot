"""工作空间内置资源播种。"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Dict, List, Set

from loguru import logger

from backend.utils.paths import APPLICATION_ROOT

_SKILL_FILE = "SKILL.md"
# 内置技能清单：随应用分发，用于区分「内置技能」与「自建技能」
_BUILTIN_MANIFEST_NAME = ".builtin-skills.json"


def bundled_skills_dir() -> Path:
    """随应用分发的技能目录。"""
    return APPLICATION_ROOT / "workspace" / "skills"


def builtin_skill_manifest_path() -> Path:
    """内置技能清单文件路径（随应用分发）。"""
    return bundled_skills_dir() / _BUILTIN_MANIFEST_NAME


def builtin_skill_names() -> Set[str]:
    """内置技能名集合。

    有清单时以清单为准：清单外的技能视为自建，不参与共享模式的只读下发。
    没有清单时回退为扫描内置目录，保持旧行为。
    """
    manifest = builtin_skill_manifest_path()
    if manifest.is_file():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(f"读取内置技能清单失败，回退目录扫描: {exc}")
        else:
            if isinstance(data, dict):
                data = data.get("builtin")
            if isinstance(data, list):
                return {str(item).strip() for item in data if str(item).strip()}
            logger.warning("内置技能清单格式非法，回退目录扫描")

    root = bundled_skills_dir()
    if not root.is_dir():
        return set()
    return {
        entry.name
        for entry in root.iterdir()
        if entry.is_dir() and (entry / _SKILL_FILE).is_file()
    }


def bundled_skill_copy_names(workspace: Path) -> Set[str]:
    """识别工作区里由初始化播种产生的内置技能副本，不算用户私有技能。"""
    source_root = bundled_skills_dir()
    target_root = workspace / "skills"
    if not source_root.is_dir() or not target_root.is_dir():
        return set()

    return {
        entry.name
        for entry in source_root.iterdir()
        if entry.is_dir()
        and (entry / _SKILL_FILE).is_file()
        and (target_root / entry.name / _SKILL_FILE).is_file()
    }


def _copy_directory_contents(source: Path, target: Path) -> int:
    """只复制目标目录中缺失的条目。"""
    copied_count = 0
    target.mkdir(parents=True, exist_ok=True)

    for child in source.iterdir():
        destination = target / child.name
        if destination.exists():
            continue
        if child.is_dir():
            shutil.copytree(child, destination)
        else:
            shutil.copy2(child, destination)
        copied_count += 1

    return copied_count


def seed_bundled_workspace_resources(
    workspace: Path, *, include_skills: bool = True
) -> Dict[str, List[str] | int]:
    """把打包进应用的工作空间资源播种到当前工作空间。

    用户工作区不播种技能：内置技能由管理员通过共享策略下发，复制进私有
    目录会让普通用户看到并可改写管理员的技能集合。
    """
    workspace = workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    bundled_workspace = APPLICATION_ROOT / "workspace"
    seeded_items: List[str] = []
    copied_entries = 0

    bundled_skills = bundled_skills_dir()
    skills_seed_marker = workspace / ".builtin_skills_seeded"
    if include_skills and bundled_skills.is_dir() and not skills_seed_marker.exists():
        skills_dir = workspace / "skills"
        copied = _copy_directory_contents(bundled_skills, skills_dir)
        skills_seed_marker.write_text("seeded\n", encoding="utf-8")
        copied_entries += copied
        seeded_items.append("skills")
        logger.info(
            "Seeded {} bundled skill entry(s) into workspace: {}",
            copied,
            skills_dir,
        )

    bundled_quick_reference = bundled_workspace / "AI_QUICK_REFERENCE.md"
    if bundled_quick_reference.is_dir():
        bundled_quick_reference = bundled_quick_reference / "AI_QUICK_REFERENCE.md"

    quick_reference_marker = workspace / ".ai_quick_reference_seeded"
    quick_reference_target = workspace / "AI_QUICK_REFERENCE.md"
    if bundled_quick_reference.is_file() and not quick_reference_marker.exists():
        if not quick_reference_target.exists():
            shutil.copy2(bundled_quick_reference, quick_reference_target)
            copied_entries += 1
        quick_reference_marker.write_text("seeded\n", encoding="utf-8")
        seeded_items.append("AI_QUICK_REFERENCE.md")
        logger.info(
            "Seeded bundled AI quick reference into workspace: {}",
            quick_reference_target,
        )

    return {
        "workspace": str(workspace),
        "seeded_items": seeded_items,
        "copied_entries": copied_entries,
    }
