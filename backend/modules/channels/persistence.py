"""频道消息持久化与上下文构建（Mixin）

从 channels/handler.py 拆出的消息持久化方法（纯搬家，无逻辑改动）：
- 渠道临时媒体转存到工作空间持久目录
- 用户/助手消息上下文构建
- 消息落库与会话历史重建（含历史压缩）
ChannelMessageHandler 继承本 Mixin，行为与拆分前完全一致。
"""

from typing import Dict, List, Optional

from loguru import logger

from backend.models.message import Message
from backend.modules.agent.history_compactor import HistoryCompactor, should_compress
from backend.modules.channels.base import InboundMessage
from backend.modules.channels.inbound_utils import (
    _build_history_message,
    _encode_message_context,
    _resolve_session_route,
)
from backend.modules.channels.media_utils import promote_inbound_media


class ChannelPersistenceMixin:
    """频道消息持久化与上下文构建方法集合。"""

    async def _promote_inbound_media(self, msg: InboundMessage, content: str) -> str:
        """把渠道临时媒体转存到工作空间持久目录，并回填附件元信息。"""
        if not msg.media or (msg.metadata or {}).get("_media_promoted"):
            return content

        try:
            promotion = await promote_inbound_media(
                msg.channel,
                msg.media,
                account_id=str((msg.metadata or {}).get("account_id") or "default"),
            )
        except Exception as exc:
            logger.warning(f"[{msg.channel}] Failed to promote inbound media: {exc}")
            return content

        if not promotion.entries:
            return content

        for entry in promotion.entries:
            if entry.stored_path == entry.original_path:
                continue
            content = content.replace(entry.original_path, entry.stored_path)
            windows_path = entry.original_path.replace("/", "\\")
            if windows_path != entry.original_path:
                content = content.replace(windows_path, entry.stored_path)

        msg.media = promotion.media_paths or msg.media
        if promotion.attachment_items:
            msg.metadata["attachment_items"] = promotion.attachment_items
        msg.metadata["_media_promoted"] = True
        return content


    def _build_user_message_context(
        self,
        msg: InboundMessage,
        session_route: Optional[Dict[str, object]] = None,
    ) -> dict:
        session_route = session_route or _resolve_session_route(msg)
        context = {
            "channel": msg.channel,
            "role": "user",
            "sender_id": str(session_route["sender_id"]),
            "sender_name": str(session_route["sender_name"]),
            "source_account_id": str(session_route["source_account_id"]),
            "reply_account_id": str(session_route["reply_account_id"]),
            "context_owner_account_id": str(session_route["context_owner_account_id"]),
            "primary_account_id": str(session_route["primary_account_id"]),
            "session_scope": str(session_route["session_scope"]),
            "is_group": bool(session_route["is_group"]),
            "group_chat_id": (
                str(session_route["group_chat_id"])
                if session_route["is_group"]
                else None
            ),
            "thread_id": session_route.get("thread_id"),
            "target_bot_label": str(session_route["target_bot_label"]),
            "reply_bot_label": str(session_route["reply_bot_label"]),
        }
        attachment_items = (msg.metadata or {}).get("attachment_items")
        if isinstance(attachment_items, list) and attachment_items:
            context["attachment_items"] = attachment_items
        return context


    def _build_assistant_message_context(
        self,
        msg: InboundMessage,
        session_route: Optional[Dict[str, object]] = None,
    ) -> dict:
        session_route = session_route or _resolve_session_route(msg)
        return {
            "channel": msg.channel,
            "role": "assistant",
            "source_account_id": str(session_route["source_account_id"]),
            "reply_account_id": str(session_route["reply_account_id"]),
            "context_owner_account_id": str(session_route["context_owner_account_id"]),
            "primary_account_id": str(session_route["primary_account_id"]),
            "session_scope": str(session_route["session_scope"]),
            "is_group": bool(session_route["is_group"]),
            "group_chat_id": (
                str(session_route["group_chat_id"])
                if session_route["is_group"]
                else None
            ),
            "reply_bot_label": str(session_route["reply_bot_label"]),
            "target_bot_label": str(session_route["target_bot_label"]),
        }


    async def _save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        message_context: Optional[dict] = None,
    ) -> None:
        """保存消息到数据库。"""
        async with self.db_session_factory() as db:
            db.add(
                Message(
                    session_id=session_id,
                    role=role,
                    content=content,
                    message_context=_encode_message_context(message_context),
                )
            )
            await db.commit()


    async def _get_session_history(
        self,
        session_id: str,
        *,
        max_history_messages: Optional[int] = None,
        summary_provider=None,
    ) -> List[dict]:
        """获取会话历史消息。"""
        from sqlalchemy import select

        if max_history_messages is None:
            max_history_messages = self.max_history_messages
        if summary_provider is None:
            summary_provider = self.agent_loop.provider

        limit = max_history_messages if max_history_messages != -1 else None

        async with self.db_session_factory() as db:
            if limit is not None:
                query = (
                    select(Message)
                    .where(Message.session_id == session_id)
                    .order_by(Message.created_at.desc())
                    .limit(limit)
                )
                result = await db.execute(query)
                messages = list(result.scalars().all())
                message_dicts = [
                    _build_history_message(m) for m in reversed(messages)
                ]
            else:
                query = (
                    select(Message)
                    .where(Message.session_id == session_id)
                    .order_by(Message.created_at.asc())
                )
                result = await db.execute(query)
                message_dicts = [_build_history_message(m) for m in result.scalars().all()]

        if not summary_provider or not should_compress(message_dicts):
            return message_dicts

        try:
            compactor = HistoryCompactor(
                provider=summary_provider,
                min_keep_recent=10,
                threshold=15,
                char_limit=12000,
                token_threshold=80_000,
            )
            outcome = await compactor.compress_with_detail(message_dicts)
            if not outcome.ok:
                # 记录未压缩原因：静默降级会让「压缩早就失效」长期不可见
                logger.info(
                    f"[history] Compression skipped for session {session_id}: "
                    f"{outcome.reason} ({outcome.before_tokens} tokens, "
                    f"{len(message_dicts)} messages)"
                )
                return message_dicts

            logger.info(
                f"[history] Compressed session {session_id}: "
                f"{len(message_dicts)} -> {len(outcome.messages)} messages, "
                f"{outcome.before_tokens} -> {outcome.after_tokens} tokens "
                f"(saved {outcome.saved_tokens})"
            )
            return outcome.messages
        except Exception as exc:
            logger.warning(f"Failed to summarize channel history for {session_id}: {exc}")
            return message_dicts


