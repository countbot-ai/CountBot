"""WebSocket MCP状态广播

提供WebSocket会话的MCP状态变更通知功能。
"""

from typing import Set
from loguru import logger
from fastapi import WebSocket


# 全局活跃WebSocket连接集合
_active_websockets: Set[WebSocket] = set()


def register_websocket(websocket: WebSocket) -> None:
    """注册活跃的WebSocket连接"""
    _active_websockets.add(websocket)
    logger.debug(f"WebSocket registered, total: {len(_active_websockets)}")


def unregister_websocket(websocket: WebSocket) -> None:
    """注销WebSocket连接"""
    _active_websockets.discard(websocket)
    logger.debug(f"WebSocket unregistered, total: {len(_active_websockets)}")


async def broadcast_mcp_status_change(connected: bool) -> None:
    """广播MCP状态变更到所有活跃的WebSocket连接

    Args:
        connected: MCP是否已连接
    """
    if not _active_websockets:
        return

    message = {
        "type": "mcp_status_change",
        "connected": connected,
        "message": "MCP service connected" if connected else "MCP service disconnected",
    }

    disconnected = []
    for ws in _active_websockets:
        try:
            await ws.send_json(message)
        except Exception as e:
            logger.debug(f"Failed to send MCP status to WebSocket: {e}")
            disconnected.append(ws)

    # 清理已断开的连接
    for ws in disconnected:
        _active_websockets.discard(ws)

    logger.info(f"Broadcasted MCP status change (connected={connected}) to {len(_active_websockets)} clients")


def get_active_websocket_count() -> int:
    """获取活跃WebSocket连接数"""
    return len(_active_websockets)
