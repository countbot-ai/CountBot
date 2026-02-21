"""Tasks API - 子 Agent 任务管理"""

from fastapi import APIRouter, HTTPException, status
from loguru import logger
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


# ============================================================================
# Request/Response Models
# ============================================================================


class TaskResponse(BaseModel):
    """任务响应"""
    
    task_id: str
    label: str
    message: str
    session_id: str | None
    status: str
    progress: int
    result: str | None
    error: str | None
    created_at: str
    started_at: str | None
    completed_at: str | None


class TaskStatsResponse(BaseModel):
    """任务统计响应"""
    
    total: int
    pending: int
    running: int
    completed: int
    failed: int
    cancelled: int


# ============================================================================
# Get SubagentManager from chat API
# ============================================================================

def get_subagent_manager():
    """获取 SubagentManager 实例"""
    from backend.api.chat import get_global_subagent_manager
    
    manager = get_global_subagent_manager()
    if manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SubagentManager not initialized. Please send a chat message first."
        )
    return manager


# ============================================================================
# Tasks Endpoints
# ============================================================================


@router.get("/", response_model=list[TaskResponse])
async def list_tasks(
    status_filter: str | None = None,
    session_id: str | None = None,
) -> list[TaskResponse]:
    """
    列出所有任务
    
    Args:
        status_filter: 状态过滤（pending, running, completed, failed, cancelled）
        session_id: 会话 ID 过滤
        
    Returns:
        list[TaskResponse]: 任务列表
    """
    try:
        manager = get_subagent_manager()
        
        # 解析状态过滤
        from backend.modules.agent.subagent import TaskStatus
        status_enum = None
        if status_filter:
            try:
                status_enum = TaskStatus(status_filter)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid status: {status_filter}"
                )
        
        # 获取任务列表
        tasks = manager.list_tasks(status=status_enum, session_id=session_id)
        
        # 转换为响应模型
        return [
            TaskResponse(
                task_id=task.task_id,
                label=task.label,
                message=task.message,
                session_id=task.session_id,
                status=task.status.value,
                progress=task.progress,
                result=task.result,
                error=task.error,
                created_at=task.created_at.isoformat(),
                started_at=task.started_at.isoformat() if task.started_at else None,
                completed_at=task.completed_at.isoformat() if task.completed_at else None,
            )
            for task in tasks
        ]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to list tasks: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list tasks: {str(e)}"
        )


@router.get("/stats", response_model=TaskStatsResponse)
async def get_task_stats() -> TaskStatsResponse:
    """
    获取任务统计信息
    
    Returns:
        TaskStatsResponse: 统计信息
    """
    try:
        manager = get_subagent_manager()
        stats = manager.get_stats()
        
        return TaskStatsResponse(**stats)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get task stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get task stats: {str(e)}"
        )


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str) -> TaskResponse:
    """
    获取任务详情
    
    Args:
        task_id: 任务 ID
        
    Returns:
        TaskResponse: 任务详情
        
    Raises:
        HTTPException: 任务不存在
    """
    try:
        manager = get_subagent_manager()
        task = manager.get_task(task_id)
        
        if task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task '{task_id}' not found"
            )
        
        return TaskResponse(
            task_id=task.task_id,
            label=task.label,
            message=task.message,
            session_id=task.session_id,
            status=task.status.value,
            progress=task.progress,
            result=task.result,
            error=task.error,
            created_at=task.created_at.isoformat(),
            started_at=task.started_at.isoformat() if task.started_at else None,
            completed_at=task.completed_at.isoformat() if task.completed_at else None,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get task: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get task: {str(e)}"
        )


@router.delete("/{task_id}")
async def cancel_task(task_id: str) -> dict[str, bool]:
    """
    取消任务
    
    Args:
        task_id: 任务 ID
        
    Returns:
        dict: 取消结果
        
    Raises:
        HTTPException: 任务不存在或无法取消
    """
    try:
        manager = get_subagent_manager()
        success = await manager.cancel_task(task_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot cancel task '{task_id}' (not found or not running)"
            )
        
        return {"success": True}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to cancel task: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel task: {str(e)}"
        )


@router.post("/{task_id}/delete")
async def delete_task(task_id: str) -> dict[str, bool]:
    """
    删除任务
    
    Args:
        task_id: 任务 ID
        
    Returns:
        dict: 删除结果
        
    Raises:
        HTTPException: 任务不存在
    """
    try:
        manager = get_subagent_manager()
        success = manager.delete_task(task_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task '{task_id}' not found"
            )
        
        return {"success": True}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to delete task: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete task: {str(e)}"
        )
