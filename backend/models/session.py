"""会话模型"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base

if TYPE_CHECKING:
    from backend.models.message import Message


def utc_now():
    """返回带时区的UTC时间"""
    return datetime.now(timezone.utc)


class Session(Base):
    """会话表"""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )
    
    # 会话总结字段（20-200字符）
    summary: Mapped[str | None] = mapped_column(String(200), nullable=True)
    summary_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    
    # 上下文滚动压缩：已总结到的消息ID（该ID及之前的消息已写入记忆）
    last_summarized_msg_id: Mapped[int | None] = mapped_column(nullable=True)

    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="session", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("idx_sessions_updated", "updated_at"),)
