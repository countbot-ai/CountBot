"""工作区相关操作：选择目录、查询信息、清理临时文件、设置路径。"""

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

from backend.modules.workspace import seed_bundled_workspace_resources

from backend.api.settings._router import router
from backend.api.settings.runtime import (
    _hot_reload_workspace_runtime,
    _validate_workspace_path_or_raise,
)


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
