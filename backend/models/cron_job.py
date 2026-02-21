"""定时任务模型"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class CronJob(Base):
    """定时任务表"""

    __tablename__ = "cron_jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    schedule: Mapped[str] = mapped_column(String, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # 渠道支持
    channel: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # "web", "feishu", "telegram" 等
    chat_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # 群组 ID 或用户 ID
    deliver_response: Mapped[bool] = mapped_column(Boolean, default=False)  # 是否发送响应到渠道
    
    # 执行状态
    last_run: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    next_run: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # "ok", "error"
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Agent 响应
    
    # 统计信息
    run_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_cron_next_run", "next_run", sqlite_where=enabled.is_(True)),
        Index("idx_cron_channel", "channel", "chat_id"),
    )
