"""管理员多用户策略与审计日志接口"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from backend.api.admin._router import router
from backend.database import AsyncSessionLocal
from backend.models.user import AuditLog
from backend.modules.multiuser import audit
from backend.modules.multiuser.identity import AuthUser
from backend.modules.multiuser.permissions import require_admin
from backend.modules.multiuser.settings import load_settings, save_settings


class MultiuserSettingsResponse(BaseModel):
    enabled: bool
    registration_open: bool
    approval: str
    mode: str
    shared_providers: bool
    shared_skills_wiki_mcp: bool
    allow_user_mcp: bool
    user_mcp_stdio_allowlist: List[str]
    notify_shared_channels: List[str]
    allow_local_admin_bypass: bool
    max_users: int


class UpdateMultiuserSettingsRequest(BaseModel):
    enabled: Optional[bool] = None
    registration_open: Optional[bool] = None
    approval: Optional[str] = Field(None, description="manual | auto")
    mode: Optional[str] = Field(None, description="shared | isolated")
    shared_providers: Optional[bool] = None
    shared_skills_wiki_mcp: Optional[bool] = None
    allow_user_mcp: Optional[bool] = None
    user_mcp_stdio_allowlist: Optional[List[str]] = None
    notify_shared_channels: Optional[List[str]] = None


class AuditLogItem(BaseModel):
    id: int
    actor_name: Optional[str] = None
    action: str
    target: Optional[str] = None
    detail: Optional[str] = None
    ip: Optional[str] = None
    created_at: Optional[datetime] = None


class AuditLogListResponse(BaseModel):
    items: List[AuditLogItem]
    total: int
    page: int
    page_size: int


@router.get("/multiuser/settings", response_model=MultiuserSettingsResponse)
async def get_multiuser_settings(
    _admin: AuthUser = Depends(require_admin),
) -> MultiuserSettingsResponse:
    settings = await load_settings(use_cache=False)
    return MultiuserSettingsResponse(
        enabled=settings.enabled,
        registration_open=settings.registration_open,
        approval=settings.approval,
        mode=settings.mode,
        shared_providers=settings.shared_providers,
        shared_skills_wiki_mcp=settings.shared_skills_wiki_mcp,
        allow_user_mcp=settings.allow_user_mcp,
        user_mcp_stdio_allowlist=list(settings.user_mcp_stdio_allowlist),
        notify_shared_channels=list(settings.notify_shared_channels),
        allow_local_admin_bypass=settings.allow_local_admin_bypass,
        max_users=settings.max_users,
    )


@router.put("/multiuser/settings", response_model=MultiuserSettingsResponse)
async def update_multiuser_settings(
    payload: UpdateMultiuserSettingsRequest,
    request: Request,
    admin: AuthUser = Depends(require_admin),
) -> MultiuserSettingsResponse:
    before = await load_settings(use_cache=False)
    await save_settings(
        enabled=payload.enabled,
        registration_open=payload.registration_open,
        approval=payload.approval,
        mode=payload.mode,
        shared_providers=payload.shared_providers,
        shared_skills_wiki_mcp=payload.shared_skills_wiki_mcp,
        allow_user_mcp=payload.allow_user_mcp,
        user_mcp_stdio_allowlist=payload.user_mcp_stdio_allowlist,
        notify_shared_channels=payload.notify_shared_channels,
    )
    settings = await load_settings(use_cache=False)

    # 共享能力变更后立即失效：清理运行时与 Wiki 缓存，并断开普通用户连接
    revocable_fields = (
        "enabled",
        "mode",
        "shared_providers",
        "shared_skills_wiki_mcp",
        "allow_user_mcp",
        "user_mcp_stdio_allowlist",
    )
    if any(getattr(before, field) != getattr(settings, field) for field in revocable_fields):
        from backend.api.wiki import reset_user_wiki_services
        from backend.modules.multiuser.runtime import user_runtime_manager
        from backend.ws.connection import connection_manager

        user_runtime_manager.invalidate_all()
        reset_user_wiki_services()
        await connection_manager.disconnect_regular_users()

    changed = {
        key: value
        for key, value in payload.model_dump(exclude_none=True).items()
        if key
        in {
            "enabled",
            "registration_open",
            "approval",
            "mode",
            "shared_providers",
            "shared_skills_wiki_mcp",
            "allow_user_mcp",
            "user_mcp_stdio_allowlist",
            "notify_shared_channels",
        }
    }
    await audit.record_audit(
        audit.ACTION_SETTINGS_UPDATE,
        actor=admin,
        target="multiuser",
        detail=str(changed),
        request=request,
    )

    return MultiuserSettingsResponse(
        enabled=settings.enabled,
        registration_open=settings.registration_open,
        approval=settings.approval,
        mode=settings.mode,
        shared_providers=settings.shared_providers,
        shared_skills_wiki_mcp=settings.shared_skills_wiki_mcp,
        allow_user_mcp=settings.allow_user_mcp,
        user_mcp_stdio_allowlist=list(settings.user_mcp_stdio_allowlist),
        notify_shared_channels=list(settings.notify_shared_channels),
        allow_local_admin_bypass=settings.allow_local_admin_bypass,
        max_users=settings.max_users,
    )


@router.get("/audit-logs", response_model=AuditLogListResponse)
async def list_audit_logs(
    action: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    _admin: AuthUser = Depends(require_admin),
) -> AuditLogListResponse:
    async with AsyncSessionLocal() as session:
        stmt = select(AuditLog)
        count_stmt = select(func.count()).select_from(AuditLog)
        if action:
            stmt = stmt.where(AuditLog.action == action)
            count_stmt = count_stmt.where(AuditLog.action == action)

        total = int((await session.execute(count_stmt)).scalar() or 0)
        stmt = stmt.order_by(AuditLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        rows = (await session.execute(stmt)).scalars().all()

        return AuditLogListResponse(
            items=[
                AuditLogItem(
                    id=row.id,
                    actor_name=row.actor_name,
                    action=row.action,
                    target=row.target,
                    detail=row.detail,
                    ip=row.ip,
                    created_at=row.created_at,
                )
                for row in rows
            ],
            total=total,
            page=page,
            page_size=page_size,
        )
