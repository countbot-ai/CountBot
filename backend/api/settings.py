"""Settings API 端点"""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.modules.config.loader import config_loader
from backend.modules.config.schema import AppConfig, ModelConfig, ProviderConfig, WorkspaceConfig

router = APIRouter(prefix="/api/settings", tags=["settings"])


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
    message_handler = getattr(request.app.state, 'message_handler', None)
    if message_handler:
        try:
            message_handler.reload_config(workspace=workspace_path)
            logger.info(f"Message handler workspace reloaded: {workspace_path}")
        except Exception as e:
            logger.warning(f"Failed to reload message handler workspace: {e}")

    shared = getattr(request.app.state, 'shared', None)
    if shared:
        try:
            shared['workspace'] = workspace_path

            context_builder = shared.get('context_builder')
            if context_builder:
                if hasattr(context_builder, 'update_workspace'):
                    context_builder.update_workspace(workspace_path)
                else:
                    context_builder.workspace = workspace_path

            subagent_manager = shared.get('subagent_manager')
            if subagent_manager:
                subagent_manager.workspace = workspace_path

            skills_loader = shared.get('skills_loader')
            if skills_loader:
                try:
                    skills_dir = workspace_path / 'skills'
                    skills_dir.mkdir(parents=True, exist_ok=True)
                    if hasattr(skills_loader, 'workspace_skills'):
                        skills_loader.workspace_skills = skills_dir
                    if hasattr(skills_loader, 'config_file'):
                        skills_loader.config_file = workspace_path / '.skills_config.json'
                    if hasattr(skills_loader, 'reload_skills'):
                        skills_loader.reload_skills()
                    logger.info(f"Skills loader workspace reloaded: {skills_dir}")
                except Exception as e:
                    logger.warning(f"Failed to reload skills after workspace change: {e}")

            logger.info(f"Shared components workspace reloaded: {workspace_path}")
        except Exception as e:
            logger.warning(f"Failed to reload shared components workspace: {e}")


def _prepare_message_handler_reload_params(
    config: AppConfig,
    *,
    reload_provider_model: bool = False,
    reload_persona: bool = False,
) -> dict[str, object]:
    """根据最新配置构建渠道消息处理器的热重载参数。"""
    reload_params: dict[str, object] = {}

    if reload_provider_model:
        try:
            from backend.modules.providers.litellm_provider import LiteLLMProvider
            from backend.modules.providers.registry import get_provider_metadata

            provider_id = config.model.provider
            provider_config = config.providers.get(provider_id)
            provider_meta = get_provider_metadata(provider_id)

            api_key = provider_config.api_key if provider_config else None
            api_base = (
                provider_config.api_base
                if provider_config and provider_config.api_base
                else (provider_meta.default_api_base if provider_meta else None)
            )

            reload_params['provider'] = LiteLLMProvider(
                api_key=api_key,
                api_base=api_base,
                default_model=config.model.model,
                timeout=600.0,
                max_retries=3,
                provider_id=provider_id,
            )
            reload_params['model'] = config.model.model
            reload_params['temperature'] = config.model.temperature
            reload_params['max_tokens'] = config.model.max_tokens
            reload_params['max_iterations'] = config.model.max_iterations
            reload_params['max_history_messages'] = config.persona.max_history_messages

            logger.info("Prepared AI config for hot reload")
        except Exception as e:
            logger.warning(f"Failed to prepare AI config for reload: {e}")

    if reload_persona:
        reload_params['persona_config'] = config.persona
        logger.info(
            "Prepared persona config for hot reload: "
            f"{config.persona.ai_name}, {config.persona.user_name}, "
            f"{getattr(config.persona, 'user_address', '')}"
        )

    return reload_params


async def _apply_saved_config_runtime(
    req: Request,
    config: AppConfig,
    *,
    workspace_path: Path | None = None,
    reload_persona: bool = False,
    reload_provider_model: bool = False,
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
        )
        if reload_params:
            try:
                message_handler.reload_config(**reload_params)
                logger.info("Channel message handler reloaded successfully")
            except Exception as e:
                logger.warning(f"Failed to reload channel handler config: {e}")

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
        list[dict]: 危险命令模式列表，每个包含 pattern, description, key
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
    default_api_base: str | None = Field(None, description="默认 API 基础 URL")
    default_model: str | None = Field(None, description="默认模型名称")


class ProviderConfigResponse(BaseModel):
    """Provider 配置响应"""
    
    enabled: bool = Field(..., description="是否启用")
    api_key: str | None = Field(None, description="API 密钥（脱敏）")
    api_base: str | None = Field(None, description="API 基础 URL")


class ModelConfigResponse(BaseModel):
    """模型配置响应"""
    
    provider: str = Field(..., description="Provider 名称")
    model: str = Field(..., description="模型名称")
    temperature: float = Field(..., description="温度参数")
    max_tokens: int = Field(..., description="最大 token 数")
    max_iterations: int = Field(..., description="最大迭代次数")


class WorkspaceConfigResponse(BaseModel):
    """工作空间配置响应"""

    path: str = Field(..., description="工作空间路径")


class SecurityConfigResponse(BaseModel):
    """安全配置响应"""
    
    # 危险命令检测
    dangerous_commands_blocked: bool = Field(..., description="是否阻止危险命令")
    custom_deny_patterns: list[str] = Field(..., description="自定义拒绝模式列表")
    
    # 命令白名单
    command_whitelist_enabled: bool = Field(..., description="是否启用命令白名单")
    custom_allow_patterns: list[str] = Field(..., description="自定义允许模式列表")
    
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
    max_history_messages: int = Field(..., description="最大对话历史条数")
    heartbeat: HeartbeatConfigResponse = Field(..., description="主动问候配置")


class SettingsResponse(BaseModel):
    """设置响应"""
    
    providers: dict[str, ProviderConfigResponse] = Field(..., description="Provider 配置")
    model: ModelConfigResponse = Field(..., description="模型配置")
    workspace: WorkspaceConfigResponse = Field(..., description="工作空间配置")
    security: SecurityConfigResponse = Field(..., description="安全配置")
    persona: PersonaConfigResponse = Field(..., description="用户信息和AI人设配置")
    workspace_migration: dict | None = Field(None, description="工作区迁移提示信息")


class UpdateSettingsRequest(BaseModel):
    """更新设置请求"""
    
    providers: dict[str, dict] | None = Field(None, description="Provider 配置")
    model: dict | None = Field(None, description="模型配置")
    workspace: dict | None = Field(None, description="工作空间配置")
    security: dict | None = Field(None, description="安全配置")
    persona: dict | None = Field(None, description="用户信息和AI人设配置")


class TestConnectionRequest(BaseModel):
    """测试连接请求"""
    
    provider: str = Field(..., description="Provider 名称")
    api_key: str = Field(default="", description="API 密钥")
    api_base: str | None = Field(None, description="API 基础 URL")
    model: str | None = Field(None, description="模型名称（可选）")


class TestConnectionResponse(BaseModel):
    """测试连接响应"""
    
    success: bool = Field(..., description="是否成功")
    message: str | None = Field(None, description="消息")
    error: str | None = Field(None, description="错误信息")


# ============================================================================
# Settings Endpoints
# ============================================================================


@router.get("/providers", response_model=list[ProviderMetadataResponse])
async def get_available_providers() -> list[ProviderMetadataResponse]:
    """
    获取所有可用的 Provider
    
    Returns:
        list[ProviderMetadataResponse]: Provider 列表
    """
    from backend.modules.providers.registry import get_all_providers
    
    providers = get_all_providers()
    return [
        ProviderMetadataResponse(
            id=meta.id,
            name=meta.name,
            default_api_base=meta.default_api_base,
            default_model=meta.default_model,
        )
        for meta in providers.values()
    ]


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
                temperature=config.model.temperature,
                max_tokens=config.model.max_tokens,
                max_iterations=config.model.max_iterations,
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
                heartbeat=HeartbeatConfigResponse(
                    enabled=config.persona.heartbeat.enabled,
                    channel=config.persona.heartbeat.channel,
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
            
            if "temperature" in request.model:
                config.model.temperature = request.model["temperature"]
            
            if "max_tokens" in request.model:
                config.model.max_tokens = request.model["max_tokens"]
            
            if "max_iterations" in request.model:
                config.model.max_iterations = request.model["max_iterations"]
        
        if request.workspace:
            if "path" in request.workspace:
                requested_workspace = request.workspace["path"]
                if isinstance(requested_workspace, str) and requested_workspace.strip():
                    from backend.modules.workspace.manager import workspace_manager

                    old_workspace = workspace_manager.get_workspace_path()
                    validated_workspace_path = _validate_workspace_path_or_raise(requested_workspace)
                    config.workspace.path = str(validated_workspace_path)
                else:
                    config.workspace.path = requested_workspace
        
        if request.security:
            if "dangerous_commands_blocked" in request.security:
                config.security.dangerous_commands_blocked = request.security["dangerous_commands_blocked"]
            
            if "custom_deny_patterns" in request.security:
                config.security.custom_deny_patterns = request.security["custom_deny_patterns"]
            
            if "command_whitelist_enabled" in request.security:
                config.security.command_whitelist_enabled = request.security["command_whitelist_enabled"]
            
            if "custom_allow_patterns" in request.security:
                config.security.custom_allow_patterns = request.security["custom_allow_patterns"]
            
            if "audit_log_enabled" in request.security:
                config.security.audit_log_enabled = request.security["audit_log_enabled"]
            
            if "command_timeout" in request.security:
                timeout = request.security["command_timeout"]
                # 处理空字符串或无效值
                if timeout == "" or timeout is None:
                    timeout = 60  # 默认值
                elif isinstance(timeout, str):
                    try:
                        timeout = int(timeout)
                    except ValueError:
                        timeout = 60
                # 确保在有效范围内
                timeout = max(1, min(300, int(timeout)))
                config.security.command_timeout = timeout
            
            if "subagent_timeout" in request.security:
                timeout = request.security["subagent_timeout"]
                # 处理空字符串或无效值
                if timeout == "" or timeout is None:
                    timeout = 600  # 默认值
                elif isinstance(timeout, str):
                    try:
                        timeout = int(timeout)
                    except ValueError:
                        timeout = 600
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
            
            if "heartbeat" in request.persona:
                hb = request.persona["heartbeat"]
                if isinstance(hb, dict):
                    if "enabled" in hb:
                        config.persona.heartbeat.enabled = hb["enabled"]
                    if "channel" in hb:
                        config.persona.heartbeat.channel = hb["channel"]
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
        
        # 保存配置（await 确保写入完成）
        await config_loader.save_config(config)
        config = config_loader.config

        runtime_workspace = validated_workspace_path.resolve() if validated_workspace_path is not None else None
        
        # 工作区迁移提示（如果有变更）
        if runtime_workspace is not None:
            try:
                from backend.modules.workspace.manager import workspace_manager

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
            sync_heartbeat=bool(request.persona and "heartbeat" in request.persona),
        )
        
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
        from backend.modules.providers.litellm_provider import LiteLLMProvider
        from backend.modules.providers.registry import get_provider_metadata
        
        # 获取 provider 元数据
        provider_meta = get_provider_metadata(request.provider)
        if not provider_meta:
            return TestConnectionResponse(
                success=False,
                error=f"未知的 provider: {request.provider}",
            )
        
        # 使用用户提供的配置
        test_model = request.model or "gpt-3.5-turbo"
        test_api_base = request.api_base or provider_meta.default_api_base
        
        logger.info(f"Using {provider_meta.name}, model: {test_model}, base: {test_api_base}")
        
        # 创建临时 provider
        provider = LiteLLMProvider(
            api_key=request.api_key,
            api_base=test_api_base,
            default_model=test_model,
            timeout=10.0,
            max_retries=1,
            provider_id=request.provider,
        )
        
        # 测试简单的聊天请求
        test_messages = [{"role": "user", "content": "Hello"}]
        
        response_received = False
        error_message = None
        response_content = ""
        
        async for chunk in provider.chat_stream(
            messages=test_messages,
            tools=None,
            model=test_model,
            max_tokens=10,
            temperature=0.7,
        ):
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


@router.post("/reload-oss")
async def reload_oss_config():
    """
    重新加载 OSS 配置（热重载，无需重启应用）
    
    Returns:
        dict: 重载结果
    """
    try:
        from backend.modules.tools.image_uploader import init_oss_uploader, get_upload_manager
        
        # 重新加载配置
        await config_loader.load()
        
        # 获取 OSS 配置
        oss_config = None
        if hasattr(config_loader.config.channels, 'qq') and hasattr(config_loader.config.channels.qq, 'oss'):
            oss_config = config_loader.config.channels.qq.oss.model_dump()
        
        # 重新初始化 OSS 上传器
        init_oss_uploader(oss_config)
        
        manager = get_upload_manager()
        if manager.uploader:
            logger.info(f"OSS 配置已重新加载: {manager.uploader.bucket} ({manager.uploader.region})")
            return {
                "success": True,
                "message": "OSS 配置已重新加载",
                "config": {
                    "bucket": manager.uploader.bucket,
                    "region": manager.uploader.region,
                    "endpoint": manager.uploader.endpoint
                }
            }
        else:
            logger.info("OSS 配置已清除（未配置）")
            return {
                "success": True,
                "message": "OSS 配置已清除",
                "config": None
            }
    
    except Exception as e:
        logger.error(f"重新加载 OSS 配置失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"重新加载 OSS 配置失败: {str(e)}"
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
    sections: str | None = None
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
                        
                        # 移除 OSS 密钥
                        if 'oss' in channel_data and isinstance(channel_data['oss'], dict):
                            channel_data['oss']['secret_id'] = ""
                            channel_data['oss']['secret_key'] = ""
        else:
            logger.info("保留敏感信息（包含 API 密钥）")
        
        # 构建导出数据
        export_data = {
            "version": "1.0.0",
            "exported_at": datetime.utcnow().isoformat() + "Z",
            "app_version": "1.0.0",  # 可以从版本文件读取
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
    sections: list[str] | None = Field(None, description="要导入的配置节")


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
