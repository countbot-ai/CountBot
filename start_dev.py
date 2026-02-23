#!/usr/bin/env python3
"""
CountBot 应用启动脚本
开发模式启动，支持热重载
支持本地网络 IP 监控，类似 Vue3 启动模式
"""

import os
import sys
from pathlib import Path
from backend.utils.network import get_local_ips

# Windows 平台强制 UTF-8 编码，避免 GBK 编码错误
if sys.platform == "win32":
    # Python 3.7+ 支持
    os.environ["PYTHONIOENCODING"] = "utf-8"
    # 设置控制台代码页为 UTF-8
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleCP(65001)
        kernel32.SetConsoleOutputCP(65001)
    except Exception:
        pass

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def main():
    """启动应用（开发模式）"""
    import uvicorn
    from loguru import logger
    
    # 配置
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    
    # 获取本地 IP 地址
    local_ips = get_local_ips()
    
    # 打印启动信息
    logger.info("=" * 60)
    logger.info("CountBot 开发模式启动中...")
    logger.info("=" * 60)
    
    try:
        # 启动服务器前显示"服务器启动完成"消息和访问地址
        logger.info("服务器启动完成！")
        logger.info("=" * 60)
        
        # 显示本地访问地址
        logger.info(f"Local:   http://localhost:{port}")
        
        # 显示网络访问地址（如果监听了所有接口或用户明确设置了 0.0.0.0）
        if host in ["0.0.0.0", "::"]:
            if local_ips:
                for ip in local_ips:
                    logger.info(f"Network: http://{ip}:{port}")
            else:
                logger.info("Network: (无法检测到本地 IP 地址)")
                logger.info(f"提示: 请检查网络连接或手动访问 http://<your-ip>:{port}")
        else:
            # 即使监听 127.0.0.1，也显示可用的网络 IP 供参考
            if local_ips:
                logger.info(f"Network: http://{host}:{port}")
                logger.info("提示: 如需从其他设备访问，请设置 HOST=0.0.0.0")
                logger.info(f"可用网络 IP: {', '.join(local_ips)}")
            else:
                logger.info(f"Network: http://{host}:{port}")
                logger.info("提示: 如需从其他设备访问，请设置 HOST=0.0.0.0")
        
        logger.info("-" * 60)
        logger.info("热重载已启用 - 文件更改将自动重启")
        logger.info("按下 Ctrl+C 停止服务器")
        logger.info("=" * 60)
        
        # 启动服务器（开发模式）
        uvicorn.run(
            "backend.app:app",
            host=host,
            port=port,
            reload=True,  # 开发模式启用热重载
            reload_dirs=["backend"],  # 监控 backend 目录
            log_level="debug"
        )
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Server error: {e}")
        raise
    finally:
        logger.info("Application shutdown complete")


if __name__ == "__main__":
    main()
