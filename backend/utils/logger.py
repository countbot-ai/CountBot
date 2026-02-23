"""日志配置"""

import sys
import io
from pathlib import Path

from loguru import logger

# 使用统一路径管理
from backend.utils.paths import DATA_DIR

# 日志目录
LOG_DIR = DATA_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


def setup_logger() -> None:
    """配置日志系统"""
    # Windows UTF-8 编码
    if sys.platform == "win32":
        if not isinstance(sys.stderr, io.TextIOWrapper) or sys.stderr.encoding.lower() != "utf-8":
            try:
                sys.stderr = io.TextIOWrapper(
                    sys.stderr.buffer,
                    encoding="utf-8",
                    errors="replace",
                    line_buffering=True
                )
            except Exception:
                pass
    
    logger.remove()

    # 控制台输出
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO",
        colorize=True,
        filter=lambda record: record["level"].name in ["INFO", "WARNING", "ERROR", "CRITICAL"]
    )

    # 文件输出
    logger.add(
        LOG_DIR / "CountBot_{time:YYYY-MM-DD}.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="DEBUG",
        rotation="00:00",
        retention="7 days",
        compression="zip",
    )

    # 错误日志单独记录
    logger.add(
        LOG_DIR / "error_{time:YYYY-MM-DD}.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="ERROR",
        rotation="00:00",
        retention="30 days",
        compression="zip",
    )

    logger.info("日志系统初始化完成")
