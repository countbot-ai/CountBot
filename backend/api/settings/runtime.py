"""配置保存后把新值热重载到已运行的单例：工具注册表、渠道消息处理器、cron、工作区路径。"""

import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, Request, status
from loguru import logger

from backend.modules.config.loader import config_loader
from backend.modules.config.schema import AppConfig
from backend.modules.external_agents.registry import ExternalAgentRegistry
from backend.modules.workspace import seed_bundled_workspace_resources, workspace_manager

from backend.api.settings.models import (
    ExternalCodingProfilePayload,
    ExternalCodingToolsConfigPayload,
)


def _get_external_coding_registry() -> ExternalAgentRegistry:
    """基于当前工作空间创建外部编码工具注册表。"""
    workspace = Path(config_loader.config.workspace.path).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    return ExternalAgentRegistry(workspace=workspace)


def _load_external_coding_tools_config() -> tuple[ExternalAgentRegistry, Dict[str, Any]]:
    """加载外部编码工具配置原始 JSON。"""
    registry = _get_external_coding_registry()
    try:
        raw = json.loads(registry.config_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        registry._ensure_default_config()
        raw = json.loads(registry.config_path.read_text(encoding="utf-8"))

    if not isinstance(raw, dict):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="外部编码工具配置文件格式无效",
        )
    return registry, raw


def _validate_external_coding_tools_payload(
    payload: ExternalCodingToolsConfigPayload,
    registry: ExternalAgentRegistry,
) -> Dict[str, Any]:
    """复用 registry 校验待保存的外部编码工具配置。"""
    raw = payload.model_dump()
    profiles = raw.get("profiles", [])

    parsed_profiles = []
    for index, item in enumerate(profiles):
        parsed_profiles.append(registry._parse_profile(item, index))

        command = str(item.get("command", "")).strip()
        if not command:
            raise HTTPException(status_code=400, detail=f"profile '{item.get('name')}' 缺少 command")

    try:
        registry._validate_profile_collisions(parsed_profiles)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return raw


def _resolve_profile_command(command: str) -> Optional[str]:
    """解析 profile command 到实际可执行路径。"""
    normalized = str(command or "").strip()
    if not normalized:
        return None
    if os.path.isabs(normalized):
        return normalized if os.path.isfile(normalized) and os.access(normalized, os.X_OK) else None
    return shutil.which(normalized)


def _validate_workspace_path_or_raise(path: str) -> Path:
    """验证工作空间路径；失败时返回 400，而不是污染运行态或配置。"""
    from backend.modules.workspace import workspace_manager

    normalized = (path or "").strip()
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="路径不能为空"
        )

    try:
        return workspace_manager.prepare_workspace_path(normalized)
    except Exception as e:
        logger.warning(f"拒绝保存不可用工作空间路径: {normalized}, error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"工作空间路径不可用: {str(e)}"
        ) from e


def _hot_reload_workspace_runtime(request: Request, workspace_path: Path) -> None:
    """将新的工作空间路径热更新到当前运行态。"""
    from backend.modules.agent.memory import MemoryStore

    workspace_path = workspace_manager.activate_workspace_path(workspace_path)
    seed_bundled_workspace_resources(workspace_path)
    memory_dir = workspace_path / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    memory_store = MemoryStore(memory_dir)

    message_handler = getattr(request.app.state, 'message_handler', None)
    if message_handler:
        try:
            message_handler.reload_config(
                workspace=workspace_path,
                memory_store=memory_store,
            )
            logger.info(f"Message handler workspace reloaded: {workspace_path}")
        except Exception as e:
            logger.warning(f"Failed to reload message handler workspace: {e}")

    shared = getattr(request.app.state, 'shared', None)
    if shared:
        try:
            shared['workspace'] = workspace_path
            shared['memory'] = memory_store
            tool_params = shared.get('tool_params')
            if isinstance(tool_params, dict):
                tool_params['workspace'] = workspace_path

            context_builder = shared.get('context_builder')
            if context_builder:
                if hasattr(context_builder, 'update_workspace'):
                    context_builder.update_workspace(workspace_path)
                else:
                    context_builder.workspace = workspace_path
                context_builder.memory = memory_store

            subagent_manager = shared.get('subagent_manager')
            if subagent_manager:
                subagent_manager.workspace = workspace_path

            skills_loader = shared.get('skills')
            if skills_loader:
                try:
                    skills_dir = workspace_path / 'skills'
                    skills_dir.mkdir(parents=True, exist_ok=True)
                    if hasattr(skills_loader, 'workspace_skills'):
                        skills_loader.workspace_skills = skills_dir
                    if hasattr(skills_loader, 'config_file'):
                        skills_loader.config_file = workspace_path / '.skills_config.json'
                    if hasattr(skills_loader, 'reload'):
                        skills_loader.reload()
                    logger.info(f"Skills loader workspace reloaded: {skills_dir}")
                except Exception as e:
                    logger.warning(f"Failed to reload skills after workspace change: {e}")

            _rebuild_shared_tool_registry_runtime(request)
            request.app.state.skills = shared.get('skills')
            request.app.state.memory = memory_store

            logger.info(f"Shared components workspace reloaded: {workspace_path}")
        except Exception as e:
            logger.warning(f"Failed to reload shared components workspace: {e}")


def _rebuild_shared_tool_registry_runtime(request: Request) -> None:
    """重建全局共享工具注册表，保证依赖共享注册表的渠道读取到最新配置。"""
    shared = getattr(request.app.state, 'shared', None)
    if not shared:
        return

    tool_params = shared.get('tool_params')
    if not isinstance(tool_params, dict):
        return

    from backend.modules.tools.setup import register_all_tools

    register_kwargs = dict(tool_params)
    channel_manager = getattr(request.app.state, 'channel_manager', None)
    if channel_manager is not None:
        register_kwargs['channel_manager'] = channel_manager
        tool_params['channel_manager'] = channel_manager

    shared['tool_registry'] = register_all_tools(
        **register_kwargs,
        memory_store=shared.get('memory'),
    )
    logger.info("Shared tool registry reloaded")


def _reload_injection_runtime(request: Request, config: AppConfig) -> None:
    """把注入开关（injection）同步到当前运行态。

    单点处理四处持有者（共享 ContextBuilder、共享工具注册表、渠道消息处理器、
    cron agent），避免调用方各自拼装。
    """
    from backend.modules.tools.setup import register_all_tools

    disabled_tools = list(config.injection.disabled_tools)
    shared = getattr(request.app.state, 'shared', None) or {}

    context_builder = shared.get('context_builder')
    if context_builder is not None:
        context_builder.update_injection_config(config.injection)

    tool_params = shared.get('tool_params')
    if isinstance(tool_params, dict):
        tool_params['disabled_tools'] = disabled_tools
    _rebuild_shared_tool_registry_runtime(request)

    message_handler = getattr(request.app.state, 'message_handler', None)
    if message_handler is not None:
        message_handler.reload_config(
            injection_config=config.injection,
            tool_params_updates={'disabled_tools': disabled_tools},
        )

    cron_executor = getattr(request.app.state, 'cron_executor', None)
    cron_agent = getattr(cron_executor, 'agent', None) if cron_executor else None
    if cron_agent is not None and isinstance(tool_params, dict):
        # cron agent 与共享 ContextBuilder 是同一对象，此处只需重建其工具注册表
        cron_agent.tools = register_all_tools(
            **tool_params,
            memory_store=shared.get('memory'),
        )

    logger.info(f"Injection runtime reloaded: disabled_tools={disabled_tools}")


def _prepare_message_handler_reload_params(
    config: AppConfig,
    *,
    reload_provider_model: bool = False,
    reload_persona: bool = False,
    reload_security: bool = False,
) -> Dict[str, object]:
    """根据最新配置构建渠道消息处理器的热重载参数。

    注入开关不走这里，统一由 _reload_injection_runtime 处理。
    """
    reload_params: Dict[str, object] = {}

    if reload_provider_model:
        try:
            from backend.modules.providers import create_provider
            from backend.modules.providers.runtime import find_first_selectable_provider, get_provider_runtime_state

            provider_id = config.model.provider
            runtime_state = get_provider_runtime_state(config, provider_id)
            if not runtime_state.selectable:
                fallback_state = find_first_selectable_provider(config)
                if fallback_state:
                    provider_id = fallback_state.provider_id
                    runtime_state = fallback_state

            reload_params['provider'] = create_provider(
                api_key=runtime_state.api_key or None,
                api_keys=runtime_state.api_keys or None,
                api_base=runtime_state.api_base,
                default_model=config.model.model,
                api_mode=config.model.api_mode,
                timeout=600.0,
                max_retries=3,
                provider_id=provider_id,
                api_type=runtime_state.api_type,
            )
            reload_params['model'] = config.model.model
            reload_params['temperature'] = config.model.temperature
            reload_params['max_tokens'] = config.model.max_tokens
            reload_params['max_iterations'] = config.model.max_iterations
            reload_params['thinking_enabled'] = config.model.thinking_enabled
            reload_params['reasoning_level'] = config.model.reasoning_level
            reload_params['max_history_messages'] = config.persona.max_history_messages

            logger.info("Prepared AI config for hot reload")
        except Exception as e:
            logger.warning(f"Failed to prepare AI config for reload: {e}")

    if reload_persona:
        reload_params['persona_config'] = config.persona
        reload_params['max_history_messages'] = config.persona.max_history_messages
        logger.info(
            "Prepared persona config for hot reload: "
            f"{config.persona.ai_name}, {config.persona.user_name}, "
            f"{getattr(config.persona, 'user_address', '')}"
        )

    if reload_security:
        reload_params['tool_params_updates'] = {
            "command_timeout": config.security.command_timeout,
            "max_output_length": config.security.max_output_length,
            "allow_dangerous": not config.security.dangerous_commands_blocked,
            "restrict_to_workspace": config.security.restrict_to_workspace,
            "custom_deny_patterns": config.security.custom_deny_patterns,
            "custom_allow_patterns": (
                config.security.custom_allow_patterns
                if config.security.command_whitelist_enabled
                else None
            ),
            "audit_log_enabled": config.security.audit_log_enabled,
        }
        logger.info("Prepared tool security config for hot reload")

    return reload_params


def _reload_cron_runtime(
    request: Request,
    config: AppConfig,
    reload_params: Dict[str, object],
    *,
    workspace_path: Optional[Path] = None,
    reload_provider_model: bool = False,
    reload_persona: bool = False,
    reload_security: bool = False,
) -> None:
    """将最新配置同步到 cron agent / heartbeat 运行态。"""
    cron_executor = getattr(request.app.state, 'cron_executor', None)
    if not cron_executor:
        return

    shared = getattr(request.app.state, 'shared', None) or {}
    provider = reload_params.get('provider') if reload_provider_model else None
    tool_updates = reload_params.get('tool_params_updates')

    if provider is not None:
        shared['provider'] = provider
        subagent_manager = shared.get('subagent_manager')
        if subagent_manager is not None:
            subagent_manager.provider = provider
    else:
        subagent_manager = shared.get('subagent_manager')

    if subagent_manager is not None and reload_provider_model:
        subagent_manager.model = config.model.model
        subagent_manager.temperature = config.model.temperature
        subagent_manager.max_tokens = config.model.max_tokens

    tool_params = shared.get('tool_params')
    if isinstance(tool_params, dict):
        if workspace_path is not None:
            tool_params['workspace'] = workspace_path
        if isinstance(tool_updates, dict):
            tool_params.update(tool_updates)

    cron_agent = getattr(cron_executor, 'agent', None)
    if cron_agent is not None:
        if provider is not None:
            cron_agent.provider = provider
        if reload_provider_model:
            cron_agent.model = config.model.model
            cron_agent.temperature = config.model.temperature
            cron_agent.max_tokens = config.model.max_tokens
            cron_agent.max_iterations = config.model.max_iterations
            cron_agent.thinking_enabled = config.model.thinking_enabled
            cron_agent.reasoning_level = config.model.reasoning_level
        if workspace_path is not None:
            cron_agent.workspace = workspace_path

        if isinstance(tool_params, dict) and (workspace_path is not None or reload_security):
            try:
                from backend.modules.tools.setup import register_all_tools

                cron_agent.tools = register_all_tools(
                    **tool_params,
                    memory_store=shared.get('memory'),
                )
                logger.info("Cron agent tool registry reloaded")
            except Exception as e:
                logger.warning(f"Failed to reload cron agent tools: {e}")

    heartbeat_service = getattr(cron_executor, 'heartbeat_service', None)
    if heartbeat_service is not None:
        if provider is not None:
            heartbeat_service.provider = provider
        if reload_provider_model:
            heartbeat_service.model = config.model.model
        if workspace_path is not None:
            heartbeat_service.workspace = workspace_path
            heartbeat_service._state_file = workspace_path / "memory" / "heartbeat_state.json"

        if reload_persona or reload_provider_model or workspace_path is not None:
            heartbeat_cfg = config.persona.heartbeat
            heartbeat_service.ai_name = config.persona.ai_name or "小C"
            heartbeat_service.user_name = config.persona.user_name or "主人"
            heartbeat_service.user_address = config.persona.user_address or ""
            heartbeat_service.personality = config.persona.personality or "professional"
            heartbeat_service.custom_personality = config.persona.custom_personality or ""
            heartbeat_service.idle_threshold_hours = heartbeat_cfg.idle_threshold_hours
            heartbeat_service.quiet_start = heartbeat_cfg.quiet_start
            heartbeat_service.quiet_end = heartbeat_cfg.quiet_end
            heartbeat_service.max_greets_per_day = heartbeat_cfg.max_greets_per_day

    if (
        provider is not None
        or workspace_path is not None
        or reload_persona
        or reload_provider_model
        or reload_security
    ):
        logger.info("Cron runtime reloaded successfully")


async def _apply_saved_config_runtime(
    req: Request,
    config: AppConfig,
    *,
    workspace_path: Optional[Path] = None,
    reload_persona: bool = False,
    reload_provider_model: bool = False,
    reload_security: bool = False,
    reload_injection: bool = False,
    sync_heartbeat: bool = False,
) -> None:
    """将已保存的配置同步到当前运行态。"""
    if workspace_path is not None:
        try:
            _hot_reload_workspace_runtime(req, workspace_path.resolve())
        except Exception as e:
            logger.warning(f"Failed to hot reload workspace: {e}")

    if reload_persona:
        try:
            shared = getattr(req.app.state, 'shared', None)
            if shared and 'context_builder' in shared:
                context_builder = shared['context_builder']
                if hasattr(context_builder, 'update_persona_config'):
                    context_builder.update_persona_config(config.persona)
                    logger.info("Hot reloaded persona config")
        except Exception as e:
            logger.warning(f"Failed to hot reload persona config: {e}")

    if reload_injection:
        try:
            _reload_injection_runtime(req, config)
        except Exception as e:
            logger.warning(f"Failed to reload injection runtime: {e}")

    message_handler = getattr(req.app.state, 'message_handler', None)
    if message_handler:
        reload_params = _prepare_message_handler_reload_params(
            config,
            reload_provider_model=reload_provider_model,
            reload_persona=reload_persona,
            reload_security=reload_security,
        )
        if reload_params:
            try:
                message_handler.reload_config(**reload_params)
                logger.info("Channel message handler reloaded successfully")
            except Exception as e:
                logger.warning(f"Failed to reload channel handler config: {e}")
    else:
        reload_params = _prepare_message_handler_reload_params(
            config,
            reload_provider_model=reload_provider_model,
            reload_persona=reload_persona,
            reload_security=reload_security,
        )

    if reload_security and workspace_path is None:
        try:
            _rebuild_shared_tool_registry_runtime(req)
        except Exception as e:
            logger.warning(f"Failed to reload shared tool registry: {e}")

    try:
        _reload_cron_runtime(
            req,
            config,
            reload_params,
            workspace_path=workspace_path,
            reload_provider_model=reload_provider_model,
            reload_persona=reload_persona,
            reload_security=reload_security,
        )
    except Exception as e:
        logger.warning(f"Failed to reload cron runtime: {e}")

    if sync_heartbeat:
        try:
            from backend.database import get_db_session_factory
            from backend.modules.agent.heartbeat import ensure_heartbeat_job

            db_session_factory = get_db_session_factory()
            await ensure_heartbeat_job(
                db_session_factory,
                heartbeat_config=config.persona.heartbeat,
            )

            scheduler = getattr(req.app.state, 'cron_scheduler', None)
            if scheduler:
                await scheduler.trigger_reschedule()
        except Exception as e:
            logger.warning(f"Failed to sync heartbeat cron job: {e}")
