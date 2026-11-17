"""频道外部编码代理直连路由。"""

import time
from typing import Dict, List, Optional

from loguru import logger

from backend.modules.agent.session_gate import get_session_gate
from backend.modules.agent.task_manager import CancellationToken
from backend.modules.channels.base import InboundMessage
from backend.modules.channels.inbound_utils import _encode_message_context
from backend.modules.config.loader import config_loader
from backend.modules.external_agents.conversation import (
    build_history_prompt,
    resolve_effective_session_mode,
)
from backend.modules.external_agents.routing import (
    extract_explicit_external_agent_request,
)


class ChannelDirectRouteMixin:
    """频道路由偏好与外部编码代理直连。"""

    def _get_route_preference_key(self, msg: InboundMessage) -> str:
        return self._get_chat_key(msg)

    def _resolve_channel_account_config(self, msg: InboundMessage):
        channel_config = getattr(config_loader.config.channels, msg.channel, None)
        if channel_config is None:
            return None

        account_id = str((msg.metadata or {}).get("account_id") or "default")
        root_account_id = str(getattr(channel_config, "account_id", "default") or "default")
        if account_id == root_account_id:
            return channel_config

        account_cfg = getattr(channel_config, "accounts", {}).get(account_id)
        return account_cfg or channel_config

    def _get_routing_preferences(self, msg: InboundMessage) -> tuple[str, str]:
        key = self._get_route_preference_key(msg)
        channel_cfg = self._resolve_channel_account_config(msg)
        if channel_cfg is None:
            channel_cfg = object()

        route_mode = str(getattr(channel_cfg, "routing_mode", "ai") or "ai").strip().lower()
        if route_mode not in {"ai", "direct"}:
            route_mode = "ai"

        coder_profile = str(
            getattr(channel_cfg, "external_coding_profile", "") or ""
        ).strip()

        if key in self._route_mode_overrides:
            route_mode = self._route_mode_overrides[key]
        if key in self._coder_profile_overrides:
            coder_profile = self._coder_profile_overrides[key]

        return route_mode, coder_profile

    def _resolve_explicit_external_coder(self, content: str) -> tuple[str, str]:
        """Resolve explicit natural-language routing like '用 codex 帮我修一下'."""
        parsed = extract_explicit_external_agent_request(content)
        if not parsed:
            return "", ""

        requested_profile, task = parsed
        external_tool = self.tool_registry.get_tool("external_coding_agent")
        registry = getattr(external_tool, "registry", None)
        if registry is None:
            return "", ""

        try:
            canonical_name = registry.resolve_profile_name(requested_profile)
            registry.resolve_profile(canonical_name)
        except Exception:
            return "", ""

        return canonical_name, task

    def _prepare_external_task(
        self,
        profile,
        task: str,
        history: List[dict],
    ) -> str:
        """根据 profile 会话模式构造实际下发任务。"""
        session_mode = resolve_effective_session_mode(profile)
        if session_mode == "stateless":
            return task
        if session_mode == "native":
            return task
        return build_history_prompt(
            task=task,
            history_messages=history,
            history_message_count=profile.history_message_count,
        )

    async def _handle_direct_coding_message(
        self,
        *,
        msg: InboundMessage,
        content: str,
        task_content: Optional[str] = None,
        session_route: Dict[str, object],
        user_message_context: dict,
        cancel_token: CancellationToken,
        coder_profile: str,
        start_time: float,
    ) -> None:
        """在 direct 路由模式下直接调用 external_coding_agent。"""
        session_id = await self._get_or_create_session(msg)
        # 外部编码代理是长任务，同样按会话串行：同一会话不允许两条指令并发下发。
        gate = get_session_gate()
        turn_acquired = False
        if gate.is_busy(session_id):
            await self._send_reply(msg, "当前会话还有任务在执行，请等它结束后再试。")
            return
        try:
            # acquire 到 release 之间的代码都在本 try 内，
            # 任何异常路径都能走到 finally 的 release。
            await gate.acquire(session_id)
            turn_acquired = True
            self._active_tasks[session_id] = cancel_token
            stream_abort_handler = msg.metadata.get('_stream_abort_handler') if msg.metadata else None
            if stream_abort_handler:
                self._register_stream_abort_callback(
                    cancel_token,
                    stream_abort_handler,
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                )

            self.tool_registry.set_message_context(
                {
                    "channel": msg.channel,
                    "sender_id": msg.sender_id,
                    "chat_id": msg.chat_id,
                    "metadata": msg.metadata,
                }
            )
            self.tool_registry.set_session_id(session_id)
            self.tool_registry.set_channel(msg.channel)
            self.tool_registry.set_cancel_token(cancel_token)
            self._reconcile_mcp_tools()

            await self._save_message(
                session_id,
                "user",
                content,
                message_context=user_message_context,
            )

            external_tool = self.tool_registry.get_tool("external_coding_agent")
            registry = getattr(external_tool, "registry", None)
            if registry is None:
                raise ValueError("external_coding_agent 工具当前不可用。")

            profile = registry.resolve_profile(coder_profile.strip() or None)
            history = await self._get_session_history(session_id)
            if history:
                history = history[:-1]
            prepared_task = self._prepare_external_task(
                profile,
                (task_content or content).strip(),
                history,
            )

            arguments = {
                "task": prepared_task,
                "mode": "run",
                "timeout": self._tool_params.get("command_timeout", 180),
                "profile": profile.name,
            }
            profile_name = profile.name

            result = await self.tool_registry.execute(
                tool_name="external_coding_agent",
                arguments=arguments,
            )

            if cancel_token.is_cancelled:
                logger.info(f"[{msg.channel}] Direct coding route cancelled for session {session_id}")
                await self._send_reply(msg, "Task cancelled")
                return

            async with self.db_session_factory() as db:
                from backend.modules.session.manager import SessionManager
                from backend.modules.tools.conversation_history import get_conversation_history

                session_manager = SessionManager(db)
                assistant_message = await session_manager.add_message(
                    session_id=session_id,
                    role="assistant",
                    content=result,
                    message_context=_encode_message_context(
                        self._build_assistant_message_context(msg, session_route)
                    ),
                )

                conversation_history = get_conversation_history()
                try:
                    await conversation_history.backfill_message_id(
                        session_id=session_id,
                        message_id=assistant_message.id,
                    )
                except Exception as e:
                    logger.warning(
                        f"[{msg.channel}] Failed to backfill direct-mode tool message_id: {e}"
                    )

            await self._send_reply(msg, result)
            duration = time.time() - start_time
            logger.info(
                f"[{msg.channel}] Direct coding route handled via profile={profile_name or 'auto'} "
                f"for session {session_id} in {duration:.2f}s"
            )
        finally:
            # 与 handle_message / _handle_team_command 的 finally 对齐：
            # 清掉本轮设置的会话上下文，避免工具注册表把 channel/session
            # 上下文残留到下一个会话的第一次工具调用。
            self.tool_registry.set_cancel_token(None)
            self.tool_registry.set_message_context(None)
            self._active_tasks.pop(session_id, None)
            if turn_acquired:
                get_session_gate().release(session_id)
