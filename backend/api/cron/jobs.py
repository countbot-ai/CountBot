"""Cron 任务的增删改查路由。"""

from fastapi import Depends, HTTPException, status
from loguru import logger

from backend.modules.cron.service import CronService

from backend.api.cron._common import (
    BUILTIN_PREFIX,
    build_job_info,
    get_cron_service,
    router,
)
from backend.api.cron.models import (
    CreateCronJobRequest,
    CronJobDetailResponse,
    CronJobResponse,
    DeleteCronJobResponse,
    ListCronJobsResponse,
    UpdateCronJobRequest,
)


@router.get("/jobs", response_model=ListCronJobsResponse)
async def list_cron_jobs(
    cron_service: CronService = Depends(get_cron_service),
) -> ListCronJobsResponse:
    """
    获取所有 Cron 任务列表
    
    Args:
        cron_service: Cron 服务（带 scheduler）
        
    Returns:
        ListCronJobsResponse: 任务列表
    """
    try:
        jobs = await cron_service.list_jobs()
        
        # 转换为响应格式
        jobs_info = [
            build_job_info(job, cron_service.scheduler)
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
    cron_service: CronService = Depends(get_cron_service),
) -> CronJobDetailResponse:
    """
    获取 Cron 任务详细信息（包括完整的响应和错误）
    
    Args:
        job_id: 任务 ID
        cron_service: Cron 服务（带 scheduler）
        
    Returns:
        CronJobDetailResponse: 任务详细信息
    """
    try:
        job = await cron_service.get_job(job_id)
        
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cron job '{job_id}' not found"
            )
        
        return CronJobDetailResponse(
            job=build_job_info(job, cron_service.scheduler, error_limit=500),
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
            link_context=request.link_context,
            model_provider=request.model_provider,
            model_name=request.model_name,
        )
        
        return CronJobResponse(
            job=build_job_info(job, cron_service.scheduler)
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
            link_context=request.link_context,
            model_provider=request.model_provider,
            model_name=request.model_name,
        )
        
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cron job '{job_id}' not found"
            )
        
        return CronJobResponse(
            job=build_job_info(job, cron_service.scheduler)
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
