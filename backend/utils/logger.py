"""日志配置"""

import sys
from pathlib import Path

from loguru import logger

# 日志目录
LOG_DIR = Path(__file__).parent.parent.parent / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


def setup_logger() -> None:
    """配置日志系统"""
    # 移除默认处理器
    logger.remove()

    # 控制台输出（INFO 级别）- 简化格式，不显示模块路径
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO",
        colorize=True,
        filter=lambda record: record["level"].name in ["INFO", "WARNING", "ERROR", "CRITICAL"]
    )

    # 文件输出（DEBUG 级别）
    logger.add(
        LOG_DIR / "CountBot_{time:YYYY-MM-DD}.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="DEBUG",
        rotation="00:00",
        retention="7 days",
        compression="zip",
        encoding="utf-8",
    )

    # 错误日志单独记录
    logger.add(
        LOG_DIR / "error_{time:YYYY-MM-DD}.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="ERROR",
        rotation="00:00",
        retention="30 days",
        compression="zip",
        encoding="utf-8",
    )

    logger.info("日志系统初始化完成")
