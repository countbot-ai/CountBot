"""Cron API 的公共依赖：路由器、时区工具、服务获取。"""

from typing import Optional
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Request
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
    if not isinstance(dt, datetime):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_SHANGHAI_TZ)
    return dt.isoformat()


async def get_cron_service(request: Request, db: AsyncSession = Depends(get_db)) -> CronService:
    """获取带 scheduler 的 CronService"""
    scheduler = getattr(request.app.state, 'cron_scheduler', None)
    return CronService(db, scheduler=scheduler)


def is_job_running(job, scheduler=None) -> bool:
    """任务是否正在执行。

    调度器内存中的占用集合最实时；落库的 running 用于进程内任务刚开始、
    或页面在任务执行期间重新打开时兜底。
    """
    if job.last_status == "running":
        return True
    if scheduler is not None and scheduler.is_job_active(job.id):
        return True
    return False


def build_job_info(job, scheduler=None, *, error_limit: Optional[int] = None):
    """把 ORM 任务转换为 API 响应对象（列表/详情/创建/批量共用）。"""
    from backend.api.cron.models import CronJobInfo

    last_error = job.last_error
    if error_limit is not None and last_error:
        last_error = last_error[:error_limit]

    return CronJobInfo(
        id=job.id,
        name=job.name,
        schedule=job.schedule,
        message=job.message,
        enabled=job.enabled,
        channel=job.channel,
        account_id=job.account_id,
        chat_id=job.chat_id,
        deliver_response=job.deliver_response,
        model_provider=job.model_provider,
        model_name=job.model_name,
        last_run=_to_shanghai_iso(job.last_run),
        last_finished_at=_to_shanghai_iso(getattr(job, "last_finished_at", None)),
        next_run=_to_shanghai_iso(job.next_run),
        last_status=job.last_status,
        last_error=last_error,
        last_delivery_status=getattr(job, "last_delivery_status", None),
        last_delivery_error=getattr(job, "last_delivery_error", None),
        run_count=job.run_count or 0,
        error_count=job.error_count or 0,
        created_at=_to_shanghai_iso(job.created_at),
        max_retries=job.max_retries or 0,
        retry_delay=job.retry_delay or 60,
        delete_on_success=job.delete_on_success or False,
        link_context=bool(getattr(job, "link_context", False)),
        is_running=bool(is_job_running(job, scheduler)),
    )
