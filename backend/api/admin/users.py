"""管理员用户管理接口：角色与状态变更写审计并吊销会话。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import Depends, HTTPException, Query, Request, status
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from backend.api.admin._router import router
from backend.database import AsyncSessionLocal
from backend.models.user import (
    ROLE_ADMIN,
    ROLE_USER,
    STATUS_ACTIVE,
    STATUS_DISABLED,
    STATUS_PENDING,
    User,
)
from backend.modules.auth.utils import (
    hash_password,
    validate_password,
    validate_username,
)
from backend.modules.multiuser import audit
from backend.modules.multiuser.effective import list_shared_models
from backend.modules.multiuser.identity import (
    CHAT_MODE_POLICY_ALL,
    AuthUser,
    normalize_chat_mode_policy,
)
from backend.modules.multiuser.permissions import require_admin
from backend.modules.multiuser.shared_access import (
    SHARED_MODEL_SCOPE_ALL,
    SHARED_MODEL_SCOPE_SELECTED,
    normalize_shared_model_refs,
    normalize_shared_model_scope,
    serialize_shared_model_refs,
)
from backend.modules.workspace import archive_user_workspace

_VALID_ROLES = {ROLE_ADMIN, ROLE_USER}
_VALID_STATUS = {STATUS_PENDING, STATUS_ACTIVE, STATUS_DISABLED}


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


class UserItem(BaseModel):
    id: str
    username: str
    role: str
    status: str
    display_name: Optional[str] = None
    chat_mode_policy: str = CHAT_MODE_POLICY_ALL
    shared_model_scope: str = SHARED_MODEL_SCOPE_ALL
    shared_model_refs: List[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None
    # 连续登录失败触发的临时锁定剩余秒数；0 表示未锁定
    login_locked: int = 0


class UserListResponse(BaseModel):
    items: List[UserItem]
    total: int
    page: int
    page_size: int


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=8)
    role: str = Field(ROLE_USER)
    status: str = Field(STATUS_ACTIVE)
    display_name: Optional[str] = None
    chat_mode_policy: str = Field(CHAT_MODE_POLICY_ALL, description="all | chat | agent")
    shared_model_scope: Optional[str] = Field(None, description="all | selected")
    shared_model_refs: Optional[List[str]] = None


class UpdateUserRequest(BaseModel):
    status: Optional[str] = None
    role: Optional[str] = None
    display_name: Optional[str] = None
    chat_mode_policy: Optional[str] = Field(None, description="all | chat | agent")
    shared_model_scope: Optional[str] = Field(None, description="all | selected")
    shared_model_refs: Optional[List[str]] = None


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=8)


class SimpleResponse(BaseModel):
    success: bool = True
    message: str = ""


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------


def _to_item(user: User) -> UserItem:
    from backend.modules.auth.router import login_lock_remaining

    return UserItem(
        id=user.id,
        username=user.username,
        role=user.role,
        status=user.status,
        display_name=user.display_name,
        chat_mode_policy=normalize_chat_mode_policy(
            getattr(user, "chat_mode_policy", CHAT_MODE_POLICY_ALL)
        ),
        shared_model_scope=normalize_shared_model_scope(
            getattr(user, "shared_model_scope", None)
        ),
        shared_model_refs=list(
            normalize_shared_model_refs(getattr(user, "shared_model_refs", ()))
        ),
        created_at=user.created_at,
        approved_at=user.approved_at,
        last_login_at=user.last_login_at,
        login_locked=login_lock_remaining(user.username),
    )


async def _load_user(session, user_id: str) -> Optional[User]:
    return await session.get(User, user_id)


async def _count_active_admins(session) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(User)
        .where(User.role == ROLE_ADMIN, User.status == STATUS_ACTIVE)
    )
    return int(result.scalar() or 0)


def _shared_selection(
    role: str, scope: Optional[str], refs: Optional[List[str]]
) -> tuple[str, List[str]]:
    """校验并收敛共享模型范围；管理员始终全量。"""
    if role == ROLE_ADMIN:
        return SHARED_MODEL_SCOPE_ALL, []

    normalized_scope = normalize_shared_model_scope(scope)
    normalized_refs = list(normalize_shared_model_refs(refs or []))
    if normalized_scope == SHARED_MODEL_SCOPE_SELECTED:
        available = {item["ref"] for item in list_shared_models()}
        invalid = [ref for ref in normalized_refs if ref not in available]
        if invalid:
            raise HTTPException(
                status_code=400,
                detail="共享模型不存在或已取消共享，请刷新后重新选择",
            )
    else:
        normalized_refs = []
    return normalized_scope, normalized_refs


def _revoke(user: User) -> None:
    from backend.modules.auth.utils import revoke_all_sessions, revoke_sessions_for_user_id

    if user.id:
        revoke_sessions_for_user_id(user.id)
    revoke_all_sessions(user.username)


# ---------------------------------------------------------------------------
# 接口
# ---------------------------------------------------------------------------


@router.get("/users", response_model=UserListResponse)
async def list_users(
    q: Optional[str] = Query(None, description="按用户名/显示名搜索"),
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _admin: AuthUser = Depends(require_admin),
) -> UserListResponse:
    async with AsyncSessionLocal() as session:
        stmt = select(User)
        count_stmt = select(func.count()).select_from(User)

        if q:
            pattern = f"%{q.strip()}%"
            condition = or_(User.username.like(pattern), User.display_name.like(pattern))
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if status_filter in _VALID_STATUS:
            stmt = stmt.where(User.status == status_filter)
            count_stmt = count_stmt.where(User.status == status_filter)

        total = int((await session.execute(count_stmt)).scalar() or 0)
        stmt = stmt.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        rows = (await session.execute(stmt)).scalars().all()

        return UserListResponse(
            items=[_to_item(u) for u in rows],
            total=total,
            page=page,
            page_size=page_size,
        )


@router.post("/users", response_model=UserItem, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: CreateUserRequest,
    request: Request,
    admin: AuthUser = Depends(require_admin),
) -> UserItem:
    valid_username, username_msg = validate_username(payload.username)
    if not valid_username:
        raise HTTPException(status_code=400, detail=username_msg)

    valid_password, password_msg = validate_password(payload.password)
    if not valid_password:
        raise HTTPException(status_code=400, detail=password_msg)

    role = payload.role if payload.role in _VALID_ROLES else ROLE_USER
    user_status = payload.status if payload.status in _VALID_STATUS else STATUS_ACTIVE
    chat_mode_policy = (
        CHAT_MODE_POLICY_ALL
        if role == ROLE_ADMIN
        else normalize_chat_mode_policy(payload.chat_mode_policy)
    )
    shared_scope, shared_refs = _shared_selection(
        role, payload.shared_model_scope, payload.shared_model_refs
    )

    async with AsyncSessionLocal() as session:
        existing = (
            await session.execute(select(User).where(User.username == payload.username.strip()))
        ).scalars().first()
        if existing is not None:
            raise HTTPException(status_code=409, detail="用户名已存在")

        user = User(
            id=str(uuid.uuid4()),
            username=payload.username.strip(),
            password_hash=hash_password(payload.password),
            role=role,
            status=user_status,
            display_name=(payload.display_name or payload.username).strip(),
            chat_mode_policy=chat_mode_policy,
            shared_model_scope=shared_scope,
            shared_model_refs=serialize_shared_model_refs(shared_refs),
            approved_at=datetime.utcnow() if user_status == STATUS_ACTIVE else None,
            approved_by=admin.username if user_status == STATUS_ACTIVE else None,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    await audit.record_audit(
        audit.ACTION_USER_CREATE,
        actor=admin,
        target=user.username,
        detail=(
            f"role={role} status={user_status} chat_mode={chat_mode_policy} "
            f"shared_scope={shared_scope} shared_refs={len(shared_refs)}"
        ),
        request=request,
    )
    logger.info(f"Admin {admin.username} created user {user.username} ({role}/{user_status})")
    return _to_item(user)


@router.patch("/users/{user_id}", response_model=UserItem)
async def update_user(
    user_id: str,
    payload: UpdateUserRequest,
    request: Request,
    admin: AuthUser = Depends(require_admin),
) -> UserItem:
    async with AsyncSessionLocal() as session:
        user = await _load_user(session, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="用户不存在")

        new_role = payload.role if payload.role in _VALID_ROLES else user.role
        new_status = payload.status if payload.status in _VALID_STATUS else user.status
        old_policy = normalize_chat_mode_policy(
            getattr(user, "chat_mode_policy", CHAT_MODE_POLICY_ALL)
        )
        new_policy = (
            CHAT_MODE_POLICY_ALL
            if new_role == ROLE_ADMIN
            else (
                normalize_chat_mode_policy(payload.chat_mode_policy)
                if payload.chat_mode_policy is not None
                else old_policy
            )
        )
        old_scope = normalize_shared_model_scope(
            getattr(user, "shared_model_scope", None)
        )
        old_refs = list(
            normalize_shared_model_refs(getattr(user, "shared_model_refs", ()))
        )
        requested_scope = (
            payload.shared_model_scope
            if payload.shared_model_scope is not None
            else old_scope
        )
        requested_refs = (
            payload.shared_model_refs
            if payload.shared_model_refs is not None
            else old_refs
        )
        new_scope, new_refs = _shared_selection(
            new_role, requested_scope, requested_refs
        )

        # 护栏：不能把最后一个活跃管理员降级或禁用
        if user.role == ROLE_ADMIN and user.status == STATUS_ACTIVE:
            losing_admin = new_role != ROLE_ADMIN or new_status != STATUS_ACTIVE
            if losing_admin and await _count_active_admins(session) <= 1:
                raise HTTPException(status_code=400, detail="不能禁用或降级最后一个管理员")

        role_changed = new_role != user.role
        status_changed = new_status != user.status
        policy_changed = new_policy != old_policy
        shared_changed = new_scope != old_scope or tuple(new_refs) != tuple(old_refs)

        user.role = new_role
        user.status = new_status
        user.chat_mode_policy = new_policy
        user.shared_model_scope = new_scope
        user.shared_model_refs = serialize_shared_model_refs(new_refs)
        if payload.display_name is not None:
            user.display_name = payload.display_name.strip()
        if status_changed and new_status == STATUS_ACTIVE and user.approved_at is None:
            user.approved_at = datetime.utcnow()
            user.approved_by = admin.username

        await session.commit()
        await session.refresh(user)

    # 状态或角色变更立即生效
    if status_changed or role_changed:
        _revoke(user)
    if policy_changed or shared_changed:
        from backend.ws.connection import connection_manager

        await connection_manager.disconnect_owner(user.id)

    action = audit.ACTION_SETTINGS_UPDATE
    if role_changed:
        action = audit.ACTION_USER_ROLE_CHANGE
    elif status_changed:
        action = {
            STATUS_ACTIVE: audit.ACTION_USER_APPROVE,
            STATUS_DISABLED: audit.ACTION_USER_DISABLE,
            STATUS_PENDING: audit.ACTION_USER_REJECT,
        }.get(new_status, audit.ACTION_SETTINGS_UPDATE)

    await audit.record_audit(
        action,
        actor=admin,
        target=user.username,
        detail=(
            f"role={new_role} status={new_status} chat_mode={new_policy} "
            f"shared_scope={new_scope} shared_refs={len(new_refs)}"
        ),
        request=request,
    )
    return _to_item(user)


@router.put("/users/{user_id}/password", response_model=SimpleResponse)
async def reset_user_password(
    user_id: str,
    payload: ResetPasswordRequest,
    request: Request,
    admin: AuthUser = Depends(require_admin),
) -> SimpleResponse:
    valid, msg = validate_password(payload.new_password)
    if not valid:
        raise HTTPException(status_code=400, detail=msg)

    async with AsyncSessionLocal() as session:
        user = await _load_user(session, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="用户不存在")

        user.password_hash = hash_password(payload.new_password)
        await session.commit()

        # 管理员改密后同步回 settings，保持凭据唯一来源
        if user.role == ROLE_ADMIN:
            from backend.modules.auth.router import save_credentials

            await save_credentials(user.username, user.password_hash)

    _revoke(user)

    await audit.record_audit(
        audit.ACTION_RESET_PASSWORD,
        actor=admin,
        target=user.username,
        request=request,
    )
    return SimpleResponse(message="密码已重置，该用户需重新登录")


@router.post("/users/{user_id}/unlock", response_model=SimpleResponse)
async def unlock_user(
    user_id: str,
    request: Request,
    admin: AuthUser = Depends(require_admin),
) -> SimpleResponse:
    """解除「连续登录失败」造成的临时锁定（跨来源 IP 一并清除）。"""
    from backend.modules.auth.router import clear_login_lockouts

    async with AsyncSessionLocal() as session:
        user = await _load_user(session, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="用户不存在")
        username = user.username

    cleared = clear_login_lockouts(username)

    await audit.record_audit(
        audit.ACTION_USER_UNLOCK,
        actor=admin,
        target=username,
        detail=f"cleared={cleared}",
        request=request,
    )
    return SimpleResponse(
        message="登录锁定已解除" if cleared else "该账号当前没有登录锁定"
    )


@router.delete("/users/{user_id}", response_model=SimpleResponse)
async def delete_user(
    user_id: str,
    request: Request,
    admin: AuthUser = Depends(require_admin),
) -> SimpleResponse:
    if admin.id and admin.id == user_id:
        raise HTTPException(status_code=400, detail="不能删除自己")

    async with AsyncSessionLocal() as session:
        user = await _load_user(session, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="用户不存在")

        if user.role == ROLE_ADMIN and await _count_active_admins(session) <= 1:
            raise HTTPException(status_code=400, detail="不能删除最后一个管理员")

        username = user.username
        user_id_copy = user.id
        await session.delete(user)
        await session.commit()

    from backend.modules.auth.utils import revoke_all_sessions, revoke_sessions_for_user_id

    revoke_sessions_for_user_id(user_id_copy)
    revoke_all_sessions(username)

    # 先删除用户再归档工作区，归档失败时可人工找回
    archived = archive_user_workspace(user_id_copy)
    if archived is not None:
        logger.info(f"Archived workspace of deleted user {username}: {archived}")

    # 清理该用户自己的渠道机器人，避免删除后实例继续运行
    try:
        from backend.api.channels import purge_owner_channel_accounts

        await purge_owner_channel_accounts(user_id_copy, request)
    except Exception as exc:
        logger.warning(f"Failed to purge channel accounts for deleted user {username}: {exc}")

    await audit.record_audit(
        audit.ACTION_USER_DELETE,
        actor=admin,
        target=username,
        request=request,
        detail=f"workspace_archived={str(archived) if archived else 'none'}",
    )
    logger.info(f"Admin {admin.username} deleted user {username}")
    return SimpleResponse(message="用户已删除")
