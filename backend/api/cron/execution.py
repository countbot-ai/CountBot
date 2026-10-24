"""Cron 任务的立即执行与表达式校验路由。"""

import asyncio
from typing import Optional
from fastapi import Depends, HTTPException, Request, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.modules.cron.service import CronService

from backend.api.cron._common import (
    _now_beijing,
    _to_shanghai_iso,
    get_cron_service,
    router,
)
from backend.api.cron.helpers import _find_cron_session, _get_cron_job_or_404
from backend.api.cron.models import (
    ExecuteCronJobResponse,
    ValidateCronRequest,
    ValidateCronResponse,
)


@router.post("/jobs/{job_id}/run", response_model=ExecuteCronJobResponse)
async def trigger_cron_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> ExecuteCronJobResponse:
    """
    手动触发 Cron 任务立即执行（异步，立即返回）
    
    Args:
        job_id: 任务 ID
        db: 数据库会话
        
    Returns:
        ExecuteCronJobResponse: 提交结果
    """
    try:
        from backend.app import app
        import asyncio
        
        # 获取执行器
        executor = getattr(app.state, 'cron_executor', None)
        if not executor:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Cron executor not available"
            )
        
        # 获取任务
        cron_service = CronService(db)
        job = await cron_service.get_job(job_id)
        
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cron job '{job_id}' not found"
            )
        
        # 占用执行权：检查与占用合并为一次同步调用，避免并发请求同时通过检查
        scheduler = getattr(app.state, 'cron_scheduler', None)
        if scheduler:
            if not scheduler.try_acquire_job(job_id):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Job '{job.name}' is already running"
                )
        else:
            # 无调度器时退化为原检查，仍可阻止顺序重复提交
            pass
        
        logger.info(f"Manually triggering cron job: {job.name} ({job_id})")
        
        # 捕获需要的字段，避免在后台任务中使用已关闭的 db session
        job_name = job.name
        job_message = job.message
        job_channel = job.channel
        job_account_id = job.account_id
        job_chat_id = job.chat_id
        job_deliver_response = job.deliver_response
        job_schedule = job.schedule
        job_enabled = job.enabled
        
        # 后台异步执行
        async def _run_in_background():
            from backend.database import get_db_session_factory
            try:
                response = await executor.execute(
                    job_id=job_id,
                    message=job_message,
                    channel=job_channel,
                    account_id=job_account_id,
                    chat_id=job_chat_id,
                    deliver_response=job_deliver_response
                )
                # 用独立 session 更新状态
                async with get_db_session_factory()() as bg_db:
                    bg_service = CronService(bg_db)
                    bg_job = await bg_service.get_job(job_id)
                    if bg_job:
                        bg_job.last_run = _now_beijing()
                        bg_job.last_status = "ok"
                        bg_job.last_response = response[:1000] if response else None
                        bg_job.last_error = None
                        bg_job.run_count = (bg_job.run_count or 0) + 1
                        if bg_job.enabled:
                            bg_job.next_run = bg_service.calculate_next_run(bg_job.schedule)
                        await bg_db.commit()
                logger.info(f"Manual job completed: {job_name}")
            except Exception as e:
                logger.error(f"Manual job failed: {job_name} - {e}")
                try:
                    async with get_db_session_factory()() as bg_db:
                        bg_service = CronService(bg_db)
                        bg_job = await bg_service.get_job(job_id)
                        if bg_job:
                            bg_job.last_run = _now_beijing()
                            bg_job.last_status = "error"
                            bg_job.last_error = str(e)[:1000]
                            bg_job.run_count = (bg_job.run_count or 0) + 1
                            bg_job.error_count = (bg_job.error_count or 0) + 1
                            if bg_job.enabled:
                                bg_job.next_run = bg_service.calculate_next_run(bg_job.schedule)
                            await bg_db.commit()
                except Exception as db_err:
                    logger.error(f"Failed to update error status: {db_err}")
            finally:
                if scheduler:
                    scheduler.release_job(job_id)

        asyncio.create_task(_run_in_background())
        
        return ExecuteCronJobResponse(
            success=True,
            message=f"任务 '{job_name}' 已提交执行",
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to trigger cron job: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger cron job: {str(e)}"
        )

@router.post("/validate", response_model=ValidateCronResponse)
async def validate_cron_schedule(
    request: ValidateCronRequest,
    db: AsyncSession = Depends(get_db),
) -> ValidateCronResponse:
    """
    验证 Cron 表达式并返回描述和下次运行时间
    
    Args:
        request: 验证请求
        db: 数据库会话
        
    Returns:
        ValidateCronResponse: 验证结果
    """
    try:
        cron_service = CronService(db)
        
        # 验证表达式
        valid = cron_service.validate_schedule(request.schedule)
        if not valid:
            return ValidateCronResponse(valid=False)
        
        # 获取描述和下次运行时间
        description = cron_service.get_schedule_description(request.schedule)
        next_run = cron_service.calculate_next_run(request.schedule)
        
        return ValidateCronResponse(
            valid=True,
            description=description,
            next_run=_to_shanghai_iso(next_run),
        )
        
    except Exception as e:
        return ValidateCronResponse(valid=False, description=str(e))
