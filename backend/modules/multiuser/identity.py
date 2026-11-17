"""用户身份解析：会话 token 转为 ``AuthUser``，并提供用户查询与会话签发。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from loguru import logger

from backend.models.user import ROLE_ADMIN, STATUS_ACTIVE, User
from backend.modules.multiuser.shared_access import (
    SHARED_MODEL_SCOPE_ALL,
    normalize_shared_model_refs,
    normalize_shared_model_scope,
)

CHAT_MODE_POLICY_ALL = "all"
CHAT_MODE_POLICY_CHAT = "chat"
CHAT_MODE_POLICY_AGENT = "agent"
CHAT_MODE_POLICIES = frozenset(
    {CHAT_MODE_POLICY_ALL, CHAT_MODE_POLICY_CHAT, CHAT_MODE_POLICY_AGENT}
)


def normalize_chat_mode_policy(value) -> str:
    """把用户可用模式收敛为 all / chat / agent，未知值按 all 处理。"""
    text = str(value or "").strip().lower()
    return text if text in CHAT_MODE_POLICIES else CHAT_MODE_POLICY_ALL


def allowed_chat_modes(user) -> List[str]:
    """当前用户可用的对话模式；管理员始终可用两种。"""
    if user is None or getattr(user, "is_admin", False):
        return ["agent", "chat"]
    policy = normalize_chat_mode_policy(getattr(user, "chat_mode_policy", None))
    if policy in ("agent", "chat"):
        return [policy]
    return ["agent", "chat"]


def resolve_chat_mode_for_user(user, requested) -> str:
    """按用户策略收敛会话模式；管理员与未登录场景保持原值。"""
    mode = "chat" if str(requested or "").strip().lower() == "chat" else "agent"
    allowed = allowed_chat_modes(user)
    return mode if mode in allowed else allowed[0]


@dataclass(frozen=True)
class AuthUser:
    """经过解析的请求身份。"""

    id: str
    username: str
    role: str = ROLE_ADMIN
    status: str = STATUS_ACTIVE
    display_name: str = ""
    chat_mode_policy: str = CHAT_MODE_POLICY_ALL
    shared_model_scope: str = SHARED_MODEL_SCOPE_ALL
    shared_model_refs: Tuple[str, ...] = ()

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN

    @property
    def is_active(self) -> bool:
        return self.status == STATUS_ACTIVE

    @property
    def owner_id(self) -> Optional[str]:
        """数据归属键。管理员返回 None，管理员数据的 owner 为空。"""
        return None if self.is_admin else (self.id or None)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "status": self.status,
            "display_name": self.display_name,
            "is_admin": self.is_admin,
            "chat_mode_policy": normalize_chat_mode_policy(self.chat_mode_policy),
        }


def user_to_auth_user(user: User) -> AuthUser:
    return AuthUser(
        id=user.id,
        username=user.username,
        role=user.role or ROLE_ADMIN,
        status=user.status or STATUS_ACTIVE,
        display_name=user.display_name or "",
        chat_mode_policy=normalize_chat_mode_policy(
            getattr(user, "chat_mode_policy", CHAT_MODE_POLICY_ALL)
        ),
        shared_model_scope=normalize_shared_model_scope(
            getattr(user, "shared_model_scope", None)
        ),
        shared_model_refs=normalize_shared_model_refs(
            getattr(user, "shared_model_refs", ())
        ),
    )


def anonymous_admin() -> AuthUser:
    """本机免登录 / 单用户模式下的管理员身份。"""
    return AuthUser(id="", username="admin", role=ROLE_ADMIN, status=STATUS_ACTIVE)


async def get_user_by_username(username: str) -> Optional[User]:
    if not username:
        return None
    from sqlalchemy import select

    from backend.database import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(User).where(User.username == username))
            return result.scalars().first()
    except Exception as exc:
        logger.warning(f"Failed to load user by username {username!r}: {exc}")
        return None


async def get_user_by_id(user_id: str) -> Optional[User]:
    if not user_id:
        return None
    from backend.database import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as session:
            return await session.get(User, user_id)
    except Exception as exc:
        logger.warning(f"Failed to load user by id {user_id!r}: {exc}")
        return None


async def resolve_session_user(token: Optional[str], require_active: bool = True) -> Optional[AuthUser]:
    """把 token 解析成 ``AuthUser``；非活跃用户在 require_active 时返回 None。"""
    if not token:
        return None

    from backend.modules.auth.utils import read_session

    payload = read_session(token)
    if payload is None:
        return None

    user: Optional[User] = None
    user_id = payload.get("user_id")
    if user_id:
        user = await get_user_by_id(user_id)
    if user is None:
        user = await get_user_by_username(payload.get("username", ""))

    if user is None:
        # 历史 token / 单用户模式：多用户关闭时视为管理员，保持旧行为
        from backend.modules.multiuser.settings import load_settings

        settings = await load_settings()
        if not settings.enabled:
            return AuthUser(
                id="",
                username=payload.get("username", "admin"),
                role=ROLE_ADMIN,
                status=STATUS_ACTIVE,
            )
        return None

    auth_user = user_to_auth_user(user)
    if require_active and not auth_user.is_active:
        return None

    from backend.modules.multiuser.settings import load_settings

    if not (await load_settings()).enabled and not auth_user.is_admin:
        return None
    return auth_user


def create_user_session_token(user: AuthUser) -> str:
    """为用户签发会话 token（带 user_id）。"""
    from backend.modules.auth.utils import create_session

    return create_session(user.username, user_id=user.id or None)


def revoke_user_sessions(user: AuthUser) -> int:
    """吊销某用户全部会话。"""
    from backend.modules.auth.utils import revoke_all_sessions, revoke_sessions_for_user_id

    removed = 0
    if user.id:
        removed += revoke_sessions_for_user_id(user.id)
    # 旧 token 无 user_id，按用户名再吊销一次
    removed += revoke_all_sessions(user.username)
    return removed
