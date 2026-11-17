"""Cron 任务的立即执行与表达式校验路由。"""

import asyncio

from fastapi import Depends, HTTPException, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.modules.cron.service import CronService

from backend.api.cron._common import (
    _to_shanghai_iso,
    router,
)
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

        scheduler = getattr(app.state, 'cron_scheduler', None)
        if not scheduler:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Cron scheduler not available"
            )

        cron_service = CronService(db, scheduler=scheduler)
        job = await cron_service.get_job(job_id)

        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cron job '{job_id}' not found"
            )

        # 占用执行权：检查与占用合并为一次同步调用，避免并发请求同时通过检查
        if not scheduler.try_acquire_job(job_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Job '{job.name}' is already running"
            )

        job_name = job.name

        try:
            # 先落库「运行中」：接口返回后前端刷新、或退出页面再回来，
            # 都能看到任务当前处于执行中，而不是一片空白。
            await cron_service.mark_job_running(job_id)
            asyncio.create_task(scheduler.run_job_manually(job_id))
        except Exception:
            scheduler.release_job(job_id)
            raise

        logger.info(f"Manually triggering cron job: {job_name} ({job_id})")

        return ExecuteCronJobResponse(
            success=True,
            message=f"任务 '{job_name}' 已开始执行",
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
