"""WebSocket 连接处理

实现 WebSocket 连接管理，支持：
- 客户端连接/断开管理
- 消息路由和处理
- 流式响应推送
- 工具调用通知
- 错误处理和重连
"""

import asyncio
import json
import uuid
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect, status
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, ValidationError

# 全局取消令牌管理器
from backend.modules.agent.task_manager import CancellationToken

_session_cancel_tokens: dict[str, CancellationToken] = {}


def get_cancel_token(session_id: str) -> CancellationToken:
    """获取或创建会话的取消令牌"""
    # 如果已存在且已取消，先清理
    if session_id in _session_cancel_tokens:
        old_token = _session_cancel_tokens[session_id]
        if old_token.is_cancelled:
            logger.debug(f"Cleaning up cancelled token for session {session_id}")
            del _session_cancel_tokens[session_id]
    
    # 创建新的取消令牌
    if session_id not in _session_cancel_tokens:
        _session_cancel_tokens[session_id] = CancellationToken()
        logger.debug(f"Created new cancel token for session {session_id}")
    
    return _session_cancel_tokens[session_id]


def cancel_session(session_id: str) -> bool:
    """取消会话的处理"""
    if session_id in _session_cancel_tokens:
        _session_cancel_tokens[session_id].cancel()
        logger.info(f"Cancelled session: {session_id}")
        return True
    return False


def cleanup_cancel_token(session_id: str):
    """清理会话的取消令牌"""
    if session_id in _session_cancel_tokens:
        del _session_cancel_tokens[session_id]


# ============================================================================
# Message Models
# ============================================================================


class ClientMessage(BaseModel):
    """客户端发送的消息"""

    type: str = Field(..., description="消息类型")
    session_id: str = Field(..., alias="sessionId", description="会话 ID")
    content: str | None = Field(None, description="消息内容（ping 消息可选）")


class ServerMessage(BaseModel):
    """服务器发送的消息基类"""

    type: str = Field(..., description="消息类型")

    def to_json(self) -> str:
        """转换为 JSON 字符串"""
        return self.model_dump_json(by_alias=True)


class MessageChunk(ServerMessage):
    """消息块（流式响应）"""

    type: str = Field(default="message_chunk", description="消息类型")
    content: str = Field(..., description="消息内容")


class ToolCall(ServerMessage):
    """工具调用通知"""

    model_config = ConfigDict(populate_by_name=True)

    type: str = Field(default="tool_call", description="消息类型")
    tool: str = Field(..., description="工具名称")
    arguments: dict[str, Any] = Field(..., description="工具参数")
    message_id: int | None = Field(None, alias="messageId", description="关联的消息ID")


class ToolResult(ServerMessage):
    """工具执行结果"""

    model_config = ConfigDict(populate_by_name=True)

    type: str = Field(default="tool_result", description="消息类型")
    tool: str = Field(..., description="工具名称")
    result: str = Field(..., description="执行结果")
    message_id: int | None = Field(None, alias="messageId", description="关联的消息ID")
    duration: float | None = Field(None, description="执行耗时（毫秒）")


class MessageComplete(ServerMessage):
    """消息完成通知"""

    model_config = ConfigDict(populate_by_name=True)

    type: str = Field(default="message_complete", description="消息类型")
    message_id: str = Field(..., alias="messageId", description="消息 ID")


class ErrorMessage(ServerMessage):
    """错误消息"""

    type: str = Field(default="error", description="消息类型")
    message: str = Field(..., description="错误描述")
    code: str | None = Field(None, description="错误代码")


# ============================================================================
# Connection Manager
# ============================================================================


class ConnectionManager:
    """WebSocket 连接管理器

    管理所有活跃的 WebSocket 连接，支持：
    - 连接注册和注销
    - 消息广播
    - 会话级别的消息推送
    """

    def __init__(self):
        """初始化连接管理器"""
        # 存储所有活跃连接: {connection_id: websocket}
        self._connections: dict[str, WebSocket] = {}

        # 存储会话到连接的映射: {session_id: set(connection_id)}
        self._session_connections: dict[str, set[str]] = {}

        # 连接锁，防止并发修改
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, connection_id: str | None = None) -> str:
        """注册新连接

        Args:
            websocket: WebSocket 连接
            connection_id: 连接 ID（可选，不提供则自动生成）

        Returns:
            str: 连接 ID
        """
        if connection_id is None:
            connection_id = str(uuid.uuid4())

        async with self._lock:
            await websocket.accept()
            self._connections[connection_id] = websocket
            logger.info(f"WebSocket 连接已建立: {connection_id}")

        return connection_id

    async def disconnect(self, connection_id: str):
        """注销连接

        Args:
            connection_id: 连接 ID
        """
        async with self._lock:
            # 从所有会话中移除此连接
            for session_id, conn_ids in list(self._session_connections.items()):
                if connection_id in conn_ids:
                    conn_ids.discard(connection_id)
                    if not conn_ids:
                        del self._session_connections[session_id]

            # 移除连接
            if connection_id in self._connections:
                del self._connections[connection_id]
                logger.info(f"WebSocket 连接已断开: {connection_id}")

    async def bind_session(self, connection_id: str, session_id: str):
        """绑定连接到会话

        Args:
            connection_id: 连接 ID
            session_id: 会话 ID
        """
        async with self._lock:
            if session_id not in self._session_connections:
                self._session_connections[session_id] = set()
            self._session_connections[session_id].add(connection_id)
            logger.debug(f"连接 {connection_id} 绑定到会话 {session_id}")

    async def send_message(self, connection_id: str, message: ServerMessage) -> bool:
        """发送消息到指定连接

        Args:
            connection_id: 连接 ID
            message: 服务器消息

        Returns:
            bool: 是否发送成功
        """
        websocket = self._connections.get(connection_id)
        if websocket is None:
            logger.warning(f"连接不存在: {connection_id}")
            return False

        try:
            await websocket.send_text(message.to_json())
            return True
        except Exception as e:
            logger.error(f"发送消息失败 (连接 {connection_id}): {e}")
            await self.disconnect(connection_id)
            return False

    async def send_to_session(self, session_id: str, message: ServerMessage) -> int:
        """发送消息到会话的所有连接

        Args:
            session_id: 会话 ID
            message: 服务器消息

        Returns:
            int: 成功发送的连接数
        """
        connection_ids = self._session_connections.get(session_id, set()).copy()
        if not connection_ids:
            logger.debug(f"会话 {session_id} 没有活跃连接")
            return 0

        success_count = 0
        for connection_id in connection_ids:
            if await self.send_message(connection_id, message):
                success_count += 1

        return success_count

    async def broadcast(self, message: ServerMessage) -> int:
        """广播消息到所有连接

        Args:
            message: 服务器消息

        Returns:
            int: 成功发送的连接数
        """
        connection_ids = list(self._connections.keys())
        success_count = 0

        for connection_id in connection_ids:
            if await self.send_message(connection_id, message):
                success_count += 1

        return success_count

    def get_connection_count(self) -> int:
        """获取活跃连接数

        Returns:
            int: 连接数
        """
        return len(self._connections)

    def get_session_connection_count(self, session_id: str) -> int:
        """获取会话的连接数

        Args:
            session_id: 会话 ID

        Returns:
            int: 连接数
        """
        return len(self._session_connections.get(session_id, set()))


# ============================================================================
# Global Connection Manager Instance
# ============================================================================

# 全局连接管理器实例
connection_manager = ConnectionManager()


# ============================================================================
# WebSocket Handler
# ============================================================================


async def handle_websocket(websocket: WebSocket, agent_loop=None):
    """处理 WebSocket 连接

    这是 WebSocket 端点的主处理函数，负责：
    1. 接受连接
    2. 处理客户端消息
    3. 管理连接生命周期
    4. 错误处理

    Args:
        websocket: WebSocket 连接
        agent_loop: Agent 循环实例（可选，用于事件处理）
    """
    connection_id = None

    try:
        # 建立连接
        connection_id = await connection_manager.connect(websocket)

        # 发送连接成功消息
        await connection_manager.send_message(
            connection_id,
            ServerMessage(type="connected"),
        )

        # 如果提供了 agent_loop，使用事件循环处理
        if agent_loop:
            from backend.ws.events import websocket_event_loop
            await websocket_event_loop(websocket, connection_id, agent_loop)
        else:
            # 简单的消息处理循环（用于测试）
            while True:
                try:
                    # 接收客户端消息
                    data = await websocket.receive_text()

                    # 解析消息
                    try:
                        message_dict = json.loads(data)
                        client_message = ClientMessage(**message_dict)
                    except (json.JSONDecodeError, ValidationError) as e:
                        logger.warning(f"无效的客户端消息: {e}")
                        await connection_manager.send_message(
                            connection_id,
                            ErrorMessage(
                                message="Invalid message format",
                                code="INVALID_MESSAGE",
                            ),
                        )
                        continue

                    # 绑定会话
                    await connection_manager.bind_session(
                        connection_id, client_message.session_id
                    )

                    # 处理消息（这里只是记录，实际处理逻辑在事件处理器中）
                    content_preview = (client_message.content[:50] if client_message.content else "(empty)")
                    logger.info(
                        f"收到消息 (连接 {connection_id}, 会话 {client_message.session_id}): "
                        f"{content_preview}..."
                    )

                    # 发送确认消息
                    await connection_manager.send_message(
                        connection_id,
                        ServerMessage(type="message_received"),
                    )

                except WebSocketDisconnect:
                    logger.info(f"客户端主动断开连接: {connection_id}")
                    break
                except Exception as e:
                    logger.exception(f"处理消息时出错: {e}")
                    await connection_manager.send_message(
                        connection_id,
                        ErrorMessage(
                            message=f"Internal error: {str(e)}",
                            code="INTERNAL_ERROR",
                        ),
                    )

    except Exception as e:
        logger.exception(f"WebSocket 连接错误: {e}")
    finally:
        # 清理连接
        if connection_id:
            await connection_manager.disconnect(connection_id)


# ============================================================================
# Helper Functions
# ============================================================================


async def send_message_chunk(session_id: str, content: str) -> int:
    """发送消息块到会话

    Args:
        session_id: 会话 ID
        content: 消息内容

    Returns:
        int: 成功发送的连接数
    """
    return await connection_manager.send_to_session(
        session_id, MessageChunk(content=content)
    )


async def send_tool_call(session_id: str, tool: str, arguments: dict[str, Any], message_id: int | None = None) -> int:
    """发送工具调用通知到会话

    Args:
        session_id: 会话 ID
        tool: 工具名称
        arguments: 工具参数
        message_id: 关联的消息ID

    Returns:
        int: 成功发送的连接数
    """
    return await connection_manager.send_to_session(
        session_id, ToolCall(tool=tool, arguments=arguments, message_id=message_id)
    )


async def send_tool_result(session_id: str, tool: str, result: str, message_id: int | None = None, duration: float | None = None) -> int:
    """发送工具执行结果到会话

    Args:
        session_id: 会话 ID
        tool: 工具名称
        result: 执行结果
        message_id: 关联的消息ID
        duration: 执行耗时（毫秒）

    Returns:
        int: 成功发送的连接数
    """
    return await connection_manager.send_to_session(
        session_id, ToolResult(tool=tool, result=result, message_id=message_id, duration=duration)
    )


async def send_message_complete(session_id: str, message_id: str) -> int:
    """发送消息完成通知到会话

    Args:
        session_id: 会话 ID
        message_id: 消息 ID

    Returns:
        int: 成功发送的连接数
    """
    return await connection_manager.send_to_session(
        session_id, MessageComplete(message_id=message_id)
    )


async def send_error(session_id: str, message: str, code: str | None = None) -> int:
    """发送错误消息到会话

    Args:
        session_id: 会话 ID
        message: 错误描述
        code: 错误代码（可选）

    Returns:
        int: 成功发送的连接数
    """
    return await connection_manager.send_to_session(
        session_id, ErrorMessage(message=message, code=code)
    )
