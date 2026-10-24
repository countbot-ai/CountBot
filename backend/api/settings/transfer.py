"""配置的导出与导入。"""

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

from backend.api.settings._router import router
from backend.api.settings.models import ImportSettingsRequest
from backend.api.settings.core import get_settings
from backend.api.settings.runtime import _apply_saved_config_runtime


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
