"""Chat API 端点"""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.modules.agent.context import ContextBuilder
from backend.modules.agent.loop import AgentLoop
from backend.modules.agent.memory import MemoryStore
from backend.modules.agent.skills import SkillsLoader
from backend.modules.config.loader import config_loader
from backend.modules.providers.litellm_provider import LiteLLMProvider
from backend.modules.session.manager import SessionManager
from backend.modules.tools.registry import ToolRegistry
from backend.utils.paths import WORKSPACE_DIR

router = APIRouter(prefix="/api/chat", tags=["chat"])


# ============================================================================
# Request/Response Models
# ============================================================================


class SendMessageRequest(BaseModel):
    """发送消息请求"""

    session_id: str = Field(..., description="会话 ID")
    message: str = Field(..., min_length=1, description="用户消息内容")
    attachments: list[str] | None = Field(None, description="附件路径列表（可选）")


class UpdateSessionSummaryRequest(BaseModel):
    """更新会话总结请求"""
    
    summary: str = Field(..., min_length=10, max_length=200, description="会话总结（10-200字符）")


class SummarizeSessionResponse(BaseModel):
    """总结会话响应"""
    
    success: bool = Field(..., description="是否成功")
    summary: str = Field(..., description="生成的总结")
    message: str | None = Field(None, description="消息")


class SendMessageResponse(BaseModel):
    """发送消息响应"""

    message_id: str = Field(..., description="消息 ID")
    streaming: bool = Field(True, description="是否为流式响应")


class SessionResponse(BaseModel):
    """会话响应"""

    id: str
    name: str
    created_at: str
    updated_at: str
    summary: str | None = None
    summary_updated_at: str | None = None


class MessageResponse(BaseModel):
    """消息响应"""

    id: int
    session_id: str
    role: str
    content: str
    created_at: str


# ============================================================================
# Dependency Injection
# ============================================================================


# ============================================================================
# Global SubagentManager (shared across all requests)
# ============================================================================

_global_subagent_manager = None


def get_global_subagent_manager():
    """获取全局 SubagentManager 实例"""
    return _global_subagent_manager


async def get_agent_loop(db: AsyncSession = Depends(get_db)) -> AgentLoop:
    """获取 AgentLoop 实例（依赖注入）"""
    global _global_subagent_manager
    
    try:
        # 加载配置
        config = config_loader.config
        
        # 获取工作空间路径
        from pathlib import Path
        workspace = Path(config.workspace.path) if config.workspace.path else WORKSPACE_DIR
        workspace.mkdir(parents=True, exist_ok=True)
        
        # 初始化 LLM Provider
        provider_name = config.model.provider
        provider_config = config.providers.get(provider_name)
        
        if not provider_config or not provider_config.enabled:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Provider '{provider_name}' is not configured or disabled"
            )
        
        from backend.modules.providers.registry import get_provider_metadata
        provider_meta = get_provider_metadata(provider_name)
        
        api_key = provider_config.api_key or ""
        api_base = (
            provider_config.api_base
            if provider_config.api_base
            else (provider_meta.default_api_base if provider_meta else None)
        )
        
        provider = LiteLLMProvider(
            api_key=api_key,
            api_base=api_base,
            default_model=config.model.model,
            timeout=120.0,
            max_retries=3,
            provider_id=provider_name,
        )
        
        # 初始化记忆系统
        memory_dir = workspace / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)
        memory = MemoryStore(memory_dir)
        
        # 初始化技能加载器
        skills_dir = workspace / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)
        skills = SkillsLoader(skills_dir)
        
        # 初始化上下文构建器
        context_builder = ContextBuilder(
            workspace=workspace,
            memory=memory,
            skills=skills,
            persona_config=config.persona,
        )
        
        # 初始化对话总结器
        from backend.modules.agent.memory import ConversationSummarizer
        summarizer = ConversationSummarizer(provider=provider, char_limit=2000)
        
        # 初始化 SessionManager
        session_manager = SessionManager(db, summarizer=summarizer)
        
        # 使用全局 SubagentManager（如果不存在则创建）
        from backend.modules.agent.subagent import SubagentManager
        
        if _global_subagent_manager is None:
            _global_subagent_manager = SubagentManager(
                provider=provider,
                workspace=workspace,
                model=config.model.model,
                temperature=config.model.temperature,
                max_tokens=config.model.max_tokens,
            )
            logger.info("Created global SubagentManager")
        
        # 统一注册所有工具（包括 spawn）
        from backend.modules.tools.setup import register_all_tools
        
        tools = register_all_tools(
            workspace=workspace,
            command_timeout=config.security.command_timeout,
            max_output_length=config.security.max_output_length,
            allow_dangerous=not config.security.dangerous_commands_blocked,
            restrict_to_workspace=config.security.restrict_to_workspace,
            custom_deny_patterns=config.security.custom_deny_patterns,
            custom_allow_patterns=config.security.custom_allow_patterns if config.security.command_whitelist_enabled else None,
            audit_log_enabled=config.security.audit_log_enabled,
            subagent_manager=_global_subagent_manager,
            skills_loader=skills,
            session_id=None,  # session_id 在实际使用时由工具动态设置
            memory_store=memory,
        )
        
        # 创建 AgentLoop
        agent_loop = AgentLoop(
            provider=provider,
            workspace=workspace,
            tools=tools,
            context_builder=context_builder,
            session_manager=session_manager,
            subagent_manager=_global_subagent_manager,
            model=config.model.model,
            max_iterations=config.model.max_iterations,
            max_retries=3,
            retry_delay=1.0,
            temperature=config.model.temperature,
            max_tokens=config.model.max_tokens,
        )
        
        return agent_loop
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to initialize AgentLoop: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize agent: {str(e)}"
        )


# ============================================================================
# Auto Memory Helpers
# ============================================================================

# 记录已自动总结的会话，避免重复触发（session_id -> 上次总结时的消息数）
_auto_summarized_sessions: dict[str, int] = {}

# 自动总结阈值
_AUTO_SUMMARIZE_MESSAGE_THRESHOLD = 30
_AUTO_SUMMARIZE_CHAR_THRESHOLD = 15000


async def _maybe_auto_summarize(
    session_id: str,
    session_manager: SessionManager,
    agent_loop: AgentLoop,
) -> None:
    """检查会话是否达到自动总结阈值，如果是则后台触发记忆写入。
    
    触发条件（满足任一）：
    - 会话消息数 >= 30 条
    - 会话总字符数 >= 15000
    
    且距上次自动总结后新增了至少 30 条消息。
    """
    from backend.modules.agent.analyzer import MessageAnalyzer
    from backend.modules.agent.prompts import CONVERSATION_TO_MEMORY_PROMPT
    from pathlib import Path

    messages = await session_manager.get_messages(session_id=session_id)
    if not messages:
        return

    msg_count = len(messages)
    
    # 检查是否已经在这个消息数附近总结过
    last_summarized_at = _auto_summarized_sessions.get(session_id, 0)
    if msg_count - last_summarized_at < 30:
        return

    # 检查是否达到阈值
    total_chars = sum(len(msg.content or "") for msg in messages)
    if msg_count < _AUTO_SUMMARIZE_MESSAGE_THRESHOLD and total_chars < _AUTO_SUMMARIZE_CHAR_THRESHOLD:
        return

    logger.info(
        f"Auto-summarize triggered for session {session_id}: "
        f"{msg_count} messages, {total_chars} chars"
    )

    try:
        analyzer = MessageAnalyzer()
        message_dicts = [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]
        formatted = analyzer.format_messages_for_summary(message_dicts, max_chars=4000)

        prompt = CONVERSATION_TO_MEMORY_PROMPT.format(messages=formatted)

        summary_content = ""
        async for chunk in agent_loop.provider.chat_stream(
            messages=[{"role": "user", "content": prompt}],
            model=agent_loop.model,
            temperature=0.3,
        ):
            if chunk.is_content and chunk.content:
                summary_content += chunk.content

        summary = summary_content.strip()

        if "无需记录" in summary:
            logger.info(f"Auto-summarize: no valuable content for session {session_id}")
            _auto_summarized_sessions[session_id] = msg_count
            return

        config = config_loader.config
        workspace = Path(config.workspace.path) if config.workspace.path else WORKSPACE_DIR
        memory_dir = workspace / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)
        memory = MemoryStore(memory_dir)

        line_num = memory.append_entry(source="web-chat", content=summary)
        _auto_summarized_sessions[session_id] = msg_count

        logger.info(f"Auto-summarize saved at line {line_num} for session {session_id}")

    except Exception as e:
        logger.error(f"Auto-summarize failed for session {session_id}: {e}")


# ============================================================================
# Chat Endpoints
# ============================================================================


@router.post("/send", response_model=SendMessageResponse)
async def send_message(
    request: SendMessageRequest,
    db: AsyncSession = Depends(get_db),
    agent_loop: AgentLoop = Depends(get_agent_loop),
) -> StreamingResponse:
    """
    发送消息到 Agent 并获取流式响应
    
    此端点使用 Server-Sent Events (SSE) 进行流式响应传输。
    客户端应该监听 'message' 事件来接收响应片段。
    
    Args:
        request: 发送消息请求
        db: 数据库会话
        agent_loop: Agent 循环实例
        
    Returns:
        StreamingResponse: SSE 流式响应
        
    Raises:
        HTTPException: 会话不存在或处理失败
    """
    try:
        # 验证会话是否存在并获取会话信息（包括总结）
        from sqlalchemy import select
        from backend.models.session import Session
        
        result = await db.execute(
            select(Session).where(Session.id == request.session_id)
        )
        session = result.scalar_one_or_none()
        
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{request.session_id}' not found"
            )
        
        # 获取会话总结
        session_summary = session.summary
        
        # 保存用户消息到数据库
        session_manager = SessionManager(db)
        user_message = await session_manager.add_message(
            session_id=request.session_id,
            role="user",
            content=request.message,
        )
        
        if user_message is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save user message"
            )
        
        logger.info(
            f"Processing message for session {request.session_id}: "
            f"{request.message[:50]}..."
        )
        
        # 从配置中获取最大历史消息条数
        from backend.modules.config.loader import config_loader
        config = config_loader.config
        max_history = config.persona.max_history_messages
        
        # 滚动窗口溢出总结：截断前先将旧消息写入记忆
        if max_history > 0:
            try:
                from pathlib import Path as _Path
                _workspace = _Path(config.workspace.path) if config.workspace.path else WORKSPACE_DIR
                _memory_dir = _workspace / "memory"
                _memory_dir.mkdir(parents=True, exist_ok=True)
                _overflow_memory = MemoryStore(_memory_dir)
                await session_manager.summarize_overflow(
                    session_id=request.session_id,
                    max_history=max_history,
                    provider=agent_loop.provider,
                    model=agent_loop.model,
                    memory_store=_overflow_memory,
                )
            except Exception as overflow_err:
                logger.warning(f"Overflow summarize failed (non-fatal): {overflow_err}")
        
        # 获取带总结的会话历史(使用配置的最大条数限制)
        # -1 表示不限制，传递 None 给 get_history_with_summary
        context = await session_manager.get_history_with_summary(
            session_id=request.session_id,
            limit=None if max_history == -1 else max_history
        )
        
        # 排除刚添加的用户消息(因为 process_message 会添加)
        if context and context[-1].get("role") == "user":
            context = context[:-1]
        
        # 创建流式响应生成器
        async def event_stream() -> AsyncIterator[str]:
            """SSE 事件流生成器"""
            assistant_content = ""
            
            try:
                # 发送开始事件
                yield f"event: start\ndata: {json.dumps({'message_id': str(user_message.id)})}\n\n"
                
                # 处理消息并流式输出（传入会话总结）
                # 注意：我们需要修改 process_message 来接受 session_summary
                # 但为了保持向后兼容，我们在 context_builder.build_messages 中处理
                
                # 临时方案：将 session_summary 添加到 context_builder
                if session_summary and agent_loop.context_builder:
                    # 保存原始的 build_messages 方法
                    original_build_messages = agent_loop.context_builder.build_messages
                    
                    # 创建包装方法来注入 session_summary
                    def build_messages_with_summary(*args, **kwargs):
                        kwargs['session_summary'] = session_summary
                        return original_build_messages(*args, **kwargs)
                    
                    # 临时替换方法
                    agent_loop.context_builder.build_messages = build_messages_with_summary
                
                async for chunk in agent_loop.process_message(
                    message=request.message,
                    session_id=request.session_id,
                    context=context,
                    media=request.attachments,
                ):
                    assistant_content += chunk
                    
                    # 发送内容块
                    yield f"event: message\ndata: {json.dumps({'content': chunk})}\n\n"
                    
                    # 确保立即发送
                    await asyncio.sleep(0)
                
                # 恢复原始方法
                if session_summary and agent_loop.context_builder:
                    agent_loop.context_builder.build_messages = original_build_messages
                
                # 保存助手响应到数据库
                if assistant_content:
                    assistant_message = await session_manager.add_message(
                        session_id=request.session_id,
                        role="assistant",
                        content=assistant_content,
                    )
                    
                    # 发送完成事件
                    yield f"event: done\ndata: {json.dumps({'message_id': str(assistant_message.id)})}\n\n"
                    
                    # 自动记忆检测：当会话消息达到阈值时，后台触发自动总结
                    try:
                        await _maybe_auto_summarize(
                            session_id=request.session_id,
                            session_manager=session_manager,
                            agent_loop=agent_loop,
                        )
                    except Exception as auto_err:
                        logger.warning(f"Auto-summarize check failed (non-fatal): {auto_err}")
                else:
                    # 没有内容，发送空完成事件
                    yield f"event: done\ndata: {json.dumps({'message_id': None})}\n\n"
                
            except Exception as e:
                logger.exception(f"Error in event stream: {e}")
                
                # 发送错误事件
                error_data = {
                    "error": str(e),
                    "type": type(e).__name__,
                }
                yield f"event: error\ndata: {json.dumps(error_data)}\n\n"
        
        # 返回 SSE 流式响应
        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
            },
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to send message: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process message: {str(e)}"
        )


@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(
    limit: int | None = None,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
) -> list[SessionResponse]:
    """
    获取所有会话列表
    
    Args:
        limit: 返回数量限制（可选）
        offset: 偏移量
        db: 数据库会话
        
    Returns:
        list[SessionResponse]: 会话列表
    """
    try:
        session_manager = SessionManager(db)
        sessions = await session_manager.list_sessions(limit=limit, offset=offset)
        
        return [
            SessionResponse(
                id=session.id,
                name=session.name,
                created_at=session.created_at.isoformat(),
                updated_at=session.updated_at.isoformat(),
                summary=session.summary,
                summary_updated_at=session.summary_updated_at.isoformat() if session.summary_updated_at else None,
            )
            for session in sessions
        ]
        
    except Exception as e:
        logger.exception(f"Failed to list sessions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list sessions: {str(e)}"
        )


@router.post("/sessions", response_model=SessionResponse)
async def create_session(
    name: str,
    db: AsyncSession = Depends(get_db),
) -> SessionResponse:
    """
    创建新会话
    
    Args:
        name: 会话名称
        db: 数据库会话
        
    Returns:
        SessionResponse: 创建的会话
    """
    try:
        session_manager = SessionManager(db)
        session = await session_manager.create_session(name=name)
        
        return SessionResponse(
            id=session.id,
            name=session.name,
            created_at=session.created_at.isoformat(),
            updated_at=session.updated_at.isoformat(),
        )
        
    except Exception as e:
        logger.exception(f"Failed to create session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create session: {str(e)}"
        )


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    """
    删除会话
    
    Args:
        session_id: 会话 ID
        db: 数据库会话
        
    Returns:
        dict: 删除结果
        
    Raises:
        HTTPException: 会话不存在
    """
    try:
        session_manager = SessionManager(db)
        success = await session_manager.delete_session(session_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{session_id}' not found"
            )
        
        return {"success": True}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to delete session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete session: {str(e)}"
        )


class UpdateSessionRequest(BaseModel):
    """更新会话请求"""
    name: str


@router.put("/sessions/{session_id}", response_model=SessionResponse)
async def update_session(
    session_id: str,
    request: UpdateSessionRequest,
    db: AsyncSession = Depends(get_db),
) -> SessionResponse:
    """
    更新会话信息
    
    Args:
        session_id: 会话 ID
        request: 更新请求（包含新的会话名称）
        db: 数据库会话
        
    Returns:
        SessionResponse: 更新后的会话
        
    Raises:
        HTTPException: 会话不存在
    """
    try:
        session_manager = SessionManager(db)
        session = await session_manager.update_session(session_id, name=request.name)
        
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{session_id}' not found"
            )
        
        return SessionResponse(
            id=session.id,
            name=session.name,
            created_at=session.created_at.isoformat(),
            updated_at=session.updated_at.isoformat(),
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to update session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update session: {str(e)}"
        )


@router.get("/sessions/{session_id}/messages", response_model=list[MessageResponse])
async def get_session_messages(
    session_id: str,
    limit: int | None = None,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
) -> list[MessageResponse]:
    """
    获取会话的消息列表
    
    Args:
        session_id: 会话 ID
        limit: 返回数量限制（可选）
        offset: 偏移量
        db: 数据库会话
        
    Returns:
        list[MessageResponse]: 消息列表
        
    Raises:
        HTTPException: 会话不存在
    """
    try:
        session_manager = SessionManager(db)
        
        # 验证会话是否存在
        session = await session_manager.get_session(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{session_id}' not found"
            )
        
        # 获取消息
        messages = await session_manager.get_messages(
            session_id=session_id,
            limit=limit,
            offset=offset,
        )
        
        return [
            MessageResponse(
                id=msg.id,
                session_id=msg.session_id,
                role=msg.role,
                content=msg.content,
                created_at=msg.created_at.isoformat(),
            )
            for msg in messages
        ]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get messages: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get messages: {str(e)}"
        )


@router.delete("/sessions/{session_id}/messages")
async def clear_session_messages(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    清空会话的所有消息
    
    Args:
        session_id: 会话 ID
        db: 数据库会话
        
    Returns:
        dict: 操作结果
        
    Raises:
        HTTPException: 会话不存在或清空失败
    """
    try:
        session_manager = SessionManager(db)
        
        # 验证会话是否存在
        session = await session_manager.get_session(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{session_id}' not found"
            )
        
        # 清空消息
        await session_manager.clear_messages(session_id)
        
        logger.info(f"Cleared all messages for session: {session_id}")
        
        return {
            "success": True,
            "message": f"All messages cleared for session {session_id}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to clear messages: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear messages: {str(e)}"
        )


@router.get("/sessions/{session_id}/export")
async def export_session_context(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    agent_loop: AgentLoop = Depends(get_agent_loop),
) -> dict:
    """
    导出会话的完整上下文（包括系统提示词、工具定义、所有消息和工具调用历史）
    
    导出内容：
    1. 系统提示词（发送给 LLM 的完整上下文）
    2. 工具定义（所有可用工具的描述和参数）
    3. 用户消息和 AI 回复（数据库中保存的内容）
    4. 工具执行历史（从工具历史记录中获取）
    
    Args:
        session_id: 会话 ID
        db: 数据库会话
        agent_loop: Agent 循环实例
        
    Returns:
        dict: 包含系统提示词、工具定义、消息和工具历史的完整上下文
        
    Raises:
        HTTPException: 会话不存在
    """
    try:
        session_manager = SessionManager(db)
        
        # 验证会话是否存在
        session = await session_manager.get_session(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{session_id}' not found"
            )
        
        # 获取所有消息
        messages = await session_manager.get_messages(session_id=session_id)
        
        # 构建系统提示词
        system_prompt = agent_loop.context_builder.build_system_prompt()
        
        # 获取工具定义
        tool_definitions = []
        if agent_loop.tools:
            tool_definitions = agent_loop.tools.get_definitions()
        
        # 构建消息历史
        message_history = []
        for msg in messages:
            message_history.append({
                "id": msg.id,
                "role": msg.role,
                "content": msg.content,
                "created_at": msg.created_at.isoformat(),
            })
        
        # 获取工具执行历史（从工具注册表）
        tool_history = []
        if agent_loop.tools and hasattr(agent_loop.tools, 'history'):
            # 过滤出属于当前会话的工具调用
            for record in agent_loop.tools.history:
                # 工具历史记录可能没有 session_id，所以我们导出所有记录
                # 并在前端/导出文件中标注这是全局工具历史
                tool_history.append({
                    "tool": record.get("tool"),
                    "arguments": record.get("arguments"),
                    "result": record.get("result"),
                    "error": record.get("error"),
                    "success": record.get("success"),
                    "duration": record.get("duration"),
                    "timestamp": record.get("timestamp").isoformat() if record.get("timestamp") else None,
                })
        
        return {
            "session_id": session_id,
            "session_name": session.name,
            "system_prompt": system_prompt,
            "tool_definitions": tool_definitions,
            "messages": message_history,
            "tool_history": tool_history,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "note": "此导出包含完整的系统提示词和工具定义。工具调用历史为全局记录，可能包含其他会话的工具调用。"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to export session context: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export session context: {str(e)}"
        )


# ============================================================================
# Session Summary Endpoints
# ============================================================================


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> SessionResponse:
    """
    获取会话详情（包含总结）
    
    Args:
        session_id: 会话 ID
        db: 数据库会话
        
    Returns:
        SessionResponse: 会话详情
        
    Raises:
        HTTPException: 会话不存在
    """
    try:
        session_manager = SessionManager(db)
        session = await session_manager.get_session(session_id)
        
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{session_id}' not found"
            )
        
        return SessionResponse(
            id=session.id,
            name=session.name,
            created_at=session.created_at.isoformat(),
            updated_at=session.updated_at.isoformat(),
            summary=session.summary,
            summary_updated_at=session.summary_updated_at.isoformat() if session.summary_updated_at else None,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get session: {str(e)}"
        )


@router.put("/sessions/{session_id}/summary")
async def update_session_summary(
    session_id: str,
    request: UpdateSessionSummaryRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    更新会话总结
    
    Args:
        session_id: 会话 ID
        request: 更新总结请求
        db: 数据库会话
        
    Returns:
        dict: 更新结果
        
    Raises:
        HTTPException: 会话不存在
    """
    try:
        from sqlalchemy import select
        from backend.models.session import Session
        
        # 查找会话
        result = await db.execute(
            select(Session).where(Session.id == session_id)
        )
        session = result.scalar_one_or_none()
        
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{session_id}' not found"
            )
        
        # 更新总结
        session.summary = request.summary
        session.summary_updated_at = datetime.now(timezone.utc)
        
        await db.commit()
        
        logger.info(f"Updated summary for session {session_id}")
        
        return {
            "success": True,
            "session_id": session_id,
            "summary": session.summary,
            "updated_at": session.summary_updated_at.isoformat(),
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to update session summary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update session summary: {str(e)}"
        )


@router.delete("/sessions/{session_id}/summary")
async def delete_session_summary(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    删除会话总结
    
    Args:
        session_id: 会话 ID
        db: 数据库会话
        
    Returns:
        dict: 删除结果
        
    Raises:
        HTTPException: 会话不存在
    """
    try:
        from sqlalchemy import select
        from backend.models.session import Session
        
        result = await db.execute(
            select(Session).where(Session.id == session_id)
        )
        session = result.scalar_one_or_none()
        
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{session_id}' not found"
            )
        
        session.summary = None
        session.summary_updated_at = None
        
        await db.commit()
        
        logger.info(f"Deleted summary for session {session_id}")
        
        return {"success": True, "session_id": session_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to delete session summary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete session summary: {str(e)}"
        )


@router.post("/sessions/{session_id}/summarize", response_model=SummarizeSessionResponse)
async def summarize_session_to_memory(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    agent_loop: AgentLoop = Depends(get_agent_loop),
) -> SummarizeSessionResponse:
    """总结会话内容并保存到长期记忆
    
    使用 LLM 直接总结对话为一行记忆条目，写入 MEMORY.md。
    
    Args:
        session_id: 会话 ID
        db: 数据库会话
        agent_loop: Agent 循环实例
        
    Returns:
        SummarizeSessionResponse: 总结结果
    """
    try:
        from sqlalchemy import select
        from backend.models.session import Session
        from pathlib import Path
        from backend.modules.agent.analyzer import MessageAnalyzer
        from backend.modules.agent.prompts import CONVERSATION_TO_MEMORY_PROMPT
        
        logger.info(f"Starting memory summarization for session {session_id}")
        
        # 1. 验证会话
        result = await db.execute(
            select(Session).where(Session.id == session_id)
        )
        session = result.scalar_one_or_none()
        
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{session_id}' not found"
            )
        
        # 2. 获取消息
        session_manager = SessionManager(db)
        messages = await session_manager.get_messages(session_id=session_id)
        
        if not messages or len(messages) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Session has no messages to summarize"
            )
        
        # 3. 格式化消息
        analyzer = MessageAnalyzer()
        message_dicts = [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]
        formatted = analyzer.format_messages_for_summary(message_dicts, max_chars=4000)
        
        # 4. 用 LLM 生成总结
        prompt = CONVERSATION_TO_MEMORY_PROMPT.format(messages=formatted)
        
        summary_content = ""
        async for chunk in agent_loop.provider.chat_stream(
            messages=[{"role": "user", "content": prompt}],
            model=agent_loop.model,
            temperature=0.3,
        ):
            if chunk.is_content and chunk.content:
                summary_content += chunk.content
        
        summary = summary_content.strip()
        
        # 5. 如果 LLM 认为无需记录，直接返回
        if "无需记录" in summary:
            return SummarizeSessionResponse(
                success=True,
                summary=summary,
                message="对话无需记录到长期记忆",
            )
        
        # 6. 写入记忆
        config = config_loader.config
        workspace = Path(config.workspace.path) if config.workspace.path else WORKSPACE_DIR
        memory_dir = workspace / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)
        memory = MemoryStore(memory_dir)
        
        # 确定来源 - 使用渠道标识而非会话名称
        source = "web-chat"
        line_num = memory.append_entry(source=source, content=summary)
        
        logger.info(f"Memory saved at line {line_num}: {summary[:80]}...")
        
        return SummarizeSessionResponse(
            success=True,
            summary=summary,
            message=f"已保存到记忆第 {line_num} 行（共 {memory.get_line_count()} 条）",
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to summarize session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to summarize session: {str(e)}"
        )
