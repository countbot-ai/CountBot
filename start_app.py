#!/usr/bin/env python3
"""
CountBot 应用启动脚本
生产模式启动，自动打开浏览器
支持本地网络 IP 监控，类似 Vue3 启动模式
"""

import os
import sys
import webbrowser
import threading
from pathlib import Path
from backend.utils.network import get_local_ips

# 添加项目根目录到 Python 路径
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
    
    # 获取本地 IP 地址
    local_ips = get_local_ips()
    
    # 打印启动信息
    logger.info("=" * 60)
    logger.info("CountBot 启动中...")
    logger.info("=" * 60)
    
    try:
        # 启动服务器前显示"服务器启动完成"消息和访问地址
        # 这样地址会在视觉上显示在启动完成之后
        logger.info("服务器启动完成！")
        logger.info("=" * 60)
        
        # 显示本地访问地址
        logger.info(f"Local:   http://localhost:{port}")
        
        # 显示网络访问地址（如果监听了所有接口）
        if host in ["0.0.0.0", "::"]:
            if local_ips:
                for ip in local_ips:
                    logger.info(f"Network: http://{ip}:{port}")
            else:
                logger.info("Network: (无法检测到本地 IP 地址)")
                logger.info(f"提示: 请检查网络连接或手动访问 http://<your-ip>:{port}")
        else:
            logger.info(f"Network: http://{host}:{port}")
            logger.info("提示: 如需从其他设备访问，请设置 HOST=0.0.0.0")
        
        logger.info("-" * 60)
        logger.info("按下 Ctrl+C 停止服务器")
        logger.info("=" * 60)
        
        # 延迟打开浏览器
        open_browser_delayed(f"http://localhost:{port}")
        
        # 启动服务器
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
