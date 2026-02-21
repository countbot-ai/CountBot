"""Settings API 端点"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.modules.config.loader import config_loader
from backend.modules.config.schema import AppConfig, ModelConfig, ProviderConfig, WorkspaceConfig

router = APIRouter(prefix="/api/settings", tags=["settings"])


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
    
    # API 密钥加密
    api_key_encryption_enabled: bool = Field(..., description="是否启用 API 密钥加密")
    
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
                api_key_encryption_enabled=config.security.api_key_encryption_enabled,
                dangerous_commands_blocked=config.security.dangerous_commands_blocked,
                custom_deny_patterns=config.security.custom_deny_patterns,
                command_whitelist_enabled=config.security.command_whitelist_enabled,
                custom_allow_patterns=config.security.custom_allow_patterns,
                audit_log_enabled=config.security.audit_log_enabled,
                command_timeout=config.security.command_timeout,
                max_output_length=config.security.max_output_length,
                restrict_to_workspace=config.security.restrict_to_workspace,
            ),
            persona=PersonaConfigResponse(
                ai_name=config.persona.ai_name,
                user_name=config.persona.user_name,
                user_address=getattr(config.persona, 'user_address', ''),
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
        config = config_loader.config
        
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
                config.workspace.path = request.workspace["path"]
        
        if request.security:
            if "api_key_encryption_enabled" in request.security:
                config.security.api_key_encryption_enabled = request.security["api_key_encryption_enabled"]
            
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
                config.security.command_timeout = request.security["command_timeout"]
            
            if "max_output_length" in request.security:
                config.security.max_output_length = request.security["max_output_length"]
            
            if "restrict_to_workspace" in request.security:
                config.security.restrict_to_workspace = request.security["restrict_to_workspace"]
        
        if request.persona:
            if "ai_name" in request.persona:
                config.persona.ai_name = request.persona["ai_name"]
            
            if "user_name" in request.persona:
                config.persona.user_name = request.persona["user_name"]
            
            if "user_address" in request.persona:
                config.persona.user_address = request.persona["user_address"]
            
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
        
        # 热重载渠道消息处理器的 AI 配置
        message_handler = getattr(req.app.state, 'message_handler', None)
        if message_handler:
            reload_params = {}
            
            # Provider 和模型配置变更
            if request.providers or request.model:
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
                    
                    new_provider = LiteLLMProvider(
                        api_key=api_key,
                        api_base=api_base,
                        default_model=config.model.model,
                        timeout=120.0,
                        max_retries=3,
                        provider_id=provider_id,
                    )
                    
                    reload_params['provider'] = new_provider
                    reload_params['model'] = config.model.model
                    reload_params['temperature'] = config.model.temperature
                    reload_params['max_tokens'] = config.model.max_tokens
                    reload_params['max_iterations'] = config.model.max_iterations
                    reload_params['max_history_messages'] = config.persona.max_history_messages
                    
                    logger.info("Prepared AI config for hot reload")
                except Exception as e:
                    logger.warning(f"Failed to prepare AI config for reload: {e}")
            
            # Persona 配置变更
            if request.persona:
                reload_params['persona_config'] = config.persona
                logger.info(f"Prepared persona config for hot reload: {config.persona.ai_name}, {config.persona.user_name}, {getattr(config.persona, 'user_address', '')}")
            
            # 执行热重载
            if reload_params:
                try:
                    message_handler.reload_config(**reload_params)
                    logger.info("Channel message handler reloaded successfully")
                except Exception as e:
                    logger.warning(f"Failed to reload channel handler config: {e}")
        
        # 同步 heartbeat cron job 配置
        if request.persona and "heartbeat" in request.persona:
            try:
                from backend.database import get_db_session_factory
                from backend.modules.agent.heartbeat import ensure_heartbeat_job
                db_session_factory = get_db_session_factory()
                await ensure_heartbeat_job(db_session_factory, heartbeat_config=config.persona.heartbeat)
                
                # 触发调度器重新计算
                scheduler = getattr(req.app.state, 'cron_scheduler', None)
                if scheduler:
                    await scheduler.trigger_reschedule()
            except Exception as e:
                logger.warning(f"Failed to sync heartbeat cron job: {e}")
        
        logger.info("Settings updated successfully")
        
        # 返回更新后的设置
        return await get_settings()
        
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
