"""Cron 任务的批量创建与批量删除路由。"""

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
    BatchCreateCronJobsRequest,
    BatchCreateCronJobsResponse,
    BatchDeleteCronJobsRequest,
    BatchDeleteCronJobsResponse,
)


@router.post("/jobs/batch", response_model=BatchCreateCronJobsResponse)
async def batch_create_cron_jobs(
    request: BatchCreateCronJobsRequest,
    cron_service: CronService = Depends(get_cron_service),
) -> BatchCreateCronJobsResponse:
    """
    批量创建 Cron 任务
    
    Args:
        request: 批量创建请求
        cron_service: Cron 服务（带 scheduler）
        
    Returns:
        BatchCreateCronJobsResponse: 批量创建结果
    """
    try:
        success_jobs = []
        errors = []
        
        for idx, job_req in enumerate(request.jobs):
            try:
                job = await cron_service.add_job(
                    name=job_req.name,
                    schedule=job_req.schedule,
                    message=job_req.message,
                    enabled=job_req.enabled,
                    channel=job_req.channel,
                    account_id=job_req.account_id,
                    chat_id=job_req.chat_id,
                    deliver_response=job_req.deliver_response,
                    max_retries=job_req.max_retries,
                    retry_delay=job_req.retry_delay,
                    delete_on_success=job_req.delete_on_success,
                    link_context=job_req.link_context,
                    model_provider=job_req.model_provider,
                    model_name=job_req.model_name,
                )
                success_jobs.append(job)
            except Exception as e:
                logger.error(f"Failed to create job {idx} ({job_req.name}): {e}")
                errors.append({
                    "index": idx,
                    "name": job_req.name,
                    "error": str(e)
                })
        
        # 转换为响应格式
        jobs_info = [
            build_job_info(job, cron_service.scheduler)
            for job in success_jobs
        ]
        
        return BatchCreateCronJobsResponse(
            success_count=len(success_jobs),
            failed_count=len(errors),
            jobs=jobs_info,
            errors=errors
        )
        
    except Exception as e:
        logger.exception(f"Failed to batch create cron jobs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to batch create cron jobs: {str(e)}"
        )

@router.post("/jobs/batch-delete", response_model=BatchDeleteCronJobsResponse)
async def batch_delete_cron_jobs(
    request: BatchDeleteCronJobsRequest,
    cron_service: CronService = Depends(get_cron_service),
) -> BatchDeleteCronJobsResponse:
    """
    批量删除 Cron 任务
    
    Args:
        request: 批量删除请求
        cron_service: Cron 服务（带 scheduler）
        
    Returns:
        BatchDeleteCronJobsResponse: 批量删除结果
    """
    try:
        deleted_ids = []
        errors = []
        
        for job_id in request.job_ids:
            try:
                # 禁止删除内置任务
                if job_id.startswith(BUILTIN_PREFIX):
                    errors.append({
                        "job_id": job_id,
                        "error": "内置系统任务不可删除"
                    })
                    continue
                
                success = await cron_service.delete_job(job_id)
                
                if success:
                    deleted_ids.append(job_id)
                else:
                    errors.append({
                        "job_id": job_id,
                        "error": "任务不存在"
                    })
            except Exception as e:
                logger.error(f"Failed to delete job {job_id}: {e}")
                errors.append({
                    "job_id": job_id,
                    "error": str(e)
                })
        
        return BatchDeleteCronJobsResponse(
            success_count=len(deleted_ids),
            failed_count=len(errors),
            deleted_ids=deleted_ids,
            errors=errors
        )
        
    except Exception as e:
        logger.exception(f"Failed to batch delete cron jobs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to batch delete cron jobs: {str(e)}"
        )
