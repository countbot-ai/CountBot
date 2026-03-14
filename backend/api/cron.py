"""Cron API 端点"""

from typing import List, Optional, Union
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.modules.cron.service import CronService

router = APIRouter(prefix="/api/cron", tags=["cron"])

# 北京时区
_SHANGHAI_TZ = timezone(timedelta(hours=8))

# 内置任务 ID 前缀，禁止用户删除/修改
BUILTIN_PREFIX = "builtin:"


def _now_beijing() -> datetime:
    """获取当前北京时间（naive，无 tzinfo）"""
    return datetime.now(_SHANGHAI_TZ).replace(tzinfo=None)


def _to_shanghai_iso(dt: Optional[datetime]) -> Optional[str]:
    """将 naive datetime（北京时间）转为带时区的 ISO 字符串"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_SHANGHAI_TZ)
    return dt.isoformat()


async def get_cron_service(request: Request, db: AsyncSession = Depends(get_db)) -> CronService:
    """获取带 scheduler 的 CronService"""
    scheduler = getattr(request.app.state, 'cron_scheduler', None)
    return CronService(db, scheduler=scheduler)


# ============================================================================
# Request/Response Models
# ============================================================================


class CronJobInfo(BaseModel):
    """Cron 任务信息"""
    
    id: str = Field(..., description="任务 ID")
    name: str = Field(..., description="任务名称")
    schedule: str = Field(..., description="Cron 表达式")
    message: str = Field(..., description="要执行的消息")
    enabled: bool = Field(..., description="是否启用")
    channel: Optional[str] = Field(None, description="渠道名称")
    chat_id: Optional[str] = Field(None, description="聊天 ID")
    deliver_response: bool = Field(False, description="是否发送响应到渠道")
    last_run: Optional[str] = Field(None, description="上次运行时间")
    next_run: Optional[str] = Field(None, description="下次运行时间")
    last_status: Optional[str] = Field(None, description="上次执行状态")
    last_error: Optional[str] = Field(None, description="上次错误信息")
    run_count: int = Field(0, description="执行次数")
    error_count: int = Field(0, description="错误次数")
    created_at: str = Field(..., description="创建时间")
    max_retries: int = Field(0, description="最大重试次数")
    retry_delay: int = Field(60, description="重试延迟（秒）")
    delete_on_success: bool = Field(False, description="成功后自动删除")


class ListCronJobsResponse(BaseModel):
    """Cron 任务列表响应"""
    
    jobs: List[CronJobInfo] = Field(..., description="任务列表")


class CreateCronJobRequest(BaseModel):
    """创建 Cron 任务请求"""
    
    name: str = Field(..., description="任务名称")
    schedule: str = Field(..., description="Cron 表达式")
    message: str = Field(..., description="要执行的消息")
    enabled: bool = Field(True, description="是否启用")
    channel: Optional[str] = Field(None, description="渠道名称")
    chat_id: Optional[str] = Field(None, description="聊天 ID")
    deliver_response: bool = Field(False, description="是否发送响应到渠道")
    max_retries: int = Field(0, description="最大重试次数（0=不重试）")
    retry_delay: int = Field(60, description="重试延迟（秒）")
    delete_on_success: bool = Field(False, description="成功后自动删除")


class UpdateCronJobRequest(BaseModel):
    """更新 Cron 任务请求"""
    
    name: Optional[str] = Field(None, description="任务名称")
    schedule: Optional[str] = Field(None, description="Cron 表达式")
    message: Optional[str] = Field(None, description="要执行的消息")
    enabled: Optional[bool] = Field(None, description="是否启用")
    channel: Optional[str] = Field(None, description="渠道名称")
    chat_id: Optional[str] = Field(None, description="聊天 ID")
    deliver_response: Optional[bool] = Field(None, description="是否发送响应到渠道")
    max_retries: Optional[int] = Field(None, description="最大重试次数")
    retry_delay: Optional[int] = Field(None, description="重试延迟（秒）")
    delete_on_success: Optional[bool] = Field(None, description="成功后自动删除")


class CronJobResponse(BaseModel):
    """Cron 任务响应"""
    
    job: CronJobInfo = Field(..., description="任务信息")


class DeleteCronJobResponse(BaseModel):
    """删除 Cron 任务响应"""
    
    success: bool = Field(..., description="是否成功")


class ExecuteCronJobResponse(BaseModel):
    """执行 Cron 任务响应"""
    
    success: bool = Field(..., description="是否成功")
    message: Optional[str] = Field(None, description="消息")


class ValidateCronRequest(BaseModel):
    """验证 Cron 表达式请求"""
    
    schedule: str = Field(..., description="Cron 表达式")


class ValidateCronResponse(BaseModel):
    """验证 Cron 表达式响应"""
    
    valid: bool = Field(..., description="是否有效")
    description: Optional[str] = Field(None, description="表达式描述")
    next_run: Optional[str] = Field(None, description="下次运行时间")


class BatchCreateCronJobsRequest(BaseModel):
    """批量创建 Cron 任务请求"""
    
    jobs: List[CreateCronJobRequest] = Field(..., description="任务列表")


class BatchCreateCronJobsResponse(BaseModel):
    """批量创建 Cron 任务响应"""
    
    success_count: int = Field(..., description="成功创建数量")
    failed_count: int = Field(..., description="失败数量")
    jobs: List[CronJobInfo] = Field(..., description="成功创建的任务")
    errors: List[dict] = Field(..., description="失败的任务及错误信息")


class BatchDeleteCronJobsRequest(BaseModel):
    """批量删除 Cron 任务请求"""
    
    job_ids: List[str] = Field(..., description="任务 ID 列表")


class BatchDeleteCronJobsResponse(BaseModel):
    """批量删除 Cron 任务响应"""
    
    success_count: int = Field(..., description="成功删除数量")
    failed_count: int = Field(..., description="失败数量")
    deleted_ids: List[str] = Field(..., description="成功删除的任务 ID")
    errors: List[dict] = Field(..., description="失败的任务及错误信息")


class CronJobDetailResponse(BaseModel):
    """Cron 任务详细信息响应"""
    
    job: CronJobInfo = Field(..., description="任务信息")
    last_response: Optional[str] = Field(None, description="完整的上次响应")
    last_error: Optional[str] = Field(None, description="完整的上次错误")


# ============================================================================
# Cron Endpoints
# ============================================================================


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
                    chat_id=job_req.chat_id,
                    deliver_response=job_req.deliver_response,
                    max_retries=job_req.max_retries,
                    retry_delay=job_req.retry_delay,
                    delete_on_success=job_req.delete_on_success,
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
            CronJobInfo(
                id=job.id,
                name=job.name,
                schedule=job.schedule,
                message=job.message,
                enabled=job.enabled,
                channel=job.channel,
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
        # 内置任务只允许修改 enabled/channel/chat_id/deliver_response/schedule
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
        
        # 检查是否正在执行（防止重复执行）
        scheduler = getattr(app.state, 'cron_scheduler', None)
        if scheduler and scheduler.is_job_active(job_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Job '{job.name}' is already running"
            )
        
        logger.info(f"Manually triggering cron job: {job.name} ({job_id})")
        
        # 捕获需要的字段，避免在后台任务中使用已关闭的 db session
        job_name = job.name
        job_message = job.message
        job_channel = job.channel
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
