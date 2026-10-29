"""频道会话管理（Mixin）：从 handler.py 拆出的路由键/列表范围记忆、会话查找创建（含主账号群共享路由）与非主机器人问答镜像到主群会话。"""

import json
from typing import Dict, List, Optional

from loguru import logger

from backend.models.message import Message
from backend.models.session import Session
from backend.modules.channels.base import InboundMessage
from backend.modules.channels.inbound_utils import (
    _PRIMARY_ACCOUNT_ID,
    _decode_message_context,
    _encode_message_context,
    _format_bot_label,
    _resolve_session_route,
)
from backend.modules.session.manager import session_name_matches


class ChannelSessionMixin:
    """频道会话管理方法集合。"""

    def _get_chat_key(self, msg: InboundMessage) -> str:
        """返回频道内唯一聊天键。"""
        session_route = _resolve_session_route(msg)
        return (
            f"{msg.channel}:"
            f"{session_route['context_owner_account_id']}:"
            f"{session_route['session_chat_id']}"
        )


    def _remember_session_list_scope(self, msg: InboundMessage, include_all: bool) -> None:
        """记录当前聊天最近一次使用的列表范围。"""
        self._last_session_list_scope[self._get_chat_key(msg)] = "all" if include_all else "chat"


    def _get_last_session_list_scope(self, msg: InboundMessage) -> str:
        """获取当前聊天最近一次使用的列表范围，默认当前聊天。"""
        return getattr(self, "_last_session_list_scope", {}).get(self._get_chat_key(msg), "chat")


    async def _load_recent_sessions(
        self, msg: InboundMessage, include_all: bool = False, limit: int = 10
    ) -> List[Session]:
        """加载最近会话列表。"""
        from sqlalchemy import select

        query = select(Session)
        if not include_all:
            session_route = _resolve_session_route(msg)
            account_id = str(session_route["context_owner_account_id"])
            session_chat_id = str(session_route["session_chat_id"])
            prefix = f"{msg.channel}:{account_id}:{session_chat_id}"
            if account_id == _PRIMARY_ACCOUNT_ID:
                legacy_prefix = f"{msg.channel}:{session_chat_id}"
                query = query.where(
                    (session_name_matches(prefix))
                    | (session_name_matches(legacy_prefix))
                )
            else:
                query = query.where(session_name_matches(prefix))

        query = query.order_by(Session.updated_at.desc()).limit(limit)

        async with self.db_session_factory() as db:
            result = await db.execute(query)
            return list(result.scalars().all())


    async def _load_session_message_counts(self, session_ids: List[str]) -> Dict[str, int]:
        """批量加载会话消息数量。"""
        from sqlalchemy import func, select

        if not session_ids:
            return {}

        async with self.db_session_factory() as db:
            result = await db.execute(
                select(Message.session_id, func.count(Message.id))
                .where(Message.session_id.in_(session_ids))
                .group_by(Message.session_id)
            )
            return {session_id: count for session_id, count in result.all()}


    async def _get_session_by_id(self, session_id: str) -> Optional[Session]:
        """根据 ID 查找会话。"""
        from sqlalchemy import select

        async with self.db_session_factory() as db:
            result = await db.execute(select(Session).where(Session.id == session_id))
            return result.scalar_one_or_none()


    async def _get_or_create_session(self, msg: InboundMessage) -> str:
        """获取已有会话或创建新会话。"""
        if msg.metadata:
            existing_session_id = str(msg.metadata.get("session_id") or "").strip()
            if existing_session_id:
                return existing_session_id

        if hasattr(self, "_active_sessions"):
            chat_key = self._get_chat_key(msg)
            if chat_key in self._active_sessions:
                return self._active_sessions[chat_key]

        session_route = _resolve_session_route(msg)
        return await self._get_or_create_session_for_route(
            msg,
            session_route,
            cache_key=self._get_chat_key(msg),
        )


    async def _get_or_create_session_for_route(
        self,
        msg: InboundMessage,
        session_route: Dict[str, object],
        *,
        cache_key: Optional[str] = None,
    ) -> str:
        """按指定路由解析或创建会话。"""
        from sqlalchemy import select
        from datetime import datetime

        account_id = str(session_route["context_owner_account_id"])
        session_chat_id = str(session_route["session_chat_id"])
        prefix = f"{msg.channel}:{account_id}:{session_chat_id}"
        legacy_prefix = f"{msg.channel}:{session_chat_id}"
        channel_context = self._build_session_channel_context(msg, session_route)
        async with self.db_session_factory() as db:
            result = await db.execute(
                select(Session)
                .where(session_name_matches(prefix))
                .order_by(Session.created_at.desc())
                .limit(1)
            )
            session = result.scalar_one_or_none()
            if not session and account_id == "default":
                result = await db.execute(
                    select(Session)
                    .where(session_name_matches(legacy_prefix))
                    .order_by(Session.created_at.desc())
                    .limit(1)
                )
                session = result.scalar_one_or_none()
            if session:
                existing_context = _decode_message_context(getattr(session, "channel_context", None))
                if channel_context and channel_context != existing_context:
                    session.channel_context = json.dumps(channel_context, ensure_ascii=False)
                    await db.commit()
                return session.id

            import uuid
            session_name = (
                f"{msg.channel}:{account_id}:{session_chat_id}:"
                f"{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )
            session = Session(
                id=str(uuid.uuid4()),
                name=session_name,
                channel_context=(
                    json.dumps(channel_context, ensure_ascii=False)
                    if channel_context
                    else None
                ),
                )
            db.add(session)
            await db.commit()
            await db.refresh(session)
            if cache_key:
                if not hasattr(self, "_active_sessions"):
                    self._active_sessions = {}
                self._active_sessions[cache_key] = session.id
            logger.info(f"Created session {session.id} for {session_name}")
            return session.id


    def _should_mirror_to_primary_context(self, session_route: Dict[str, object]) -> bool:
        """仅在支持的群聊渠道中，把非主机器人对话镜像到主机器人主群会话。"""
        return bool(
            session_route.get("supports_primary_group_shared")
            and session_route.get("is_group")
            and str(session_route.get("source_account_id") or "") != _PRIMARY_ACCOUNT_ID
        )


    def _build_primary_group_session_route(
        self,
        session_route: Dict[str, object],
    ) -> Dict[str, object]:
        """构造主机器人群共享会话路由，不改变原始回复账号。"""
        primary_route = dict(session_route)
        primary_route.update(
            {
                "context_owner_account_id": _PRIMARY_ACCOUNT_ID,
                "primary_account_id": _PRIMARY_ACCOUNT_ID,
                "session_scope": "group_shared_primary",
                "use_primary_group_context": True,
                "context_owner_bot_label": _format_bot_label(_PRIMARY_ACCOUNT_ID),
            }
        )
        return primary_route


    async def _mirror_group_exchange_to_primary_context(
        self,
        *,
        msg: InboundMessage,
        user_content: str,
        assistant_content: str,
        session_route: Dict[str, object],
    ) -> Optional[str]:
        """把非主机器人在群里的问答镜像写入主机器人群共享会话。"""
        if not self._should_mirror_to_primary_context(session_route):
            return None

        primary_route = self._build_primary_group_session_route(session_route)
        primary_cache_key = (
            f"{msg.channel}:{primary_route['context_owner_account_id']}:"
            f"{primary_route['session_chat_id']}"
        )
        primary_session_id = await self._get_or_create_session_for_route(
            msg,
            primary_route,
            cache_key=primary_cache_key,
        )

        async with self.db_session_factory() as db:
            from backend.modules.session.manager import SessionManager

            session_manager = SessionManager(db)
            await session_manager.add_message(
                session_id=primary_session_id,
                role="user",
                content=user_content,
                message_context=_encode_message_context(
                    self._build_user_message_context(msg, primary_route)
                ),
            )
            await session_manager.add_message(
                session_id=primary_session_id,
                role="assistant",
                content=assistant_content,
                message_context=_encode_message_context(
                    self._build_assistant_message_context(msg, primary_route)
                ),
            )

        return primary_session_id

    @staticmethod


    def _build_session_channel_context(
        msg: InboundMessage,
        session_route: Optional[Dict[str, object]] = None,
    ) -> Optional[dict]:
        """构建可持久化的频道会话上下文。"""
        session_route = session_route or _resolve_session_route(msg)
        account_id = str(session_route["context_owner_account_id"])

        context = {
            "channel": msg.channel,
            "account_id": account_id,
            "sender_id": str(msg.sender_id or ""),
            "chat_id": str(session_route["session_chat_id"] or msg.chat_id or ""),
            "source_account_id": str(session_route["source_account_id"]),
            "reply_account_id": str(session_route["reply_account_id"]),
            "context_owner_account_id": str(session_route["context_owner_account_id"]),
            "primary_account_id": str(session_route["primary_account_id"]),
            "session_scope": str(session_route["session_scope"]),
            "supports_primary_group_shared": bool(session_route["supports_primary_group_shared"]),
        }

        context.update({
            "is_group": bool(session_route["is_group"]),
            "delivery_mode": "chat" if session_route["is_group"] else "user",
            "to_user": None if session_route["is_group"] else (str(msg.sender_id or "") or str(msg.chat_id or "")),
            "group_chat_id": (
                str(session_route["group_chat_id"])
                if session_route["is_group"]
                else None
            ),
            "thread_id": session_route.get("thread_id"),
        })
        return context


