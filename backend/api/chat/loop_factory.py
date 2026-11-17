"""
AgentLoop 装配。

按会话级配置构造 provider、技能、工具注册表与 AgentLoop。
全局 SubagentManager 经 state 模块共享，本模块不持有该状态。
"""

from pathlib import Path
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db, get_db_session_factory
from backend.modules.agent.context import ContextBuilder
from backend.modules.agent.loop import AgentLoop
from backend.modules.agent.memory import MemoryStore
from backend.modules.agent.skills import SkillsLoader
from backend.modules.config.loader import config_loader
from backend.modules.providers import create_provider
from backend.modules.providers.runtime import (
    build_provider_unavailable_message,
    get_provider_runtime_state,
)
from backend.modules.session import build_session_model_override, resolve_session_runtime_config
from backend.modules.workspace import (
    get_global_workspace_path,
    resolve_session_workspace,
    seed_bundled_workspace_resources,
)


async def get_agent_loop(
    request: Request,
    db: AsyncSession = Depends(get_db),
    session_id: Optional[str] = None
) -> AgentLoop:
    """获取 AgentLoop 实例（依赖注入）
    
    Args:
        request: FastAPI 请求对象
        db: 数据库会话
        session_id: 可选的会话 ID，如果提供则使用会话级配置
    """
    
    try:
        config = config_loader.config
        session = None

        if session_id:
            from sqlalchemy import select
            from backend.models.session import Session
            
            result = await db.execute(
                select(Session).where(Session.id == session_id)
            )
            session = result.scalar_one_or_none()

        runtime_config = resolve_session_runtime_config(config, session)
        if session_id and runtime_config.use_custom_config:
            logger.info(f"会话使用自定义运行时配置：{session_id}")
        
        # 会话级工作空间优先；为空时回退全局配置
        workspace = resolve_session_workspace(session)
        workspace.mkdir(parents=True, exist_ok=True)
        
        # 初始化 LLM Provider（使用有效配置）
        provider_name = runtime_config.provider_name
        runtime_state = get_provider_runtime_state(
            config,
            provider_name,
            api_key_override=runtime_config.api_key,
            api_base_override=runtime_config.api_base,
        )

        if not runtime_state.selectable:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=build_provider_unavailable_message(provider_name, runtime_state.reason)
            )
        
        provider = create_provider(
            api_key=runtime_state.api_key or None,
            api_keys=runtime_state.api_keys or None,
            api_base=runtime_state.api_base,
            default_model=runtime_config.model_name,
            api_mode=runtime_config.api_mode,
            timeout=120.0,
            max_retries=3,
            provider_id=provider_name,
            api_type=runtime_state.api_type,
        )
        
        # 初始化记忆系统和技能加载器
        memory_dir = workspace / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)
        memory = MemoryStore(memory_dir)
        
        # 只有全局工作空间才复用共享 skills；会话自定义目录必须独立加载
        shared = getattr(request.app.state, 'shared', None)
        uses_global_workspace = workspace == get_global_workspace_path()
        if uses_global_workspace and hasattr(request.app.state, 'skills'):
            skills = request.app.state.skills
            logger.debug("Using global skills instance from app.state")
        elif uses_global_workspace and shared and shared.get('skills') is not None:
            skills = shared['skills']
            logger.debug("Using global skills instance from app.state")
        else:
            seed_bundled_workspace_resources(workspace)
            skills_dir = workspace / "skills"
            skills_dir.mkdir(parents=True, exist_ok=True)
            skills = SkillsLoader(skills_dir)
            logger.debug(f"Using workspace-scoped skills: {skills_dir}")
        
        context_builder = ContextBuilder(
            workspace=workspace,
            memory=memory,
            skills=skills,
            persona_config=runtime_config.persona_config,
            injection_config=config.injection,
        )
        
        # SubagentManager 惰性初始化；状态在 state 模块，这里不持有 global
        from backend.modules.agent.subagent import SubagentManager
        from backend.api.chat import state as chat_state

        def create_subagent_manager() -> SubagentManager:
            return SubagentManager(
                provider=provider,
                workspace=workspace,
                model=config.model.model,
                temperature=config.model.temperature,
                max_tokens=config.model.max_tokens,
                db_session_factory=get_db_session_factory(),
                config_loader=config_loader,
                skills=skills,
            )

        if uses_global_workspace:
            subagent_manager = chat_state.ensure_global_subagent_manager(
                create_subagent_manager()
            )
        else:
            subagent_manager = chat_state.get_or_create_workspace_subagent_manager(
                str(workspace),
                create_subagent_manager,
            )
        
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
            subagent_manager=subagent_manager,
            skills_loader=skills,
            session_id=None,
            memory_store=memory,
            disabled_tools=list(config.injection.disabled_tools),
        )
        
        agent_loop = AgentLoop(
            provider=provider,
            workspace=workspace,
            tools=tools,
            context_builder=context_builder,
            subagent_manager=subagent_manager,
            model=runtime_config.model_name,
            max_iterations=runtime_config.max_iterations,
            max_retries=3,
            retry_delay=1.0,
            temperature=runtime_config.temperature,
            max_tokens=runtime_config.max_tokens,
            thinking_enabled=runtime_config.thinking_enabled,
            reasoning_level=getattr(runtime_config, "reasoning_level", None),
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


def build_workspace_agent_loop(app_state, workspace: Path) -> AgentLoop:
    """为会话自定义工作空间构建独立 AgentLoop。

    WebSocket 连接默认复用全局 AgentLoop；一旦会话指定了自定义目录，
    必须为它单独装配 memory / skills / subagent / tools，避免和全局实例串台。
    """
    shared = app_state.shared
    config = config_loader.config
    provider = shared["provider"]

    seed_bundled_workspace_resources(workspace)
    memory_dir = workspace / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    skills_dir = workspace / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    memory = MemoryStore(memory_dir)
    skills = SkillsLoader(skills_dir)
    context_builder = ContextBuilder(
        workspace=workspace,
        memory=memory,
        skills=skills,
        persona_config=config.persona,
        injection_config=config.injection,
    )

    from backend.modules.agent.subagent import SubagentManager

    subagent_manager = SubagentManager(
        provider=provider,
        workspace=workspace,
        model=config.model.model,
        temperature=config.model.temperature,
        max_tokens=config.model.max_tokens,
        db_session_factory=get_db_session_factory(),
        config_loader=config_loader,
        skills=skills,
    )

    from backend.modules.tools.setup import register_all_tools

    tool_params = dict(shared.get("tool_params") or {})
    tool_params.update(
        workspace=workspace,
        subagent_manager=subagent_manager,
        skills_loader=skills,
    )
    tools = register_all_tools(**tool_params, memory_store=memory)

    try:
        from backend.modules.mcp.client import McpClientManager

        manager = McpClientManager.get_instance()
        if manager.connected:
            manager.sync_to_registry_sync(tools)
    except Exception as exc:
        logger.debug(f"Failed to sync MCP tools for workspace {workspace}: {exc}")

    logger.info(f"Built workspace-scoped AgentLoop: {workspace}")
    return AgentLoop(
        provider=provider,
        workspace=workspace,
        tools=tools,
        context_builder=context_builder,
        subagent_manager=subagent_manager,
        model=config.model.model,
        max_iterations=config.model.max_iterations,
        temperature=config.model.temperature,
        max_tokens=config.model.max_tokens,
        thinking_enabled=config.model.thinking_enabled,
        reasoning_level=config.model.reasoning_level,
    )
