"""队列与任务管理 API"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from loguru import logger
from pydantic import BaseModel

from backend.modules.multiuser.permissions import (
    AuthUser,
    ensure_owner_or_admin,
    require_active_user,
    require_admin,
)

router = APIRouter(
    prefix="/api/queue",
    tags=["queue"],
)


class QueueStatsResponse(BaseModel):
    """队列统计响应"""
    inbound_size: int
    outbound_size: int
    active_tasks: int
    # 会话闸门统计由 handler.get_queue_stats() 返回，须在此声明
    session_gate: Optional[dict] = None
    rate_limiter: Optional[dict]


class CancelTaskRequest(BaseModel):
    """取消任务请求"""
    session_id: str


def _get_handler(request: Request):
    """获取 message_handler，不存在则抛 503"""
    if not hasattr(request.app.state, "message_handler"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Message handler not initialized",
        )
    return request.app.state.message_handler


async def _session_owner(session_id: str) -> Optional[str]:
    """查会话归属；不存在返回 None。"""
    from backend.database import AsyncSessionLocal
    from backend.models.session import Session

    async with AsyncSessionLocal() as session:
        row = await session.get(Session, session_id)
        return row.owner_id if row is not None else None


@router.get(
    "/stats",
    response_model=QueueStatsResponse,
    dependencies=[Depends(require_admin)],
)
async def get_queue_stats(request: Request) -> QueueStatsResponse:
    """获取队列统计信息（全局视角，仅管理员）"""
    try:
        handler = _get_handler(request)
        stats = await handler.get_queue_stats()
        return QueueStatsResponse(**stats)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get queue stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.post("/cancel")
async def cancel_task(
    request: Request,
    body: CancelTaskRequest,
    user: AuthUser = Depends(require_active_user),
) -> dict:
    """取消正在处理的任务，按会话归属授权，查不到记录统一返回 404。"""
    ensure_owner_or_admin(user, await _session_owner(body.session_id))
    try:
        # 取消 WebSocket 会话
        from backend.ws.connection import cancel_session
        ws_cancelled = cancel_session(body.session_id)

        # 取消渠道消息处理
        channel_cancelled = False
        if hasattr(request.app.state, "message_handler"):
            handler = request.app.state.message_handler
            channel_cancelled = await handler.cancel_task(body.session_id)

        success = ws_cancelled or channel_cancelled
        return {
            "success": success,
            "message": "任务已停止" if success else "没有正在执行的任务",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to cancel task: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/active-tasks", dependencies=[Depends(require_admin)])
async def list_active_tasks(request: Request) -> dict:
    """列出所有活跃任务（全局视角，仅管理员）"""
    try:
        handler = _get_handler(request)
        active_tasks = handler.get_active_tasks()
        return {"active_tasks": active_tasks, "count": len(active_tasks)}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to list active tasks: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
