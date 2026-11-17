"""频道单轮对话的执行、持久化与收尾。"""

import time
from typing import Dict, List, Optional

from loguru import logger

from backend.models.session import Session
from backend.modules.channels.base import InboundMessage
from backend.modules.channels.inbound_utils import (
    _WORKFLOW_META_RE,
    _encode_message_context,
    _friendly_channel_error,
    _normalize_assistant_output,
    _validate_runtime_provider,
)
from backend.modules.agent.session_gate import get_session_gate
from backend.modules.config.loader import config_loader
from backend.modules.session import (
    build_session_model_override,
    resolve_session_runtime_config,
)


class ChannelAgentTurnMixin:
    """频道单轮对话的执行、持久化与收尾。"""

    async def _resolve_runtime_config_for_session(self, session_id: str):
        """解析指定会话当前消息应使用的运行时配置。"""
        async with self.db_session_factory() as db:
            from sqlalchemy import select

            result = await db.execute(select(Session).where(Session.id == session_id))
            session = result.scalar_one_or_none()

        return resolve_session_runtime_config(config_loader.config, session)

    async def _run_streaming_turn(
        self,
        *,
        msg: InboundMessage,
        session_id: str,
        model_input: str,
        history: List[dict],
        cancel_token,
        stream_handler,
        tool_event_handler,
        model_override: Dict,
        persona_override,
        prefer_direct_workflow_result: bool,
    ) -> tuple[str, str]:
        """流式执行一轮 Agent 对话，实时发送每个 chunk。"""
        response_parts: List[str] = []
        reasoning_parts: List[str] = []

        async def reasoning_event_handler(reasoning_chunk: str) -> None:
            if not reasoning_chunk:
                return
            reasoning_parts.append(reasoning_chunk)
            await stream_handler(
                reasoning_chunk,
                is_final=False,
                is_reasoning=True,
            )

        async for chunk in self.agent_loop.process_message(
            message=model_input,
            session_id=session_id,
            context=history,
            media=msg.media,
            channel=msg.channel,
            chat_id=msg.chat_id,
            account_id=str((msg.metadata or {}).get("account_id") or "").strip() or None,
            cancel_token=cancel_token,
            yield_intermediate=True,
            model_override=model_override,
            persona_override=persona_override,
            tool_event_handler=tool_event_handler,
            reasoning_event_handler=reasoning_event_handler,
            prefer_direct_workflow_result=prefer_direct_workflow_result,
            pending_message_provider=lambda: get_session_gate().take_pending(session_id),
        ):
            if cancel_token.is_cancelled:
                break
            response_parts.append(chunk)
            await stream_handler(chunk, is_final=False)

        response, response_reasoning = _normalize_assistant_output(
            "".join(response_parts),
            "".join(reasoning_parts),
        )
        if not response and response_reasoning:
            response = "抱歉，这次没有整理出可发送的回复，请重试。"
        if not cancel_token.is_cancelled:
            await stream_handler("", is_final=True)
        return response, response_reasoning

    async def _persist_and_send_response(
        self,
        *,
        msg: InboundMessage,
        session_id: str,
        content: str,
        response: str,
        response_reasoning: str,
        session_route: Dict[str, object],
        stream_handler,
        start_time: float,
    ) -> None:
        """保存助手回复（含镜像与工具记录回填），并在非流式模式下发送。"""
        assistant_message_context = _encode_message_context(
            {
                **self._build_assistant_message_context(msg, session_route),
                **({"reasoning_content": response_reasoning} if response_reasoning else {}),
            }
        )
        # 保存消息到数据库
        async with self.db_session_factory() as db:
            from backend.modules.session.manager import SessionManager
            session_manager = SessionManager(db)

            assistant_message = await session_manager.add_message(
                session_id=session_id,
                role="assistant",
                content=response,
                message_context=assistant_message_context,
            )

            # 回填 message_id 到工具调用记录
            try:
                from backend.modules.tools.conversation_history import get_conversation_history
                conversation_history = get_conversation_history()
                updated_count = await conversation_history.backfill_message_id(
                    session_id=session_id,
                    message_id=assistant_message.id,
                )
                if updated_count > 0:
                    logger.info(
                        f"[{msg.channel}] Backfilled message_id={assistant_message.id} "
                        f"to {updated_count} tool conversations"
                    )
            except Exception as e:
                logger.warning(f"[{msg.channel}] Failed to backfill message_id: {e}")

        try:
            mirrored_session_id = await self._mirror_group_exchange_to_primary_context(
                msg=msg,
                user_content=content,
                assistant_content=response,
                session_route=session_route,
            )
            if mirrored_session_id:
                logger.info(
                    f"[{msg.channel}] Mirrored group exchange to primary session "
                    f"{mirrored_session_id} from account={session_route['source_account_id']}"
                )
        except Exception as e:
            logger.warning(f"[{msg.channel}] Failed to mirror group exchange: {e}")

        # 剥离工作流元数据注释
        channel_response = _WORKFLOW_META_RE.sub("", response).strip()

        # 非流式模式才需要发送回复
        if not stream_handler:
            await self._send_reply(msg, channel_response or response)

        duration = time.time() - start_time
        logger.info(f"[{msg.channel}] Handled session {session_id} in {duration:.2f}s")

    async def _cleanup_turn(
        self,
        *,
        msg: InboundMessage,
        session_id: Optional[str],
        cancel_token,
        turn_token_acquired: bool,
        typing_session_key: Optional[str],
    ) -> None:
        """本轮收尾：关闭 typing、清理工具上下文、释放闸门并重投未消费插话。"""
        await self._maybe_stop_channel_typing(msg, typing_session_key)
        workflow_tool = self.tool_registry.get_tool("workflow_run")
        if workflow_tool and hasattr(workflow_tool, "set_event_callback"):
            workflow_tool.set_event_callback(None)
        self.tool_registry.set_message_context(None)
        # 只清理自己登记的令牌：并发排队时后者不能误删前者的引用
        if session_id and self._active_tasks.get(session_id) is cancel_token:
            del self._active_tasks[session_id]
        if turn_token_acquired:
            # 本轮结束前若还有未被消费的插话（例如本轮被取消、异常退出，
            # 或直接按 workflow 结果返回），将其重新投递回队列，
            # 由下一轮继续处理，避免消息滞留在内存队列。
            leftover = get_session_gate().drain_pending(session_id)
            if leftover and not cancel_token.is_cancelled:
                try:
                    requeue_metadata = dict(msg.metadata or {})
                    # 这些内容在登记为插话时已经落库，重新处理时不能再写一次；
                    # 同时清掉本轮残留的流式回调，避免旧的发送句柄被复用。
                    requeue_metadata["_persisted"] = True
                    requeue_metadata.pop("_stream_handler", None)
                    requeue_metadata.pop("_stream_abort_handler", None)
                    requeue_metadata.pop("_tool_event_handler", None)
                    await self.bus.publish_inbound(
                        InboundMessage(
                            channel=msg.channel,
                            sender_id=msg.sender_id,
                            chat_id=msg.chat_id,
                            content="\n".join(leftover),
                            media=None,
                            metadata=requeue_metadata,
                        )
                    )
                    logger.info(
                        f"[{msg.channel}] Re-queued {len(leftover)} unconsumed "
                        f"message(s) for session {session_id}"
                    )
                except Exception as exc:
                    logger.warning(
                        f"[{msg.channel}] Failed to re-queue unconsumed messages: {exc}"
                    )
            get_session_gate().release(session_id)

    async def _process_with_agent(
        self,
        session_id: str,
        user_message: str,
        history: List[dict],
        cancel_token,
        media: Optional[List[str]] = None,
        channel: Optional[str] = None,
        chat_id: Optional[str] = None,
        account_id: Optional[str] = None,
        runtime_config=None,
        tool_event_handler=None,
        prefer_direct_workflow_result: bool = False,
    ) -> tuple[str, str]:
        """运行 Agent 循环并收集响应。"""
        try:
            if runtime_config is None:
                runtime_config = await self._resolve_runtime_config_for_session(session_id)

            _validate_runtime_provider(runtime_config)
            model_override = build_session_model_override(runtime_config, force=True)
            persona_override = runtime_config.persona_config

            parts = []
            reasoning_parts = []

            async def reasoning_event_handler(reasoning_chunk: str) -> None:
                if reasoning_chunk:
                    reasoning_parts.append(reasoning_chunk)

            async for chunk in self.agent_loop.process_message(
                message=user_message,
                session_id=session_id,
                context=history,
                media=media,
                channel=channel,
                chat_id=chat_id,
                account_id=account_id,
                cancel_token=cancel_token,
                yield_intermediate=True,  # 启用流式输出
                model_override=model_override,
                persona_override=persona_override,
                tool_event_handler=tool_event_handler,
                reasoning_event_handler=reasoning_event_handler,
                prefer_direct_workflow_result=prefer_direct_workflow_result,
                pending_message_provider=lambda: get_session_gate().take_pending(session_id),
            ):
                if cancel_token.is_cancelled:
                    break
                parts.append(chunk)
            result, normalized_reasoning = _normalize_assistant_output(
                "".join(parts),
                "".join(reasoning_parts),
            )
            return (
                result
                or (
                    "抱歉，这次没有整理出可发送的回复，请重试。"
                    if normalized_reasoning
                    else "抱歉，未能生成回复，请稍后重试。"
                ),
                normalized_reasoning,
            )
        except Exception as e:
            logger.error(f"Agent processing error: {e}")
            return _friendly_channel_error(str(e)), ""
