"""WebSocket 连接处理：连接/断开管理、消息路由、流式推送、工具调用通知与错误处理。"""

import asyncio
import json
import uuid
from typing import Any, Dict, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime

from fastapi import WebSocket, WebSocketDisconnect, status
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.modules.agent.task_manager import CancellationToken

_session_cancel_tokens: Dict[str, CancellationToken] = {}


@dataclass
class SessionTask:
    """会话任务信息"""
    task_id: str
    cancel_token: CancellationToken
    created_at: datetime = field(default_factory=datetime.now)
    connection_count: int = 0  # 引用计数


_session_tasks: Dict[str, SessionTask] = {}
_pending_cancellations: Dict[str, asyncio.Task] = {}


def get_cancel_token(session_id: str) -> CancellationToken:
    """获取或创建会话的取消令牌"""
    if session_id in _session_cancel_tokens:
        old_token = _session_cancel_tokens[session_id]
        if old_token.is_cancelled:
            logger.debug(f"Cleaning up cancelled token for session {session_id}")
            del _session_cancel_tokens[session_id]
            if session_id in _session_tasks:
                del _session_tasks[session_id]

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


def acquire_cancel_token(session_id: str) -> "tuple[CancellationToken, bool]":
    """获取会话取消令牌，并返回本次是否新建；复用的令牌由原回合负责清理。"""
    existing = _session_cancel_tokens.get(session_id)
    owns_existing = existing is not None and not existing.is_cancelled
    return get_cancel_token(session_id), not owns_existing


def increment_connection_count(session_id: str) -> int:
    """增加会话的连接计数"""
    if session_id in _session_tasks:
        _session_tasks[session_id].connection_count += 1
        count = _session_tasks[session_id].connection_count
        logger.debug(f"Session {session_id} connection count: {count}")
        return count
    return 0


def decrement_connection_count(session_id: str) -> int:
    """减少会话的连接计数"""
    if session_id in _session_tasks:
        _session_tasks[session_id].connection_count = max(0, _session_tasks[session_id].connection_count - 1)
        count = _session_tasks[session_id].connection_count
        logger.debug(f"Session {session_id} connection count: {count}")
        return count
    return 0


def cancel_session(session_id: str) -> bool:
    """取消会话的处理"""
    if session_id in _session_cancel_tokens:
        _session_cancel_tokens[session_id].cancel()
        logger.info(f"Cancelled session: {session_id}")
        return True
    return False


def cleanup_cancel_token(session_id: str, token=None):
    """清理会话的取消令牌"""
    if token is not None and _session_cancel_tokens.get(session_id) is not token:
        return
    if session_id in _session_cancel_tokens:
        del _session_cancel_tokens[session_id]
    if session_id in _session_tasks:
        del _session_tasks[session_id]


async def schedule_delayed_cancellation(session_id: str, delay_seconds: int = 5):
    """延迟取消会话任务：会话无活跃连接时延迟取消，期间出现新连接则取消本次延迟。"""
    current_task = _session_tasks.get(session_id)
    if not current_task:
        logger.debug(f"No task found for session {session_id}, skip scheduling cancellation")
        return

    task_id = current_task.task_id

    cancel_key = f"{session_id}:{task_id}"
    if cancel_key in _pending_cancellations:
        _pending_cancellations[cancel_key].cancel()
        logger.debug(f"Cancelled previous delayed cancellation for {cancel_key}")
    
    async def delayed_cancel():
        try:
            logger.info(f"Scheduled delayed cancellation for session {session_id} (task_id={task_id}, delay={delay_seconds}s)")
            await asyncio.sleep(delay_seconds)

            # 任务已被替换说明是新任务，跳过取消
            current = _session_tasks.get(session_id)
            if not current or current.task_id != task_id:
                logger.debug(f"Task changed for session {session_id}, skip cancellation")
                return

            if current.connection_count > 0:
                logger.debug(f"Session {session_id} has {current.connection_count} connections, skip cancellation")
                return

            if cancel_session(session_id):
                logger.info(f"Delayed cancellation executed for session {session_id} (task_id={task_id})")
            
        except asyncio.CancelledError:
            logger.debug(f"Delayed cancellation interrupted for session {session_id} (task_id={task_id})")
        except Exception as e:
            logger.error(f"Error in delayed cancellation for session {session_id}: {e}")
        finally:
            if cancel_key in _pending_cancellations:
                del _pending_cancellations[cancel_key]
    
    task = asyncio.create_task(delayed_cancel())
    _pending_cancellations[cancel_key] = task


def cancel_delayed_cancellation(session_id: str):
    """取消延迟取消任务：有新连接时调用，取消此前安排的延迟取消。"""
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
# 消息模型
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


class NativeEvent(ServerMessage):
    """供应商原生能力事件（联网搜索、阅读链接、引用等）。"""

    type: str = Field(default="native_event", description="消息类型")
    event: Dict[str, Any] = Field(..., description="原生事件负载")


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
# 连接管理器
# ============================================================================


class ConnectionManager:
    """WebSocket 连接管理器：负责连接注册注销、广播与会话级推送，按 owner_id 隔离。"""

    def __init__(self):
        """初始化连接管理器"""
        self._connections: Dict[str, WebSocket] = {}

        self._session_connections: Dict[str, Set[str]] = {}

        self._lock = asyncio.Lock()

        # 连接 -> 归属（管理员为 None）
        self._connection_owners: Dict[str, Optional[str]] = {}

    async def connect(
        self,
        websocket: WebSocket,
        connection_id: Optional[str] = None,
        owner_id: Optional[str] = None,
    ) -> str:
        """注册新连接"""
        if connection_id is None:
            connection_id = str(uuid.uuid4())

        async with self._lock:
            await websocket.accept()
            self._connections[connection_id] = websocket
            self._connection_owners[connection_id] = owner_id or None
            logger.debug(f"WebSocket 连接已建立: {connection_id} (owner={owner_id})")

        return connection_id

    def get_owner(self, connection_id: str) -> Optional[str]:
        return self._connection_owners.get(connection_id)

    async def disconnect(self, connection_id: str):
        """注销连接"""
        sessions_to_check = []
        
        async with self._lock:
            for session_id, conn_ids in list(self._session_connections.items()):
                if connection_id in conn_ids:
                    conn_ids.discard(connection_id)
                    count = decrement_connection_count(session_id)

                    if not conn_ids:
                        del self._session_connections[session_id]
                        if count == 0:
                            sessions_to_check.append(session_id)

            if connection_id in self._connections:
                del self._connections[connection_id]
                self._connection_owners.pop(connection_id, None)
                logger.info(f"WebSocket 连接已断开: {connection_id}")

        # 锁外处理延迟取消，避免死锁
        for session_id in sessions_to_check:
            await schedule_delayed_cancellation(session_id, delay_seconds=5)

    async def bind_session(
        self,
        connection_id: str,
        session_id: str,
        owner_id: Optional[str] = None,
        allow_any_owner: bool = False,
    ):
        """绑定连接到会话"""
        async with self._lock:
            connection_owner = self._connection_owners.get(connection_id)
            if not allow_any_owner and (connection_owner or None) != (owner_id or None):
                logger.warning(
                    f"拒绝绑定：连接 {connection_id} 归属 {connection_owner} "
                    f"与会话 {session_id} 归属 {owner_id} 不一致"
                )
                raise PermissionError("session does not belong to this connection")

            if session_id not in self._session_connections:
                self._session_connections[session_id] = set()
            
            is_new = connection_id not in self._session_connections[session_id]
            self._session_connections[session_id].add(connection_id)
            
            if is_new:
                count = increment_connection_count(session_id)
                logger.debug(f"连接 {connection_id} 绑定到会话 {session_id} (连接数: {count})")
        
        # 锁外取消延迟取消，避免死锁
        if is_new:
            cancel_delayed_cancellation(session_id)

    async def send_message(self, connection_id: str, message: ServerMessage) -> bool:
        """发送消息到指定连接"""
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
        """发送消息到会话的所有连接"""
        connection_ids = self._session_connections.get(session_id, set()).copy()
        if not connection_ids:
            # 频道会话（QQ/Telegram 等）不走 WebSocket，无连接属正常，故降为 DEBUG
            logger.debug(f"[WS] 会话 {session_id} 无活跃 WebSocket 连接（可能是频道会话）")
            return 0

        success_count = 0
        for connection_id in connection_ids:
            if await self.send_message(connection_id, message):
                success_count += 1

        return success_count

    async def broadcast(self, message: ServerMessage) -> int:
        """广播消息到所有连接（仅用于管理员级系统通知）。"""
        connection_ids = list(self._connections.keys())
        success_count = 0

        for connection_id in connection_ids:
            if await self.send_message(connection_id, message):
                success_count += 1

        return success_count

    async def broadcast_to_owner(self, owner_id: Optional[str], message: ServerMessage) -> int:
        """按归属推送：``owner_id`` 为空时只发给管理员连接。"""
        target = owner_id or None
        connection_ids = [
            conn_id
            for conn_id, conn_owner in self._connection_owners.items()
            if (conn_owner or None) == target
        ]
        success_count = 0
        for connection_id in connection_ids:
            if await self.send_message(connection_id, message):
                success_count += 1
        return success_count

    async def disconnect_regular_users(self, reason: str = "配置已更新，请重新连接") -> int:
        """断开所有普通用户连接，使其重连后加载新权限。"""
        connection_ids = [
            conn_id for conn_id, owner in self._connection_owners.items() if owner
        ]
        return await self._close_connections(connection_ids, reason)

    async def disconnect_owner(self, owner_id: Optional[str], reason: str = "配置已更新，请重新连接") -> int:
        """断开某个用户的连接，使其重连后加载新权限。"""
        if not owner_id:
            return 0
        connection_ids = [
            conn_id
            for conn_id, conn_owner in self._connection_owners.items()
            if conn_owner == owner_id
        ]
        return await self._close_connections(connection_ids, reason)

    async def _close_connections(self, connection_ids: list[str], reason: str) -> int:
        for connection_id in connection_ids:
            websocket = self._connections.get(connection_id)
            if websocket is not None:
                try:
                    await websocket.close(code=4008, reason=reason)
                except Exception:
                    pass
            await self.disconnect(connection_id)
        return len(connection_ids)

    def get_connection_count(self) -> int:
        """获取活跃连接数"""
        return len(self._connections)

    def get_session_connection_count(self, session_id: str) -> int:
        """获取会话的连接数"""
        return len(self._session_connections.get(session_id, set()))


# ============================================================================
# 全局连接管理器实例
# ============================================================================

connection_manager = ConnectionManager()


# ============================================================================
# WebSocket 处理器
# ============================================================================


async def handle_websocket(websocket: WebSocket, agent_loop=None, loop_factory=None, user=None):
    """处理 WebSocket 连接：接受连接、处理客户端消息、管理生命周期与错误处理。"""
    connection_id = None
    owner_id = getattr(user, "owner_id", None) if user is not None else None

    try:
        connection_id = await connection_manager.connect(websocket, owner_id=owner_id)

        await connection_manager.send_message(
            connection_id,
            ServerMessage(type="connected"),
        )

        if agent_loop:
            from backend.ws.events import websocket_event_loop
            await websocket_event_loop(
                websocket,
                connection_id,
                agent_loop,
                loop_factory=loop_factory,
                user=user,
            )
        else:
            # 无 agent_loop 时的简单消息循环（用于测试）
            while True:
                try:
                    data = await websocket.receive_text()

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

                    # 绑定会话前校验归属：否则普通用户能把连接绑到他人会话上，
                    # 进而收到别人会话的广播。
                    if user is not None and not getattr(user, "is_admin", False):
                        from backend.database import AsyncSessionLocal
                        from backend.modules.multiuser.permissions import owner_scope
                        from backend.modules.session.manager import SessionManager

                        async with AsyncSessionLocal() as _db:
                            owned_session = await SessionManager(
                                _db, owner_id=owner_scope(user)
                            ).get_session(client_message.session_id)
                        if owned_session is None:
                            await connection_manager.send_message(
                                connection_id,
                                ErrorMessage(
                                    message="会话不存在或无权访问",
                                    code="SESSION_NOT_FOUND",
                                ),
                            )
                            continue

                    await connection_manager.bind_session(
                        connection_id, client_message.session_id
                    )

                    # 此路径仅记录，实际处理逻辑在事件处理器中
                    content_preview = (client_message.content[:50] if client_message.content else "(empty)")
                    logger.info(
                        f"收到消息 (连接 {connection_id}, 会话 {client_message.session_id}): "
                        f"{content_preview}..."
                    )

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
        if connection_id:
            await connection_manager.disconnect(connection_id)


# ============================================================================
# 辅助函数
# ============================================================================


async def send_message_chunk(session_id: str, content: str) -> int:
    """发送消息块到会话"""
    return await connection_manager.send_to_session(
        session_id, MessageChunk(content=content)
    )


async def send_reasoning_chunk(session_id: str, content: str) -> int:
    """发送推理消息块到会话。"""
    return await connection_manager.send_to_session(
        session_id, ReasoningChunk(content=content)
    )


async def send_native_event(session_id: str, event: Dict[str, Any]) -> int:
    """发送供应商原生能力事件到会话。"""
    return await connection_manager.send_to_session(
        session_id, NativeEvent(event=event)
    )


async def send_tool_call(session_id: str, tool: str, arguments: Dict[str, Any], message_id: Optional[int] = None) -> int:
    """发送工具调用通知到会话"""
    return await connection_manager.send_to_session(
        session_id, ToolCall(tool=tool, arguments=arguments, message_id=message_id)
    )


async def send_tool_result(session_id: str, tool: str, result: str, message_id: Optional[int] = None, duration: Optional[float] = None) -> int:
    """发送工具执行结果到会话"""
    return await connection_manager.send_to_session(
        session_id, ToolResult(tool=tool, result=result, message_id=message_id, duration=duration)
    )


async def send_message_complete(session_id: str, message_id: str) -> int:
    """发送消息完成通知到会话"""
    return await connection_manager.send_to_session(
        session_id, MessageComplete(message_id=message_id)
    )


async def send_dict_to_session(session_id: str, data: dict) -> int:
    """将原始字典以 JSON 形式发送到会话的所有连接"""
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
    """发送错误消息到会话"""
    return await connection_manager.send_to_session(
        session_id, ErrorMessage(message=message, code=code)
    )
