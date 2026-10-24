"""Cron 任务的增删改查路由。"""

from typing import Optional
from fastapi import Depends, HTTPException, Request, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.modules.cron.service import CronService

from backend.api.cron._common import (
    BUILTIN_PREFIX,
    _now_beijing,
    _to_shanghai_iso,
    get_cron_service,
    router,
)
from backend.api.cron.helpers import _get_cron_job_or_404, _find_cron_session
from backend.api.cron.models import (
    CreateCronJobRequest,
    CronJobDetailResponse,
    CronJobInfo,
    CronJobResponse,
    DeleteCronJobResponse,
    ListCronJobsResponse,
    UpdateCronJobRequest,
)


@router.get("/jobs", response_model=ListCronJobsResponse)
async def list_cron_jobs(db: AsyncSession = Depends(get_db)) -> ListCronJobsResponse:
    """
    获取所有 Cron 任务列表
    
    Args:
        db: 数据库会话
        
    Returns:
        ListCronJobsResponse: 任务列表
    """
    try:
        cron_service = CronService(db)
        jobs = await cron_service.list_jobs()
        
        # 转换为响应格式
        jobs_info = [
            CronJobInfo(
                id=job.id,
                name=job.name,
                schedule=job.schedule,
                message=job.message,
                enabled=job.enabled,
                channel=job.channel,
                account_id=job.account_id,
                chat_id=job.chat_id,
                deliver_response=job.deliver_response,
                last_run=_to_shanghai_iso(job.last_run),
                next_run=_to_shanghai_iso(job.next_run),
                last_status=job.last_status,
                last_error=job.last_error,
                run_count=job.run_count or 0,
                error_count=job.error_count or 0,
                created_at=_to_shanghai_iso(job.created_at),
                max_retries=job.max_retries or 0,
                retry_delay=job.retry_delay or 60,
                delete_on_success=job.delete_on_success or False,
            )
            for job in jobs
        ]
        
        return ListCronJobsResponse(jobs=jobs_info)
        
    except Exception as e:
        logger.exception(f"Failed to list cron jobs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list cron jobs: {str(e)}"
        )

@router.get("/jobs/{job_id}", response_model=CronJobDetailResponse)
async def get_cron_job_detail(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> CronJobDetailResponse:
    """
    获取 Cron 任务详细信息（包括完整的响应和错误）
    
    Args:
        job_id: 任务 ID
        db: 数据库会话
        
    Returns:
        CronJobDetailResponse: 任务详细信息
    """
    try:
        cron_service = CronService(db)
        job = await cron_service.get_job(job_id)
        
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cron job '{job_id}' not found"
            )
        
        return CronJobDetailResponse(
            job=CronJobInfo(
                id=job.id,
                name=job.name,
                schedule=job.schedule,
                message=job.message,
                enabled=job.enabled,
                channel=job.channel,
                account_id=job.account_id,
                chat_id=job.chat_id,
                deliver_response=job.deliver_response,
                last_run=_to_shanghai_iso(job.last_run),
                next_run=_to_shanghai_iso(job.next_run),
                last_status=job.last_status,
                last_error=job.last_error[:500] if job.last_error else None,  # 列表中显示截断版本
                run_count=job.run_count or 0,
                error_count=job.error_count or 0,
                created_at=_to_shanghai_iso(job.created_at),
                max_retries=job.max_retries or 0,
                retry_delay=job.retry_delay or 60,
                delete_on_success=job.delete_on_success or False,
            ),
            last_response=job.last_response,  # 完整响应
            last_error=job.last_error,  # 完整错误
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get cron job detail: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get cron job detail: {str(e)}"
        )

@router.post("/jobs", response_model=CronJobResponse)
async def create_cron_job(
    request: CreateCronJobRequest,
    cron_service: CronService = Depends(get_cron_service),
) -> CronJobResponse:
    """
    创建新的 Cron 任务
    
    Args:
        request: 创建任务请求
        cron_service: Cron 服务（带 scheduler）
        
    Returns:
        CronJobResponse: 创建的任务
    """
    try:
        job = await cron_service.add_job(
            name=request.name,
            schedule=request.schedule,
            message=request.message,
            enabled=request.enabled,
            channel=request.channel,
            account_id=request.account_id,
            chat_id=request.chat_id,
            deliver_response=request.deliver_response,
            max_retries=request.max_retries,
            retry_delay=request.retry_delay,
            delete_on_success=request.delete_on_success,
        )
        
        return CronJobResponse(
            job=CronJobInfo(
                id=job.id,
                name=job.name,
                schedule=job.schedule,
                message=job.message,
                enabled=job.enabled,
                channel=job.channel,
                account_id=job.account_id,
                chat_id=job.chat_id,
                deliver_response=job.deliver_response,
                last_run=_to_shanghai_iso(job.last_run),
                next_run=_to_shanghai_iso(job.next_run),
                last_status=job.last_status,
                last_error=job.last_error,
                run_count=job.run_count or 0,
                error_count=job.error_count or 0,
                created_at=_to_shanghai_iso(job.created_at),
                max_retries=job.max_retries or 0,
                retry_delay=job.retry_delay or 60,
                delete_on_success=job.delete_on_success or False,
            )
        )
        
    except ValueError as e:
        # 无效的 cron 表达式
        logger.warning(f"Invalid cron schedule: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.exception(f"Failed to create cron job: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create cron job: {str(e)}"
        )

@router.put("/jobs/{job_id}", response_model=CronJobResponse)
async def update_cron_job(
    job_id: str,
    request: UpdateCronJobRequest,
    cron_service: CronService = Depends(get_cron_service),
) -> CronJobResponse:
    """
    更新 Cron 任务
    
    Args:
        job_id: 任务 ID
        request: 更新任务请求
        cron_service: Cron 服务（带 scheduler）
        
    Returns:
        CronJobResponse: 更新后的任务
    """
    try:
        # 内置任务只允许修改 enabled/channel/account_id/chat_id/deliver_response/schedule
        if job_id.startswith(BUILTIN_PREFIX):
            if request.name is not None or request.message is not None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="内置系统任务不可修改名称和消息内容"
                )
        
        job = await cron_service.update_job(
            job_id=job_id,
            name=request.name,
            schedule=request.schedule,
            message=request.message,
            enabled=request.enabled,
            channel=request.channel,
            account_id=request.account_id,
            chat_id=request.chat_id,
            deliver_response=request.deliver_response,
            max_retries=request.max_retries,
            retry_delay=request.retry_delay,
            delete_on_success=request.delete_on_success,
        )
        
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cron job '{job_id}' not found"
            )
        
        return CronJobResponse(
            job=CronJobInfo(
                id=job.id,
                name=job.name,
                schedule=job.schedule,
                message=job.message,
                enabled=job.enabled,
                channel=job.channel,
                account_id=job.account_id,
                chat_id=job.chat_id,
                deliver_response=job.deliver_response,
                last_run=_to_shanghai_iso(job.last_run),
                next_run=_to_shanghai_iso(job.next_run),
                last_status=job.last_status,
                last_error=job.last_error,
                run_count=job.run_count or 0,
                error_count=job.error_count or 0,
                created_at=_to_shanghai_iso(job.created_at),
                max_retries=job.max_retries or 0,
                retry_delay=job.retry_delay or 60,
                delete_on_success=job.delete_on_success or False,
            )
        )
        
    except HTTPException:
        raise
    except ValueError as e:
        # 无效的 cron 表达式
        logger.warning(f"Invalid cron schedule: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.exception(f"Failed to update cron job: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update cron job: {str(e)}"
        )

@router.delete("/jobs/{job_id}", response_model=DeleteCronJobResponse)
async def delete_cron_job(
    job_id: str,
    cron_service: CronService = Depends(get_cron_service),
) -> DeleteCronJobResponse:
    """
    删除 Cron 任务
    
    Args:
        job_id: 任务 ID
        cron_service: Cron 服务（带 scheduler）
        
    Returns:
        DeleteCronJobResponse: 删除结果
    """
    try:
        # 禁止删除内置任务
        if job_id.startswith(BUILTIN_PREFIX):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="内置系统任务不可删除"
            )
        
        success = await cron_service.delete_job(job_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cron job '{job_id}' not found"
            )
        
        return DeleteCronJobResponse(success=True)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to delete cron job: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete cron job: {str(e)}"
        )
