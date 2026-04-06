"""Settings API 端点"""

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.modules.config.loader import config_loader
from backend.modules.config.schema import AppConfig, ModelConfig, ProviderConfig, WorkspaceConfig
from backend.modules.external_agents.conversation import profile_supports_native_session
from backend.modules.external_agents.registry import ExternalAgentRegistry
from backend.modules.providers.runtime import get_provider_runtime_state
from backend.modules.workspace import seed_bundled_workspace_resources, workspace_manager
from backend.version import APP_VERSION

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _normalize_api_mode_value(value: Any) -> str:
    return "chat_completions"


def _coerce_boolean_value(value: Any, *, field_name: str) -> bool:
    """将用户输入安全转换为布尔值，拒绝模糊字符串。"""
    if isinstance(value, bool):
        return value

    if isinstance(value, int) and value in {0, 1}:
        return bool(value)

    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"{field_name} must be a boolean",
    )


def _list_enabled_channel_account_ids(config: AppConfig, channel_name: str) -> List[str]:
    """列出指定渠道当前已启用的账号 ID。"""
    channel_cfg = getattr(config.channels, channel_name, None)
    if channel_cfg is None:
        return []

    ordered_account_ids: List[str] = []

    if bool(getattr(channel_cfg, "enabled", False)):
        top_level_account_id = str(getattr(channel_cfg, "account_id", "default") or "default")
        ordered_account_ids.append(top_level_account_id)

    accounts = getattr(channel_cfg, "accounts", {}) or {}
    for raw_account_id, account_cfg in accounts.items():
        if isinstance(account_cfg, dict):
            enabled = bool(account_cfg.get("enabled", False))
            account_id = str(raw_account_id or account_cfg.get("account_id") or "default")
        else:
            enabled = bool(getattr(account_cfg, "enabled", False))
            account_id = str(raw_account_id or getattr(account_cfg, "account_id", "default") or "default")
        if enabled:
            ordered_account_ids.append(account_id)

    deduped: List[str] = []
    for account_id in ordered_account_ids:
        if account_id not in deduped:
            deduped.append(account_id)
    return deduped


def _normalize_pattern_list(value: Any) -> List[str]:
    """清理正则模式列表，去掉空白项并去重，保留原顺序。"""
    if not isinstance(value, list):
        return []

    normalized: List[str] = []
    for item in value:
        text = str(item or "").strip()
        if not text or text in normalized:
            continue
        normalized.append(text)
    return normalized


def _validate_regex_patterns_or_raise(patterns: List[str], *, field_name: str) -> None:
    """保存配置前校验正则表达式，尽早返回明确错误。"""
    for index, pattern in enumerate(patterns):
        try:
            re.compile(pattern)
        except re.error as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{field_name}[{index}] 无效: {exc}",
            ) from exc


def _validate_cron_schedule_or_raise(schedule: Any, *, field_name: str) -> str:
    """校验 cron 表达式。"""
    from croniter import croniter

    normalized = str(schedule or "").strip()
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} 不能为空",
        )

    try:
        croniter(normalized)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} 无效: {e}",
        ) from e

    return normalized


def _validate_and_normalize_heartbeat_settings(config: AppConfig) -> None:
    """校验问候助手配置，并在单机器人场景下自动补全真实账号 ID。"""
    heartbeat = config.persona.heartbeat
    heartbeat.account_id = str(getattr(heartbeat, "account_id", "default") or "default").strip() or "default"
    heartbeat.schedule = _validate_cron_schedule_or_raise(
        heartbeat.schedule,
        field_name="persona.heartbeat.schedule",
    )

    if not heartbeat.enabled:
        return

    heartbeat.channel = str(heartbeat.channel or "").strip()
    heartbeat.chat_id = str(heartbeat.chat_id or "").strip()
    if not heartbeat.channel:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="启用问候助手前必须先选择推送渠道",
        )
    if not heartbeat.chat_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="启用问候助手前必须填写推送目标 ID",
        )

    enabled_account_ids = _list_enabled_channel_account_ids(config, heartbeat.channel)
    if not enabled_account_ids:
        available_channels = ", ".join(config.channels.model_dump().keys())
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"问候助手渠道 '{heartbeat.channel}' 当前没有可用机器人实例。"
                f"可用渠道: {available_channels}"
            ),
        )

    if heartbeat.account_id in enabled_account_ids:
        return

    if heartbeat.account_id == "default" and len(enabled_account_ids) == 1:
        heartbeat.account_id = enabled_account_ids[0]
        return

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            f"问候助手账号 ID '{heartbeat.account_id}' 无效，"
            f"当前渠道可用账号: {', '.join(enabled_account_ids)}"
        ),
    )


def _heartbeat_plan_settings_changed(before: Optional[Dict[str, Any]], after: Optional[Dict[str, Any]]) -> bool:
    """判断是否需要刷新当天随机问候计划。"""
    if not before or not after:
        return False

    watched_keys = ("quiet_start", "quiet_end", "max_greets_per_day")
    return any(before.get(key) != after.get(key) for key in watched_keys)


class ExternalCodingProfilePayload(BaseModel):
    """外部编码工具 profile 配置。"""

    name: str = Field(..., min_length=1)
    aliases: List[str] = Field(default_factory=list)
    type: str = "cli"
    icon_svg: str = ""
    enabled: bool = False
    description: str = ""
    command: str = ""
    args: List[str] = Field(default_factory=list)
    working_dir: str = ""
    stdin_template: Optional[str] = None
    env: Dict[str, str] = Field(default_factory=dict)
    inherit_env: List[str] = Field(default_factory=list)
    session_mode: str = "history"
    history_message_count: int = Field(default=10, ge=1, le=50)
    timeout: Optional[int] = None
    success_exit_codes: List[int] = Field(default_factory=lambda: [0])


class ExternalCodingToolsConfigPayload(BaseModel):
    """外部编码工具完整配置。"""

    version: int = 1
    profiles: List[ExternalCodingProfilePayload] = Field(default_factory=list)


class ExternalCodingToolsConfigResponse(ExternalCodingToolsConfigPayload):
    """外部编码工具配置响应。"""

    config_path: str


class ExternalCodingProfileCheckRequest(BaseModel):
    """外部编码工具 profile 检查请求。"""

    profile: ExternalCodingProfilePayload


class ExternalCodingProfileCheckResponse(BaseModel):
    """外部编码工具 profile 检查结果。"""

    success: bool
    message: str
    resolved_command: Optional[str] = None
    missing_env: List[str] = Field(default_factory=list)


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


def _prepare_message_handler_reload_params(
    config: AppConfig,
    *,
    reload_provider_model: bool = False,
    reload_persona: bool = False,
    reload_security: bool = False,
) -> Dict[str, object]:
    """根据最新配置构建渠道消息处理器的热重载参数。"""
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
                api_base=runtime_state.api_base,
                default_model=config.model.model,
                api_mode=config.model.api_mode,
                timeout=600.0,
                max_retries=3,
                provider_id=provider_id,
            )
            reload_params['model'] = config.model.model
            reload_params['temperature'] = config.model.temperature
            reload_params['max_tokens'] = config.model.max_tokens
            reload_params['max_iterations'] = config.model.max_iterations
            reload_params['thinking_enabled'] = config.model.thinking_enabled
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


@router.get("/security/dangerous-patterns")
async def get_dangerous_patterns():
    """
    获取内置的危险命令模式及其描述
    
    Returns:
        List[dict]: 危险命令模式列表，每个包含 pattern, description, key
    """
    # 内置危险模式及其描述
    patterns = [
        {
            "pattern": r"\brm\s+-[rf]{1,2}\b",
            "description": "删除文件和目录（rm -rf）",
            "key": "rm_rf"
        },
        {
            "pattern": r"\bdel\s+/[fq]\b",
            "description": "强制删除文件（Windows del /f）",
            "key": "del_force"
        },
        {
            "pattern": r"\brmdir\s+/s\b",
            "description": "递归删除目录（Windows rmdir /s）",
            "key": "rmdir_recursive"
        },
        {
            "pattern": r"\b(format|mkfs|diskpart)\b",
            "description": "磁盘格式化和分区操作",
            "key": "disk_operations"
        },
        {
            "pattern": r"\bdd\s+if=",
            "description": "磁盘数据复制命令",
            "key": "dd_command"
        },
        {
            "pattern": r">\s*/dev/sd",
            "description": "直接写入磁盘设备",
            "key": "write_device"
        },
        {
            "pattern": r"\b(shutdown|reboot|poweroff|halt)\b",
            "description": "系统关机/重启命令",
            "key": "power_operations"
        },
        {
            "pattern": r":\(\)\s*\{.*\};\s*:",
            "description": "Fork 炸弹攻击",
            "key": "fork_bomb"
        },
        {
            "pattern": r"\binit\s+[06]\b",
            "description": "系统初始化级别切换",
            "key": "init_shutdown"
        }
    ]
    
    return {
        "success": True,
        "patterns": patterns
    }


# ============================================================================
# Request/Response Models
# ============================================================================


class ProviderMetadataResponse(BaseModel):
    """Provider 元数据响应"""
    
    id: str = Field(..., description="Provider ID")
    name: str = Field(..., description="显示名称")
    default_api_base: Optional[str] = Field(None, description="默认 API 基础 URL")
    default_model: Optional[str] = Field(None, description="默认模型名称")
    enabled: bool = Field(False, description="是否已启用")
    configured: bool = Field(False, description="配置是否完整")
    selectable: bool = Field(False, description="是否可用于实际请求")
    requires_api_key: bool = Field(True, description="是否要求 API Key")
    requires_api_base: bool = Field(False, description="是否要求自定义 API Base")
    status: str = Field("disabled", description="运行状态")
    reason: str = Field("disabled", description="状态原因")
    provider_group: str = Field("experimental", description="前端展示分组")
    thinking_control_tier: str = Field("unsupported", description="思考开关支持等级")


class ProviderConfigResponse(BaseModel):
    """Provider 配置响应"""
    
    enabled: bool = Field(..., description="是否启用")
    api_key: Optional[str] = Field(None, description="API 密钥（脱敏）")
    api_base: Optional[str] = Field(None, description="API 基础 URL")


class ModelConfigResponse(BaseModel):
    """模型配置响应"""
    
    provider: str = Field(..., description="Provider 名称")
    model: str = Field(..., description="模型名称")
    api_mode: str = Field(..., description="OpenAI API 模式，固定为 chat.completions")
    temperature: float = Field(..., description="温度参数，0 表示不发送")
    max_tokens: int = Field(..., description="最大 token 数")
    max_iterations: int = Field(..., description="最大迭代次数")
    thinking_enabled: bool = Field(..., description="是否启用思考模式")


class WorkspaceConfigResponse(BaseModel):
    """工作空间配置响应"""

    path: str = Field(..., description="工作空间路径")


class SecurityConfigResponse(BaseModel):
    """安全配置响应"""
    
    # 危险命令检测
    dangerous_commands_blocked: bool = Field(..., description="是否阻止危险命令")
    custom_deny_patterns: List[str] = Field(..., description="自定义拒绝模式列表")
    
    # 命令白名单
    command_whitelist_enabled: bool = Field(..., description="是否启用命令白名单")
    custom_allow_patterns: List[str] = Field(..., description="自定义允许模式列表")
    
    # 审计日志
    audit_log_enabled: bool = Field(..., description="是否启用审计日志")
    
    # 其他安全选项
    command_timeout: int = Field(..., description="命令超时时间（秒）")
    subagent_timeout: int = Field(..., description="子代理超时时间（秒）")
    max_output_length: int = Field(..., description="最大输出长度")
    restrict_to_workspace: bool = Field(..., description="是否限制在工作空间内")


class HeartbeatConfigResponse(BaseModel):
    """主动问候配置响应"""
    enabled: bool = Field(..., description="是否启用")
    channel: str = Field(..., description="推送渠道")
    account_id: str = Field(default="default", description="推送机器人账号 ID")
    chat_id: str = Field(..., description="推送目标 ID")
    schedule: str = Field(..., description="检查频率 cron 表达式")
    idle_threshold_hours: int = Field(..., description="空闲阈值（小时）")
    quiet_start: int = Field(..., description="免打扰开始时间")
    quiet_end: int = Field(..., description="免打扰结束时间")
    max_greets_per_day: int = Field(..., description="每天最多问候次数")


class PersonaConfigResponse(BaseModel):
    """用户信息和AI人设配置响应"""
    
    ai_name: str = Field(..., description="AI的名字")
    user_name: str = Field(..., description="用户的称呼")
    user_address: str = Field(default="", description="用户的常用地址")
    output_language: str = Field(default="中文", description="AI默认输出语言")
    personality: str = Field(..., description="AI的性格类型")
    custom_personality: str = Field(..., description="自定义性格描述")
    max_history_messages: int = Field(
        ...,
        description="最大对话历史条数，0 表示不限且关闭短期上下文总结",
    )
    enable_short_context_summary: bool = Field(
        default=False,
        description="是否启用短期上下文摘要缓存，默认关闭",
    )
    heartbeat: HeartbeatConfigResponse = Field(..., description="主动问候配置")


class SettingsResponse(BaseModel):
    """设置响应"""
    
    providers: Dict[str, ProviderConfigResponse] = Field(..., description="Provider 配置")
    model: ModelConfigResponse = Field(..., description="模型配置")
    workspace: WorkspaceConfigResponse = Field(..., description="工作空间配置")
    security: SecurityConfigResponse = Field(..., description="安全配置")
    persona: PersonaConfigResponse = Field(..., description="用户信息和AI人设配置")
    workspace_migration: Optional[dict] = Field(None, description="工作区迁移提示信息")


class UpdateSettingsRequest(BaseModel):
    """更新设置请求"""
    
    providers: Optional[Dict[str, dict]] = Field(None, description="Provider 配置")
    model: Optional[dict] = Field(None, description="模型配置")
    workspace: Optional[dict] = Field(None, description="工作空间配置")
    security: Optional[dict] = Field(None, description="安全配置")
    persona: Optional[dict] = Field(None, description="用户信息和AI人设配置")


class TestConnectionRequest(BaseModel):
    """测试连接请求"""
    
    provider: str = Field(..., description="Provider 名称")
    api_key: str = Field(default="", description="API 密钥")
    api_base: Optional[str] = Field(None, description="API 基础 URL")
    model: Optional[str] = Field(None, description="模型名称（可选）")
    api_mode: Optional[str] = Field(None, description="API 模式（仅保留兼容字段）")
    temperature: Optional[float] = Field(None, description="温度参数（可选，0 表示不发送）")
    max_tokens: Optional[int] = Field(None, description="最大 token 数（可选，0 表示不发送）")
    thinking_enabled: Optional[bool] = Field(None, description="是否启用思考模式（可选）")


class TestConnectionResponse(BaseModel):
    """测试连接响应"""
    
    success: bool = Field(..., description="是否成功")
    message: Optional[str] = Field(None, description="消息")
    error: Optional[str] = Field(None, description="错误信息")


# ============================================================================
# Settings Endpoints
# ============================================================================


@router.get("/providers", response_model=List[ProviderMetadataResponse])
async def get_available_providers() -> List[ProviderMetadataResponse]:
    """
    获取所有可用的 Provider
    
    Returns:
        List[ProviderMetadataResponse]: Provider 列表
    """
    from backend.modules.providers.registry import get_all_providers
    
    config = config_loader.config
    providers = get_all_providers()
    response: List[ProviderMetadataResponse] = []
    for meta in providers.values():
        runtime_state = get_provider_runtime_state(config, meta.id)
        response.append(
            ProviderMetadataResponse(
                id=meta.id,
                name=meta.name,
                default_api_base=meta.default_api_base,
                default_model=meta.default_model,
                enabled=runtime_state.enabled,
                configured=runtime_state.configured,
                selectable=runtime_state.selectable,
                requires_api_key=runtime_state.requires_api_key,
                requires_api_base=runtime_state.requires_api_base,
                status=runtime_state.status,
                reason=runtime_state.reason,
                provider_group=meta.provider_group,
                thinking_control_tier=meta.thinking_control_tier,
            )
        )
    return response


@router.get("", response_model=SettingsResponse)
async def get_settings() -> SettingsResponse:
    """
    获取所有设置
    
    Returns:
        SettingsResponse: 设置信息
    """
    try:
        config = config_loader.config
        
        # 构建 providers 响应（不脱敏，直接返回）
        providers_response = {}
        for name, provider_config in config.providers.items():
            providers_response[name] = ProviderConfigResponse(
                enabled=provider_config.enabled,
                api_key=provider_config.api_key,  # 直接返回，不脱敏
                api_base=provider_config.api_base,
            )
        
        # 构建响应
        return SettingsResponse(
            providers=providers_response,
            model=ModelConfigResponse(
                provider=config.model.provider,
                model=config.model.model,
                api_mode=_normalize_api_mode_value(config.model.api_mode),
                temperature=config.model.temperature,
                max_tokens=config.model.max_tokens,
                max_iterations=config.model.max_iterations,
                thinking_enabled=config.model.thinking_enabled,
            ),
            workspace=WorkspaceConfigResponse(
                path=config.workspace.path,
            ),
            security=SecurityConfigResponse(
                dangerous_commands_blocked=config.security.dangerous_commands_blocked,
                custom_deny_patterns=config.security.custom_deny_patterns,
                command_whitelist_enabled=config.security.command_whitelist_enabled,
                custom_allow_patterns=config.security.custom_allow_patterns,
                audit_log_enabled=config.security.audit_log_enabled,
                command_timeout=config.security.command_timeout,
                subagent_timeout=config.security.subagent_timeout,
                max_output_length=config.security.max_output_length,
                restrict_to_workspace=config.security.restrict_to_workspace,
            ),
            persona=PersonaConfigResponse(
                ai_name=config.persona.ai_name,
                user_name=config.persona.user_name,
                user_address=getattr(config.persona, 'user_address', ''),
                output_language=getattr(config.persona, 'output_language', '中文'),
                personality=config.persona.personality,
                custom_personality=config.persona.custom_personality,
                max_history_messages=config.persona.max_history_messages,
                enable_short_context_summary=getattr(
                    config.persona,
                    'enable_short_context_summary',
                    False,
                ),
                heartbeat=HeartbeatConfigResponse(
                    enabled=config.persona.heartbeat.enabled,
                    channel=config.persona.heartbeat.channel,
                    account_id=config.persona.heartbeat.account_id,
                    chat_id=config.persona.heartbeat.chat_id,
                    schedule=config.persona.heartbeat.schedule,
                    idle_threshold_hours=config.persona.heartbeat.idle_threshold_hours,
                    quiet_start=config.persona.heartbeat.quiet_start,
                    quiet_end=config.persona.heartbeat.quiet_end,
                    max_greets_per_day=config.persona.heartbeat.max_greets_per_day,
                ),
            ),
            workspace_migration=None,  # GET 请求不返回迁移信息
        )
        
    except Exception as e:
        logger.exception(f"Failed to get settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get settings: {str(e)}"
        )


@router.put("", response_model=SettingsResponse)
async def update_settings(request: UpdateSettingsRequest, req: Request) -> SettingsResponse:
    """
    更新设置
    
    Args:
        request: 更新设置请求
        
    Returns:
        SettingsResponse: 更新后的设置
    """
    try:
        previous_heartbeat = config_loader.config.persona.heartbeat.model_dump()
        config = config_loader.config.model_copy(deep=True)
        workspace_migration_info = None
        old_workspace = None
        validated_workspace_path = None
        
        if request.providers:
            for name, provider_data in request.providers.items():
                # 如果 provider 不存在，自动创建
                if name not in config.providers:
                    config.providers[name] = ProviderConfig()

                provider_config = config.providers[name]

                if "enabled" in provider_data:
                    provider_config.enabled = provider_data["enabled"]

                if "api_key" in provider_data:
                    provider_config.api_key = provider_data["api_key"]

                if "api_base" in provider_data:
                    provider_config.api_base = provider_data["api_base"]
        
        if request.model:
            if "provider" in request.model:
                config.model.provider = request.model["provider"]
            
            if "model" in request.model:
                config.model.model = request.model["model"]

            if "api_mode" in request.model:
                config.model.api_mode = _normalize_api_mode_value(request.model["api_mode"])
            
            if "temperature" in request.model:
                config.model.temperature = request.model["temperature"]
            
            if "max_tokens" in request.model:
                config.model.max_tokens = request.model["max_tokens"]
            
            if "max_iterations" in request.model:
                config.model.max_iterations = request.model["max_iterations"]

            if "thinking_enabled" in request.model:
                config.model.thinking_enabled = request.model["thinking_enabled"]
        
        if request.workspace:
            if "path" in request.workspace:
                requested_workspace = request.workspace["path"]
                if isinstance(requested_workspace, str) and requested_workspace.strip():
                    old_workspace = workspace_manager.get_workspace_path()
                    validated_workspace_path = _validate_workspace_path_or_raise(requested_workspace)
                    config.workspace.path = str(validated_workspace_path)
                else:
                    config.workspace.path = requested_workspace
        
        if request.security:
            if "dangerous_commands_blocked" in request.security:
                config.security.dangerous_commands_blocked = request.security["dangerous_commands_blocked"]
            
            if "custom_deny_patterns" in request.security:
                config.security.custom_deny_patterns = _normalize_pattern_list(
                    request.security["custom_deny_patterns"]
                )
            
            if "command_whitelist_enabled" in request.security:
                config.security.command_whitelist_enabled = request.security["command_whitelist_enabled"]
            
            if "custom_allow_patterns" in request.security:
                config.security.custom_allow_patterns = _normalize_pattern_list(
                    request.security["custom_allow_patterns"]
                )
            
            if "audit_log_enabled" in request.security:
                config.security.audit_log_enabled = request.security["audit_log_enabled"]
            
            if "command_timeout" in request.security:
                timeout = request.security["command_timeout"]
                # 处理空字符串或无效值
                if timeout == "" or timeout is None:
                    timeout = 180
                elif isinstance(timeout, str):
                    try:
                        timeout = int(timeout)
                    except ValueError:
                        timeout = 180
                # 确保在有效范围内
                timeout = max(10, min(1800, int(timeout)))
                config.security.command_timeout = timeout
            
            if "subagent_timeout" in request.security:
                timeout = request.security["subagent_timeout"]
                # 处理空字符串或无效值
                if timeout == "" or timeout is None:
                    timeout = 1200  # 默认值
                elif isinstance(timeout, str):
                    try:
                        timeout = int(timeout)
                    except ValueError:
                        timeout = 1200
                # 确保在有效范围内
                timeout = max(60, min(3600, int(timeout)))
                config.security.subagent_timeout = timeout
            
            if "max_output_length" in request.security:
                length = request.security["max_output_length"]
                # 处理空字符串或无效值
                if length == "" or length is None:
                    length = 10000  # 默认值
                elif isinstance(length, str):
                    try:
                        length = int(length)
                    except ValueError:
                        length = 10000
                # 确保在有效范围内
                length = max(100, min(1000000, int(length)))
                config.security.max_output_length = length
            
            if "restrict_to_workspace" in request.security:
                config.security.restrict_to_workspace = request.security["restrict_to_workspace"]

            _validate_regex_patterns_or_raise(
                config.security.custom_deny_patterns,
                field_name="security.custom_deny_patterns",
            )
            _validate_regex_patterns_or_raise(
                config.security.custom_allow_patterns,
                field_name="security.custom_allow_patterns",
            )
        
        if request.persona:
            if "ai_name" in request.persona:
                config.persona.ai_name = request.persona["ai_name"]
            
            if "user_name" in request.persona:
                config.persona.user_name = request.persona["user_name"]
            
            if "user_address" in request.persona:
                config.persona.user_address = request.persona["user_address"]

            if "output_language" in request.persona:
                config.persona.output_language = request.persona["output_language"] or "中文"
            
            if "personality" in request.persona:
                config.persona.personality = request.persona["personality"]
            
            if "custom_personality" in request.persona:
                config.persona.custom_personality = request.persona["custom_personality"]
            
            if "max_history_messages" in request.persona:
                config.persona.max_history_messages = request.persona["max_history_messages"]

            if "enable_short_context_summary" in request.persona:
                config.persona.enable_short_context_summary = _coerce_boolean_value(
                    request.persona["enable_short_context_summary"],
                    field_name="persona.enable_short_context_summary",
                )
            
            if "heartbeat" in request.persona:
                hb = request.persona["heartbeat"]
                if isinstance(hb, dict):
                    if "enabled" in hb:
                        config.persona.heartbeat.enabled = hb["enabled"]
                    if "channel" in hb:
                        config.persona.heartbeat.channel = hb["channel"]
                    if "account_id" in hb:
                        config.persona.heartbeat.account_id = hb["account_id"] or "default"
                    if "chat_id" in hb:
                        config.persona.heartbeat.chat_id = hb["chat_id"]
                    if "schedule" in hb:
                        config.persona.heartbeat.schedule = hb["schedule"]
                    if "idle_threshold_hours" in hb:
                        config.persona.heartbeat.idle_threshold_hours = hb["idle_threshold_hours"]
                    if "quiet_start" in hb:
                        config.persona.heartbeat.quiet_start = hb["quiet_start"]
                    if "quiet_end" in hb:
                        config.persona.heartbeat.quiet_end = hb["quiet_end"]
                    if "max_greets_per_day" in hb:
                        config.persona.heartbeat.max_greets_per_day = hb["max_greets_per_day"]

            if "heartbeat" in request.persona:
                _validate_and_normalize_heartbeat_settings(config)
        
        # 保存配置（await 确保写入完成）
        await config_loader.save_config(config)
        config = config_loader.config

        runtime_workspace = validated_workspace_path.resolve() if validated_workspace_path is not None else None
        
        # 工作区迁移提示（如果有变更）
        if runtime_workspace is not None:
            try:
                if old_workspace is not None:
                    migration_check = workspace_manager.check_skills_migration_needed(
                        old_workspace, runtime_workspace
                    )
                    if migration_check["needed"]:
                        workspace_migration_info = {
                            "migration_needed": True,
                            "old_path": str(old_workspace),
                            "new_path": str(runtime_workspace),
                            "old_skills_count": migration_check["old_skills_count"],
                            "new_skills_count": migration_check["new_skills_count"],
                            "message": f"检测到旧工作区有 {migration_check['old_skills_count']} 个技能，新工作区只有 {migration_check['new_skills_count']} 个。建议手动迁移技能文件。"
                        }
                        logger.warning(f"Skills migration may be needed: {workspace_migration_info['message']}")
            except Exception as e:
                logger.warning(f"Failed to check workspace migration: {e}")

        await _apply_saved_config_runtime(
            req,
            config,
            workspace_path=runtime_workspace,
            reload_persona=bool(request.persona),
            reload_provider_model=bool(request.providers or request.model),
            reload_security=bool(request.security),
            sync_heartbeat=bool(request.persona and "heartbeat" in request.persona),
        )

        if request.persona and "heartbeat" in request.persona:
            current_heartbeat = config.persona.heartbeat.model_dump()
            if _heartbeat_plan_settings_changed(previous_heartbeat, current_heartbeat):
                cron_executor = getattr(req.app.state, "cron_executor", None)
                heartbeat_service = getattr(cron_executor, "heartbeat_service", None)
                if heartbeat_service is not None and hasattr(heartbeat_service, "refresh_today_schedule"):
                    try:
                        heartbeat_service.refresh_today_schedule(reason="设置页修改问候参数")
                    except Exception as e:
                        logger.warning(f"Failed to refresh heartbeat today schedule: {e}")
        
        logger.info("Settings updated successfully")
        
        # 返回更新后的设置
        response = await get_settings()
        
        # 添加工作区迁移提示（如果有）
        if workspace_migration_info:
            response.workspace_migration = workspace_migration_info
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to update settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update settings: {str(e)}"
        )


@router.get("/external-coding-tools", response_model=ExternalCodingToolsConfigResponse)
async def get_external_coding_tools_config() -> ExternalCodingToolsConfigResponse:
    """读取工作空间中的外部编码工具配置。"""
    try:
        registry, raw = _load_external_coding_tools_config()
        payload = ExternalCodingToolsConfigPayload(**raw)
        return ExternalCodingToolsConfigResponse(
            config_path=str(registry.config_path),
            **payload.model_dump(),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to load external coding tools config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load external coding tools config: {str(e)}",
        )


@router.put("/external-coding-tools", response_model=ExternalCodingToolsConfigResponse)
async def update_external_coding_tools_config(
    request: ExternalCodingToolsConfigPayload,
) -> ExternalCodingToolsConfigResponse:
    """保存工作空间中的外部编码工具配置。"""
    try:
        registry = _get_external_coding_registry()
        raw = _validate_external_coding_tools_payload(request, registry)
        registry.config_path.parent.mkdir(parents=True, exist_ok=True)
        registry.config_path.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        logger.info(f"Updated external coding tools config: {registry.config_path}")
        return ExternalCodingToolsConfigResponse(
            config_path=str(registry.config_path),
            **request.model_dump(),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to save external coding tools config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save external coding tools config: {str(e)}",
        )


@router.post("/external-coding-tools/check", response_model=ExternalCodingProfileCheckResponse)
async def check_external_coding_tool_profile(
    request: ExternalCodingProfileCheckRequest,
) -> ExternalCodingProfileCheckResponse:
    """检查单个外部编码工具 profile 的命令解析和环境变量情况。"""
    try:
        registry = _get_external_coding_registry()
        payload = request.profile.model_dump()
        parsed_profile = registry._parse_profile(payload, 0)

        command = str(payload.get("command", "")).strip()
        resolved_command = _resolve_profile_command(command)
        missing_env = [
            env_name
            for env_name in (payload.get("inherit_env", []) or [])
            if str(env_name).strip() and not os.getenv(str(env_name).strip())
        ]

        if resolved_command:
            message = f"命令可用: {resolved_command}"
            if missing_env:
                message += f"；缺少环境变量: {', '.join(missing_env)}"
            if (
                parsed_profile.session_mode == "native"
                and not profile_supports_native_session(parsed_profile)
            ):
                message += "；当前原生会话模式会自动回退为最近历史模式"
            return ExternalCodingProfileCheckResponse(
                success=True,
                message=message,
                resolved_command=resolved_command,
                missing_env=missing_env,
            )

        return ExternalCodingProfileCheckResponse(
            success=False,
            message=f"未找到可执行命令: {command}",
            resolved_command=None,
            missing_env=missing_env,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to check external coding tool profile: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check external coding tool profile: {str(e)}",
        )


@router.post("/test-connection", response_model=TestConnectionResponse)
async def test_connection(request: TestConnectionRequest) -> TestConnectionResponse:
    """
    测试 Provider 连接
    
    Args:
        request: 测试连接请求
        
    Returns:
        TestConnectionResponse: 测试结果
    """
    logger.info(f"Testing connection to {request.provider} with model {request.model}")
    
    try:
        from backend.modules.providers import create_provider
        from backend.modules.providers.registry import get_provider_metadata
        
        # 获取 provider 元数据
        provider_meta = get_provider_metadata(request.provider)
        if not provider_meta:
            return TestConnectionResponse(
                success=False,
                error=f"未知的 provider: {request.provider}",
            )
        
        # 使用用户提供的配置
        test_model = (request.model or provider_meta.default_model or "").strip()
        test_api_base = request.api_base or provider_meta.default_api_base

        if not test_model:
            return TestConnectionResponse(
                success=False,
                error="请先填写模型名称，再测试连接。",
            )
        
        logger.info(f"Using {provider_meta.name}, model: {test_model}, base: {test_api_base}")
        
        # 创建临时 provider
        provider = create_provider(
            api_key=request.api_key,
            api_base=test_api_base,
            default_model=test_model,
            api_mode=_normalize_api_mode_value(request.api_mode or config_loader.config.model.api_mode),
            timeout=30.0,
            max_retries=1,
            provider_id=request.provider,
        )
        
        # 测试简单的聊天请求
        test_messages = [{"role": "user", "content": "Hello"}]
        
        response_received = False
        error_message = None
        response_content = ""
        
        request_kwargs: Dict[str, Any] = {
            "messages": test_messages,
            "tools": None,
            "model": test_model,
            "max_tokens": request.max_tokens or 0,
        }
        if request.temperature is not None and request.temperature > 0:
            request_kwargs["temperature"] = request.temperature
        if request.thinking_enabled is not None:
            request_kwargs["thinking_enabled"] = request.thinking_enabled

        async for chunk in provider.chat_stream(**request_kwargs):
            if chunk.error:
                error_message = chunk.error
                logger.error(f"Provider returned error: {chunk.error}")
                break
            
            if chunk.content:
                response_content += chunk.content
                response_received = True
            
            if chunk.finish_reason:
                logger.info(f"Stream finished with reason: {chunk.finish_reason}")
                response_received = True
                break
        
        if error_message:
            return TestConnectionResponse(
                success=False,
                error=error_message,
            )
        
        if response_received:
            logger.info(f"Connection test successful for {request.provider}")
            success_msg = f"Successfully connected to {request.provider}"
            if response_content:
                success_msg += f", received response: {response_content[:50]}"
            return TestConnectionResponse(
                success=True,
                message=success_msg,
            )
        else:
            return TestConnectionResponse(
                success=False,
                error="No response received from provider",
            )
        
    except Exception as e:
        logger.exception(f"Connection test failed: {e}")
        return TestConnectionResponse(
            success=False,
            error=str(e),
        )


# ============================================================================
# 配置导出导入
# ============================================================================


@router.post("/workspace/select-directory")
async def select_directory():
    """
    选择目录
    
    Returns:
        dict: 选择的目录路径
    """
    try:
        from backend.utils.file_dialog import select_directory as desktop_select_directory, is_desktop_environment
        
        # 检查是否在桌面环境中
        if not is_desktop_environment():
            return {
                "success": False,
                "message": "目录选择功能仅在桌面环境中可用",
                "path": None
            }
        
        # 打开目录选择对话框
        selected_path = desktop_select_directory("选择工作空间目录")
        
        if selected_path:
            return {
                "success": True,
                "message": "目录选择成功",
                "path": selected_path
            }
        else:
            return {
                "success": False,
                "message": "用户取消选择",
                "path": None
            }
            
    except Exception as e:
        logger.error(f"选择目录失败: {e}")
        return {
            "success": False,
            "message": f"选择目录失败: {str(e)}",
            "path": None
        }


@router.get("/workspace/info")
async def get_workspace_info(force: bool = False):
    """
    获取工作空间信息
    
    Args:
        force: 是否强制刷新缓存
    
    Returns:
        dict: 工作空间详细信息
    """
    try:
        from backend.modules.workspace import workspace_manager
        
        info = workspace_manager.get_workspace_info(force_refresh=force)
        
        # 新的API返回格式已经包含格式化的大小，直接返回
        return info
    
    except Exception as e:
        logger.error(f"获取工作空间信息失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取工作空间信息失败: {str(e)}"
        )


@router.post("/workspace/clean-temp")
async def clean_temp_files(request: Request):
    """
    清理临时文件
    
    Returns:
        dict: 清理结果
    """
    try:
        from backend.modules.workspace import workspace_manager
        
        # 获取请求参数
        try:
            body = await request.json()
            max_age_hours = body.get('max_age_hours', 24)
            clean_all = body.get('clean_all', False)
        except Exception:
            max_age_hours = 24
            clean_all = False
        
        # 确保参数在合理范围内
        max_age_hours = max(1, min(168, int(max_age_hours)))  # 1小时到7天
        
        result = workspace_manager.clean_temp_files(max_age_hours, clean_all)
        
        return result
    
    except Exception as e:
        logger.error(f"清理临时文件失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"清理临时文件失败: {str(e)}"
        )


@router.post("/workspace/set-path")
async def set_workspace_path(request: Request):
    """
    设置工作空间路径（支持热重载，无需重启）
    
    Returns:
        dict: 设置结果
    """
    try:
        from backend.modules.workspace import workspace_manager
        from backend.modules.config.loader import config_loader
        
        # 获取请求参数
        try:
            body = await request.json()
            path = body.get('path', '').strip()
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="无效的请求参数"
            )
        
        if not path:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="路径不能为空"
            )
        
        workspace_path = _validate_workspace_path_or_raise(path)

        updated_config = config_loader.config.model_copy(deep=True)
        updated_config.workspace.path = str(workspace_path)
        await config_loader.save_config(updated_config)

        _hot_reload_workspace_runtime(request, workspace_path)
        
        return {
            "success": True,
            "message": f"工作空间路径已设置为: {workspace_path}（已热重载，无需重启）",
            "path": str(workspace_manager.workspace_path),
            "reloaded": True
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"设置工作空间路径失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"设置工作空间路径失败: {str(e)}"
        )


@router.get("/export")
async def export_settings(
    include_api_keys: bool = False,
    sections: Optional[str] = None
):
    """
    导出配置
    
    Args:
        include_api_keys: 是否包含 API 密钥（默认不包含，保护敏感信息）
        sections: 要导出的配置节，逗号分隔（如：providers,model,persona）
    
    Returns:
        JSON 格式的配置文件
    """
    try:
        from datetime import datetime
        
        # 添加日志以便调试
        logger.info(f"导出配置请求: include_api_keys={include_api_keys} (type={type(include_api_keys).__name__}), sections={sections}")
        
        config = config_loader.config
        config_dict = config.model_dump()
        
        # 过滤配置节
        if sections:
            section_list = [s.strip() for s in sections.split(',')]
            config_dict = {k: v for k, v in config_dict.items() if k in section_list}
            logger.info(f"过滤配置节: {section_list}")
        
        # 移除敏感信息
        if not include_api_keys:
            logger.info("移除敏感信息（API 密钥）")
            # 移除 provider API 密钥
            if 'providers' in config_dict:
                for provider in config_dict['providers'].values():
                    if isinstance(provider, dict) and 'api_key' in provider:
                        provider['api_key'] = ""
            
            # 移除渠道密钥
            if 'channels' in config_dict:
                for channel_name, channel_data in config_dict['channels'].items():
                    if isinstance(channel_data, dict):
                        # 移除各种密钥字段
                        for key in ['token', 'secret', 'app_secret', 'secret_key', 
                                   'client_secret', 'encoding_aes_key', 'encrypt_key']:
                            if key in channel_data:
                                channel_data[key] = ""
                        
        else:
            logger.info("保留敏感信息（包含 API 密钥）")
        
        # 构建导出数据
        export_data = {
            "version": "1.0.0",
            "exported_at": datetime.utcnow().isoformat() + "Z",
            "app_version": APP_VERSION,
            "config": config_dict
        }
        
        logger.info(f"配置导出成功，sections={sections}, include_api_keys={include_api_keys}")
        
        return export_data
    
    except Exception as e:
        logger.error(f"导出配置失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"导出失败: {str(e)}"
        )


class ImportSettingsRequest(BaseModel):
    """导入配置请求"""
    
    version: str = Field(..., description="配置文件版本")
    config: dict = Field(..., description="配置数据")
    merge: bool = Field(default=False, description="是否合并现有配置")
    sections: Optional[List[str]] = Field(None, description="要导入的配置节")


@router.post("/import")
async def import_settings(request: ImportSettingsRequest, req: Request):
    """
    导入配置
    
    Args:
        request: 导入配置请求
    
    Returns:
        导入结果和更新后的配置
    """
    try:
        # 检查版本兼容性
        version = request.version
        if not version.startswith("1."):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"不支持的配置版本: {version}，当前仅支持 1.x 版本"
            )
        
        import_config = request.config
        
        # 过滤配置节
        if request.sections:
            import_config = {k: v for k, v in import_config.items() if k in request.sections}
        
        # 获取当前配置
        current_config = config_loader.config
        current_dict = current_config.model_dump()
        
        # 合并或覆盖
        if request.merge:
            # 深度合并
            merged_dict = _deep_merge(current_dict, import_config)
            logger.info(f"配置合并模式，sections={request.sections}")
        else:
            # 覆盖指定节
            merged_dict = current_dict.copy()
            merged_dict.update(import_config)
            logger.info(f"配置覆盖模式，sections={request.sections}")
        
        # 验证配置
        try:
            new_config = AppConfig(**merged_dict)
        except Exception as e:
            logger.error(f"配置验证失败: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"配置验证失败: {str(e)}"
            )
        
        # 保存配置
        try:
            await config_loader.save_config(new_config)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"配置中的工作空间路径不可用: {str(e)}"
            ) from e

        config = config_loader.config
        imported_sections = set(import_config.keys())
        runtime_workspace = None
        if "workspace" in imported_sections:
            try:
                runtime_workspace = Path(config.workspace.path).resolve()
            except Exception as e:
                logger.warning(f"Failed to resolve imported workspace for hot reload: {e}")

        await _apply_saved_config_runtime(
            req,
            config,
            workspace_path=runtime_workspace,
            reload_persona="persona" in imported_sections,
            reload_provider_model=bool({"providers", "model"} & imported_sections),
            sync_heartbeat="persona" in imported_sections,
        )
        
        logger.info("配置导入成功")
        
        # 返回更新后的配置
        return {
            "success": True,
            "message": "配置导入成功",
            "settings": await get_settings()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"导入配置失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"导入失败: {str(e)}"
        )


def _deep_merge(base: dict, update: dict) -> dict:
    """
    深度合并字典
    
    Args:
        base: 基础字典
        update: 更新字典
    
    Returns:
        合并后的字典
    """
    result = base.copy()
    for key, value in update.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
