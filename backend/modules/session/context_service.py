"""Unified conversation context orchestration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.models.message import Message
from backend.models.session import Session
from backend.modules.agent.memory import MemoryStore
MessageFormatter = Callable[[Message], dict[str, str]]

_CONTEXT_MAINTENANCE_TASKS: dict[str, asyncio.Task[None]] = {}
_PENDING_CONTEXT_MAINTENANCE: dict[str, "ContextMaintenanceRequest"] = {}

_AUTO_SUMMARIZE_MESSAGE_THRESHOLD = 30
_AUTO_SUMMARIZE_CHAR_THRESHOLD = 15000


def default_message_formatter(message: Message) -> dict[str, str]:
    """Default formatter for web chat style history."""
    return {
        "role": message.role,
        "content": str(message.content or ""),
    }


def build_short_summary_system_message(summary_text: str) -> dict[str, str]:
    return {
        "role": "system",
        "content": f"## Previous Conversation Summary\n\n{summary_text.strip()}",
    }


def _format_log_content(label: str, content: str) -> str:
    normalized = str(content or "").strip()
    if not normalized:
        return f"{label}: <空>"
    return f"{label}:\n{normalized}"


@dataclass
class ConversationModelContext:
    """Prepared model context for a single request."""

    history: list[dict[str, str]]
    session_summary: Optional[str]
    short_summary_used: bool
    history_limit: Optional[int]


@dataclass
class ContextMaintenanceRequest:
    db_session_factory: async_sessionmaker[AsyncSession]
    session_id: str
    max_history_messages: int
    enable_short_context_summary: bool
    provider: object
    model: Optional[str]
    message_formatter: MessageFormatter
    memory_store: Optional[MemoryStore]
    auto_summary_source: str


class ConversationContextService:
    """Single service for model context building and post-response maintenance."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_session(self, session_id: str) -> Optional[Session]:
        return await self.db.get(Session, session_id)

    async def update_session_summary(
        self,
        session_id: str,
        summary: str,
    ) -> Optional[Session]:
        """Update user-visible session summary text."""
        session = await self.get_session(session_id)
        if session is None:
            return None

        session.summary = str(summary).strip()
        session.summary_updated_at = datetime.now(timezone.utc)
        session.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def clear_session_summary(self, session_id: str) -> Optional[Session]:
        """Clear user-visible session summary text."""
        session = await self.get_session(session_id)
        if session is None:
            return None

        session.summary = None
        session.summary_updated_at = None
        session.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def build_model_context(
        self,
        *,
        session_id: str,
        max_history_messages: int,
        enable_short_context_summary: bool = False,
        message_formatter: MessageFormatter = default_message_formatter,
    ) -> ConversationModelContext:
        """Build request-time model context without blocking on new summaries."""
        session = await self.get_session(session_id)
        session_summary = session.summary if session else None

        if max_history_messages <= 0:
            messages = await self._load_messages(session_id)
            return ConversationModelContext(
                history=[message_formatter(message) for message in messages],
                session_summary=session_summary,
                short_summary_used=False,
                history_limit=None,
            )

        if session is None:
            return ConversationModelContext(
                history=[],
                session_summary=None,
                short_summary_used=False,
                history_limit=max_history_messages,
            )

        cached_summary = str(session.short_context_summary or "").strip()
        covered_until_msg_id = session.short_context_summary_msg_id
        cached_window_size = session.short_context_summary_window_size

        if (
            enable_short_context_summary
            and cached_summary
            and covered_until_msg_id is not None
            and cached_window_size == max_history_messages
        ):
            tail_messages = await self._load_messages(
                session_id,
                after_message_id=covered_until_msg_id,
            )
            logger.info(
                f"命中短期上下文摘要缓存 | 会话={session_id} | 覆盖至消息ID={covered_until_msg_id} "
                f"| 历史窗口={max_history_messages}条 | 尾部消息数={len(tail_messages)}\n"
                f"{_format_log_content('短期上下文摘要内容', cached_summary)}"
            )
            history = [build_short_summary_system_message(cached_summary)]
            history.extend(message_formatter(message) for message in tail_messages)
            return ConversationModelContext(
                history=history,
                session_summary=session_summary,
                short_summary_used=True,
                history_limit=max_history_messages,
            )

        recent_messages = await self._load_messages(
            session_id,
            limit=max_history_messages,
        )
        return ConversationModelContext(
            history=[message_formatter(message) for message in recent_messages],
            session_summary=session_summary,
            short_summary_used=False,
            history_limit=max_history_messages,
        )

    async def refresh_short_summary_cache(
        self,
        *,
        session_id: str,
        max_history_messages: int,
        enable_short_context_summary: bool = False,
        provider,
        model: Optional[str] = None,
        message_formatter: MessageFormatter = default_message_formatter,
        char_limit: int = 2000,
    ) -> bool:
        """Refresh session-level short context summary incrementally."""
        session = await self.get_session(session_id)
        if session is None:
            return False

        if (
            provider is None
            or max_history_messages <= 0
            or not enable_short_context_summary
        ):
            return await self._clear_short_summary_cache(
                session,
                reason=(
                    f"未启用短期上下文摘要（provider={provider is not None}, "
                    f"max_history_messages={max_history_messages}, "
                    f"enable_short_context_summary={enable_short_context_summary}）"
                ),
            )

        messages = await self._load_messages(session_id)
        if len(messages) <= max_history_messages:
            return await self._clear_short_summary_cache(
                session,
                reason=(
                    f"总消息数={len(messages)}，未超过历史窗口={max_history_messages}，"
                    "无需生成短期上下文摘要"
                ),
            )

        prefix_messages = messages[:-max_history_messages]
        new_covered_until_msg_id = prefix_messages[-1].id

        previous_summary = ""
        delta_messages = prefix_messages

        if (
            session.short_context_summary
            and session.short_context_summary_msg_id is not None
            and session.short_context_summary_window_size == max_history_messages
        ):
            previous_summary = str(session.short_context_summary).strip()
            previous_covered_until = session.short_context_summary_msg_id
            if previous_covered_until == new_covered_until_msg_id:
                logger.info(
                    f"短期上下文摘要无需刷新 | 会话={session_id} | 覆盖范围未变化 "
                    f"| 覆盖至消息ID={new_covered_until_msg_id}"
                )
                return False
            delta_messages = [
                message
                for message in prefix_messages
                if message.id > previous_covered_until
            ]

        if not delta_messages:
            session.short_context_summary_msg_id = new_covered_until_msg_id
            session.short_context_summary_window_size = max_history_messages
            session.short_context_summary_updated_at = datetime.now(timezone.utc)
            await self.db.commit()
            logger.info(
                f"短期上下文摘要覆盖指针已更新 | 会话={session_id} | 覆盖至消息ID={new_covered_until_msg_id} "
                f"| 历史窗口={max_history_messages}条 | 本次无需重算摘要"
            )
            return False

        summary_text = await self._summarize_short_context(
            provider=provider,
            model=model,
            messages=[message_formatter(message) for message in delta_messages],
            previous_summary=previous_summary,
            char_limit=char_limit,
        )
        summary_text = str(summary_text or "").strip()
        if not summary_text:
            logger.warning(
                f"短期上下文摘要生成结果为空 | 会话={session_id} | 覆盖至消息ID={new_covered_until_msg_id}"
            )
            return False

        session.short_context_summary = summary_text
        session.short_context_summary_msg_id = new_covered_until_msg_id
        session.short_context_summary_window_size = max_history_messages
        session.short_context_summary_updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        logger.info(
            f"短期上下文摘要已刷新 | 会话={session_id} | 覆盖至消息ID={new_covered_until_msg_id} "
            f"| 历史窗口={max_history_messages}条 | 本次压缩消息数={len(delta_messages)} "
            f"| 模式={'增量合并' if previous_summary else '首次生成'}\n"
            f"{_format_log_content('短期上下文摘要内容', summary_text)}"
        )
        return True

    async def summarize_overflow_to_memory(
        self,
        *,
        session_id: str,
        max_history_messages: int,
        provider,
        model: Optional[str] = None,
        memory_store: Optional[MemoryStore] = None,
        message_formatter: MessageFormatter = default_message_formatter,
    ) -> bool:
        """Persist overflowing history to MEMORY.md without mixing request context logic."""
        if provider is None or memory_store is None or max_history_messages <= 0:
            return False

        session = await self.get_session(session_id)
        if session is None:
            return False

        messages = await self._load_messages(session_id)
        if len(messages) <= max_history_messages:
            return False

        overflow_messages = messages[:-max_history_messages]
        last_summarized_id = session.last_summarized_msg_id or 0
        pending_messages = [
            message for message in overflow_messages if message.id > last_summarized_id
        ]
        if not pending_messages:
            return False

        to_summarize = [
            message_formatter(message)
            for message in pending_messages
            if message.role in {"user", "assistant"} and message.content
        ]

        if len(to_summarize) < 3:
            session.last_summarized_msg_id = pending_messages[-1].id
            await self.db.commit()
            return False

        from backend.modules.agent.analyzer import MessageAnalyzer
        from backend.modules.agent.prompts import OVERFLOW_SUMMARY_PROMPT

        analyzer = MessageAnalyzer()
        formatted = analyzer.format_messages_for_summary(to_summarize, max_chars=4000)
        prompt = OVERFLOW_SUMMARY_PROMPT.format(messages=formatted)

        summary_parts: list[str] = []
        async for chunk in provider.chat_stream(
            messages=[{"role": "user", "content": prompt}],
            model=model,
            temperature=0.3,
        ):
            if chunk.is_content and chunk.content:
                summary_parts.append(chunk.content)

        summary = "".join(summary_parts).strip()
        if summary and "无需记录" not in summary:
            memory_store.append_entry(source="auto-overflow", content=summary)
            logger.info(
                f"溢出历史已总结并写入记忆 | 会话={session_id} | 历史窗口={max_history_messages}条 "
                f"| 写入前溢出消息数={len(pending_messages)}\n"
                f"{_format_log_content('溢出记忆内容', summary)}"
            )
        elif summary:
            logger.info(
                f"溢出历史无需写入长期记忆 | 会话={session_id} | 检查消息数={len(pending_messages)}\n"
                f"{_format_log_content('模型返回结果', summary)}"
            )
        else:
            logger.warning(
                f"溢出历史总结结果为空 | 会话={session_id} | 检查消息数={len(pending_messages)}"
            )

        session.last_summarized_msg_id = pending_messages[-1].id
        await self.db.commit()
        return bool(summary and "无需记录" not in summary)

    async def maybe_auto_summarize_to_memory(
        self,
        *,
        session_id: str,
        provider,
        model: Optional[str] = None,
        memory_store: Optional[MemoryStore] = None,
        message_formatter: MessageFormatter = default_message_formatter,
        source: str = "web-chat",
    ) -> bool:
        """Optionally summarize the whole conversation to long-term memory."""
        if provider is None or memory_store is None:
            return False

        session = await self.get_session(session_id)
        if session is None:
            return False

        messages = await self._load_messages(session_id)
        if not messages:
            return False

        message_count = len(messages)
        current_last_message_id = messages[-1].id
        last_auto_summary_msg_id = session.auto_memory_summary_msg_id or 0
        if current_last_message_id <= last_auto_summary_msg_id:
            return False

        incremental_message_count = message_count
        if last_auto_summary_msg_id:
            incremental_message_count = sum(
                1 for message in messages if message.id > last_auto_summary_msg_id
            )
            if incremental_message_count < 30:
                return False

        total_chars = sum(
            len(message_formatter(message).get("content") or "")
            for message in messages
        )
        if (
            not last_auto_summary_msg_id
            and message_count < _AUTO_SUMMARIZE_MESSAGE_THRESHOLD
            and total_chars < _AUTO_SUMMARIZE_CHAR_THRESHOLD
        ):
            return False

        from backend.modules.agent.analyzer import MessageAnalyzer
        from backend.modules.agent.prompts import CONVERSATION_TO_MEMORY_PROMPT

        analyzer = MessageAnalyzer()
        formatted = analyzer.format_messages_for_summary(
            [message_formatter(message) for message in messages],
            max_chars=4000,
        )
        prompt = CONVERSATION_TO_MEMORY_PROMPT.format(messages=formatted)

        summary_parts: list[str] = []
        async for chunk in provider.chat_stream(
            messages=[{"role": "user", "content": prompt}],
            model=model,
            temperature=0.3,
        ):
            if chunk.is_content and chunk.content:
                summary_parts.append(chunk.content)

        summary = "".join(summary_parts).strip()
        session.auto_memory_summary_msg_id = current_last_message_id
        await self.db.commit()

        if not summary:
            logger.warning(
                f"整会话自动总结结果为空 | 会话={session_id} | 消息数={message_count}"
            )
            return False

        if "无需记录" in summary:
            logger.info(
                f"整会话自动总结判定无需写入记忆 | 会话={session_id} | 消息数={message_count} "
                f"| 增量消息数={incremental_message_count}\n"
                f"{_format_log_content('模型返回结果', summary)}"
            )
            return False

        memory_store.append_entry(source=source, content=summary)
        logger.info(
            f"整会话已自动总结并写入记忆 | 会话={session_id} | 消息数={message_count} "
            f"| 增量消息数={incremental_message_count}\n"
            f"{_format_log_content('整会话记忆内容', summary)}"
        )
        return True

    async def _load_messages(
        self,
        session_id: str,
        *,
        limit: Optional[int] = None,
        after_message_id: Optional[int] = None,
    ) -> list[Message]:
        if limit is not None:
            query = (
                select(Message)
                .where(Message.session_id == session_id)
                .order_by(Message.created_at.desc())
                .limit(limit)
            )
            if after_message_id is not None:
                query = query.where(Message.id > after_message_id)
            result = await self.db.execute(query)
            return list(reversed(list(result.scalars().all())))

        query = (
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.asc())
        )
        if after_message_id is not None:
            query = query.where(Message.id > after_message_id)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def _summarize_short_context(
        self,
        *,
        provider,
        model: Optional[str],
        messages: list[dict[str, str]],
        previous_summary: str,
        char_limit: int,
    ) -> str:
        from backend.modules.agent.analyzer import MessageAnalyzer
        from backend.modules.agent.prompts import (
            RECURSIVE_SHORT_CONTEXT_SUMMARY_PROMPT,
            SHORT_CONTEXT_SUMMARY_PROMPT,
        )

        analyzer = MessageAnalyzer()
        formatted = analyzer.format_messages_for_summary(
            messages,
            max_chars=char_limit * 2,
        )
        if not formatted:
            return ""

        if previous_summary:
            prompt = RECURSIVE_SHORT_CONTEXT_SUMMARY_PROMPT.format(
                previous_summary=previous_summary,
                past_messages=formatted,
                char_limit=char_limit,
            )
        else:
            prompt = SHORT_CONTEXT_SUMMARY_PROMPT.format(
                messages=formatted,
                char_limit=char_limit,
            )

        parts: list[str] = []
        async for chunk in provider.chat_stream(
            messages=[{"role": "user", "content": prompt}],
            model=model,
            temperature=0.3,
        ):
            if chunk.is_content and chunk.content:
                parts.append(chunk.content)

        return "".join(parts).strip()

    async def _clear_short_summary_cache(
        self,
        session: Session,
        reason: Optional[str] = None,
    ) -> bool:
        changed = any(
            (
                session.short_context_summary,
                session.short_context_summary_msg_id is not None,
                session.short_context_summary_updated_at is not None,
                session.short_context_summary_window_size is not None,
            )
        )
        if not changed:
            return False

        session.short_context_summary = None
        session.short_context_summary_msg_id = None
        session.short_context_summary_updated_at = None
        session.short_context_summary_window_size = None
        await self.db.commit()
        logger.info(
            f"短期上下文摘要缓存已清空 | 会话={session.id} | 原因={reason or '未提供'}"
        )
        return True


def schedule_context_maintenance(
    *,
    db_session_factory: async_sessionmaker[AsyncSession],
    session_id: str,
    max_history_messages: int,
    enable_short_context_summary: bool = False,
    provider,
    model: Optional[str] = None,
    message_formatter: MessageFormatter = default_message_formatter,
    memory_store: Optional[MemoryStore] = None,
    auto_summary_source: str = "web-chat",
) -> Optional[asyncio.Task[None]]:
    """Schedule post-response maintenance once per session."""
    request = ContextMaintenanceRequest(
        db_session_factory=db_session_factory,
        session_id=session_id,
        max_history_messages=max_history_messages,
        enable_short_context_summary=enable_short_context_summary,
        provider=provider,
        model=model,
        message_formatter=message_formatter,
        memory_store=memory_store,
        auto_summary_source=auto_summary_source,
    )

    existing_task = _CONTEXT_MAINTENANCE_TASKS.get(session_id)
    if existing_task is not None and not existing_task.done():
        _PENDING_CONTEXT_MAINTENANCE[session_id] = request
        return existing_task

    async def _runner(initial_request: ContextMaintenanceRequest) -> None:
        try:
            current_request = initial_request
            while True:
                logger.info(
                    f"开始后台会话上下文维护 | 会话={current_request.session_id} "
                    f"| 历史窗口={current_request.max_history_messages}条"
                )
                async with current_request.db_session_factory() as db:
                    service = ConversationContextService(db)
                    await service.refresh_short_summary_cache(
                        session_id=current_request.session_id,
                        max_history_messages=current_request.max_history_messages,
                        enable_short_context_summary=current_request.enable_short_context_summary,
                        provider=current_request.provider,
                        model=current_request.model,
                        message_formatter=current_request.message_formatter,
                    )
                    await service.summarize_overflow_to_memory(
                        session_id=current_request.session_id,
                        max_history_messages=current_request.max_history_messages,
                        provider=current_request.provider,
                        model=current_request.model,
                        memory_store=current_request.memory_store,
                        message_formatter=current_request.message_formatter,
                    )
                    await service.maybe_auto_summarize_to_memory(
                        session_id=current_request.session_id,
                        provider=current_request.provider,
                        model=current_request.model,
                        memory_store=current_request.memory_store,
                        message_formatter=current_request.message_formatter,
                        source=current_request.auto_summary_source,
                    )
                logger.info(
                    f"后台会话上下文维护完成 | 会话={current_request.session_id}"
                )

                next_request = _PENDING_CONTEXT_MAINTENANCE.pop(
                    current_request.session_id,
                    None,
                )
                if next_request is None:
                    break
                logger.info(
                    f"继续处理合并后的会话上下文维护请求 | 会话={current_request.session_id}"
                )
                current_request = next_request
        except Exception as exc:
            logger.warning(
                f"Conversation context maintenance failed for session {session_id}: {exc}"
            )
        finally:
            _PENDING_CONTEXT_MAINTENANCE.pop(session_id, None)
            current_task = _CONTEXT_MAINTENANCE_TASKS.get(session_id)
            if current_task is asyncio.current_task():
                _CONTEXT_MAINTENANCE_TASKS.pop(session_id, None)

    task = asyncio.create_task(_runner(request))
    _CONTEXT_MAINTENANCE_TASKS[session_id] = task
    return task


def reset_conversation_context_runtime_state(session_id: str) -> None:
    """清理会话级上下文维护的进程内状态。"""
    _PENDING_CONTEXT_MAINTENANCE.pop(session_id, None)

    task = _CONTEXT_MAINTENANCE_TASKS.pop(session_id, None)
    if task is not None and not task.done():
        task.cancel()
