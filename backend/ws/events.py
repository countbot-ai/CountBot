"""WebSocket 消息事件处理

实现消息事件的处理逻辑，包括：
- 消息接收和验证
- Agent 处理集成
- 流式响应推送
- 工具调用通知
- 错误处理
"""

import asyncio
from typing import Any

from fastapi import WebSocket
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.modules.agent.loop import AgentLoop
from backend.modules.session.manager import SessionManager
from backend.ws.connection import (
    ClientMessage,
    connection_manager,
    send_error,
    send_message_chunk,
    send_message_complete,
    send_tool_call,
    send_tool_result,
)


def _friendly_processing_error(raw: str) -> str:
    """将原始处理错误转换为用户友好提示"""
    lower = raw.lower()
    if any(k in lower for k in ("429", "余额", "quota", "rate limit")):
        return "AI 服务配额不足，请检查 API 账户余额。"
    if any(k in lower for k in ("401", "unauthorized", "api_key", "authentication")):
        return "API 认证失败，请检查密钥配置。"
    if any(k in lower for k in ("timeout", "connection", "network")):
        return "网络连接异常，请稍后重试。"
    return f"消息处理出错，请稍后重试。"


# ============================================================================
# Message Event Handlers
# ============================================================================


async def handle_message_event(
    connection_id: str,
    message: ClientMessage,
    agent_loop: AgentLoop,
    db: AsyncSession,
) -> None:
    """处理客户端消息事件

    Args:
        connection_id: 连接 ID
        message: 客户端消息
        agent_loop: Agent 循环实例
        db: 数据库会话
    """
    session_id = message.session_id
    content = message.content

    logger.info(
        f"收到消息 - 连接:{connection_id}, 会话:{session_id}, 内容:{content[:50]}..."
    )

    try:
        # 获取取消令牌
        from backend.ws.connection import get_cancel_token, cleanup_cancel_token
        cancel_token = get_cancel_token(session_id)
        
        # 验证会话是否存在
        session_manager = SessionManager(db)
        session = await session_manager.get_session(session_id)

        if session is None:
            logger.error(f"会话不存在: {session_id}")
            await send_error(
                session_id,
                f"Session '{session_id}' not found",
                "SESSION_NOT_FOUND",
            )
            return

        logger.info(f"会话验证通过: {session_id}")

        # 保存用户消息到数据库
        user_message = await session_manager.add_message(
            session_id=session_id,
            role="user",
            content=content,
        )

        if user_message is None:
            logger.error(f"保存用户消息失败")
            await send_error(
                session_id,
                "Failed to save user message",
                "DATABASE_ERROR",
            )
            return

        logger.info(f"用户消息已保存: ID={user_message.id}")

        # 获取会话历史
        messages = await session_manager.get_messages(
            session_id=session_id,
            limit=50,  # 限制历史消息数量
        )

        logger.info(f"加载历史消息: {len(messages)} 条")

        # 构建上下文（排除刚添加的用户消息）
        context = []
        for msg in messages[:-1]:
            context.append({
                "role": msg.role,
                "content": msg.content,
            })

        logger.info(f"开始AI处理，上下文消息数: {len(context)}")

        # 处理消息并流式输出
        assistant_content = ""

        # 使用缓冲流式处理器 - 优化参数以实现实时输出
        from backend.ws.streaming import BufferedStreamingHandler

        streaming_handler = BufferedStreamingHandler(
            session_id=session_id,
            buffer_size=10,  # 减小缓冲区，更快输出
            flush_interval_ms=10,  # 减小刷新间隔，更实时
        )

        chunk_count = 0
        async for chunk in agent_loop.process_message(
            message=content,
            session_id=session_id,
            context=context,
            cancel_token=cancel_token,
        ):
            # 检查是否被取消
            if cancel_token.is_cancelled:
                logger.info(f"处理被取消: {session_id}")
                await streaming_handler.write("\n\n[已停止生成]")
                await streaming_handler.flush()
                break
            
            assistant_content += chunk
            await streaming_handler.write(chunk)
            chunk_count += 1
            
            # 每100个chunk记录一次
            if chunk_count % 100 == 0:
                logger.debug(f"已发送 {chunk_count} 个chunk")

        logger.info(f"AI处理完成，共发送 {chunk_count} 个chunk，总长度: {len(assistant_content)}")

        # 确保刷新剩余内容
        await streaming_handler.flush()

        # 记录统计信息
        stats = streaming_handler.get_stats()
        logger.debug(f"流式响应统计: {stats}")

        # 保存助手响应到数据库
        if assistant_content:
            assistant_message = await session_manager.add_message(
                session_id=session_id,
                role="assistant",
                content=assistant_content,
            )

            logger.info(f"助手消息已保存到数据库: ID={assistant_message.id}")

            # 回填 message_id 到该轮对话产生的工具调用记录
            try:
                from backend.modules.tools.conversation_history import get_conversation_history
                conversation_history = get_conversation_history()
                await conversation_history.backfill_message_id(
                    session_id=session_id,
                    message_id=assistant_message.id,
                )
            except Exception as e:
                logger.warning(f"Failed to backfill message_id: {e}")

            # 发送完成通知
            await send_message_complete(session_id, "")
        else:
            logger.warning(f"AI响应为空")
            # 没有内容，发送空完成通知
            await send_message_complete(session_id, "")

        logger.info(f"消息处理完成 (会话 {session_id})")
        
        # 清理取消令牌
        cleanup_cancel_token(session_id)

    except Exception as e:
        logger.exception(f"处理消息事件时出错: {e}")
        friendly = _friendly_processing_error(str(e))
        await send_error(
            session_id,
            friendly,
            "PROCESSING_ERROR",
        )
        # 清理取消令牌
        from backend.ws.connection import cleanup_cancel_token
        cleanup_cancel_token(session_id)


async def handle_tool_execution(
    session_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    agent_loop: AgentLoop,
) -> None:
    """处理工具执行事件

    Args:
        session_id: 会话 ID
        tool_name: 工具名称
        arguments: 工具参数
        agent_loop: Agent 循环实例
    """
    from backend.ws.tool_notifications import execute_tool_with_notifications

    try:
        logger.info(f"执行工具 {tool_name} (会话 {session_id})")

        # 使用增强的工具通知执行
        result = await execute_tool_with_notifications(
            session_id=session_id,
            tool_name=tool_name,
            arguments=arguments,
            executor=agent_loop.execute_tool,
        )

        logger.info(f"工具执行完成: {tool_name}")

    except Exception as e:
        logger.exception(f"工具执行失败: {e}")
        # 错误已经在 execute_tool_with_notifications 中通知了


async def handle_ping_event(connection_id: str) -> None:
    """处理心跳事件

    Args:
        connection_id: 连接 ID
    """
    from backend.ws.connection import ServerMessage

    await connection_manager.send_message(
        connection_id,
        ServerMessage(type="pong"),
    )


async def handle_subscribe_event(
    connection_id: str,
    session_id: str,
) -> None:
    """处理订阅事件

    Args:
        connection_id: 连接 ID
        session_id: 会话 ID
    """
    await connection_manager.bind_session(connection_id, session_id)
    logger.info(f"连接 {connection_id} 订阅会话 {session_id}")


async def handle_unsubscribe_event(
    connection_id: str,
    session_id: str,
) -> None:
    """处理取消订阅事件

    Args:
        connection_id: 连接 ID
        session_id: 会话 ID
    """
    # 注意：当前 ConnectionManager 不支持取消订阅单个会话
    # 这里只是记录日志，实际实现需要扩展 ConnectionManager
    logger.info(f"连接 {connection_id} 取消订阅会话 {session_id}")


# ============================================================================
# Event Router
# ============================================================================


async def route_event(
    connection_id: str,
    event_type: str,
    event_data: dict[str, Any],
    agent_loop: AgentLoop,
    db: AsyncSession,
) -> None:
    """路由事件到对应的处理器

    Args:
        connection_id: 连接 ID
        event_type: 事件类型
        event_data: 事件数据
        agent_loop: Agent 循环实例
        db: 数据库会话
    """
    try:
        if event_type == "message":
            # 处理消息事件
            message = ClientMessage(**event_data)
            await handle_message_event(connection_id, message, agent_loop, db)

        elif event_type == "tool_execute":
            # 处理工具执行事件
            session_id = event_data.get("sessionId")
            tool_name = event_data.get("tool")
            arguments = event_data.get("arguments", {})

            if not session_id or not tool_name:
                await send_error(
                    session_id or "",
                    "Missing required fields: sessionId, tool",
                    "INVALID_EVENT",
                )
                return

            await handle_tool_execution(session_id, tool_name, arguments, agent_loop)

        elif event_type == "ping":
            # 处理心跳事件
            await handle_ping_event(connection_id)

        elif event_type == "subscribe":
            # 处理订阅事件
            session_id = event_data.get("sessionId")
            if not session_id:
                logger.warning("订阅事件缺少 sessionId")
                return

            await handle_subscribe_event(connection_id, session_id)

        elif event_type == "unsubscribe":
            # 处理取消订阅事件
            session_id = event_data.get("sessionId")
            if not session_id:
                logger.warning("取消订阅事件缺少 sessionId")
                return

            await handle_unsubscribe_event(connection_id, session_id)

        else:
            logger.warning(f"未知事件类型: {event_type}")
            await send_error(
                event_data.get("sessionId", ""),
                f"Unknown event type: {event_type}",
                "UNKNOWN_EVENT",
            )

    except Exception as e:
        logger.exception(f"路由事件时出错: {e}")
        await send_error(
            event_data.get("sessionId", ""),
            f"Event routing failed: {str(e)}",
            "ROUTING_ERROR",
        )


# ============================================================================
# WebSocket Event Loop
# ============================================================================


async def websocket_event_loop(
    websocket: WebSocket,
    connection_id: str,
    agent_loop: AgentLoop,
) -> None:
    """WebSocket 事件循环

    持续监听和处理 WebSocket 事件，直到连接断开。

    Args:
        websocket: WebSocket 连接
        connection_id: 连接 ID
        agent_loop: Agent 循环实例
    """
    from fastapi import WebSocketDisconnect
    import json
    from pydantic import ValidationError

    try:
        while True:
            # 检查 WebSocket 连接状态
            if websocket.client_state.name != "CONNECTED":
                logger.info(f"WebSocket 连接已关闭 (状态: {websocket.client_state.name}): {connection_id}")
                break

            try:
                # 接收消息
                data = await websocket.receive_text()
            except RuntimeError as e:
                # 捕获 "WebSocket is not connected" 错误
                if "not connected" in str(e).lower():
                    logger.info(f"WebSocket 连接已断开: {connection_id}")
                    break
                raise

            # 解析消息
            try:
                message_dict = json.loads(data)
                event_type = message_dict.get("type")
                event_data = message_dict

                if not event_type:
                    await send_error(
                        "",
                        "Missing event type",
                        "INVALID_EVENT",
                    )
                    continue

                # 获取数据库会话
                async for db in get_db():
                    try:
                        # 路由事件
                        await route_event(
                            connection_id,
                            event_type,
                            event_data,
                            agent_loop,
                            db,
                        )
                    finally:
                        await db.close()
                    break

            except (json.JSONDecodeError, ValidationError) as e:
                logger.warning(f"无效的消息格式: {e}")
                await send_error(
                    "",
                    "Invalid message format",
                    "INVALID_MESSAGE",
                )

    except WebSocketDisconnect:
        logger.info(f"客户端断开连接: {connection_id}")
    except RuntimeError as e:
        # 捕获连接相关的运行时错误
        if "not connected" in str(e).lower() or "accept" in str(e).lower():
            logger.info(f"WebSocket 连接已关闭: {connection_id}")
        else:
            logger.exception(f"WebSocket 运行时错误: {e}")
    except Exception as e:
        logger.exception(f"WebSocket 事件循环错误: {e}")
