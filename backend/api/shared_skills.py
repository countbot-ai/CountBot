"""共享技能接口：仅管理员可发布，普通用户只能浏览并启停可见技能。"""

from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from backend.database import get_db
from backend.models.skill import STATUS_APPROVED, SkillRegistry
from backend.modules.multiuser import audit
from backend.modules.multiuser.identity import AuthUser
from backend.modules.multiuser.permissions import require_active_user, require_admin
from backend.modules.multiuser.shared_skills import (
    SharedSkillError,
    enabled_state_map,
    list_registry,
    publish_skill,
    review_skill,
    revoke_skill,
    set_state,
)

router = APIRouter(
    prefix="/api/shared-skills",
    tags=["shared-skills"],
    dependencies=[Depends(require_active_user)],
)


class PublishSkillRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64, description="自己工作区里的技能名")
    audience: Optional[List[str]] = Field(
        None, description="可见用户 id 列表；为空表示全站可见"
    )


class ReviewSkillRequest(BaseModel):
    approved: bool
    reason: str = ""


class RevokeSkillRequest(BaseModel):
    reason: str = ""


class SkillStateRequest(BaseModel):
    enabled: bool


class SharedSkillItem(BaseModel):
    id: str
    name: str
    owner_id: Optional[str] = None
    scope: str
    visibility: str
    status: str
    description: str = ""
    version: int = 1
    audience: Optional[List[str]] = None
    reject_reason: Optional[str] = None
    approved_at: Optional[str] = None
    created_at: Optional[str] = None
    is_mine: bool = False
    # 当前用户是否启用了该技能（未记录视为启用）
    enabled: bool = True


def _to_item(
    row: SkillRegistry,
    user: AuthUser,
    state: Optional[Dict[str, bool]] = None,
) -> SharedSkillItem:
    audience: Optional[List[str]] = None
    if row.audience_json:
        import json

        try:
            data = json.loads(row.audience_json)
            audience = [str(x) for x in data] if isinstance(data, list) else []
        except (ValueError, TypeError):
            audience = []

    owner_id = getattr(user, "owner_id", None)
    is_mine = bool(owner_id and row.owner_id == owner_id)
    # 可见范围里存的是其他用户的 id，只对作者与管理员回显
    can_see_audience = is_mine or bool(getattr(user, "is_admin", False))

    return SharedSkillItem(
        id=row.id,
        name=row.name,
        owner_id=row.owner_id if can_see_audience else None,
        scope=row.scope,
        visibility=row.visibility,
        status=row.status,
        description=row.description or "",
        version=row.version,
        audience=audience if can_see_audience else None,
        reject_reason=row.reject_reason if is_mine or can_see_audience else None,
        approved_at=row.approved_at.isoformat() if row.approved_at else None,
        created_at=row.created_at.isoformat() if row.created_at else None,
        is_mine=bool(owner_id and row.owner_id == owner_id),
        enabled=(state or {}).get(row.id, True),
    )


def _invalidate_shared_skill_runtimes() -> None:
    """共享技能登记变更后丢弃用户运行时缓存，让快照与停用状态即时生效。"""
    from backend.modules.multiuser.runtime import user_runtime_manager

    user_runtime_manager.invalidate_all()


@router.get("", response_model=List[SharedSkillItem])
async def list_shared_skills(
    user: AuthUser = Depends(require_active_user),
    db=Depends(get_db),
) -> List[SharedSkillItem]:
    """列出与我相关的技能登记：我发布的 + 分发给我的已批准共享技能。"""
    rows = await list_registry(db, user)
    state = await enabled_state_map(db, user)
    rows.sort(key=lambda row: (row.status != STATUS_APPROVED, row.name))
    return [_to_item(row, user, state) for row in rows]


@router.get("/publishable", response_model=List[str])
async def list_publishable_skills(
    admin: AuthUser = Depends(require_admin),
) -> List[str]:
    """返回管理员可发布的技能名，过滤含脚本、符号链接或超限的技能。"""
    from backend.modules.multiuser.shared_skills import (
        user_skills_dir,
        validate_publishable,
    )

    root = user_skills_dir(admin)
    names: List[str] = []
    for entry in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        if not entry.is_dir() or not (entry / "SKILL.md").is_file():
            continue
        try:
            validate_publishable(entry, entry.name)
        except SharedSkillError:
            continue
        names.append(entry.name)
    return names


@router.post("/publish", response_model=SharedSkillItem, status_code=status.HTTP_201_CREATED)
async def publish(
    payload: PublishSkillRequest,
    request: Request,
    user: AuthUser = Depends(require_admin),
    db=Depends(get_db),
) -> SharedSkillItem:
    """把技能复制为不可变快照并发布为共享。"""
    try:
        row = await publish_skill(
            db,
            user,
            payload.name.strip(),
            audience_ids=payload.audience,
        )
    except SharedSkillError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await audit.record_audit(
        audit.ACTION_SKILL_PUBLISH,
        actor=user,
        target=f"shared-skill:{row.name}",
        detail=f"publish v{row.version}",
        request=request,
    )
    _invalidate_shared_skill_runtimes()
    return _to_item(row, user)


@router.post("/{skill_id}/review", response_model=SharedSkillItem)
async def review(
    skill_id: str,
    payload: ReviewSkillRequest,
    request: Request,
    admin: AuthUser = Depends(require_admin),
    db=Depends(get_db),
) -> SharedSkillItem:
    """管理员审核：通过即分发，驳回需给出原因。"""
    try:
        row = await review_skill(
            db,
            admin,
            skill_id,
            approved=payload.approved,
            reason=payload.reason,
        )
    except SharedSkillError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await audit.record_audit(
        audit.ACTION_SKILL_REVIEW,
        actor=admin,
        target=f"shared-skill:{row.name}",
        detail=f"review -> {row.status}",
        request=request,
    )
    _invalidate_shared_skill_runtimes()
    return _to_item(row, admin)


@router.post("/{skill_id}/revoke", response_model=SharedSkillItem)
async def revoke(
    skill_id: str,
    payload: RevokeSkillRequest,
    request: Request,
    admin: AuthUser = Depends(require_admin),
    db=Depends(get_db),
) -> SharedSkillItem:
    """撤回共享技能：停止分发，磁盘快照与记录保留。"""
    try:
        row = await revoke_skill(db, admin, skill_id, payload.reason)
    except SharedSkillError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await audit.record_audit(
        audit.ACTION_SKILL_REVOKE,
        actor=admin,
        target=f"shared-skill:{row.name}",
        detail="revoke",
        request=request,
    )
    _invalidate_shared_skill_runtimes()
    return _to_item(row, admin)


@router.put("/{skill_id}/state", response_model=SharedSkillItem)
async def update_state(
    skill_id: str,
    payload: SkillStateRequest,
    user: AuthUser = Depends(require_active_user),
    db=Depends(get_db),
) -> SharedSkillItem:
    """启用 / 停用某个共享技能（只影响自己）。"""
    rows = await list_registry(db, user)
    target = next((row for row in rows if row.id == skill_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="共享技能不存在")

    try:
        await set_state(db, user, skill_id, payload.enabled)
    except SharedSkillError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _invalidate_shared_skill_runtimes()
    return _to_item(target, user, {skill_id: payload.enabled})
