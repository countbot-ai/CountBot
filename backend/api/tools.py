"""Tools API 端点"""

from pathlib import Path

from fastapi import APIRouter, HTTPException, status, Query
from loguru import logger
from pydantic import BaseModel, Field

from backend.modules.config.loader import config_loader
from backend.modules.tools.registry import ToolRegistry
from backend.modules.tools.conversation_history import get_conversation_history
from backend.modules.tools.file_audit_logger import file_audit_logger

router = APIRouter(prefix="/api/tools", tags=["tools"])


# ============================================================================
# Request/Response Models
# ============================================================================


class ToolDefinition(BaseModel):
    """工具定义"""
    
    name: str = Field(..., description="工具名称")
    description: str = Field(..., description="工具描述")
    parameters: dict = Field(..., description="工具参数定义")


class ExecuteToolRequest(BaseModel):
    """执行工具请求"""
    
    tool: str = Field(..., description="工具名称")
    arguments: dict = Field(default_factory=dict, description="工具参数")


class ExecuteToolResponse(BaseModel):
    """执行工具响应"""
    
    result: str = Field(..., description="执行结果")
    success: bool = Field(..., description="是否成功")
    error: str | None = Field(None, description="错误信息")


class ListToolsResponse(BaseModel):
    """工具列表响应"""
    
    tools: list[ToolDefinition] = Field(..., description="工具列表")


class ConversationHistoryResponse(BaseModel):
    """工具调用对话历史响应"""
    
    conversations: list[dict] = Field(..., description="对话记录列表")
    total: int = Field(..., description="总记录数")


class ConversationStatsResponse(BaseModel):
    """工具调用对话统计响应"""
    
    total: int = Field(..., description="总记录数")
    by_tool: dict[str, int] = Field(..., description="按工具统计")
    by_session: dict[str, int] = Field(..., description="按会话统计")
    success_rate: float = Field(..., description="成功率")


# ============================================================================
# Helper Functions
# ============================================================================


def get_tool_registry() -> ToolRegistry:
    """获取工具注册表实例（包含所有工具)"""
    from backend.modules.tools.setup import register_all_tools
    from backend.api.chat import get_global_subagent_manager
    from backend.api.channels import get_channel_manager
    from backend.utils.paths import WORKSPACE_DIR
    
    config = config_loader.config
    workspace = Path(config.workspace.path) if config.workspace.path else WORKSPACE_DIR
    workspace.mkdir(parents=True, exist_ok=True)
    
    # 获取全局 SubagentManager
    subagent_manager = get_global_subagent_manager()
    
    # 尝试获取 ChannelManager（如果已初始化）
    try:
        channel_manager = get_channel_manager()
    except:
        channel_manager = None
        logger.debug("ChannelManager not initialized, send_image tool will not be available")
    
    # 统一注册所有工具（包括 send_image 如果 channel_manager 可用）
    tools = register_all_tools(
        workspace=workspace,
        command_timeout=config.security.command_timeout,
        max_output_length=config.security.max_output_length,
        allow_dangerous=not config.security.dangerous_commands_blocked,
        restrict_to_workspace=config.security.restrict_to_workspace,
        custom_deny_patterns=config.security.custom_deny_patterns,
        custom_allow_patterns=config.security.custom_allow_patterns if config.security.command_whitelist_enabled else None,
        audit_log_enabled=config.security.audit_log_enabled,
        subagent_manager=subagent_manager,
        channel_manager=channel_manager,  # 添加 channel_manager
    )
    
    return tools


# ============================================================================
# Tools Endpoints
# ============================================================================


@router.post("/execute", response_model=ExecuteToolResponse)
async def execute_tool(request: ExecuteToolRequest) -> ExecuteToolResponse:
    """
    执行工具
    
    Args:
        request: 执行工具请求
        
    Returns:
        ExecuteToolResponse: 执行结果
    """
    try:
        # 隐藏的工具列表（禁止前端直接调用）
        hidden_tools = {'read_file', 'write_file', 'edit_file', 'list_dir', 'shell'}
        
        # 安全检查：禁止调用隐藏的工具
        if request.tool in hidden_tools:
            logger.warning(f"Blocked attempt to execute hidden tool: {request.tool}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Tool '{request.tool}' is not available for direct execution"
            )
        
        tools = get_tool_registry()
        
        # 执行工具
        result = await tools.execute(
            tool_name=request.tool,
            arguments=request.arguments,
        )
        
        return ExecuteToolResponse(
            result=result,
            success=True,
        )
        
    except HTTPException:
        # 重新抛出 HTTP 异常
        raise
    except ValueError as e:
        # 工具不存在或参数错误
        logger.warning(f"Tool execution failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        # 执行错误
        logger.exception(f"Tool execution error: {e}")
        return ExecuteToolResponse(
            result="",
            success=False,
            error=str(e),
        )


@router.get("/list", response_model=ListToolsResponse)
async def list_tools() -> ListToolsResponse:
    """
    获取所有可用工具列表
    
    Returns:
        ListToolsResponse: 工具列表
    """
    try:
        tools = get_tool_registry()
        
        # 获取工具定义
        definitions = tools.get_definitions()
        
        # 隐藏的工具列表（不在前端显示）
        hidden_tools = {'read_file', 'write_file', 'edit_file', 'list_dir', 'shell'}
        
        # 转换为响应格式，过滤隐藏的工具
        tool_list = [
            ToolDefinition(
                name=tool_def["function"]["name"],
                description=tool_def["function"]["description"],
                parameters=tool_def["function"]["parameters"],
            )
            for tool_def in definitions
            if tool_def["function"]["name"] not in hidden_tools
        ]
        
        return ListToolsResponse(tools=tool_list)
        
    except Exception as e:
        logger.exception(f"Failed to list tools: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list tools: {str(e)}"
        )


@router.get("/conversations", response_model=ConversationHistoryResponse)
async def get_conversations(
    session_id: str | None = Query(None, description="按会话ID过滤"),
    tool_name: str | None = Query(None, description="按工具名称过滤"),
    limit: int | None = Query(None, description="限制返回数量"),
    offset: int = Query(0, description="偏移量，用于分页")
) -> ConversationHistoryResponse:
    """
    获取工具调用对话历史
    
    Args:
        session_id: 可选，按会话ID过滤
        tool_name: 可选，按工具名称过滤
        limit: 可选，限制返回数量
        offset: 偏移量，用于分页（默认0）
        
    Returns:
        ConversationHistoryResponse: 对话历史记录
    """
    try:
        conversation_history = get_conversation_history()
        
        # 隐藏的工具列表
        hidden_tools = {'read_file', 'write_file', 'edit_file', 'list_dir', 'shell'}
        
        # 根据参数获取不同的记录
        if session_id:
            conversations = await conversation_history.get_by_session(session_id, limit, offset)
        elif tool_name:
            conversations = await conversation_history.get_by_tool(tool_name, limit, offset)
        else:
            conversations = await conversation_history.get_all(limit, offset)
        
        # 过滤隐藏的工具
        filtered_conversations = [
            conv for conv in conversations
            if conv.get('tool_name') not in hidden_tools
        ]
        
        return ConversationHistoryResponse(
            conversations=filtered_conversations,
            total=len(filtered_conversations)
        )
        
    except Exception as e:
        logger.exception(f"Failed to get conversation history: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get conversation history: {str(e)}"
        )


@router.get("/conversations/stats", response_model=ConversationStatsResponse)
async def get_conversation_stats() -> ConversationStatsResponse:
    """
    获取工具调用对话统计信息
    
    Returns:
        ConversationStatsResponse: 统计信息
    """
    try:
        conversation_history = get_conversation_history()
        stats = await conversation_history.get_stats()
        
        return ConversationStatsResponse(
            total=stats["total"],
            by_tool=stats["by_tool"],
            by_session=stats["by_session"],
            success_rate=stats["success_rate"]
        )
        
    except Exception as e:
        logger.exception(f"Failed to get conversation stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get conversation stats: {str(e)}"
        )


@router.delete("/conversations")
async def clear_conversations() -> dict:
    """
    清空所有工具调用对话历史
    
    Returns:
        dict: 操作结果
    """
    try:
        conversation_history = get_conversation_history()
        conversation_history.clear()
        
        return {"success": True, "message": "Conversation history cleared"}
        
    except Exception as e:
        logger.exception(f"Failed to clear conversation history: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear conversation history: {str(e)}"
        )



# ============================================================================
# Audit Log Endpoints
# ============================================================================


@router.get("/audit/history")
async def get_audit_history(
    limit: int = 50,
    session_id: str | None = None
):
    """
    获取工具调用审计历史（从文件）
    
    Args:
        limit: 返回的记录数量（默认 50）
        session_id: 可选的会话 ID 过滤
        
    Returns:
        工具调用历史记录列表
    """
    try:
        # 隐藏的工具列表
        hidden_tools = {'read_file', 'write_file', 'edit_file', 'list_dir', 'shell'}
        
        if session_id:
            history = file_audit_logger.get_logs_by_session(session_id, limit)
        else:
            history = file_audit_logger.get_recent_logs(limit)
        
        # 过滤隐藏的工具
        filtered_history = [
            log for log in history
            if log.get('tool_name') not in hidden_tools
        ]
        
        return {
            "success": True,
            "data": filtered_history,
            "total": len(filtered_history)
        }
    except Exception as e:
        logger.exception(f"Failed to get audit history: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get audit history: {str(e)}"
        )


@router.get("/audit/stats")
async def get_audit_stats():
    """
    获取工具调用统计信息（从文件）
    
    Returns:
        统计信息（总调用数、失败数、成功率等）
    """
    try:
        stats = file_audit_logger.get_stats()
        return {
            "success": True,
            "data": stats
        }
    except Exception as e:
        logger.exception(f"Failed to get audit stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get audit stats: {str(e)}"
        )


@router.delete("/audit/history")
async def clear_audit_history():
    """
    清空审计历史记录（删除所有日志文件）
    
    Returns:
        操作结果
    """
    try:
        deleted_count = file_audit_logger.clear_all_logs()
        return {
            "success": True,
            "message": f"Cleared {deleted_count} audit log files"
        }
    except Exception as e:
        logger.exception(f"Failed to clear audit history: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear audit history: {str(e)}"
        )


@router.post("/audit/cleanup")
async def cleanup_old_audit_logs():
    """
    清理旧的审计日志（超过 30 天）
    
    Returns:
        操作结果
    """
    try:
        deleted_count = file_audit_logger.cleanup_old_logs()
        return {
            "success": True,
            "message": f"Cleaned up {deleted_count} old audit log files"
        }
    except Exception as e:
        logger.exception(f"Failed to cleanup old logs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cleanup old logs: {str(e)}"
        )
