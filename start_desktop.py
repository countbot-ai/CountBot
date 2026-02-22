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


# ── 友好的错误提示 ──────────────────────────────────────

def show_error_dialog(title: str, message: str) -> None:
    """显示错误对话框（跨平台）"""
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()  # 隐藏主窗口
        messagebox.showerror(title, message)
        root.destroy()
    except Exception:
        # 如果 tkinter 不可用，打印到控制台
        print(f"\n{'='*60}")
        print(f"错误: {title}")
        print(f"{'='*60}")
        print(message)
        print(f"{'='*60}\n")


def check_dependencies() -> tuple[bool, str]:
    """检查关键依赖是否可用"""
    missing = []
    
    try:
        import webview
    except ImportError:
        missing.append("pywebview")
    
    try:
        import fastapi
    except ImportError:
        missing.append("fastapi")
    
    try:
        import uvicorn
    except ImportError:
        missing.append("uvicorn")
    
    try:
        import litellm
    except ImportError:
        missing.append("litellm")
    
    if missing:
        deps = ", ".join(missing)
        msg = (
            f"缺少必要的依赖包: {deps}\n\n"
            f"请运行以下命令安装:\n"
            f"pip install -r requirements.txt\n\n"
            f"或使用国内镜像:\n"
            f"pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/"
        )
        return False, msg
    
    return True, ""


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
    except OSError as e:
        if "Address already in use" in str(e) or "Only one usage" in str(e):
            error_msg = (
                f"端口 {port} 已被占用！\n\n"
                f"可能的原因:\n"
                f"1. CountBot 已经在运行中\n"
                f"2. 其他程序占用了该端口\n\n"
                f"解决方法:\n"
                f"1. 关闭其他 CountBot 实例\n"
                f"2. 修改端口: 设置环境变量 PORT=8001\n"
                f"3. 使用命令查看占用: netstat -ano | findstr {port} (Windows)\n"
                f"   或: lsof -i :{port} (Mac/Linux)"
            )
            logger.error(error_msg)
            show_error_dialog("端口被占用", error_msg)
        else:
            logger.error(f"后端启动失败: {e}")
            show_error_dialog("启动失败", f"后端服务启动失败:\n{e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"后端启动失败: {e}")
        show_error_dialog("启动失败", f"后端服务启动失败:\n{e}\n\n请检查日志文件获取详细信息。")
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


def _check_frontend() -> tuple[bool, str]:
    """检查前端文件是否存在"""
    index = PROJECT_ROOT / "frontend" / "dist" / "index.html"
    if not index.exists():
        msg = (
            f"前端文件不存在！\n\n"
            f"缺少文件: {index}\n\n"
            f"可能的原因:\n"
            f"1. 首次运行，前端尚未构建\n"
            f"2. 文件被误删除\n\n"
            f"解决方法:\n"
            f"1. 如果是源码运行，请先构建前端:\n"
            f"   cd frontend && npm install && npm run build\n"
            f"2. 如果是下载的桌面版，请重新下载完整包\n"
            f"3. 检查解压是否完整"
        )
        return False, msg
    return True, ""


# ── 主入口 ────────────────────────────────────────────

def main():
    from loguru import logger
    
    # 检查依赖
    deps_ok, deps_msg = check_dependencies()
    if not deps_ok:
        show_error_dialog("缺少依赖", deps_msg)
        sys.exit(1)
    
    import webview
    
    # Windows 优先使用 EdgeChromium 后端，避免 pythonnet 依赖问题
    if platform.system() == "Windows":
        os.environ["PYWEBVIEW_GUI"] = "edgechromium"
        logger.info("Windows 平台: 使用 EdgeChromium 渲染引擎")

    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    os.environ["HOST"] = host

    logger.info(f"CountBot Desktop 启动中… http://{host}:{port}")
    
    # 检查前端文件
    frontend_ok, frontend_msg = _check_frontend()
    if not frontend_ok:
        logger.error(frontend_msg)
        show_error_dialog("前端文件缺失", frontend_msg)
        sys.exit(1)

    # 启动后端
    logger.info("正在启动后端服务...")
    threading.Thread(target=_start_backend, args=(host, port), daemon=True).start()
    
    logger.info("等待后端服务就绪...")
    if not _wait_for_server(host, port):
        error_msg = (
            f"后端服务启动超时（15秒）\n\n"
            f"可能的原因:\n"
            f"1. 端口 {port} 被占用\n"
            f"2. 防火墙阻止了连接\n"
            f"3. 系统资源不足\n\n"
            f"建议:\n"
            f"1. 检查是否有其他 CountBot 实例在运行\n"
            f"2. 尝试更换端口: 设置环境变量 PORT=8001\n"
            f"3. 查看日志文件: data/logs/CountBot_*.log"
        )
        logger.error(error_msg)
        show_error_dialog("启动超时", error_msg)
        sys.exit(1)
    
    logger.info("✓ 后端服务已就绪")

    # 设置平台图标
    icon_path = get_icon_path()
    if icon_path:
        logger.info(f"图标: {icon_path}")
        if platform.system() == "Darwin":
            _set_macos_dock_icon(icon_path)
        elif platform.system() == "Windows":
            _set_windows_app_id()

    # 创建窗口
    try:
        logger.info("正在创建应用窗口...")
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
        
        logger.info("✓ CountBot Desktop 启动成功")
        logger.info(f"访问地址: http://{host}:{port}")
        webview.start(**start_kwargs)
        
    except Exception as e:
        error_msg = (
            f"窗口创建失败:\n{e}\n\n"
            f"可能的原因:\n"
            f"1. 缺少必要的系统组件\n"
            f"2. 显示驱动问题\n\n"
            f"Windows 用户:\n"
            f"- 确保已安装 Edge WebView2 运行时\n"
            f"- 下载地址: https://go.microsoft.com/fwlink/p/?LinkId=2124703\n\n"
            f"Mac 用户:\n"
            f"- 确保系统版本 >= 10.13\n\n"
            f"Linux 用户:\n"
            f"- 确保已安装 WebKit2GTK: sudo apt install webkit2gtk-4.0"
        )
        logger.error(error_msg)
        show_error_dialog("窗口创建失败", error_msg)
        sys.exit(1)

    logger.info("CountBot Desktop 已退出")
    os._exit(0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n用户中断，正在退出...")
        sys.exit(0)
    except Exception as e:
        error_msg = (
            f"程序发生未预期的错误:\n{e}\n\n"
            f"请尝试以下操作:\n"
            f"1. 重新启动程序\n"
            f"2. 检查日志文件: data/logs/CountBot_*.log\n"
            f"3. 如果问题持续，请在 GitHub 提交 Issue:\n"
            f"   https://github.com/countbot-ai/CountBot/issues"
        )
        show_error_dialog("程序错误", error_msg)
        import traceback
        traceback.print_exc()
        sys.exit(1)
