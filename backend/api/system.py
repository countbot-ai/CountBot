"""系统集成 API 端点"""

from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from loguru import logger
from typing import Optional

router = APIRouter(prefix="/api/system", tags=["system"])

# 全局引用（由 main.py 设置）
tray_manager = None
hotkey_manager = None
autostart_manager = None


@router.get("/health")
async def health_check():
    """健康检查端点 - 用于前端检测服务器是否就绪"""
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "CountBot"
    }


@router.get("/info")
async def system_info():
    """返回系统运行信息，供前端侧边栏展示"""
    import platform
    import os
    import sys

    host = os.getenv("HOST", "127.0.0.1")
    port = os.getenv("PORT", "8000")
    api_url = f"http://{host}:{port}"

    return {
        "api_url": api_url,
        "version": "0.1.0",
        "python_version": platform.python_version(),
        "os": f"{platform.system()} {platform.release()}",
        "arch": platform.machine(),
        "pid": os.getpid(),
        "uptime_start": datetime.now(timezone.utc).isoformat(),
    }


class NotificationRequest(BaseModel):
    """通知请求模型"""
    title: str
    message: str
    icon: Optional[str] = None


class HotkeyRequest(BaseModel):
    """快捷键注册请求"""
    hotkey: str
    action: str


class AutoStartRequest(BaseModel):
    """自启动配置请求"""
    enabled: bool


@router.post("/notify")
async def send_notification(request: NotificationRequest):
    """发送系统通知"""
    try:
        logger.info(f"Notification: {request.title} - {request.message}")
        return {"success": True, "message": "Notification sent"}
    except Exception as e:
        logger.error(f"Failed to send notification: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tray/status")
async def get_tray_status():
    """获取系统托盘状态"""
    return JSONResponse(content={
        "available": tray_manager is not None,
        "visible": True  # pywebview doesn't provide tray visibility status
    })


@router.post("/tray/minimize")
async def minimize_to_tray():
    """最小化到系统托盘"""
    if not tray_manager:
        raise HTTPException(status_code=503, detail="System tray not available")
    
    try:
        tray_manager.minimize_to_tray()
        return JSONResponse(content={"success": True})
    except Exception as e:
        logger.error(f"Failed to minimize to tray: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tray/restore")
async def restore_from_tray():
    """从系统托盘恢复窗口"""
    if not tray_manager:
        raise HTTPException(status_code=503, detail="System tray not available")
    
    try:
        tray_manager.restore_from_tray()
        return JSONResponse(content={"success": True})
    except Exception as e:
        logger.error(f"Failed to restore from tray: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/hotkeys")
async def get_hotkeys():
    """获取已注册的快捷键"""
    if not hotkey_manager:
        raise HTTPException(status_code=503, detail="Hotkey manager not available")
    
    return JSONResponse(content={
        "hotkeys": list(hotkey_manager.hotkeys.keys()),
        "enabled": hotkey_manager.enabled
    })


@router.post("/hotkeys/register")
async def register_hotkey(request: HotkeyRequest):
    """注册全局快捷键"""
    if not hotkey_manager:
        raise HTTPException(status_code=503, detail="Hotkey manager not available")
    
    try:
        # Note: Actual hotkey implementation would need platform-specific libraries
        # like keyboard or pynput
        hotkey_manager.register(request.hotkey, lambda: logger.info(f"Hotkey triggered: {request.action}"))
        return JSONResponse(content={"success": True})
    except Exception as e:
        logger.error(f"Failed to register hotkey: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/hotkeys/{hotkey}")
async def unregister_hotkey(hotkey: str):
    """注销全局快捷键"""
    if not hotkey_manager:
        raise HTTPException(status_code=503, detail="Hotkey manager not available")
    
    try:
        hotkey_manager.unregister(hotkey)
        return JSONResponse(content={"success": True})
    except Exception as e:
        logger.error(f"Failed to unregister hotkey: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/autostart")
async def get_autostart_status():
    """获取自启动状态"""
    if not autostart_manager:
        raise HTTPException(status_code=503, detail="Auto-start manager not available")
    
    try:
        enabled = autostart_manager.is_enabled()
        return JSONResponse(content={"enabled": enabled})
    except Exception as e:
        logger.error(f"Failed to get auto-start status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/autostart")
async def set_autostart(request: AutoStartRequest):
    """启用或禁用自启动"""
    if not autostart_manager:
        raise HTTPException(status_code=503, detail="Auto-start manager not available")
    
    try:
        if request.enabled:
            success = autostart_manager.enable()
        else:
            success = autostart_manager.disable()
        
        if success:
            return JSONResponse(content={"success": True, "enabled": request.enabled})
        else:
            raise HTTPException(status_code=500, detail="Failed to update auto-start")
    except Exception as e:
        logger.error(f"Failed to set auto-start: {e}")
        raise HTTPException(status_code=500, detail=str(e))
