"""Tasks API - 子 Agent 任务管理"""

from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException, status, Depends
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.modules.multiuser.identity import AuthUser
from backend.modules.multiuser.permissions import owner_scope, require_active_user

router = APIRouter(
    prefix="/api/tasks",
    tags=["tasks"],
    dependencies=[Depends(require_active_user)],
)


# ============================================================================
# Request/Response Models
# ============================================================================


class TaskResponse(BaseModel):
    """任务响应"""

    task_id: str
    label: str
    message: str
    session_id: Optional[str]
    status: str
    progress: int
    result: Optional[str]
    error: Optional[str]
    created_at: str
    started_at: Optional[str]
    completed_at: Optional[str]
    tool_call_records: List[dict] = []
    outcome_projection: Optional[dict] = None
    outcome_projection_state: str = "absent"


class TaskStatsResponse(BaseModel):
    """任务统计响应"""

    total: int
    pending: int
    # 已入队等待并发额度的任务数
    queued: int = 0
    # 真正在执行的任务数，不超过 max_concurrent
    running: int
    completed: int
    failed: int
    cancelled: int


# ============================================================================
# Get SubagentManager from chat API
# ============================================================================

def get_subagent_manager():
    """获取 SubagentManager 实例（可能为 None）"""
    from backend.api.chat import get_global_subagent_manager
    return get_global_subagent_manager()


def require_subagent_manager():
    """管理员使用的全局 SubagentManager；未初始化返回 404"""
    manager = get_subagent_manager()
    if manager is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No tasks available. SubagentManager has not been initialized yet."
        )
    return manager


async def get_scoped_subagent_manager(
    user: AuthUser = Depends(require_active_user),
):
    """按身份取 SubagentManager，每个用户使用自己的实例。"""
    if not isinstance(user, AuthUser) or user.is_admin:
        return require_subagent_manager()

    from backend.modules.multiuser.runtime import user_runtime_manager

    return await user_runtime_manager.get_subagent_manager(user)


# ============================================================================
# Tasks Endpoints
# ============================================================================


@router.get("/", response_model=List[TaskResponse])
async def list_tasks(
    status_filter: Optional[str] = None,
    session_id: Optional[str] = None,
    user: AuthUser = Depends(require_active_user),
) -> List[TaskResponse]:
    """列出任务，可按状态和会话过滤。"""
    try:
        manager = await get_scoped_subagent_manager(user)

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
        return [TaskResponse(**task.to_dict()) for task in tasks]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to list tasks: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list tasks: {str(e)}"
        )


@router.get("/stats", response_model=TaskStatsResponse)
async def get_task_stats(
    user: AuthUser = Depends(require_active_user),
) -> TaskStatsResponse:
    """获取任务统计信息。"""
    try:
        manager = await get_scoped_subagent_manager(user)
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
async def get_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(require_active_user),
) -> TaskResponse:
    """获取任务详情。"""
    try:
        manager = await get_scoped_subagent_manager(user)
        
        # 先从内存查询
        task = manager.get_task(task_id)
        
        # 如果内存中没有，从数据库查询
        if not task:
            from sqlalchemy import select
            from backend.models.task import Task
            
            query = select(Task).where(Task.id == task_id)
            scope = owner_scope(user)
            if scope:
                query = query.where(Task.owner_id == scope)
            result = await db.execute(query)
            db_task = result.scalar_one_or_none()
            
            if not db_task:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Task '{task_id}' not found"
                )
            
            # 从数据库任务构建响应
            import json
            tool_call_records = []
            if db_task.tool_call_records:
                try:
                    tool_call_records = json.loads(db_task.tool_call_records)
                except json.JSONDecodeError:
                    pass
            from backend.modules.tools.outcome_projection import task_read_view
            task_status, projection_state, projection = task_read_view(
                db_task.status, db_task.outcome_projection,
            )
            
            return TaskResponse(
                task_id=db_task.id,
                label=db_task.label,
                message=db_task.message,
                session_id=db_task.session_id,
                status=task_status,
                progress=db_task.progress,
                result=db_task.result,
                error=db_task.error,
                created_at=db_task.created_at.isoformat(),
                started_at=db_task.started_at.isoformat() if db_task.started_at else None,
                completed_at=db_task.completed_at.isoformat() if db_task.completed_at else None,
                tool_call_records=tool_call_records,
                outcome_projection=projection,
                outcome_projection_state=projection_state,
            )
        
        # 从内存任务返回
        from backend.modules.tools.outcome_projection import task_read_view
        task_status, projection_state, projection = task_read_view(
            task.status.value, task.outcome_projection(),
        )
        return TaskResponse(
            task_id=task.task_id,
            label=task.label,
            message=task.message,
            session_id=task.session_id,
            status=task_status,
            progress=task.progress,
            result=task.result,
            error=task.error,
            created_at=task.created_at.isoformat(),
            started_at=task.started_at.isoformat() if task.started_at else None,
            completed_at=task.completed_at.isoformat() if task.completed_at else None,
            tool_call_records=task.tool_call_records,
            outcome_projection=projection,
            outcome_projection_state=projection_state,
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
async def cancel_task(
    task_id: str,
    user: AuthUser = Depends(require_active_user),
) -> Dict[str, bool]:
    """取消任务。"""
    try:
        manager = await get_scoped_subagent_manager(user)
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
async def delete_task(
    task_id: str,
    user: AuthUser = Depends(require_active_user),
) -> Dict[str, bool]:
    """删除任务。"""
    try:
        manager = await get_scoped_subagent_manager(user)
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
