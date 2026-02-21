"""Cron API 端点"""

from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
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


def _to_shanghai_iso(dt: datetime | None) -> str | None:
    """将 naive datetime（北京时间）转为带时区的 ISO 字符串"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_SHANGHAI_TZ)
    return dt.isoformat()


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
    channel: str | None = Field(None, description="渠道名称")
    chat_id: str | None = Field(None, description="聊天 ID")
    deliver_response: bool = Field(False, description="是否发送响应到渠道")
    last_run: str | None = Field(None, description="上次运行时间")
    next_run: str | None = Field(None, description="下次运行时间")
    last_status: str | None = Field(None, description="上次执行状态")
    last_error: str | None = Field(None, description="上次错误信息")
    run_count: int = Field(0, description="执行次数")
    error_count: int = Field(0, description="错误次数")
    created_at: str = Field(..., description="创建时间")


class ListCronJobsResponse(BaseModel):
    """Cron 任务列表响应"""
    
    jobs: list[CronJobInfo] = Field(..., description="任务列表")


class CreateCronJobRequest(BaseModel):
    """创建 Cron 任务请求"""
    
    name: str = Field(..., description="任务名称")
    schedule: str = Field(..., description="Cron 表达式")
    message: str = Field(..., description="要执行的消息")
    enabled: bool = Field(True, description="是否启用")
    channel: str | None = Field(None, description="渠道名称")
    chat_id: str | None = Field(None, description="聊天 ID")
    deliver_response: bool = Field(False, description="是否发送响应到渠道")


class UpdateCronJobRequest(BaseModel):
    """更新 Cron 任务请求"""
    
    name: str | None = Field(None, description="任务名称")
    schedule: str | None = Field(None, description="Cron 表达式")
    message: str | None = Field(None, description="要执行的消息")
    enabled: bool | None = Field(None, description="是否启用")
    channel: str | None = Field(None, description="渠道名称")
    chat_id: str | None = Field(None, description="聊天 ID")
    deliver_response: bool | None = Field(None, description="是否发送响应到渠道")


class CronJobResponse(BaseModel):
    """Cron 任务响应"""
    
    job: CronJobInfo = Field(..., description="任务信息")


class DeleteCronJobResponse(BaseModel):
    """删除 Cron 任务响应"""
    
    success: bool = Field(..., description="是否成功")


class ExecuteCronJobResponse(BaseModel):
    """执行 Cron 任务响应"""
    
    success: bool = Field(..., description="是否成功")
    message: str | None = Field(None, description="消息")


class ValidateCronRequest(BaseModel):
    """验证 Cron 表达式请求"""
    
    schedule: str = Field(..., description="Cron 表达式")


class ValidateCronResponse(BaseModel):
    """验证 Cron 表达式响应"""
    
    valid: bool = Field(..., description="是否有效")
    description: str | None = Field(None, description="表达式描述")
    next_run: str | None = Field(None, description="下次运行时间")


class CronJobDetailResponse(BaseModel):
    """Cron 任务详细信息响应"""
    
    job: CronJobInfo = Field(..., description="任务信息")
    last_response: str | None = Field(None, description="完整的上次响应")
    last_error: str | None = Field(None, description="完整的上次错误")


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
                chat_id=job.chat_id,
                deliver_response=job.deliver_response,
                last_run=_to_shanghai_iso(job.last_run),
                next_run=_to_shanghai_iso(job.next_run),
                last_status=job.last_status,
                last_error=job.last_error[:500] if job.last_error else None,  # 列表中显示截断版本
                run_count=job.run_count or 0,
                error_count=job.error_count or 0,
                created_at=_to_shanghai_iso(job.created_at),
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
    db: AsyncSession = Depends(get_db),
) -> CronJobResponse:
    """
    创建新的 Cron 任务
    
    Args:
        request: 创建任务请求
        db: 数据库会话
        
    Returns:
        CronJobResponse: 创建的任务
    """
    try:
        cron_service = CronService(db)
        job = await cron_service.add_job(
            name=request.name,
            schedule=request.schedule,
            message=request.message,
            enabled=request.enabled,
            channel=request.channel,
            chat_id=request.chat_id,
            deliver_response=request.deliver_response,
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
    db: AsyncSession = Depends(get_db),
) -> CronJobResponse:
    """
    更新 Cron 任务
    
    Args:
        job_id: 任务 ID
        request: 更新任务请求
        db: 数据库会话
        
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
        
        cron_service = CronService(db)
        job = await cron_service.update_job(
            job_id=job_id,
            name=request.name,
            schedule=request.schedule,
            message=request.message,
            enabled=request.enabled,
            channel=request.channel,
            chat_id=request.chat_id,
            deliver_response=request.deliver_response,
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
    db: AsyncSession = Depends(get_db),
) -> DeleteCronJobResponse:
    """
    删除 Cron 任务
    
    Args:
        job_id: 任务 ID
        db: 数据库会话
        
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
        
        cron_service = CronService(db)
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
