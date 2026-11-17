"""审计日志：只记录行为与目标，禁止写入密码、API Key 等敏感值；写入失败仅告警。"""

from __future__ import annotations

from typing import Optional

from fastapi import Request
from loguru import logger

from backend.models.user import AuditLog
from backend.modules.multiuser.identity import AuthUser

# 动作常量，避免各处硬编码字符串
ACTION_LOGIN_SUCCESS = "auth.login.success"
ACTION_LOGIN_FAILURE = "auth.login.failure"
ACTION_LOGOUT = "auth.logout"
ACTION_REGISTER = "auth.register"
ACTION_CHANGE_PASSWORD = "auth.password.change"
ACTION_RESET_PASSWORD = "admin.user.password.reset"
ACTION_USER_CREATE = "admin.user.create"
ACTION_USER_APPROVE = "admin.user.approve"
ACTION_USER_REJECT = "admin.user.reject"
ACTION_USER_DISABLE = "admin.user.disable"
ACTION_USER_ENABLE = "admin.user.enable"
ACTION_USER_DELETE = "admin.user.delete"
ACTION_USER_ROLE_CHANGE = "admin.user.role.change"
ACTION_USER_UNLOCK = "admin.user.unlock"
ACTION_SETTINGS_UPDATE = "admin.multiuser.settings.update"
ACTION_SKILL_PUBLISH = "skill.shared.publish"
ACTION_SKILL_REVIEW = "skill.shared.review"
ACTION_SKILL_REVOKE = "skill.shared.revoke"


def client_ip(request: Optional[Request]) -> Optional[str]:
    if request is None:
        return None
    if request.client and request.client.host:
        return request.client.host
    return None


async def record_audit(
    action: str,
    *,
    actor: Optional[AuthUser] = None,
    target: Optional[str] = None,
    detail: Optional[str] = None,
    request: Optional[Request] = None,
) -> None:
    """写入一条审计日志（失败仅告警，不上抛）。"""
    from backend.database import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as session:
            session.add(
                AuditLog(
                    actor_id=(actor.id if actor and actor.id else None),
                    actor_name=(actor.username if actor else None),
                    action=action,
                    target=target,
                    detail=detail,
                    ip=client_ip(request),
                )
            )
            await session.commit()
    except Exception as exc:
        logger.warning(f"Failed to record audit log ({action}): {exc}")
