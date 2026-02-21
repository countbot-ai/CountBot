"""队列与任务管理 API"""

from fastapi import APIRouter, HTTPException, Request, status
from loguru import logger
from pydantic import BaseModel

router = APIRouter(prefix="/api/queue", tags=["queue"])


class QueueStatsResponse(BaseModel):
    """队列统计响应"""
    inbound_size: int
    outbound_size: int
    active_tasks: int
    rate_limiter: dict | None


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


@router.get("/stats", response_model=QueueStatsResponse)
async def get_queue_stats(request: Request) -> QueueStatsResponse:
    """获取队列统计信息"""
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
async def cancel_task(request: Request, body: CancelTaskRequest) -> dict:
    """取消正在处理的任务（同时取消 WebSocket 和渠道任务）"""
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


@router.get("/active-tasks")
async def list_active_tasks(request: Request) -> dict:
    """列出所有活跃任务"""
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
