"""共享技能：不可变快照 + 审核分发；禁止携带脚本与 ``always: true``。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml
from loguru import logger
from sqlalchemy import select

from backend.models.skill import (
    SCOPE_USER,
    STATUS_APPROVED,
    STATUS_DRAFT,
    STATUS_PENDING,
    STATUS_REJECTED,
    STATUS_REVOKED,
    VISIBILITY_PRIVATE,
    VISIBILITY_SHARED,
    SkillRegistry,
    UserSkillState,
)

# 管理员共享技能的归档分区：管理员没有用户工作区，用固定标识承载其发布记录
SYSTEM_OWNER_ID = "__system__"

MAX_PUBLISHED_SKILLS_PER_USER = 20
MAX_AUDIENCE_USERS = 200
MAX_SNAPSHOT_FILES = 60
MAX_SNAPSHOT_FILE_BYTES = 512 * 1024
MAX_SNAPSHOT_TOTAL_BYTES = 4 * 1024 * 1024

# 交换文件名，禁止覆盖 SKILL.md
_SKILL_FILE = "SKILL.md"
# 技能目录名可带版本号，但不允许连续点号
_SKILL_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")
_SHARED_ROOT_DIRNAME = ".shared-skills"


class SharedSkillError(ValueError):
    """共享技能操作未通过校验。"""


# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------


def shared_skills_root() -> Path:
    """共享技能快照根目录：``<全局工作区>/.shared-skills``。"""
    from backend.modules.workspace import get_global_workspace_path

    root = get_global_workspace_path() / _SHARED_ROOT_DIRNAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def user_skills_dir(user) -> Path:
    """当前用户的私有技能目录。"""
    from backend.modules.workspace import resolve_user_workspace

    skills_dir = resolve_user_workspace(user) / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    return skills_dir


def snapshot_dir(skill_id: str, version: int) -> Path:
    """某版本的快照目录。"""
    return shared_skills_root() / skill_id / str(version)


def resolve_storage_path(storage_path: str) -> Optional[Path]:
    """把登记的相对路径还原成绝对路径；不存在则返回 None。"""
    if not storage_path:
        return None
    from backend.modules.workspace import get_global_workspace_path

    candidate = (get_global_workspace_path() / storage_path).resolve()
    # 防越界：快照必须落在 .shared-skills 之内
    root = shared_skills_root().resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        logger.warning(f"Shared skill storage path escapes root: {storage_path}")
        return None
    return candidate if candidate.is_dir() else None


# ---------------------------------------------------------------------------
# 技能文件解析与校验
# ---------------------------------------------------------------------------


def _extract_frontmatter(content: str) -> Optional[str]:
    """取出 SKILL.md 的 YAML frontmatter 原文；没有则返回 None。"""
    text = content.lstrip("\ufeff")
    if not text.startswith("---"):
        return None
    parts = re.split(r"\r?\n---\s*\r?\n", text, maxsplit=1)
    if len(parts) < 2:
        return None
    return parts[0][3:].lstrip("\r\n")


def read_skill_frontmatter(skill_dir: Path) -> Dict[str, Any]:
    """读取技能 frontmatter；文件缺失或非法直接抛错。"""
    skill_file = skill_dir / _SKILL_FILE
    if not skill_file.is_file():
        raise SharedSkillError(f"技能目录缺少 {_SKILL_FILE}")
    try:
        content = skill_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise SharedSkillError(f"无法读取技能文件: {exc}") from exc

    raw = _extract_frontmatter(content)
    if raw is None:
        raise SharedSkillError("技能文件缺少 frontmatter，无法发布")
    try:
        data = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        raise SharedSkillError(f"frontmatter 不是合法 YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise SharedSkillError("frontmatter 必须是键值映射")
    return data


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def validate_publishable(skill_dir: Path, declared_name: str) -> Dict[str, Any]:
    """校验一个技能能否作为共享技能发布，返回 frontmatter。

    拒绝项：非法目录名、``always: true``、符号链接或超限资源。
    """
    if not _SKILL_NAME_RE.match(declared_name or "") or ".." in declared_name:
        raise SharedSkillError(
            "技能名只能包含字母、数字、点号、下划线与连字符（1-64 位，且不含连续点号）"
        )

    data = read_skill_frontmatter(skill_dir)

    # 加载按目录名寻址，frontmatter 的 name 只用于展示，不一致不影响使用
    if _coerce_bool(data.get("always")):
        raise SharedSkillError("共享技能不允许 always: true，否则会注入每个用户每一轮对话")

    _validate_snapshot_files(skill_dir)
    return data


def _walk_snapshot_entries(skill_dir: Path) -> Iterable[tuple[Path, bool]]:
    """遍历技能目录，产出 (路径, 是否符号链接)，不进入隐藏项。"""
    for root, dirs, names in os.walk(skill_dir, followlinks=False):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        base = Path(root)
        for name in names:
            if name.startswith("."):
                continue
            path = base / name
            yield path, path.is_symlink()


def _iter_snapshot_files(skill_dir: Path) -> Iterable[Path]:
    """可用于快照的文件；符号链接一律跳过（校验阶段已会直接拒绝）。"""
    for path, is_link in _walk_snapshot_entries(skill_dir):
        if is_link:
            continue
        yield path


def _validate_snapshot_files(skill_dir: Path) -> None:
    """限制数量与体积，符号链接一律拒绝。"""
    entries = list(_walk_snapshot_entries(skill_dir))
    files = [path for path, is_link in entries if not is_link]

    for path, is_link in entries:
        if is_link:
            raise SharedSkillError(
                f"共享技能不允许包含符号链接：{path.relative_to(skill_dir)}"
            )
    if not files:
        raise SharedSkillError("技能目录为空，无法发布")
    if len(files) > MAX_SNAPSHOT_FILES:
        raise SharedSkillError(f"技能文件数超过上限（{MAX_SNAPSHOT_FILES}）")

    total = 0
    for path in files:
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(skill_dir.resolve())
        except ValueError as exc:
            raise SharedSkillError(
                f"文件越出技能目录：{path.relative_to(skill_dir)}"
            ) from exc
        except OSError as exc:
            raise SharedSkillError(f"无法读取文件 {path.name}: {exc}") from exc

        size = resolved.stat().st_size
        if size > MAX_SNAPSHOT_FILE_BYTES:
            raise SharedSkillError(f"单个文件超过上限：{path.relative_to(skill_dir)}")
        total += size

    if total > MAX_SNAPSHOT_TOTAL_BYTES:
        raise SharedSkillError("技能总体积超过上限")


def _content_hash(skill_dir: Path) -> str:
    digest = hashlib.sha256()
    for path in _iter_snapshot_files(skill_dir):
        digest.update(str(path.relative_to(skill_dir)).encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _write_snapshot(skill_dir: Path, target: Path) -> None:
    """把技能复制为不可变快照，版本目录下按技能名再包一层以匹配加载规则。"""
    if target.exists():
        shutil.rmtree(target)
    destination_root = target / skill_dir.name
    destination_root.mkdir(parents=True, exist_ok=True)
    for path in _iter_snapshot_files(skill_dir):
        relative = path.relative_to(skill_dir)
        destination = destination_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)


# ---------------------------------------------------------------------------
# 同名与可见范围
# ---------------------------------------------------------------------------


async def _approved_shared_names(db) -> set[str]:
    rows = (
        await db.execute(
            select(SkillRegistry.name).where(
                SkillRegistry.status == STATUS_APPROVED,
                SkillRegistry.visibility == VISIBILITY_SHARED,
            )
        )
    ).scalars().all()
    return {str(name) for name in rows}


def system_skill_names() -> set[str]:
    """全局工作区里的系统技能名（只读层）。"""
    from backend.modules.workspace import get_global_workspace_path

    skills_dir = get_global_workspace_path() / "skills"
    if not skills_dir.is_dir():
        return set()
    return {
        entry.name
        for entry in skills_dir.iterdir()
        if entry.is_dir() and (entry / _SKILL_FILE).is_file()
    }


async def ensure_name_available(db, name: str, user) -> None:
    """创建/发布前的同名检查：不得影子覆盖系统技能或已批准的共享技能。"""
    if name in system_skill_names():
        raise SharedSkillError(f"技能名「{name}」与系统技能冲突，请换一个名字")
    if name in await _approved_shared_names(db):
        raise SharedSkillError(f"技能名「{name}」已被共享技能占用，请换一个名字")


def _audience_ids(registry: SkillRegistry) -> Optional[List[str]]:
    """解析可见范围；None 表示全站可见。"""
    if not registry.audience_json:
        return None
    try:
        data = json.loads(registry.audience_json)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    return [str(item) for item in data if str(item).strip()]


def is_visible_to(registry: SkillRegistry, user) -> bool:
    """已批准的共享技能对该用户是否可见。"""
    if registry.status != STATUS_APPROVED:
        return False
    if registry.visibility != VISIBILITY_SHARED:
        return False
    owner_id = getattr(user, "owner_id", None)
    if registry.owner_id and owner_id and registry.owner_id == owner_id:
        return True
    audience = _audience_ids(registry)
    if audience is None:
        return True  # 全站
    return bool(user and getattr(user, "id", None) in audience)


# ---------------------------------------------------------------------------
# 发布 / 审核 / 撤回
# ---------------------------------------------------------------------------


async def _load_registry(db, skill_id: str) -> SkillRegistry:
    row = await db.get(SkillRegistry, skill_id)
    if row is None:
        raise SharedSkillError("共享技能不存在")
    return row


async def publish_skill(
    db,
    user,
    name: str,
    *,
    audience_ids: Optional[List[str]] = None,
) -> SkillRegistry:
    """把技能复制为共享快照并登记，重复发布同名技能时递增版本。"""
    owner_id = getattr(user, "owner_id", None)
    if not owner_id:
        # 管理员技能位于全局工作区，归档到系统分区后所有用户可见
        owner_id = SYSTEM_OWNER_ID

    if audience_ids is not None:
        cleaned = [str(item).strip() for item in audience_ids if str(item).strip()]
        if len(cleaned) > MAX_AUDIENCE_USERS:
            raise SharedSkillError(f"指定用户数超过上限（{MAX_AUDIENCE_USERS}）")
        audience_ids = list(dict.fromkeys(cleaned))

    skills_dir = user_skills_dir(user)
    skill_dir = skills_dir / name
    if not skill_dir.is_dir():
        raise SharedSkillError(f"技能「{name}」不存在")

    validate_publishable(skill_dir, name)

    existing_rows = (
        await db.execute(
            select(SkillRegistry).where(
                SkillRegistry.owner_id == owner_id,
                SkillRegistry.name == name,
            )
        )
    ).scalars().all()
    if not existing_rows:
        count = len(
            (
                await db.execute(
                    select(SkillRegistry.id).where(SkillRegistry.owner_id == owner_id)
                )
            ).scalars().all()
        )
        if count >= MAX_PUBLISHED_SKILLS_PER_USER:
            raise SharedSkillError(f"最多发布 {MAX_PUBLISHED_SKILLS_PER_USER} 个共享技能")

    # 管理员发布自己的技能不算影子覆盖，同名约束只针对普通用户
    if not existing_rows and owner_id != SYSTEM_OWNER_ID:
        await ensure_name_available(db, name, user)

    version = max((row.version for row in existing_rows), default=0) + 1
    skill_id = existing_rows[0].id if existing_rows else str(uuid.uuid4())
    target = snapshot_dir(skill_id, version)
    _write_snapshot(skill_dir, target)

    from backend.modules.workspace import get_global_workspace_path

    storage_path = str(
        target.resolve().relative_to(get_global_workspace_path().resolve())
    )
    frontmatter = read_skill_frontmatter(skill_dir)

    is_new = not existing_rows
    row = existing_rows[0] if existing_rows else SkillRegistry(id=skill_id)
    row.owner_id = owner_id
    row.name = name
    row.scope = SCOPE_USER
    row.visibility = VISIBILITY_SHARED
    row.status = STATUS_PENDING
    row.description = str(frontmatter.get("description") or "").strip()[:2000]
    row.version = version
    row.content_hash = _content_hash(skill_dir)
    row.storage_path = storage_path
    # 区分「不传 = 全站」与「空数组 = 不发给任何人」
    row.audience_json = (
        None if audience_ids is None else json.dumps(audience_ids, ensure_ascii=False)
    )
    row.reject_reason = None
    row.approved_by = None
    row.approved_at = None
    if not getattr(user, "owner_id", None):
        # 管理员就是审核方，自审没有意义，发布即分发
        row.status = STATUS_APPROVED
        row.approved_by = getattr(user, "id", None) or "admin"
        row.approved_at = datetime.utcnow()
    if is_new:
        db.add(row)
    await db.commit()
    await db.refresh(row)
    logger.info(f"Shared skill '{name}' submitted by {owner_id} (v{version})")
    return row


async def review_skill(
    db,
    admin,
    skill_id: str,
    *,
    approved: bool,
    reason: str = "",
) -> SkillRegistry:
    """管理员审核：通过则分发，驳回则记录原因（快照保留，便于作者修正后重提）。"""
    row = await _load_registry(db, skill_id)
    if row.status not in (STATUS_PENDING, STATUS_DRAFT):
        raise SharedSkillError(f"当前状态（{row.status}）不可审核")

    if approved:
        # 审核是分发的最后环节，需再次检查同名，避免并发提交产生重复记录
        duplicate = (
            await db.execute(
                select(SkillRegistry.id).where(
                    SkillRegistry.name == row.name,
                    SkillRegistry.status == STATUS_APPROVED,
                    SkillRegistry.visibility == VISIBILITY_SHARED,
                    SkillRegistry.id != row.id,
                )
            )
        ).scalars().first()
        if duplicate is not None:
            raise SharedSkillError(
                f"技能名「{row.name}」已有其他已批准的共享技能，请先撤回旧版本"
            )

        row.status = STATUS_APPROVED
        row.reject_reason = None
        row.approved_by = getattr(admin, "id", None) or getattr(admin, "username", "")
        row.approved_at = datetime.utcnow()
    else:
        row.status = STATUS_REJECTED
        row.reject_reason = (reason or "").strip()[:2000] or "未通过审核"

    await db.commit()
    await db.refresh(row)
    logger.info(f"Shared skill {skill_id} review -> {row.status}")
    return row


async def revoke_skill(db, admin, skill_id: str, reason: str = "") -> SkillRegistry:
    """撤回：停止分发，但保留快照与记录（可审计、可恢复）。"""
    row = await _load_registry(db, skill_id)
    if row.status == STATUS_REVOKED:
        return row
    row.status = STATUS_REVOKED
    if reason:
        row.reject_reason = reason.strip()[:2000]
    await db.commit()
    await db.refresh(row)
    logger.info(f"Shared skill {skill_id} revoked")
    return row


async def list_registry(db, user) -> List[SkillRegistry]:
    """列出该用户可见的技能登记：自己发布的全部 + 分发给自己的已批准共享技能。"""
    owner_id = getattr(user, "owner_id", None)
    rows = (await db.execute(select(SkillRegistry))).scalars().all()
    result: List[SkillRegistry] = []
    for row in rows:
        if owner_id and row.owner_id == owner_id:
            result.append(row)
            continue
        if is_visible_to(row, user):
            result.append(row)
    return result


async def visible_shared_dirs(db, user) -> List[Path]:
    """返回该用户可见的共享技能快照目录（供 SkillsLoader 只读加载）。"""
    owner_id = getattr(user, "owner_id", None)
    rows = (
        await db.execute(
            select(SkillRegistry).where(
                SkillRegistry.status == STATUS_APPROVED,
                SkillRegistry.visibility == VISIBILITY_SHARED,
            )
        )
    ).scalars().all()

    dirs: List[Path] = []
    for row in rows:
        if owner_id and row.owner_id == owner_id:
            continue  # 作者自己的技能走私有目录，不重复加载
        if not is_visible_to(row, user):
            continue
        path = resolve_storage_path(row.storage_path)
        if path is not None:
            dirs.append(path)
    return dirs


# ---------------------------------------------------------------------------
# 用户启用状态
# ---------------------------------------------------------------------------


async def set_state(db, user, skill_id: str, enabled: bool) -> UserSkillState:
    owner_id = getattr(user, "owner_id", None)
    if not owner_id:
        raise SharedSkillError("管理员不需要记录共享技能启用状态")

    # 只能对自己可见的技能写状态，避免任意 skill_id 被写入启用记录
    target = await _load_registry(db, skill_id)
    is_own = bool(target.owner_id and target.owner_id == owner_id)
    if not is_own and not is_visible_to(target, user):
        raise SharedSkillError("共享技能不存在或未分发给你")

    row = (
        await db.execute(
            select(UserSkillState).where(
                UserSkillState.user_id == owner_id,
                UserSkillState.skill_id == skill_id,
            )
        )
    ).scalar_one_or_none()

    if row is None:
        row = UserSkillState(user_id=owner_id, skill_id=skill_id, enabled=enabled)
        db.add(row)
    else:
        row.enabled = enabled
    await db.commit()
    await db.refresh(row)
    return row


async def enabled_state_map(db, user) -> Dict[str, bool]:
    """该用户对各技能的启用状态（skill_id -> enabled）；未记录视为启用。"""
    owner_id = getattr(user, "owner_id", None)
    if not owner_id:
        return {}

    rows = (
        await db.execute(
            select(UserSkillState.skill_id, UserSkillState.enabled).where(
                UserSkillState.user_id == owner_id
            )
        )
    ).all()
    return {str(skill_id): bool(enabled) for skill_id, enabled in rows}


async def disabled_shared_names(db, user) -> set[str]:
    """该用户主动停用的共享技能名；SkillsLoader 据此过滤。"""
    owner_id = getattr(user, "owner_id", None)
    if not owner_id:
        return set()

    rows = (
        await db.execute(
            select(SkillRegistry.name, UserSkillState.enabled)
            .join(UserSkillState, UserSkillState.skill_id == SkillRegistry.id)
            .where(
                UserSkillState.user_id == owner_id,
                SkillRegistry.status == STATUS_APPROVED,
            )
        )
    ).all()
    return {str(name) for name, enabled in rows if not enabled}
