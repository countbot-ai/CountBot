"""管理员账号迁移：把 settings 中的存量凭据同步到 users 表，重复调用幂等。"""

from __future__ import annotations

import uuid
from typing import Optional

from loguru import logger
from sqlalchemy import select, func

from backend.models.user import ROLE_ADMIN, STATUS_ACTIVE, User


async def _get_admin_row(session) -> Optional[User]:
    result = await session.execute(select(User).where(User.role == ROLE_ADMIN).limit(1))
    return result.scalars().first()


async def get_admin_user() -> Optional[User]:
    """返回当前管理员用户行（不存在则为 None）。"""
    from backend.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        return await _get_admin_row(session)


async def count_users() -> int:
    from backend.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(func.count()).select_from(User))
        return int(result.scalar() or 0)


async def ensure_admin_user() -> Optional[User]:
    """确保管理员用户行存在，缺失时从 settings 存量凭据迁移。"""
    from backend.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        existing = await _get_admin_row(session)
        if existing is not None:
            return existing

        from backend.modules.auth.router import get_stored_credentials

        username, password_hash = await get_stored_credentials()
        if not username:
            logger.info("No stored credentials found; admin user will be created on setup")
            return None

        admin = User(
            id=str(uuid.uuid4()),
            username=username,
            password_hash=password_hash,
            role=ROLE_ADMIN,
            status=STATUS_ACTIVE,
            display_name=username,
        )
        session.add(admin)
        await session.commit()
        await session.refresh(admin)
        logger.info(f"Migrated existing administrator into users table: {username}")
        return admin


async def sync_admin_credentials(username: str, password_hash: str) -> None:
    """把管理员凭据同步到 users 表；用户名变更时改名，保持单一管理员。"""
    from backend.database import AsyncSessionLocal

    normalized = (username or "").strip()
    if not normalized:
        return

    async with AsyncSessionLocal() as session:
        admin = await _get_admin_row(session)
        if admin is None:
            session.add(
                User(
                    id=str(uuid.uuid4()),
                    username=normalized,
                    password_hash=password_hash,
                    role=ROLE_ADMIN,
                    status=STATUS_ACTIVE,
                    display_name=normalized,
                )
            )
        else:
            admin.username = normalized
            admin.password_hash = password_hash
            admin.status = STATUS_ACTIVE
            admin.role = ROLE_ADMIN
        await session.commit()
