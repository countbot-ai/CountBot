"""WebSocket 消息事件处理

实现消息事件的处理逻辑，包括：
- 消息接收和验证
- Agent 处理集成
- 流式响应推送
- 工具调用通知
- 错误处理
"""

import asyncio
import json
from pathlib import Path
from typing import Any, Dict

from fastapi import WebSocket
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db, get_db_session_factory
from backend.modules.agent.loop import AgentLoop
from backend.modules.config.loader import config_loader
from backend.modules.external_agents.conversation import (
    build_history_prompt,
    resolve_effective_session_mode,
)
from backend.modules.external_agents.routing import (
    build_explicit_external_agent_system_message,
    extract_explicit_external_agent_request,
)
from backend.modules.session import (
    ConversationContextService,
    build_session_model_override,
    resolve_session_runtime_config,
    schedule_context_maintenance,
)
from backend.modules.session.message_context import (
    build_attachment_items_from_workspace,
    build_message_context,
    normalize_assistant_persistence_payload,
    resolve_workspace_attachments,
)
from backend.modules.providers.runtime import (
    build_provider_unavailable_message,
    get_provider_runtime_state,
)
from backend.modules.session.manager import SessionManager
from backend.ws.connection import (
    ClientMessage,
    connection_manager,
    send_error,
    send_message_chunk,
    send_message_complete,
    send_reasoning_chunk,
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


def _validate_message_or_attachments(content: str, attachments: list[str] | None) -> str:
    normalized_content = str(content or "")
    if normalized_content.strip() or attachments:
        return normalized_content
    raise ValueError("Message or attachments are required")


def _resolve_attachment_inputs(attachments: list[str] | None, workspace: Path) -> list[tuple[str, Path]]:
    return resolve_workspace_attachments(attachments, workspace=workspace)


def _resolve_explicit_external_tool_request(
    agent_loop: AgentLoop,
    message: str,
) -> tuple[str, str] | None:
    """Resolve natural-language routing like '用 claude 帮我写个爬虫'."""
    parsed = extract_explicit_external_agent_request(message)
    if not parsed or not agent_loop.tools:
        return None

    requested_profile, task = parsed
    external_tool = agent_loop.tools.get_tool("external_coding_agent")
    registry = getattr(external_tool, "registry", None)
    if registry is None:
        return None

    try:
        canonical_name = registry.resolve_profile_name(requested_profile)
        registry.resolve_profile(canonical_name)
    except Exception:
        return None

    return canonical_name, task


def _prepare_external_task(profile, task: str, history: list[dict]) -> str:
    """根据 profile 会话模式构造实际任务。"""
    session_mode = resolve_effective_session_mode(profile)
    if session_mode in {"stateless", "native"}:
        return task
    return build_history_prompt(
        task=task,
        history_messages=history,
        history_message_count=profile.history_message_count,
    )


def _inject_explicit_external_request_context(
    agent_loop: AgentLoop,
    context: list[dict],
    explicit_external_request: tuple[str, str] | None,
) -> list[dict]:
    """Keep WebSocket web chat on the normal tool-call path for explicit external-agent requests."""
    if not explicit_external_request:
        return list(context)

    external_tool = agent_loop.tools.get_tool("external_coding_agent") if agent_loop.tools else None
    registry = getattr(external_tool, "registry", None)
    if registry is None:
        return list(context)

    profile_name, task = explicit_external_request
    profile = registry.resolve_profile(profile_name)
    prepared_task = _prepare_external_task(profile, task, context)
    system_message = build_explicit_external_agent_system_message(
        profile.name,
        prepared_task,
    )
    if not system_message:
        return list(context)

    augmented_context = list(context)
    augmented_context.append({"role": "system", "content": system_message})
    return augmented_context


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
    try:
        content = _validate_message_or_attachments(
            message.content or "",
            message.attachments,
        )
    except ValueError as exc:
        await send_error(session_id, str(exc), "INVALID_MESSAGE")
        return

    logger.info(
        f"收到消息 - 连接:{connection_id}, 会话:{session_id}, 内容:{content[:50]}..."
    )

    try:
        # 立即绑定 session — 确保即使 subscribe 事件尚未到达，后续 WS 事件也能路由到此连接
        await connection_manager.bind_session(connection_id, session_id)

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

        try:
            resolved_attachments = _resolve_attachment_inputs(
                message.attachments,
                getattr(agent_loop, "workspace", config_loader.config.workspace.path or "."),
            )
        except ValueError as exc:
            await send_error(session_id, str(exc), "INVALID_ATTACHMENT")
            return

        attachment_items = build_attachment_items_from_workspace(resolved_attachments)
        attachment_paths = [relative_path for relative_path, _ in resolved_attachments]

        runtime_config = resolve_session_runtime_config(config_loader.config, session)
        runtime_state = get_provider_runtime_state(
            config_loader.config,
            runtime_config.provider_name,
            api_key_override=runtime_config.api_key,
            api_base_override=runtime_config.api_base,
        )
        if not runtime_state.selectable:
            await send_error(
                session_id,
                build_provider_unavailable_message(
                    runtime_config.provider_name,
                    runtime_state.reason,
                ),
                "PROVIDER_UNAVAILABLE",
            )
            return

        model_override = build_session_model_override(runtime_config, force=True)
        persona_override = runtime_config.persona_config

        if session.use_custom_config:
            if runtime_config.has_custom_model_config:
                logger.info(
                    "✓ 使用会话级模型配置: "
                    f"{runtime_config.provider_name}/{runtime_config.model_name}"
                )
            if runtime_config.has_custom_persona_config:
                logger.info(f"✓ 使用自定义性格: {runtime_config.persona_config.personality}")
        else:
            logger.info(
                "使用全局配置: "
                f"{runtime_config.provider_name}/{runtime_config.model_name}"
            )

        active_provider, _, _, _, _, _ = agent_loop._resolve_execution_runtime(
            model_override
        )

        # 保存用户消息到数据库
        user_message = await session_manager.add_message(
            session_id=session_id,
            role="user",
            content=content,
            message_context=build_message_context(attachment_items=attachment_items),
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

        context_service = ConversationContextService(db)
        history_limit = runtime_config.persona_config.max_history_messages
        context_payload = await context_service.build_model_context(
            session_id=session_id,
            max_history_messages=history_limit,
            enable_short_context_summary=runtime_config.persona_config.enable_short_context_summary,
        )
        context = context_payload.history
        if context and context[-1].get("role") == "user":
            context = context[:-1]

        logger.info(f"开始AI处理，上下文消息数: {len(context)}")

        # 将当前 session_id 注入到所有支持会话感知的工具（如 workflow_run）
        if agent_loop.tools:
            agent_loop.tools.set_session_id(session_id)
            agent_loop.tools.set_cancel_token(cancel_token)
            logger.debug(f"Propagated session_id={session_id} to tool registry")
        explicit_external_request = _resolve_explicit_external_tool_request(
            agent_loop,
            content,
        )

        # 处理消息并流式输出
        assistant_content = ""
        assistant_reasoning = ""

        # 使用缓冲流式处理器 - 优化参数以实现实时输出
        from backend.ws.streaming import BufferedStreamingHandler

        streaming_handler = BufferedStreamingHandler(
            session_id=session_id,
            buffer_size=10,  # 减小缓冲区，更快输出
            flush_interval_ms=10,  # 减小刷新间隔，更实时
        )
        prefer_direct_workflow_result = False
        team_finder = getattr(agent_loop.context_builder, "_find_mentioned_team", None)
        if callable(team_finder):
            try:
                prefer_direct_workflow_result = bool(team_finder(content))
            except Exception as exc:
                logger.warning(f"Failed to detect mentioned team for websocket chat: {exc}")

        chunk_count = 0
        async def reasoning_event_handler(reasoning_chunk: str) -> None:
            nonlocal assistant_reasoning
            assistant_reasoning += reasoning_chunk or ""
            await send_reasoning_chunk(session_id, reasoning_chunk)

        if explicit_external_request:
            profile_name, _task = explicit_external_request
            logger.info(
                "Routing websocket chat explicit external-agent request through agent loop: "
                f"profile={profile_name}, session={session_id}"
            )
            context = _inject_explicit_external_request_context(
                agent_loop,
                context,
                explicit_external_request,
            )

        async for chunk in agent_loop.process_message(
            message=content,
            session_id=session_id,
            context=context,
            session_summary=context_payload.session_summary,
            media=attachment_paths,
            channel="web-chat",
            cancel_token=cancel_token,
            model_override=model_override,
            persona_override=persona_override,
            reasoning_event_handler=reasoning_event_handler,
            prefer_direct_workflow_result=prefer_direct_workflow_result,
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
        persisted_content, normalized_reasoning, used_reasoning_fallback = (
            normalize_assistant_persistence_payload(
                assistant_content,
                assistant_reasoning,
            )
        )
        assistant_message_context = (
            build_message_context(reasoning_content=normalized_reasoning)
        )

        if persisted_content:
            if used_reasoning_fallback:
                assistant_content = persisted_content
                await streaming_handler.write(persisted_content)
                await streaming_handler.flush()

            assistant_message = await session_manager.add_message(
                session_id=session_id,
                role="assistant",
                content=persisted_content,
                message_context=assistant_message_context,
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

            schedule_context_maintenance(
                db_session_factory=get_db_session_factory(),
                session_id=session_id,
                max_history_messages=history_limit,
                enable_short_context_summary=runtime_config.persona_config.enable_short_context_summary,
                provider=active_provider,
                model=runtime_config.model_name,
                memory_store=getattr(agent_loop.context_builder, "memory", None),
                auto_summary_source="web-chat",
            )

            # 发送完成通知
            await send_message_complete(session_id, "")
        else:
            logger.warning(f"AI响应为空")
            # 没有内容，发送空完成通知
            await send_message_complete(session_id, "")

        logger.info(f"消息处理完成 (会话 {session_id})")
        cleanup_cancel_token(session_id)

    except Exception as e:
        logger.exception(f"处理消息事件时出错: {e}")
        friendly = _friendly_processing_error(str(e))
        await send_error(
            session_id,
            friendly,
            "PROCESSING_ERROR",
        )
        cleanup_cancel_token(session_id)
    finally:
        if agent_loop.tools:
            agent_loop.tools.set_cancel_token(None)


async def handle_tool_execution(
    session_id: str,
    tool_name: str,
    arguments: Dict[str, Any],
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
    logger.debug(f"连接 {connection_id} 订阅会话 {session_id}")


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
    event_data: Dict[str, Any],
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
