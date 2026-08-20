"""MCP API Error Handlers - 统一的错误处理中间件

提供统一的异常处理和错误响应格式。
"""

from typing import Callable
from functools import wraps

from fastapi import HTTPException
from loguru import logger

from backend.modules.mcp.exceptions import (
    McpError,
    McpConnectionError,
    McpTimeoutError,
    McpValidationError,
    McpServerNotFoundError,
    McpImportError,
)


def handle_mcp_errors(func: Callable):
    """MCP错误处理装饰器

    统一处理MCP相关异常，转换为标准的HTTP响应。
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except McpValidationError as e:
            logger.warning(f"MCP validation error: {e.message}")
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "ValidationError",
                    "message": e.message,
                    "details": e.details,
                }
            )
        except McpServerNotFoundError as e:
            logger.warning(f"MCP server not found: {e.message}")
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "ServerNotFound",
                    "message": e.message,
                    "details": e.details,
                }
            )
        except McpTimeoutError as e:
            logger.error(f"MCP timeout: {e.message}")
            raise HTTPException(
                status_code=504,
                detail={
                    "error": "TimeoutError",
                    "message": e.message,
                    "details": e.details,
                }
            )
        except McpConnectionError as e:
            logger.error(f"MCP connection error: {e.message}")
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "ConnectionError",
                    "message": e.message,
                    "details": e.details,
                }
            )
        except McpImportError as e:
            logger.error(f"MCP import error: {e.message}")
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "ImportError",
                    "message": e.message,
                    "details": e.details,
                }
            )
        except McpError as e:
            logger.error(f"MCP error: {e.message}")
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "McpError",
                    "message": e.message,
                    "details": e.details,
                }
            )
        except HTTPException:
            # 重新抛出已有的HTTP异常
            raise
        except Exception as e:
            logger.exception(f"Unexpected error in MCP API: {e}")
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "InternalServerError",
                    "message": f"An unexpected error occurred: {str(e)}",
                    "details": {},
                }
            )

    return wrapper


def success_response(data: dict = None, message: str = None) -> dict:
    """构造成功响应

    Args:
        data: 响应数据
        message: 成功消息

    Returns:
        标准化的成功响应
    """
    response = {"success": True}
    if message:
        response["message"] = message
    if data:
        response.update(data)
    return response


def error_response(message: str, details: dict = None) -> dict:
    """构造错误响应

    Args:
        message: 错误消息
        details: 错误详情

    Returns:
        标准化的错误响应
    """
    response = {
        "success": False,
        "message": message,
    }
    if details:
        response["details"] = details
    return response
