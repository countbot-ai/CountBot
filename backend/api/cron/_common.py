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
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_SHANGHAI_TZ)
    return dt.isoformat()


async def get_cron_service(request: Request, db: AsyncSession = Depends(get_db)) -> CronService:
    """获取带 scheduler 的 CronService"""
    scheduler = getattr(request.app.state, 'cron_scheduler', None)
    return CronService(db, scheduler=scheduler)
