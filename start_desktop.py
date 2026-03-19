#!/usr/bin/env python3
"""CountBot Desktop 启动入口"""

import http.client
import os
import platform
import sys
import threading
import time
from pathlib import Path


if sys.platform == "win32":
    os.environ["PYTHONIOENCODING"] = "utf-8"
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleCP(65001)
        kernel32.SetConsoleOutputCP(65001)
    except Exception:
        pass


if getattr(sys, "frozen", False):
    if hasattr(sys, "_MEIPASS"):
        PROJECT_ROOT = Path(sys._MEIPASS)
    else:
        exe_dir = Path(sys.executable).parent
        if sys.platform == "darwin":
            if (exe_dir / "_internal").exists():
                PROJECT_ROOT = exe_dir / "_internal"
            else:
                PROJECT_ROOT = exe_dir.parent / "Resources"
        else:
            PROJECT_ROOT = (
                exe_dir / "_internal" if (exe_dir / "_internal").exists() else exe_dir
            )
else:
    PROJECT_ROOT = Path(__file__).parent

sys.path.insert(0, str(PROJECT_ROOT))


_server = None
_backend_error: str | None = None
RESOURCES_DIR = PROJECT_ROOT / "resources"


def show_error_dialog(title: str, message: str) -> None:
    """显示错误对话框。"""
    if sys.platform == "darwin" and threading.current_thread() != threading.main_thread():
        print(f"\n{'=' * 60}\n错误: {title}\n{'=' * 60}\n{message}\n{'=' * 60}\n")
        return

    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(title, message)
        root.destroy()
    except Exception:
        print(f"\n{'=' * 60}\n错误: {title}\n{'=' * 60}\n{message}\n{'=' * 60}\n")


def check_dependencies() -> tuple[bool, str]:
    """检查桌面端运行依赖。"""
    missing = []
    for pkg in ["webview", "fastapi", "uvicorn"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg if pkg != "webview" else "pywebview")

    if missing:
        msg = (
            f"缺少依赖: {', '.join(missing)}\n\n"
            "安装命令:\n"
            "pip install -r requirements.txt"
        )
        return False, msg
    return True, ""


def get_icon_path() -> str | None:
    """获取图标路径。"""
    name_map = {"Windows": "countbot.ico", "Darwin": "countbot.icns"}
    icon = RESOURCES_DIR / name_map.get(platform.system(), "countbot.png")
    return str(icon) if icon.exists() else None


def _set_macos_dock_icon(path: str) -> None:
    """设置 macOS Dock 图标。"""
    try:
        from AppKit import NSApplication, NSImage

        img = NSImage.alloc().initWithContentsOfFile_(path)
        if img:
            NSApplication.sharedApplication().setApplicationIconImage_(img)
    except Exception:
        pass


def _set_windows_app_id() -> None:
    """设置 Windows 任务栏 AppUserModelID。"""
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("countbot.desktop.app")
    except Exception:
        pass


def _start_backend(host: str, port: int) -> None:
    """在后台线程启动 FastAPI 服务。"""
    global _server, _backend_error

    import uvicorn
    from loguru import logger

    try:
        cfg = uvicorn.Config("backend.app:app", host=host, port=port, reload=False, log_level="info")
        _server = uvicorn.Server(cfg)
        _server.run()
    except OSError as exc:
        if "Address already in use" in str(exc) or "Only one usage" in str(exc):
            _backend_error = (
                f"端口 {port} 已被占用\n\n"
                "解决方法:\n"
                "1. 关闭其他实例\n"
                "2. 修改端口: set PORT=8001"
            )
        else:
            _backend_error = f"后端服务启动失败:\n{exc}"
        logger.exception(_backend_error)
    except Exception as exc:
        _backend_error = f"后端服务启动失败:\n{exc}"
        logger.exception(_backend_error)


def _shutdown() -> None:
    """关闭后端服务。"""
    global _server
    if _server:
        _server.should_exit = True


def _wait_for_server(host: str, port: int, timeout: float = 15.0) -> tuple[bool, str]:
    """等待后端就绪，并返回最后一次探活错误。"""
    deadline = time.time() + timeout
    last_error = ""

    while time.time() < deadline:
        if _backend_error:
            return False, _backend_error

        conn = None
        try:
            conn = http.client.HTTPConnection(host, port, timeout=2)
            conn.request("GET", "/api/health")
            response = conn.getresponse()
            if response.status == 200:
                return True, ""
            last_error = f"/api/health 返回 HTTP {response.status}"
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

        time.sleep(0.3)

    return False, last_error


def _check_frontend() -> tuple[bool, str]:
    """检查前端静态文件是否存在。"""
    index = PROJECT_ROOT / "frontend" / "dist" / "index.html"
    if not index.exists():
        msg = (
            f"前端文件不存在: {index}\n\n"
            "解决方法:\n"
            "cd frontend && npm install && npm run build"
        )
        return False, msg
    return True, ""


def main() -> None:
    """桌面端主入口。"""
    global _backend_error

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
    startup_timeout = float(
        os.getenv("BACKEND_STARTUP_TIMEOUT", "30" if getattr(sys, "frozen", False) else "15")
    )
    os.environ["HOST"] = host
    _backend_error = None

    logger.info(f"CountBot Desktop 启动中: http://{host}:{port}")

    frontend_ok, frontend_msg = _check_frontend()
    if not frontend_ok:
        logger.error(frontend_msg)
        show_error_dialog("前端文件缺失", frontend_msg)
        sys.exit(1)

    logger.info("启动后端服务...")
    threading.Thread(target=_start_backend, args=(host, port), daemon=True).start()

    logger.info("等待后端就绪...")
    server_ready, probe_error = _wait_for_server(host, port, timeout=startup_timeout)
    if not server_ready:
        details = f"\n\n最后探活错误: {probe_error}" if probe_error else ""
        msg = (
            f"后端启动超时 ({int(startup_timeout)}秒){details}\n\n"
            "可能原因:\n"
            f"1. 端口 {port} 被占用\n"
            "2. 防火墙阻止\n"
            "3. 资源不足"
        )
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
            min_size=(220, 480),
            resizable=True,
            text_select=True,
        )
        window.events.closing += lambda: _shutdown()

        start_kwargs = {"debug": os.getenv("DEBUG", "").lower() in ("1", "true")}
        if icon_path:
            start_kwargs["icon"] = icon_path

        logger.info("CountBot Desktop 启动成功")
        webview.start(**start_kwargs)
    except Exception as exc:
        msg = (
            f"窗口创建失败:\n{exc}\n\n"
            "Windows: 安装 Edge WebView2\n"
            "Mac: 系统 >= 10.13\n"
            "Linux: apt install webkit2gtk-4.0"
        )
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
    except Exception as exc:
        msg = (
            f"程序错误:\n{exc}\n\n"
            "1. 重启程序\n"
            "2. 查看日志: data/logs/\n"
            "3. 提交 Issue"
        )
        show_error_dialog("程序错误", msg)
        import traceback

        traceback.print_exc()
        sys.exit(1)
