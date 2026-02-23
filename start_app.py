#!/usr/bin/env python3
"""CountBot 应用启动脚本"""

import os
import sys
import webbrowser
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
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# SSL 证书配置
from backend.utils.ssl_compat import ensure_ssl_certificates
ensure_ssl_certificates()


def open_browser_delayed(url: str, delay: float = 2.0) -> None:
    """延迟打开浏览器"""
    def _open():
        import time
        time.sleep(delay)
        try:
            webbrowser.open(url)
        except Exception:
            pass
    
    threading.Thread(target=_open, daemon=True).start()


def main() -> None:
    """启动应用"""
    import uvicorn
    from backend.utils.logger import setup_logger
    from backend.utils.process_manager import setup_graceful_shutdown
    from loguru import logger
    
    setup_logger()
    process_manager = setup_graceful_shutdown(logger=logger)
    
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    os.environ["HOST"] = host
    
    # 打印启动信息
    logger.info("=" * 60)
    logger.info("CountBot 启动中...")
    if host == "127.0.0.1":
        logger.info("远程访问已开启 — 监听所有网络接口")
        logger.info(f"本地访问: http://localhost:{port}")
        logger.info(f"远程访问: http://<your-ip>:{port}")
    else:
        logger.info(f"访问地址: http://localhost:{port}")
        logger.info("如需远程访问，请设置 HOST=0.0.0.0")
    logger.info("=" * 60)

    
    try:
        uvicorn.run(
            "backend.app:app",
            host=host,
            port=port,
            reload=False,
            log_level="info"
        )
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Server error: {e}")
        raise
    finally:
        process_manager.remove_pid_file()
        logger.info("Application shutdown complete")


if __name__ == "__main__":
    main()
