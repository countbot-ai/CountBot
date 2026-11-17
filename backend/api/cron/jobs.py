"""Cron 任务的增删改查路由。"""

from types import SimpleNamespace

from fastapi import Depends, HTTPException, status
from loguru import logger

from backend.modules.cron.service import CronService

from backend.modules.multiuser.identity import AuthUser
from backend.modules.multiuser.permissions import require_active_user
from backend.api.cron._common import (
    BUILTIN_PREFIX,
    build_job_info,
    is_job_running,
    validate_channel_push_for_user,
    validate_model_for_user,
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

_DELIVERY_FIELDS = ("channel", "account_id", "chat_id")


@router.get("/jobs", response_model=ListCronJobsResponse)
async def list_cron_jobs(
    cron_service: CronService = Depends(get_cron_service),
) -> ListCronJobsResponse:
    """获取所有 Cron 任务。"""
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
    """获取 Cron 任务详情，包含最近一次响应与错误。"""
    try:
        job = await cron_service.get_job(job_id)

        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cron job '{job_id}' not found"
            )

        return CronJobDetailResponse(
            job=build_job_info(job, cron_service.scheduler, error_limit=500),
            last_response=job.last_response,
            last_error=job.last_error,
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
    user: AuthUser = Depends(require_active_user),
) -> CronJobResponse:
    """创建 Cron 任务。"""
    try:
        await validate_channel_push_for_user(user, request)
        await validate_model_for_user(user, request)

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
    user: AuthUser = Depends(require_active_user),
) -> CronJobResponse:
    """更新 Cron 任务。"""
    try:
        # 内置任务仅允许修改运行相关字段
        if job_id.startswith(BUILTIN_PREFIX):
            if request.name is not None or request.message is not None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="内置系统任务不可修改名称和消息内容"
                )

        existing = await cron_service.get_job(job_id)
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cron job '{job_id}' not found"
            )

        fields_set = request.model_fields_set
        delivery_touched = any(field in fields_set for field in _DELIVERY_FIELDS + ("deliver_response",))
        # 历史网页任务从未真正推送；允许先修其他字段，待用户重选渠道后再收敛
        legacy_web_push = existing.deliver_response and existing.channel == "web" and not delivery_touched

        if not legacy_web_push:
            effective = SimpleNamespace(
                deliver_response=(
                    request.deliver_response
                    if "deliver_response" in fields_set
                    else existing.deliver_response
                ),
                channel=(
                    request.channel if "channel" in fields_set else existing.channel
                ),
                account_id=(
                    request.account_id if "account_id" in fields_set else existing.account_id
                ),
                chat_id=(
                    request.chat_id if "chat_id" in fields_set else existing.chat_id
                ),
                model_provider=(
                    request.model_provider
                    if request.model_provider is not None
                    else existing.model_provider
                ),
                model_name=(
                    request.model_name
                    if request.model_name is not None
                    else existing.model_name
                ),
            )
            await validate_channel_push_for_user(user, effective)
            await validate_model_for_user(user, effective)

        clear_delivery = (
            "deliver_response" in fields_set and request.deliver_response is False
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
            clear_delivery=clear_delivery,
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
    """删除 Cron 任务。"""
    try:
        # 禁止删除内置任务
        if job_id.startswith(BUILTIN_PREFIX):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="内置系统任务不可删除"
            )

        if cron_service.scheduler and cron_service.scheduler.is_job_active(job_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="任务正在执行，暂不能删除"
            )

        job = await cron_service.get_job(job_id)
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cron job '{job_id}' not found"
            )
        if is_job_running(job, cron_service.scheduler):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="任务正在执行，暂不能删除"
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
