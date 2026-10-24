"""设置的核心读写：读取全量配置、更新配置、危险命令模式、可用 provider 列表。"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.modules.config.loader import config_loader
from backend.modules.config.schema import AppConfig, ModelConfig, ProviderConfig, WorkspaceConfig
from backend.modules.external_agents.conversation import profile_supports_native_session
from backend.modules.providers.runtime import get_provider_runtime_state
from backend.modules.workspace import workspace_manager
from pydantic import ValidationError

from backend.version import APP_VERSION

from backend.api.settings._router import router
from backend.api.settings.models import (
    HeartbeatConfigResponse,
    InjectionConfigResponse,
    ModelConfigResponse,
    PersonaConfigResponse,
    ProviderConfigResponse,
    ProviderMetadataResponse,
    SecurityConfigResponse,
    SettingsResponse,
    UpdateSettingsRequest,
    WorkspaceConfigResponse,
)
from backend.api.settings.runtime import (
    _apply_saved_config_runtime,
    _validate_workspace_path_or_raise,
)
from backend.api.settings.validators import (
    _coerce_boolean_value,
    _heartbeat_plan_settings_changed,
    _normalize_api_mode_value,
    _normalize_pattern_list,
    _validate_and_normalize_heartbeat_settings,
    _validate_regex_patterns_or_raise,
)


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
                api_key=provider_config.api_key,
                api_keys=provider_config.get_effective_api_keys(),
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
                supports_image=config.model.supports_image,
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
            injection=InjectionConfigResponse(
                core_rules=config.injection.core_rules,
                external_coding_guidance=config.injection.external_coding_guidance,
                skills_always=config.injection.skills_always,
                skills_summary=config.injection.skills_summary,
                agent_teams=config.injection.agent_teams,
                dynamic_context=config.injection.dynamic_context,
                team_reminder=config.injection.team_reminder,
                disabled_tools=list(config.injection.disabled_tools),
                auto_memory_summary=config.injection.auto_memory_summary,
            ),
            workspace_migration=None,  # GET 请求不返回迁移信息
        )
        
    except ValidationError as e:
        # 配置里存在脏值（多为 PUT 写入的非法字段）时明确返回 400，
        # 而不是让响应模型构造失败后落进 500
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"配置项无效: {e.errors()[0].get('msg', e)}"
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

                if "api_keys" in provider_data:
                    raw_keys = provider_data["api_keys"]
                    if isinstance(raw_keys, list):
                        provider_config.api_keys = [
                            k for k in raw_keys if isinstance(k, str) and k.strip()
                        ]
                    else:
                        provider_config.api_keys = []

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

            if "supports_image" in request.model:
                raw_supports_image = request.model["supports_image"]
                config.model.supports_image = (
                    raw_supports_image if isinstance(raw_supports_image, bool) else None
                )
        
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

        if request.injection:
            injection_data = request.injection
            bool_fields = (
                "core_rules",
                "external_coding_guidance",
                "skills_always",
                "skills_summary",
                "agent_teams",
                "dynamic_context",
                "team_reminder",
                "auto_memory_summary",
            )
            for field_name in bool_fields:
                if field_name in injection_data:
                    setattr(
                        config.injection,
                        field_name,
                        _coerce_boolean_value(
                            injection_data[field_name],
                            field_name=f"injection.{field_name}",
                        ),
                    )
            if "disabled_tools" in injection_data:
                raw_disabled = injection_data["disabled_tools"]
                if raw_disabled is None:
                    config.injection.disabled_tools = []
                elif isinstance(raw_disabled, list):
                    config.injection.disabled_tools = [
                        str(name).strip() for name in raw_disabled if str(name).strip()
                    ]
                else:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="injection.disabled_tools 必须是字符串数组",
                    )

        # 保存前整体验证一遍。各分区在请求模型里是裸 dict，脏值若在这里
        # 不拦住，会先落库、构造响应时才失败，配置已经被污染（GET 也跟着 400）。
        AppConfig.model_validate(config.model_dump())

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
            reload_injection=bool(request.injection),
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
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"配置项无效: {e.errors()[0].get('msg', e)}"
        )
    except Exception as e:
        logger.exception(f"Failed to update settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update settings: {str(e)}"
        )
