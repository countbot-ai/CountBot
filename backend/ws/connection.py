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
from typing import Any, Dict, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime

from fastapi import WebSocket, WebSocketDisconnect, status
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, ValidationError

# 全局取消令牌管理器
from backend.modules.agent.task_manager import CancellationToken

_session_cancel_tokens: Dict[str, CancellationToken] = {}


@dataclass
class SessionTask:
    """会话任务信息"""
    task_id: str
    cancel_token: CancellationToken
    created_at: datetime = field(default_factory=datetime.now)
    connection_count: int = 0  # 引用计数


# 会话任务管理器
_session_tasks: Dict[str, SessionTask] = {}
_pending_cancellations: Dict[str, asyncio.Task] = {}


def get_cancel_token(session_id: str) -> CancellationToken:
    """获取或创建会话的取消令牌
    
    Args:
        session_id: 会话 ID
        
    Returns:
        CancellationToken: 取消令牌
    """
    # 如果已存在且已取消，先清理
    if session_id in _session_cancel_tokens:
        old_token = _session_cancel_tokens[session_id]
        if old_token.is_cancelled:
            logger.debug(f"Cleaning up cancelled token for session {session_id}")
            del _session_cancel_tokens[session_id]
            if session_id in _session_tasks:
                del _session_tasks[session_id]
    
    # 创建新的取消令牌和任务信息
    if session_id not in _session_cancel_tokens:
        task_id = str(uuid.uuid4())
        cancel_token = CancellationToken()
        _session_cancel_tokens[session_id] = cancel_token
        _session_tasks[session_id] = SessionTask(
            task_id=task_id,
            cancel_token=cancel_token,
            connection_count=0
        )
        logger.debug(f"Created new cancel token for session {session_id} (task_id={task_id})")
    
    return _session_cancel_tokens[session_id]


def increment_connection_count(session_id: str) -> int:
    """增加会话的连接计数
    
    Args:
        session_id: 会话 ID
        
    Returns:
        int: 当前连接数
    """
    if session_id in _session_tasks:
        _session_tasks[session_id].connection_count += 1
        count = _session_tasks[session_id].connection_count
        logger.debug(f"Session {session_id} connection count: {count}")
        return count
    return 0


def decrement_connection_count(session_id: str) -> int:
    """减少会话的连接计数
    
    Args:
        session_id: 会话 ID
        
    Returns:
        int: 当前连接数
    """
    if session_id in _session_tasks:
        _session_tasks[session_id].connection_count = max(0, _session_tasks[session_id].connection_count - 1)
        count = _session_tasks[session_id].connection_count
        logger.debug(f"Session {session_id} connection count: {count}")
        return count
    return 0


def cancel_session(session_id: str) -> bool:
    """取消会话的处理
    
    Args:
        session_id: 会话 ID
        
    Returns:
        bool: 是否成功取消
    """
    if session_id in _session_cancel_tokens:
        _session_cancel_tokens[session_id].cancel()
        logger.info(f"Cancelled session: {session_id}")
        return True
    return False


def cleanup_cancel_token(session_id: str):
    """清理会话的取消令牌
    
    Args:
        session_id: 会话 ID
    """
    if session_id in _session_cancel_tokens:
        del _session_cancel_tokens[session_id]
    if session_id in _session_tasks:
        del _session_tasks[session_id]


async def schedule_delayed_cancellation(session_id: str, delay_seconds: int = 5):
    """延迟取消会话任务
    
    当会话没有活跃连接时，延迟一段时间后自动取消任务。
    如果在延迟期间有新连接，则取消此延迟任务。
    
    Args:
        session_id: 会话 ID
        delay_seconds: 延迟秒数（默认 5 秒）
    """
    # 获取当前任务信息（用于验证）
    current_task = _session_tasks.get(session_id)
    if not current_task:
        logger.debug(f"No task found for session {session_id}, skip scheduling cancellation")
        return
    
    task_id = current_task.task_id
    
    # 取消之前的延迟任务（如果存在）
    cancel_key = f"{session_id}:{task_id}"
    if cancel_key in _pending_cancellations:
        _pending_cancellations[cancel_key].cancel()
        logger.debug(f"Cancelled previous delayed cancellation for {cancel_key}")
    
    async def delayed_cancel():
        try:
            logger.info(f"Scheduled delayed cancellation for session {session_id} (task_id={task_id}, delay={delay_seconds}s)")
            await asyncio.sleep(delay_seconds)
            
            # 验证任务是否仍然是同一个（避免取消新任务）
            current = _session_tasks.get(session_id)
            if not current or current.task_id != task_id:
                logger.debug(f"Task changed for session {session_id}, skip cancellation")
                return
            
            # 检查是否有新连接（使用引用计数）
            if current.connection_count > 0:
                logger.debug(f"Session {session_id} has {current.connection_count} connections, skip cancellation")
                return
            
            # 执行取消
            if cancel_session(session_id):
                logger.info(f"Delayed cancellation executed for session {session_id} (task_id={task_id})")
            
        except asyncio.CancelledError:
            logger.debug(f"Delayed cancellation interrupted for session {session_id} (task_id={task_id})")
        except Exception as e:
            logger.error(f"Error in delayed cancellation for session {session_id}: {e}")
        finally:
            # 清理
            if cancel_key in _pending_cancellations:
                del _pending_cancellations[cancel_key]
    
    # 创建延迟任务
    task = asyncio.create_task(delayed_cancel())
    _pending_cancellations[cancel_key] = task


def cancel_delayed_cancellation(session_id: str):
    """取消延迟取消任务
    
    当有新连接时调用，取消之前安排的延迟取消。
    
    Args:
        session_id: 会话 ID
    """
    # 获取当前任务信息
    current_task = _session_tasks.get(session_id)
    if not current_task:
        return
    
    task_id = current_task.task_id
    cancel_key = f"{session_id}:{task_id}"
    
    if cancel_key in _pending_cancellations:
        _pending_cancellations[cancel_key].cancel()
        del _pending_cancellations[cancel_key]
        logger.info(f"Cancelled delayed cancellation for session {session_id} (task_id={task_id})")


# ============================================================================
# Message Models
# ============================================================================


class ClientMessage(BaseModel):
    """客户端发送的消息"""

    type: str = Field(..., description="消息类型")
    session_id: str = Field(..., alias="sessionId", description="会话 ID")
    content: Optional[str] = Field(None, description="消息内容（ping 消息可选）")
    attachments: Optional[list[str]] = Field(None, description="附件路径列表")


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


class ReasoningChunk(ServerMessage):
    """推理消息块（流式思考内容）"""

    type: str = Field(default="reasoning_chunk", description="消息类型")
    content: str = Field(..., description="推理内容")


class ToolCall(ServerMessage):
    """工具调用通知"""

    model_config = ConfigDict(populate_by_name=True)

    type: str = Field(default="tool_call", description="消息类型")
    tool: str = Field(..., description="工具名称")
    arguments: Dict[str, Any] = Field(..., description="工具参数")
    message_id: Optional[int] = Field(None, alias="messageId", description="关联的消息ID")


class ToolResult(ServerMessage):
    """工具执行结果"""

    model_config = ConfigDict(populate_by_name=True)

    type: str = Field(default="tool_result", description="消息类型")
    tool: str = Field(..., description="工具名称")
    result: str = Field(..., description="执行结果")
    message_id: Optional[int] = Field(None, alias="messageId", description="关联的消息ID")
    duration: Optional[float] = Field(None, description="执行耗时（毫秒）")


class MessageComplete(ServerMessage):
    """消息完成通知"""

    model_config = ConfigDict(populate_by_name=True)

    type: str = Field(default="message_complete", description="消息类型")
    message_id: str = Field(..., alias="messageId", description="消息 ID")


class ErrorMessage(ServerMessage):
    """错误消息"""

    type: str = Field(default="error", description="消息类型")
    message: str = Field(..., description="错误描述")
    code: Optional[str] = Field(None, description="错误代码")


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
        self._connections: Dict[str, WebSocket] = {}

        # 存储会话到连接的映射: {session_id: set(connection_id)}
        self._session_connections: Dict[str, Set[str]] = {}

        # 连接锁，防止并发修改
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, connection_id: Optional[str] = None) -> str:
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
            logger.debug(f"WebSocket 连接已建立: {connection_id}")

        return connection_id

    async def disconnect(self, connection_id: str):
        """注销连接

        Args:
            connection_id: 连接 ID
        """
        sessions_to_check = []
        
        async with self._lock:
            # 从所有会话中移除此连接
            for session_id, conn_ids in list(self._session_connections.items()):
                if connection_id in conn_ids:
                    conn_ids.discard(connection_id)
                    # 减少连接计数
                    count = decrement_connection_count(session_id)
                    
                    if not conn_ids:
                        del self._session_connections[session_id]
                        # 记录需要检查的会话（连接数为 0）
                        if count == 0:
                            sessions_to_check.append(session_id)

            # 移除连接
            if connection_id in self._connections:
                del self._connections[connection_id]
                logger.info(f"WebSocket 连接已断开: {connection_id}")
        
        # 在锁外处理延迟取消（避免死锁）
        for session_id in sessions_to_check:
            await schedule_delayed_cancellation(session_id, delay_seconds=5)

    async def bind_session(self, connection_id: str, session_id: str):
        """绑定连接到会话

        Args:
            connection_id: 连接 ID
            session_id: 会话 ID
        """
        async with self._lock:
            if session_id not in self._session_connections:
                self._session_connections[session_id] = set()
            
            # 只有新连接才增加计数
            is_new = connection_id not in self._session_connections[session_id]
            self._session_connections[session_id].add(connection_id)
            
            if is_new:
                # 增加连接计数
                count = increment_connection_count(session_id)
                logger.debug(f"连接 {connection_id} 绑定到会话 {session_id} (连接数: {count})")
        
        # 在锁外取消延迟取消（避免死锁）
        if is_new:
            cancel_delayed_cancellation(session_id)

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
            # 降级为 DEBUG：频道会话（QQ/Telegram 等）不使用 WebSocket，这是正常的
            logger.debug(f"[WS] 会话 {session_id} 无活跃 WebSocket 连接（可能是频道会话）")
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


async def send_reasoning_chunk(session_id: str, content: str) -> int:
    """发送推理消息块到会话。"""
    return await connection_manager.send_to_session(
        session_id, ReasoningChunk(content=content)
    )


async def send_tool_call(session_id: str, tool: str, arguments: Dict[str, Any], message_id: Optional[int] = None) -> int:
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


async def send_tool_result(session_id: str, tool: str, result: str, message_id: Optional[int] = None, duration: Optional[float] = None) -> int:
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


async def send_dict_to_session(session_id: str, data: dict) -> int:
    """将原始字典以 JSON 形式发送到会话的所有连接

    Args:
        session_id: 会话 ID
        data: 要发送的字典数据

    Returns:
        int: 成功发送的连接数
    """
    connection_ids = connection_manager._session_connections.get(session_id, set()).copy()
    if not connection_ids:
        event_type = data.get("type", "unknown")
        # 降级为 DEBUG：频道会话（QQ/Telegram 等）不使用 WebSocket，这是正常的
        logger.debug(f"[WS] 会话 {session_id} 无活跃 WebSocket 连接（type={event_type}，可能是频道会话）")
        return 0

    payload = json.dumps(data, ensure_ascii=False)
    success_count = 0
    for conn_id in list(connection_ids):
        ws = connection_manager._connections.get(conn_id)
        if ws:
            try:
                await ws.send_text(payload)
                success_count += 1
            except Exception as exc:
                logger.debug(f"send_dict_to_session 失败 (连接 {conn_id}): {exc}")
                await connection_manager.disconnect(conn_id)
    return success_count


async def send_error(session_id: str, message: str, code: Optional[str] = None) -> int:
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
