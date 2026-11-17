"""WebSocket 消息事件处理：消息接收与校验、Agent 处理集成、流式推送、工具调用通知与错误处理。"""

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import WebSocket
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db, get_db_session_factory
from backend.modules.agent.loop import AgentLoop
from backend.modules.agent.session_gate import get_session_gate
from backend.modules.tools.execution import ExecutionState, ToolExecutionInProgress, ToolExecutionRejected
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
    send_native_event,
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
    """用户显式点名外部编码代理时，仍然走 WebSocket 常规工具调用链路。"""
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
    if augmented_context and augmented_context[0].get("role") == "system":
        existing_content = str(augmented_context[0].get("content", "") or "")
        separator = "\n\n" if existing_content else ""
        augmented_context[0] = {
            **augmented_context[0],
            "content": f"{existing_content}{separator}{system_message}",
        }
    else:
        augmented_context.insert(0, {"role": "system", "content": system_message})
    return augmented_context


# ============================================================================
# 消息事件处理
# ============================================================================


async def _resolve_ws_runtime(
    agent_loop: AgentLoop,
    session_id: str,
    session,
    runtime_config,
    user=None,
) -> Optional[tuple]:
    """校验 provider 可用性并解析执行参数，不可用时发送分类错误。"""
    if user is not None and not getattr(user, "is_admin", False):
        # 用户级 provider/persona 已按用户配置构建，会话配置不能覆盖 provider
        # 绑定与密钥；但思考档位、输出模式、采样参数等纯生成参数必须生效，
        # 否则会话面板里的「思考强度 / 输出模式」对普通用户形同虚设。
        session_override = build_session_model_override(runtime_config, force=False)
        if session_override:
            for key in ("provider", "model", "api_key", "api_base"):
                session_override.pop(key, None)
        # 会话级自定义人设（自定义系统提示词等）对普通用户同样生效：以用户自身
        # 人设为基底，只叠加会话里显式改动的字段，绝不继承管理员全局人设。
        persona_override = None
        if getattr(runtime_config, "has_custom_persona_config", False):
            base_persona = getattr(
                getattr(agent_loop, "context_builder", None), "persona_config", None
            )
            if base_persona is not None:
                persona_override = base_persona.model_copy(deep=True)
                for field_name, value in (runtime_config.persona_overrides or {}).items():
                    if value is not None and hasattr(persona_override, field_name):
                        setattr(persona_override, field_name, value)
        return session_override or None, persona_override, agent_loop.provider

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
        return None

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

    active_provider, _, _, _, _, _, _, _ = agent_loop._resolve_execution_runtime(
        model_override
    )
    return model_override, persona_override, active_provider


async def _persist_user_message_and_build_context(
    session_manager: SessionManager,
    db: AsyncSession,
    session_id: str,
    content: str,
    attachment_items: list,
    history_limit: int,
    enable_short_context_summary: bool,
) -> Optional[tuple]:
    """保存用户消息并构建模型上下文，失败时发送 DATABASE_ERROR。"""
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
        return None

    logger.info(f"用户消息已保存: ID={user_message.id}")

    context_service = ConversationContextService(db)
    context_payload = await context_service.build_model_context(
        session_id=session_id,
        max_history_messages=history_limit,
        enable_short_context_summary=enable_short_context_summary,
    )
    context = context_payload.history
    if context and context[-1].get("role") == "user":
        context = context[:-1]

    return user_message, context, context_payload


def _inject_ws_tool_context(
    agent_loop: AgentLoop,
    session_id: str,
    cancel_token,
    user=None,
) -> None:
    """把会话上下文注入工具注册表，并对齐 MCP 工具集与禁用列表。"""
    if not agent_loop.tools:
        return

    agent_loop.tools.set_session_id(session_id)
    agent_loop.tools.set_cancel_token(cancel_token)
    logger.debug(f"Propagated session_id={session_id} to tool registry")

    # 先按最新配置重建工具集，避免随后清掉刚注册的 MCP 工具
    try:
        # 不要在此重复 import config_loader，局部 import 会导致 UnboundLocalError
        from backend.modules.tools.setup import sync_disabled_tools

        sync_disabled_tools(
            agent_loop.tools,
            config_loader.config.injection.disabled_tools,
        )
    except Exception as e:
        logger.debug(f"Disabled-tools sync skipped: {e}")

    # 每条消息前对齐 MCP 工具集，并保留用户自建的 ``mcp__usr-`` 命名空间
    try:
        from backend.modules.multiuser.settings import MODE_SHARED, peek_settings
        from backend.modules.multiuser.user_mcp import USER_TOOL_PREFIX
        from backend.modules.mcp.client import McpClientManager

        # 用户私有运行时即使调用方没传 user，也不能获得全局 MCP
        is_regular_runtime = getattr(agent_loop.tools, "user_mcp_owner", None) is not None
        is_admin = (
            not is_regular_runtime
            and (user is None or bool(getattr(user, "is_admin", True)))
        )
        settings = peek_settings()
        if is_admin or (
            settings.enabled
            and settings.mode == MODE_SHARED
            and settings.shared_skills_wiki_mcp
        ):
            McpClientManager.get_instance().reconcile_registry_sync(
                agent_loop.tools,
                keep_prefixes=() if is_admin else (USER_TOOL_PREFIX,),
            )

        # 用户自建 MCP：管理员总开关关闭时立即摘除已注册的工具
        if not settings.allow_user_mcp:
            for name in list(agent_loop.tools.list_tools()):
                if name.startswith(USER_TOOL_PREFIX):
                    agent_loop.tools.unregister(name)
            owner_id = getattr(agent_loop.tools, "user_mcp_owner", None)
            if owner_id:
                from backend.modules.multiuser.user_mcp import user_mcp_manager

                user_mcp_manager.schedule_disconnect(owner_id)
        else:
            user_manager = getattr(agent_loop.tools, "user_mcp_manager", None)
            if user_manager is not None:
                user_manager.reconcile_registry_sync(
                    agent_loop.tools,
                    prefix=USER_TOOL_PREFIX,
                )
    except Exception as e:
        logger.debug(f"MCP reconcile skipped: {e}")


async def _persist_ws_exchange(
    session_manager: SessionManager,
    db: AsyncSession,
    session_id: str,
    agent_loop: AgentLoop,
    runtime_config,
    active_provider,
    assistant_content: str,
    assistant_reasoning: str,
    streaming_handler,
    history_limit: int,
    model_name: Optional[str] = None,
    native_events: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """持久化助手回复并触发上下文维护与完成通知。"""
    persisted_content, normalized_reasoning, used_reasoning_fallback = (
        normalize_assistant_persistence_payload(
            assistant_content,
            assistant_reasoning,
        )
    )
    assistant_message_context = (
        build_message_context(
            reasoning_content=normalized_reasoning,
            native_events=native_events,
        )
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
            model=model_name or runtime_config.model_name,
            memory_store=getattr(agent_loop.context_builder, "memory", None),
            auto_summary_source="web-chat",
            enable_auto_memory_summary=config_loader.config.injection.auto_memory_summary,
        )

        # 发送完成通知
        await send_message_complete(session_id, "")
    else:
        logger.warning(f"AI响应为空")
        # 没有内容，发送空完成通知
        await send_message_complete(session_id, "")


async def handle_message_event(
    connection_id: str,
    message: ClientMessage,
    agent_loop: AgentLoop,
    db: AsyncSession,
    loop_factory=None,
    user=None,
) -> None:
    """处理客户端消息事件"""
    session_id = message.session_id
    turn_gate_acquired = False
    token_registered = False
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
        from backend.modules.multiuser.permissions import owner_scope

        owner_id = owner_scope(user) if user is not None else None
        is_admin_connection = bool(getattr(user, "is_admin", False))

        # 先校验归属再绑定，避免他人用 sessionId 劫持流式输出
        session_manager = SessionManager(db, owner_id=owner_id)
        session = await session_manager.get_session(session_id)

        if session is None:
            logger.warning(f"会话不存在或无权访问: {session_id}")
            await send_error(
                session_id,
                f"Session '{session_id}' not found",
                "SESSION_NOT_FOUND",
            )
            return

        await connection_manager.bind_session(
            connection_id,
            session_id,
            owner_id=getattr(session, "owner_id", None),
            allow_any_owner=is_admin_connection,
        )

        # 获取取消令牌
        from backend.ws.connection import get_cancel_token, cleanup_cancel_token
        cancel_token = get_cancel_token(session_id)
        token_registered = True

        logger.info(f"会话验证通过: {session_id}")

        # 会话指定了自定义工作空间时，切换到该工作空间专属的 AgentLoop
        if loop_factory is not None:
            agent_loop = loop_factory(session)

        from backend.modules.workspace import resolve_session_workspace, resolve_user_workspace

        session_workspace = (
            resolve_session_workspace(session)
            if user is None or getattr(user, "is_admin", False)
            else resolve_user_workspace(user)
        )

        try:
            resolved_attachments = _resolve_attachment_inputs(
                message.attachments,
                session_workspace,
            )
        except ValueError as exc:
            await send_error(session_id, str(exc), "INVALID_ATTACHMENT")
            return

        attachment_items = build_attachment_items_from_workspace(resolved_attachments)
        attachment_paths = [relative_path for relative_path, _ in resolved_attachments]

        runtime_config = resolve_session_runtime_config(config_loader.config, session)
        from backend.modules.multiuser.identity import resolve_chat_mode_for_user

        chat_mode = resolve_chat_mode_for_user(
            user, getattr(runtime_config, "chat_mode", "agent")
        )
        runtime_config.chat_mode = chat_mode
        resolved = await _resolve_ws_runtime(
            agent_loop, session_id, session, runtime_config, user=user
        )
        if resolved is None:
            return
        model_override, persona_override, active_provider = resolved
        is_regular_connection = user is not None and not getattr(user, "is_admin", False)
        effective_model_name = (
            getattr(agent_loop, "model", None) or runtime_config.model_name
            if is_regular_connection
            else runtime_config.model_name
        )

        # 同一会话串行处理，用户消息在本轮开始处理前写入
        turn_gate = get_session_gate()
        await turn_gate.acquire(session_id)
        turn_gate_acquired = True

        history_limit = runtime_config.persona_config.max_history_messages
        persisted = await _persist_user_message_and_build_context(
            session_manager, db, session_id, content,
            attachment_items, history_limit,
            runtime_config.persona_config.enable_short_context_summary,
        )
        if persisted is None:
            return
        user_message, context, context_payload = persisted

        # 首条消息后异步补会话标题：不拼接历史/工具，失败保持默认名，不阻塞主对话
        try:
            from backend.modules.session.title import (
                maybe_schedule_session_title_generation,
            )

            await maybe_schedule_session_title_generation(
                session=session,
                session_id=session_id,
                input_text=content,
                provider=active_provider or getattr(agent_loop, "provider", None),
                model=effective_model_name,
            )
        except Exception as exc:  # noqa: BLE001 - 标题生成不影响主流程
            logger.debug(f"会话标题生成调度跳过：{exc}")

        logger.info(f"开始AI处理，上下文消息数: {len(context)}")

        _inject_ws_tool_context(agent_loop, session_id, cancel_token, user=user)
        # 对话模式不提供工具，显式外部代理指令也不注入
        explicit_external_request = (
            None
            if chat_mode == "chat"
            else _resolve_explicit_external_tool_request(agent_loop, content)
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
        native_events_buffer: List[Dict[str, Any]] = []

        async def reasoning_event_handler(reasoning_chunk: str) -> None:
            nonlocal assistant_reasoning
            assistant_reasoning += reasoning_chunk or ""
            await send_reasoning_chunk(session_id, reasoning_chunk)

        async def native_event_handler(event: Dict[str, Any]) -> None:
            native_events_buffer.append(event)
            if event.get("kind") != "history_blocks":
                await send_native_event(session_id, event)

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
            native_event_handler=native_event_handler,
            prefer_direct_workflow_result=prefer_direct_workflow_result,
            chat_mode=chat_mode,
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

        await _persist_ws_exchange(
            session_manager, db, session_id, agent_loop, runtime_config,
            active_provider, assistant_content, assistant_reasoning,
            streaming_handler, history_limit, effective_model_name,
            native_events=native_events_buffer,
        )

        logger.info(f"消息处理完成 (会话 {session_id})")

    except Exception as e:
        logger.exception(f"处理消息事件时出错: {e}")
        friendly = _friendly_processing_error(str(e))
        await send_error(
            session_id,
            friendly,
            "PROCESSING_ERROR",
        )
    finally:
        if agent_loop.tools:
            agent_loop.tools.set_cancel_token(None)
        if turn_gate_acquired:
            get_session_gate().release(session_id)
        # 统一在 finally 清理，覆盖各类提前返回路径
        if token_registered:
            cleanup_cancel_token(session_id, cancel_token)


async def handle_tool_execution(
    session_id: str,
    tool_name: str,
    arguments: Dict[str, Any],
    agent_loop: AgentLoop,
    user=None,
) -> None:
    """处理工具执行事件；由通知封装消费 Registry 结构化结果。"""
    from backend.ws.connection import acquire_cancel_token, cleanup_cancel_token
    from backend.ws.tool_notifications import execute_tool_with_notifications

    # 手动触发的工具执行也登记取消令牌，使 /stop 能中断长命令
    tool_registry = getattr(agent_loop, "tools", None)
    cancel_token, token_created = acquire_cancel_token(session_id)
    if tool_registry:
        _inject_ws_tool_context(agent_loop, session_id, cancel_token, user=user)

    try:
        logger.info(f"执行工具 {tool_name} (会话 {session_id})")

        # 使用增强的工具通知执行
        result = await execute_tool_with_notifications(
            session_id=session_id,
            tool_name=tool_name,
            arguments=arguments,
            executor=agent_loop.execute_tool,
        )

        if not isinstance(result, (ToolExecutionInProgress, ToolExecutionRejected)):
            # 通知层返回 Registry 终态后记录元数据；准入中的 attempt 不写终态审计。
            from backend.modules.tools.file_audit_logger import file_audit_logger
            file_audit_logger.record_outcome(
                result, source="websocket", session_id=session_id,
            )

        if isinstance(result, ToolExecutionInProgress):
            logger.info(f"工具仍在执行: {tool_name}")
        elif isinstance(result, ToolExecutionRejected):
            logger.warning(f"工具请求被拒绝: {tool_name}, reason={result.reason}")
        elif result.state is ExecutionState.SUCCEEDED:
            logger.info(f"工具执行完成: {tool_name}")
        else:
            logger.warning(f"工具执行未成功: {tool_name}, state={result.state.value}")

    except Exception as e:
        logger.exception(f"工具执行失败: {e}")
        # 错误已经在 execute_tool_with_notifications 中通知了
    finally:
        if tool_registry:
            tool_registry.set_cancel_token(None)
        # 仅清理自己新建的令牌，避免摘掉并行消息回合正在使用的那个
        if token_created:
            cleanup_cancel_token(session_id, cancel_token)


async def handle_ping_event(connection_id: str) -> None:
    """处理心跳事件"""
    from backend.ws.connection import ServerMessage

    await connection_manager.send_message(
        connection_id,
        ServerMessage(type="pong"),
    )


async def handle_subscribe_event(
    connection_id: str,
    session_id: str,
    user=None,
    db=None,
) -> None:
    """处理订阅事件（必须校验会话归属）"""
    from backend.modules.multiuser.permissions import owner_scope

    owner_id = None
    if db is not None:
        session_manager = SessionManager(db, owner_id=owner_scope(user) if user is not None else None)
        session = await session_manager.get_session(session_id)
        if session is None:
            await send_error(session_id, f"Session '{session_id}' not found", "SESSION_NOT_FOUND")
            return
        owner_id = getattr(session, "owner_id", None)
    elif user is not None:
        owner_id = owner_scope(user)

    await connection_manager.bind_session(
        connection_id,
        session_id,
        owner_id=owner_id,
        allow_any_owner=bool(getattr(user, "is_admin", False)),
    )
    logger.debug(f"连接 {connection_id} 订阅会话 {session_id}")


async def handle_unsubscribe_event(
    connection_id: str,
    session_id: str,
) -> None:
    """处理取消订阅事件"""
    # 当前 ConnectionManager 不支持取消订阅单个会话，此处仅记录日志
    logger.info(f"连接 {connection_id} 取消订阅会话 {session_id}")


# ============================================================================
# 事件路由
# ============================================================================


async def route_event(
    connection_id: str,
    event_type: str,
    event_data: Dict[str, Any],
    agent_loop: AgentLoop,
    db: AsyncSession,
    loop_factory=None,
    user=None,
) -> None:
    """路由事件到对应的处理器"""
    try:
        if event_type == "message":
            # 处理消息事件
            message = ClientMessage(**event_data)
            await handle_message_event(
                connection_id,
                message,
                agent_loop,
                db,
                loop_factory=loop_factory,
                user=user,
            )

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

            # 手动执行工具同样要使用会话级工作空间；会话必须存在且归属当前用户，
            # 否则会把手动执行的工具结果写进他人会话。
            from backend.modules.multiuser.permissions import owner_scope

            session = await SessionManager(
                db,
                owner_id=owner_scope(user) if user is not None else None,
            ).get_session(session_id)
            if session is None:
                await send_error(session_id, "会话不存在或无权访问", "SESSION_NOT_FOUND")
                return
            if loop_factory is not None:
                agent_loop = loop_factory(session)

            await handle_tool_execution(session_id, tool_name, arguments, agent_loop, user=user)

        elif event_type == "ping":
            # 处理心跳事件
            await handle_ping_event(connection_id)

        elif event_type == "subscribe":
            # 处理订阅事件
            session_id = event_data.get("sessionId")
            if not session_id:
                logger.warning("订阅事件缺少 sessionId")
                return

            await handle_subscribe_event(connection_id, session_id, user=user, db=db)

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
# WebSocket 事件循环
# ============================================================================


async def websocket_event_loop(
    websocket: WebSocket,
    connection_id: str,
    agent_loop: AgentLoop,
    loop_factory=None,
    user=None,
) -> None:
    """WebSocket 事件循环：持续监听和处理 WebSocket 事件，直到连接断开。"""
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
                            loop_factory=loop_factory,
                            user=user,
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
