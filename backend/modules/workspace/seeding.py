"""工作空间内置资源播种。"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Dict, List

from loguru import logger

from backend.utils.paths import APPLICATION_ROOT


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


def seed_bundled_workspace_resources(workspace: Path) -> Dict[str, List[str] | int]:
    """把打包进应用的工作空间资源播种到当前工作空间。"""
    workspace = workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    bundled_workspace = APPLICATION_ROOT / "workspace"
    seeded_items: List[str] = []
    copied_entries = 0

    bundled_skills_dir = bundled_workspace / "skills"
    skills_seed_marker = workspace / ".builtin_skills_seeded"
    if bundled_skills_dir.is_dir() and not skills_seed_marker.exists():
        skills_dir = workspace / "skills"
        copied = _copy_directory_contents(bundled_skills_dir, skills_dir)
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
