#!/usr/bin/env python3
"""CountBot Desktop 启动入口"""

import os
import sys
import platform
import threading
from pathlib import Path

# Windows UTF-8 编码
if sys.platform == "win32":
    os.environ["PYTHONIOENCODING"] = "utf-8"
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleCP(65001)
        kernel32.SetConsoleOutputCP(65001)
    except Exception:
        pass

# 项目根目录
if getattr(sys, "frozen", False):
    # 编译版本: _internal 目录包含所有资源
    if sys.platform == "darwin":
        # macOS onedir: CountBot.app/Contents/MacOS/CountBot -> 使用 _internal
        exe_dir = Path(sys.executable).parent
        if (exe_dir / "_internal").exists():
            PROJECT_ROOT = exe_dir / "_internal"
        else:
            # BUNDLE 模式: Contents/MacOS/CountBot -> Contents/Resources/
            PROJECT_ROOT = exe_dir.parent / "Resources"
    else:
        # Windows/Linux onedir: CountBot.exe 旁边的 _internal
        exe_dir = Path(sys.executable).parent
        PROJECT_ROOT = exe_dir / "_internal" if (exe_dir / "_internal").exists() else exe_dir
else:
    PROJECT_ROOT = Path(__file__).parent

sys.path.insert(0, str(PROJECT_ROOT))

from backend.utils.ssl_compat import ensure_ssl_certificates
ensure_ssl_certificates()

_server = None
RESOURCES_DIR = PROJECT_ROOT / "resources"


def show_error_dialog(title: str, message: str) -> None:
    """显示错误对话框（macOS 需在主线程）"""
    if sys.platform == "darwin" and threading.current_thread() != threading.main_thread():
        print(f"\n{'='*60}\n错误: {title}\n{'='*60}\n{message}\n{'='*60}\n")
        return
    
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(title, message)
        root.destroy()
    except Exception:
        print(f"\n{'='*60}\n错误: {title}\n{'='*60}\n{message}\n{'='*60}\n")


def check_dependencies() -> tuple[bool, str]:
    """检查依赖"""
    missing = []
    for pkg in ["webview", "fastapi", "uvicorn", "litellm"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg if pkg != "webview" else "pywebview")
    
    if missing:
        msg = (
            f"缺少依赖: {', '.join(missing)}\n\n"
            f"安装命令:\n"
            f"pip install -r requirements.txt"
        )
        return False, msg
    return True, ""


def get_icon_path() -> str | None:
    """获取图标路径"""
    name_map = {"Windows": "countbot.ico", "Darwin": "countbot.icns"}
    icon = RESOURCES_DIR / name_map.get(platform.system(), "countbot.png")
    return str(icon) if icon.exists() else None


def _set_macos_dock_icon(path: str) -> None:
    """设置 macOS Dock 图标"""
    try:
        from AppKit import NSApplication, NSImage
        img = NSImage.alloc().initWithContentsOfFile_(path)
        if img:
            NSApplication.sharedApplication().setApplicationIconImage_(img)
    except Exception:
        pass


def _set_windows_app_id() -> None:
    """设置 Windows 任务栏图标"""
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("countbot.desktop.app")
    except Exception:
        pass


def _start_backend(host: str, port: int) -> None:
    """启动后端服务"""
    global _server
    import uvicorn
    from loguru import logger

    try:
        cfg = uvicorn.Config("backend.app:app", host=host, port=port, reload=False, log_level="info")
        _server = uvicorn.Server(cfg)
        _server.run()
    except OSError as e:
        if "Address already in use" in str(e) or "Only one usage" in str(e):
            msg = f"端口 {port} 已被占用\n\n解决方法:\n1. 关闭其他实例\n2. 修改端口: export PORT=8001"
            logger.error(msg)
            show_error_dialog("端口被占用", msg)
        else:
            logger.error(f"后端启动失败: {e}")
            show_error_dialog("启动失败", f"后端服务启动失败:\n{e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"后端启动失败: {e}")
        show_error_dialog("启动失败", f"后端服务启动失败:\n{e}")
        sys.exit(1)


def _shutdown() -> None:
    """关闭后端服务"""
    global _server
    if _server:
        _server.should_exit = True


def _wait_for_server(host: str, port: int, timeout: float = 15.0) -> bool:
    """等待后端就绪"""
    import time
    import urllib.request
    
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


def _check_frontend() -> tuple[bool, str]:
    """检查前端文件"""
    index = PROJECT_ROOT / "frontend" / "dist" / "index.html"
    if not index.exists():
        msg = f"前端文件不存在: {index}\n\n解决方法:\ncd frontend && npm install && npm run build"
        return False, msg
    return True, ""


def main():
    """主入口"""
    from loguru import logger
    
    deps_ok, deps_msg = check_dependencies()
    if not deps_ok:
        show_error_dialog("缺少依赖", deps_msg)
        sys.exit(1)
    
    import webview
    
    if platform.system() == "Windows":
        os.environ["PYWEBVIEW_GUI"] = "edgechromium"
        logger.info("使用 EdgeChromium 渲染引擎")

    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    os.environ["HOST"] = host

    logger.info(f"CountBot Desktop 启动中 http://{host}:{port}")
    
    frontend_ok, frontend_msg = _check_frontend()
    if not frontend_ok:
        logger.error(frontend_msg)
        show_error_dialog("前端文件缺失", frontend_msg)
        sys.exit(1)

    logger.info("启动后端服务...")
    threading.Thread(target=_start_backend, args=(host, port), daemon=True).start()
    
    logger.info("等待后端就绪...")
    if not _wait_for_server(host, port):
        msg = f"后端启动超时 (15秒)\n\n可能原因:\n1. 端口 {port} 被占用\n2. 防火墙阻止\n3. 资源不足"
        logger.error(msg)
        show_error_dialog("启动超时", msg)
        sys.exit(1)
    
    logger.info("后端服务就绪")

    icon_path = get_icon_path()
    if icon_path:
        logger.info(f"图标: {icon_path}")
        if platform.system() == "Darwin":
            _set_macos_dock_icon(icon_path)
        elif platform.system() == "Windows":
            _set_windows_app_id()

    try:
        logger.info("创建应用窗口...")
        window = webview.create_window(
            title="CountBot Desktop",
            url=f"http://{host}:{port}",
            width=960,
            height=680,
            min_size=(720, 480),
            resizable=True,
            text_select=True,
        )
        window.events.closing += lambda: _shutdown()

        start_kwargs = {"debug": os.getenv("DEBUG", "").lower() in ("1", "true")}
        if icon_path:
            start_kwargs["icon"] = icon_path
        
        logger.info("CountBot Desktop 启动成功")
        webview.start(**start_kwargs)
        
    except Exception as e:
        msg = f"窗口创建失败:\n{e}\n\nWindows: 安装 Edge WebView2\nMac: 系统 >= 10.13\nLinux: apt install webkit2gtk-4.0"
        logger.error(msg)
        show_error_dialog("窗口创建失败", msg)
        sys.exit(1)

    logger.info("CountBot Desktop 已退出")
    os._exit(0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n用户中断，退出...")
        sys.exit(0)
    except Exception as e:
        msg = f"程序错误:\n{e}\n\n1. 重启程序\n2. 查看日志: data/logs/\n3. 提交 Issue"
        show_error_dialog("程序错误", msg)
        import traceback
        traceback.print_exc()
        sys.exit(1)
