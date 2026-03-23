"""日志配置"""

import io
import logging
import sys
from copy import deepcopy
from pathlib import Path

from loguru import logger
from uvicorn.config import LOGGING_CONFIG as UVICORN_LOGGING_CONFIG

# 使用统一路径管理
from backend.utils.paths import DATA_DIR

# 日志目录
LOG_DIR = DATA_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

_KNOWN_APP_EXACT_PATHS = {
    "/",
    "/favicon.ico",
    "/login",
    "/robots.txt",
}

_KNOWN_APP_PREFIXES = (
    "/api/",
    "/assets/",
    "/setup/",
    "/ws/",
)


def _is_local_client_addr(client_addr: object) -> bool:
    client = str(client_addr or "").strip().lower()
    return client.startswith(("127.0.0.1:", "::1:", "[::1]:", "localhost:"))


class SuppressNoisyAccessFilter(logging.Filter):
    """Suppress noisy access logs for scans and expected remote 401 responses."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = getattr(record, "args", ())
        if not isinstance(args, tuple) or len(args) != 5:
            return True

        client_addr, _, full_path, _, status_code = args
        try:
            normalized_status_code = int(status_code)
        except (TypeError, ValueError):
            return True

        if normalized_status_code == 401 and not _is_local_client_addr(client_addr):
            return False

        if normalized_status_code != 404:
            return True

        path = str(full_path).split("?", 1)[0]
        if path in _KNOWN_APP_EXACT_PATHS:
            return True

        if any(path.startswith(prefix) for prefix in _KNOWN_APP_PREFIXES):
            return True

        return False


def build_uvicorn_log_config() -> dict:
    """Build a uvicorn log config with scanner-noise access log filtering."""
    log_config = deepcopy(UVICORN_LOGGING_CONFIG)
    log_config.setdefault("filters", {})
    log_config["filters"]["suppress_noisy_access"] = {
        "()": "backend.utils.logger.SuppressNoisyAccessFilter",
    }
    log_config["handlers"]["access"]["filters"] = ["suppress_noisy_access"]
    return log_config


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
