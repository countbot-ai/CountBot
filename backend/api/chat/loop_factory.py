"""
AgentLoop 装配。

按会话级配置构造 provider、技能、工具注册表与 AgentLoop。
全局 SubagentManager 经 state 模块共享，本模块不持有该状态。
"""

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
from backend.utils.paths import WORKSPACE_DIR
from backend.modules.session import build_session_model_override, resolve_session_runtime_config


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
        
        from pathlib import Path
        workspace = Path(config.workspace.path) if config.workspace.path else WORKSPACE_DIR
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
        
        # 优先使用全局 skills 实例（性能优化）
        shared = getattr(request.app.state, 'shared', None)
        if hasattr(request.app.state, 'skills'):
            skills = request.app.state.skills
            logger.debug("Using global skills instance from app.state")
        elif shared and shared.get('skills') is not None:
            skills = shared['skills']
            logger.debug("Using global skills instance from app.state")
        else:
            # 回退：创建临时实例
            skills_dir = workspace / "skills"
            skills_dir.mkdir(parents=True, exist_ok=True)
            skills = SkillsLoader(skills_dir)
            logger.warning("Creating temporary SkillsLoader instance in chat endpoint")
        
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

        subagent_manager = chat_state.ensure_global_subagent_manager(
            SubagentManager(
                provider=provider,
                workspace=workspace,
                model=config.model.model,
                temperature=config.model.temperature,
                max_tokens=config.model.max_tokens,
                db_session_factory=get_db_session_factory(),
                config_loader=config_loader,
                skills=skills,
            )
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
