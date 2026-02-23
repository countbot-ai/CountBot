#!/usr/bin/env python3
"""
CountBot 应用启动脚本
开发模式启动，支持热重载
"""

import os
import sys
from pathlib import Path

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
    
    logger.info("=" * 60)
    logger.info("CountBot 开发模式启动中...")
    logger.info(f"访问地址: http://localhost:{port}")
    logger.info("热重载已启用")
    logger.info("=" * 60)
    
    # 不自动打开浏览器，用户可以手动访问
    
    # 启动服务器（开发模式）
    uvicorn.run(
        "backend.app:app",
        host=host,
        port=port,
        reload=True,  # 开发模式启用热重载
        reload_dirs=["backend"],  # 监控 backend 目录
        log_level="debug"
    )


if __name__ == "__main__":
    main()
