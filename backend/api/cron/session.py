"""Cron 任务关联会话的查询、清理与重置路由。"""

from typing import Optional
from fastapi import Depends, HTTPException, status
from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.message import Message
from backend.modules.cron.service import CronService

from backend.api.cron._common import (
    _now_beijing,
    _to_shanghai_iso,
    get_cron_service,
    router,
)
from backend.api.cron.helpers import _find_cron_session, _get_cron_job_or_404
from backend.api.cron.models import (
    CleanupCronSessionRequest,
    CleanupCronSessionResponse,
    CronJobMessagesResponse,
    CronSessionMessage,
    ResetCronSessionResponse,
)


@router.get("/jobs/{job_id}/messages", response_model=CronJobMessagesResponse)
async def get_cron_job_messages(
    job_id: str,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
) -> CronJobMessagesResponse:
    """获取 Cron 任务关联会话的消息。"""
    try:
        from backend.modules.session.manager import SessionManager

        job = await _get_cron_job_or_404(db, job_id)
        session = await _find_cron_session(db, job)

        if not session:
            return CronJobMessagesResponse(
                job_id=job.id,
                job_name=job.name,
                session_id=None,
                session_name=None,
                messages=[],
            )

        session_manager = SessionManager(db)
        safe_limit = max(1, min(int(limit), 200))
        messages = await session_manager.get_messages(session.id, limit=safe_limit)

        return CronJobMessagesResponse(
            job_id=job.id,
            job_name=job.name,
            session_id=session.id,
            session_name=session.name,
            messages=[
                CronSessionMessage(
                    role=msg.role,
                    content=msg.content,
                    created_at=_to_shanghai_iso(msg.created_at),
                )
                for msg in messages
            ],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get cron job messages: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get cron job messages: {str(e)}"
        )

@router.post("/jobs/{job_id}/session/cleanup", response_model=CleanupCronSessionResponse)
async def cleanup_cron_job_session(
    job_id: str,
    request: CleanupCronSessionRequest,
    db: AsyncSession = Depends(get_db),
) -> CleanupCronSessionResponse:
    """清理 Cron 任务关联会话，保留最近 N 条消息。"""
    try:
        from backend.modules.session.manager import SessionManager

        job = await _get_cron_job_or_404(db, job_id)
        session = await _find_cron_session(db, job)

        if not session:
            return CleanupCronSessionResponse(
                success=True,
                job_id=job.id,
                job_name=job.name,
                session_id=None,
                session_name=None,
                deleted_count=0,
                kept_count=0,
            )

        session_manager = SessionManager(db)
        keep = max(0, int(request.keep))
        messages = await session_manager.get_messages(session.id)
        total = len(messages)

        if total == 0:
            return CleanupCronSessionResponse(
                success=True,
                job_id=job.id,
                job_name=job.name,
                session_id=session.id,
                session_name=session.name,
                deleted_count=0,
                kept_count=0,
            )

        if keep >= total:
            return CleanupCronSessionResponse(
                success=True,
                job_id=job.id,
                job_name=job.name,
                session_id=session.id,
                session_name=session.name,
                deleted_count=0,
                kept_count=total,
            )

        if keep == 0:
            await session_manager.clear_messages(session.id)
            return CleanupCronSessionResponse(
                success=True,
                job_id=job.id,
                job_name=job.name,
                session_id=session.id,
                session_name=session.name,
                deleted_count=total,
                kept_count=0,
            )

        to_delete = messages[:-keep]
        deleted_count = 0
        for message in to_delete:
            if await session_manager.delete_message(message.id):
                deleted_count += 1

        return CleanupCronSessionResponse(
            success=True,
            job_id=job.id,
            job_name=job.name,
            session_id=session.id,
            session_name=session.name,
            deleted_count=deleted_count,
            kept_count=keep,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to cleanup cron job session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cleanup cron job session: {str(e)}"
        )

@router.post("/jobs/{job_id}/session/reset", response_model=ResetCronSessionResponse)
async def reset_cron_job_session(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> ResetCronSessionResponse:
    """重置 Cron 任务关联会话。"""
    try:
        from backend.modules.session.manager import SessionManager

        job = await _get_cron_job_or_404(db, job_id)
        session = await _find_cron_session(db, job)

        if not session:
            return ResetCronSessionResponse(
                success=True,
                job_id=job.id,
                job_name=job.name,
                session_id=None,
                session_name=None,
                deleted_message_count=0,
            )

        session_manager = SessionManager(db)
        deleted_message_count = await session_manager.get_message_count(session.id)
        await session_manager.delete_session(session.id)

        return ResetCronSessionResponse(
            success=True,
            job_id=job.id,
            job_name=job.name,
            session_id=session.id,
            session_name=session.name,
            deleted_message_count=deleted_message_count,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to reset cron job session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset cron job session: {str(e)}"
        )
