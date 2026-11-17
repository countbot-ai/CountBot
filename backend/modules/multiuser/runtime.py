"""用户运行时：按用户构建并缓存独立的 Provider、工作区、记忆与 AgentLoop。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from loguru import logger

from backend.modules.agent.loop import AgentLoop
from backend.modules.agent.memory import MemoryStore
from backend.modules.agent.skills import SkillsLoader
from backend.modules.agent.context import ContextBuilder
from backend.modules.config.loader import config_loader
from backend.modules.multiuser.effective import (
    ModelResolutionError,
    build_provider,
    resolve_model_for_user,
    resolve_persona_for_user,
    resolved_stream_enabled,
)
from backend.modules.workspace import (
    bundled_skill_copy_names,
    bundled_skills_dir,
    builtin_skill_names,
    resolve_user_workspace,
    seed_bundled_workspace_resources,
)


async def build_user_skills_loader(user, workspace: Path) -> SkillsLoader:
    """按用户构建技能加载器：私有技能、显式共享技能与共享模式下的只读内置技能。"""
    from backend.modules.multiuser.settings import MODE_SHARED, peek_settings

    skills_dir = workspace / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    settings = peek_settings()
    shared_readable = settings.mode == MODE_SHARED and settings.shared_skills_wiki_mcp
    # 只读层只放「随应用分发」的内置技能；管理员自建技能必须逐个发布共享才会下发
    builtin_dir = bundled_skills_dir() if shared_readable else None
    builtin_only_names = builtin_skill_names() if shared_readable else None

    shared_dirs: list[Path] = []
    disabled_shared: set[str] = set()
    try:
        from backend.database import AsyncSessionLocal
        from backend.modules.multiuser.shared_skills import (
            disabled_shared_names,
            visible_shared_dirs,
        )

        async with AsyncSessionLocal() as db:
            shared_dirs = await visible_shared_dirs(db, user)
            disabled_shared = await disabled_shared_names(db, user)
    except Exception as exc:
        logger.warning(f"Failed to resolve shared skills for {getattr(user, 'username', '?')}: {exc}")

    return SkillsLoader(
        skills_dir,
        builtin_skills_dir=builtin_dir,
        # 隔离模式必须显式关闭内置目录：只传 builtin_skills_dir=None 会回落默认目录
        include_builtin=shared_readable,
        # 显式传空列表：普通用户不扫描 ~/.openclaw/skills、~/skills
        external_skills_dirs=[],
        shared_skills_dirs=shared_dirs,
        extra_disabled_skills=disabled_shared,
        excluded_workspace_skills=bundled_skill_copy_names(workspace),
        builtin_only_names=builtin_only_names,
    )


@dataclass
class UserRuntime:
    """一个用户的独立运行时。"""

    user_id: str
    workspace: Path
    provider: object
    memory: MemoryStore
    skills: SkillsLoader
    context_builder: ContextBuilder
    tools: object
    subagent_manager: object
    agent_loop: AgentLoop
    model_name: str
    model_source: str
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class UserRuntimeManager:
    """按用户构建与回收运行时。"""

    def __init__(self) -> None:
        self._runtimes: Dict[str, UserRuntime] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # 构建
    # ------------------------------------------------------------------

    async def _build_skills(self, user, workspace: Path) -> SkillsLoader:
        """用户技能加载器；解析规则与技能接口共用 build_user_skills_loader。"""
        return await build_user_skills_loader(user, workspace)

    async def _build_runtime(self, user) -> UserRuntime:
        from backend.api.chat import state as chat_state
        from backend.database import get_db_session_factory
        from backend.modules.agent.subagent import SubagentManager
        from backend.modules.tools.setup import register_all_tools

        workspace = resolve_user_workspace(user)
        workspace.mkdir(parents=True, exist_ok=True)
        # 技能不播种到用户工作区：管理员的技能只通过显式共享或共享模式只读层下发。
        seed_bundled_workspace_resources(workspace, include_skills=False)

        memory_dir = workspace / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)
        memory = MemoryStore(memory_dir)
        skills = await self._build_skills(user, workspace)

        resolved = await resolve_model_for_user(user)
        provider = build_provider(resolved)
        persona = await resolve_persona_for_user(user)
        config = config_loader.config

        context_builder = ContextBuilder(
            workspace=workspace,
            memory=memory,
            skills=skills,
            persona_config=persona,
            injection_config=config.injection,
            owner_id=user.owner_id,
        )

        subagent_manager = SubagentManager(
            provider=provider,
            workspace=workspace,
            model=resolved.model_id,
            temperature=config.model.temperature,
            max_tokens=config.model.max_tokens,
            db_session_factory=get_db_session_factory(),
            config_loader=config_loader,
            skills=skills,
        )

        tools = register_all_tools(
            workspace=workspace,
            command_timeout=config.security.command_timeout,
            max_output_length=config.security.max_output_length,
            allow_dangerous=not config.security.dangerous_commands_blocked,
            restrict_to_workspace=config.security.restrict_to_workspace,
            custom_deny_patterns=config.security.custom_deny_patterns,
            custom_allow_patterns=(
                config.security.custom_allow_patterns
                if config.security.command_whitelist_enabled
                else None
            ),
            audit_log_enabled=config.security.audit_log_enabled,
            subagent_manager=subagent_manager,
            skills_loader=skills,
            owner_id=user.owner_id,
            memory_store=memory,
            disabled_tools=list(config.injection.disabled_tools),
        )

        # 共享模式：管理员 MCP 只读复用；隔离模式完全不暴露
        try:
            from backend.modules.multiuser.settings import MODE_SHARED, peek_settings

            settings = peek_settings()
            if settings.enabled and settings.mode == MODE_SHARED and settings.shared_skills_wiki_mcp:
                from backend.modules.mcp.client import McpClientManager

                shared_mcp = McpClientManager.get_instance()
                if shared_mcp.connected:
                    shared_mcp.sync_to_registry_sync(tools)
        except Exception as exc:
            logger.debug(f"Shared MCP sync skipped: {exc}")

        # 用户自建 MCP：独立实例、独立工具前缀
        try:
            from backend.modules.multiuser.user_mcp import user_mcp_manager

            await user_mcp_manager.sync_into_registry(user.owner_id, tools)
        except Exception as exc:
            logger.warning(f"Failed to sync user MCP for {user.username}: {exc}")

        agent_loop = AgentLoop(
            provider=provider,
            workspace=workspace,
            tools=tools,
            context_builder=context_builder,
            subagent_manager=subagent_manager,
            model=resolved.model_id,
            max_iterations=config.model.max_iterations,
            max_retries=3,
            retry_delay=1.0,
            temperature=config.model.temperature,
            max_tokens=config.model.max_tokens,
            thinking_enabled=config.model.thinking_enabled,
            stream_enabled=resolved_stream_enabled(
                resolved, fallback=config.model.stream_enabled
            ),
            reasoning_level=config.model.reasoning_level,
        )

        # 让任务 API 能找到这个用户的 SubagentManager
        chat_state.register_user_subagent_manager(user.owner_id, subagent_manager)

        logger.info(
            f"Built runtime for user {user.username} "
            f"(model={resolved.source}:{resolved.provider_id}/{resolved.model_id}, "
            f"workspace={workspace})"
        )

        return UserRuntime(
            user_id=user.owner_id or "",
            workspace=workspace,
            provider=provider,
            memory=memory,
            skills=skills,
            context_builder=context_builder,
            tools=tools,
            subagent_manager=subagent_manager,
            agent_loop=agent_loop,
            model_name=resolved.model_id,
            model_source=resolved.source,
        )

    # ------------------------------------------------------------------
    # 获取 / 失效
    # ------------------------------------------------------------------

    async def get(self, user) -> UserRuntime:
        """获取（必要时构建）用户运行时。管理员不走这里。"""
        if getattr(user, "is_admin", False) or not getattr(user, "owner_id", None):
            raise RuntimeError("admin runtime must use app.state.shared")

        user_id = user.owner_id
        cached = self._runtimes.get(user_id)
        if cached is not None:
            return cached

        async with self._lock:
            cached = self._runtimes.get(user_id)
            if cached is not None:
                return cached
            runtime = await self._build_runtime(user)
            self._runtimes[user_id] = runtime
            return runtime

    async def get_agent_loop(self, user) -> AgentLoop:
        return (await self.get(user)).agent_loop

    async def get_subagent_manager(self, user):
        return (await self.get(user)).subagent_manager

    async def get_workspace(self, user) -> Path:
        return (await self.get(user)).workspace

    def invalidate(self, user_id: str) -> None:
        """丢弃缓存，下次请求重建（改配置、改模型、禁用后调用）。"""
        if not user_id:
            return
        try:
            from backend.modules.multiuser.user_mcp import user_mcp_manager

            user_mcp_manager.schedule_disconnect(user_id)
        except Exception as exc:
            logger.debug(f"User MCP cleanup skipped: {exc}")
        runtime = self._runtimes.pop(user_id, None)
        if runtime is not None:
            from backend.api.chat import state as chat_state

            chat_state.unregister_user_subagent_manager(user_id)
            logger.info(f"Invalidated runtime for user {user_id}")

    def invalidate_all(self) -> None:
        for user_id in list(self._runtimes.keys()):
            self.invalidate(user_id)

    async def shutdown(self, user_id: str) -> None:
        self.invalidate(user_id)


# 全局单例
user_runtime_manager = UserRuntimeManager()
