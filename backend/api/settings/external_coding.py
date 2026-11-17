"""外部编码代理的配置读写与 profile 检查。"""

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
from backend.version import APP_VERSION

from backend.modules.external_agents.registry import ExternalAgentRegistry

from backend.api.settings._router import router
from backend.api.settings.models import (
    ExternalCodingProfileCheckRequest,
    ExternalCodingProfileCheckResponse,
    ExternalCodingToolsConfigPayload,
    ExternalCodingToolsConfigResponse,
)
from backend.api.settings.runtime import (
    _get_external_coding_registry,
    _load_external_coding_tools_config,
    _resolve_profile_command,
    _validate_external_coding_tools_payload,
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
