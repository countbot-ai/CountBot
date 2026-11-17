"""Cron API 内部辅助：任务查找与会话解析。"""

from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.session import Session
from backend.modules.cron.service import CronService
from backend.modules.session.manager import session_name_matches


async def _get_cron_job_or_404(db: AsyncSession, job_id: str, owner_id: Optional[str] = None):
    cron_service = CronService(db, owner_id=owner_id)
    job = await cron_service.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cron job '{job_id}' not found"
        )
    return job


async def _find_cron_session(db: AsyncSession, job):
    from sqlalchemy import select
    from backend.models.session import Session
    from backend.modules.session.manager import session_name_matches

    owner_id = getattr(job, "owner_id", None)
    base_query = select(Session)
    if owner_id:
        base_query = base_query.where(Session.owner_id == owner_id)

    if job.channel and job.chat_id:
        account_id = str(job.account_id or "default").strip() or "default"
        prefix = f"{job.channel}:{account_id}:{job.chat_id}"
        result = await db.execute(
            base_query
            .where(session_name_matches(prefix))
            .order_by(Session.created_at.desc())
            .limit(1)
        )
        session = result.scalar_one_or_none()

        if not session and account_id == "default":
            legacy_prefix = f"{job.channel}:{job.chat_id}"
            result = await db.execute(
                base_query
                .where(session_name_matches(legacy_prefix))
                .order_by(Session.created_at.desc())
                .limit(1)
            )
            session = result.scalar_one_or_none()

        return session

    result = await db.execute(
        base_query
        .where(Session.name == f"cron:{job.id}")
        .order_by(Session.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
