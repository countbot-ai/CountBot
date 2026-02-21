#!/usr/bin/env python3
"""CountBot Desktop — pywebview 桌面启动入口"""

import os
import sys
import platform
import threading
from pathlib import Path

# 项目根目录（兼容 PyInstaller 打包）
if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys._MEIPASS)
else:
    PROJECT_ROOT = Path(__file__).parent

sys.path.insert(0, str(PROJECT_ROOT))

from backend.utils.ssl_compat import ensure_ssl_certificates
ensure_ssl_certificates()

_server = None
RESOURCES_DIR = PROJECT_ROOT / "resources"


# ── 图标 ──────────────────────────────────────────────

def get_icon_path() -> str | None:
    """按平台返回图标路径: .ico(Win) / .icns(Mac) / .png(Linux)"""
    name_map = {"Windows": "countbot.ico", "Darwin": "countbot.icns"}
    icon = RESOURCES_DIR / name_map.get(platform.system(), "countbot.png")
    return str(icon) if icon.exists() else None


def _set_macos_dock_icon(path: str) -> None:
    """通过 PyObjC 设置 macOS Dock 图标"""
    try:
        from AppKit import NSApplication, NSImage
        img = NSImage.alloc().initWithContentsOfFile_(path)
        if img:
            NSApplication.sharedApplication().setApplicationIconImage_(img)
    except Exception:
        pass


def _set_windows_app_id() -> None:
    """设置 Windows AppUserModelID，使任务栏显示自定义图标"""
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "countbot.desktop.app"
        )
    except Exception:
        pass


# ── 后端服务 ──────────────────────────────────────────

def _start_backend(host: str, port: int) -> None:
    """后台线程启动 FastAPI/Uvicorn"""
    global _server
    import uvicorn
    from loguru import logger

    try:
        cfg = uvicorn.Config("backend.app:app", host=host, port=port,
                             reload=False, log_level="info")
        _server = uvicorn.Server(cfg)
        _server.run()
    except Exception as e:
        logger.error(f"后端启动失败: {e}")
        sys.exit(1)


def _shutdown() -> None:
    global _server
    if _server:
        _server.should_exit = True


def _wait_for_server(host: str, port: int, timeout: float = 15.0) -> bool:
    """轮询 /api/health 直到后端就绪"""
    import time, urllib.request
    url = f"http://{host}:{port}/api/health"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if urllib.request.urlopen(url, timeout=2).status == 200:
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def _check_frontend() -> bool:
    index = PROJECT_ROOT / "frontend" / "dist" / "index.html"
    return index.exists()


# ── 主入口 ────────────────────────────────────────────

def main():
    import webview
    from loguru import logger

    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    os.environ["HOST"] = host

    logger.info(f"CountBot Desktop 启动中… http://{host}:{port}")

    if not _check_frontend():
        logger.error("frontend/dist/index.html 不存在，无法启动")
        sys.exit(1)

    # 启动后端
    threading.Thread(target=_start_backend, args=(host, port), daemon=True).start()
    if not _wait_for_server(host, port):
        logger.error("后端启动超时")
        sys.exit(1)

    # 设置平台图标
    icon_path = get_icon_path()
    if icon_path:
        logger.info(f"图标: {icon_path}")
        if platform.system() == "Darwin":
            _set_macos_dock_icon(icon_path)
        elif platform.system() == "Windows":
            _set_windows_app_id()

    # 创建窗口
    window = webview.create_window(
        title="CountBot Desktop",
        url=f"http://{host}:{port}",
        width=960, height=680,
        min_size=(720, 480),
        resizable=True, text_select=True,
    )
    window.events.closing += lambda: _shutdown()

    start_kwargs = {"debug": os.getenv("DEBUG", "").lower() in ("1", "true")}
    if icon_path:
        start_kwargs["icon"] = icon_path
    webview.start(**start_kwargs)

    logger.info("CountBot Desktop 已退出")
    os._exit(0)


if __name__ == "__main__":
    main()
