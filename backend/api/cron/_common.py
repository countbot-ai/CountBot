"""Cron API 的公共依赖：路由器、时区工具、服务获取。"""

from typing import Optional
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.modules.cron.service import CronService
from backend.modules.multiuser.identity import AuthUser
from backend.modules.multiuser.permissions import require_active_user

router = APIRouter(
    prefix="/api/cron",
    tags=["cron"],
    dependencies=[Depends(require_active_user)],
)

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


async def get_cron_service(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(require_active_user),
) -> CronService:
    """获取带 scheduler 的 CronService（按当前用户归属收紧）"""
    from backend.modules.multiuser.permissions import owner_scope

    scheduler = getattr(request.app.state, 'cron_scheduler', None)
    return CronService(db, scheduler=scheduler, owner_id=owner_scope(user))


# 只支持主动推送、没有会话目标的渠道
PUSH_ONLY_CHANNELS = {"serverchan"}


async def validate_channel_push_for_user(user, request) -> None:
    """普通用户只能推送到自己的渠道账号与会话。"""
    if not getattr(request, "deliver_response", False):
        return
    channel = getattr(request, "channel", None)
    if not channel or channel == "web":
        return
    if getattr(user, "is_admin", False):
        return

    from backend.api.channels import _collect_channel_chats, _owned_account_ids
    from backend.modules.config.loader import config_loader

    channel_config = getattr(config_loader.config.channels, channel, None)
    allowed = _owned_account_ids(channel_config, user.owner_id) if channel_config else set()
    account_id = str(getattr(request, "account_id", None) or "default")
    chat_id = str(getattr(request, "chat_id", None) or "").strip()

    if account_id not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="该渠道账号不属于你",
        )
    if channel in PUSH_ONLY_CHANNELS:
        return
    if not chat_id:
        raise HTTPException(status_code=400, detail="请选择推送会话")

    chats = await _collect_channel_chats((channel,), owner_id=user.owner_id)
    if not any(
        item.get("chat_id") == chat_id and item.get("account_id") == account_id
        for item in chats.get(channel, [])
    ):
        raise HTTPException(status_code=400, detail="该会话不在你的可用推送目标中")


async def validate_model_for_user(user, request) -> None:
    """普通用户只能使用自己可选的模型（自有或管理员共享）。"""
    if getattr(user, "is_admin", False):
        return

    provider = str(getattr(request, "model_provider", None) or "").strip()
    model = str(getattr(request, "model_name", None) or "").strip()
    if not provider and not model:
        return
    if not provider or not model:
        raise HTTPException(status_code=400, detail="请同时选择供应商和模型")

    from backend.modules.multiuser.effective import (
        ModelResolutionError,
        resolve_model_ref_for_user,
    )

    try:
        await resolve_model_ref_for_user(user, provider, model)
    except ModelResolutionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def is_job_running(job, scheduler=None) -> bool:
    """判断任务是否正在执行，优先读调度器内存集合，其次读数据库状态。"""
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

    notify_channel_id = getattr(job, "notify_channel_id", None)
    if not isinstance(notify_channel_id, str):
        notify_channel_id = None

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
        notify_channel_id=notify_channel_id,
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
