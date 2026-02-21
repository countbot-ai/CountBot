#!/usr/bin/env python3
"""
CountBot 应用启动脚本
生产模式启动，自动打开浏览器
"""

import os
import sys
import webbrowser
import threading
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 跨平台 SSL 兼容性处理（macOS 需要额外配置证书）
from backend.utils.ssl_compat import ensure_ssl_certificates
ensure_ssl_certificates()


def open_browser_delayed(url: str, delay: float = 2.0) -> None:
    """
    延迟打开浏览器
    
    Args:
        url: 要打开的 URL
        delay: 延迟时间（秒）
    """
    def _open():
        import time
        time.sleep(delay)
        try:
            webbrowser.open(url)
        except Exception:
            pass  # 静默失败，不影响服务器启动
    
    threading.Thread(target=_open, daemon=True).start()


def main() -> None:
    """启动应用"""
    import uvicorn
    from backend.utils.logger import setup_logger
    from backend.utils.process_manager import setup_graceful_shutdown
    from loguru import logger
    
    # 初始化日志系统
    setup_logger()
    
    # 设置优雅关闭机制（包括清理孤儿进程、写入 PID、注册信号处理器）
    process_manager = setup_graceful_shutdown(logger=logger)
    
    # 配置
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    
    # 确保环境变量与实际绑定地址一致（供 app.py 读取）
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
        # 启动服务器
        uvicorn.run(
            "backend.app:app",
            host=host,
            port=port,
            reload=False,  # 生产模式不启用热重载
            log_level="info"
        )
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Server error: {e}")
        raise
    finally:
        # 确保清理 PID 文件
        process_manager.remove_pid_file()
        logger.info("Application shutdown complete")


if __name__ == "__main__":
    main()
