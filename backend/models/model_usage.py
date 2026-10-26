"""模型用量数据模型：按「一次请求」粒度记录 token 与缓存命中，用于成本核算。"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base

# 请求用途分类，便于把成本拆到「对话 / 摘要 / 压缩 / 子任务」等具体来源
USAGE_KIND_CHAT = "chat"
USAGE_KIND_SUMMARY = "summary"
USAGE_KIND_COMPACTION = "compaction"
USAGE_KIND_SUBAGENT = "subagent"
USAGE_KIND_OTHER = "other"


def utc_now():
    """返回带时区的 UTC 时间。"""
    return datetime.now(timezone.utc)


class ModelUsage(Base):
    """模型用量记录表"""

    __tablename__ = "model_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    provider: Mapped[str | None] = mapped_column(String, nullable=True)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    # 本轮对话内的第几次模型调用，从 1 开始
    turn_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 用途分类，取 USAGE_KIND_* 之一
    kind: Mapped[str] = mapped_column(String, nullable=False, default=USAGE_KIND_CHAT)

    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 命中提示词缓存复用的 token（越低越贵）
    cache_read_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 写入提示词缓存的 token
    cache_write_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 推理 token（部分供应商单独计价）
    reasoning_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    __table_args__ = (
        Index("idx_model_usage_session", "session_id", "created_at"),
        Index("idx_model_usage_kind", "kind", "created_at"),
    )
