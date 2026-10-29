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
    account_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # 机器人账号 ID（多机器人渠道）
    chat_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # 群组 ID 或用户 ID
    deliver_response: Mapped[bool] = mapped_column(Boolean, default=False)  # 是否发送响应到渠道

    # 本任务使用的模型；留空表示跟随全局默认模型
    model_provider: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # 供应商 ID
    model_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # 模型名
    
    # 执行状态
    last_run: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    next_run: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # "running", "ok", "error", "retrying", "skipped"
    last_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Agent 响应

    # 渠道推送状态：推送失败需要与 AI 执行失败区分开，失败原因单独留存
    last_delivery_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # "ok", "failed", "skipped"
    last_delivery_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # 统计信息
    run_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # 重试机制
    retry_count: Mapped[int] = mapped_column(Integer, default=0)  # 当前重试次数
    max_retries: Mapped[int] = mapped_column(Integer, default=0)  # 最大重试次数（0=不重试）
    retry_delay: Mapped[int] = mapped_column(Integer, default=60)  # 重试延迟（秒）
    
    # 自动删除
    delete_on_success: Mapped[bool] = mapped_column(Boolean, default=False)  # 成功后自动删除

    # 关联上下文：开启后每次执行会把该任务的历史执行记录一起发给模型
    link_context: Mapped[bool] = mapped_column(Boolean, default=False)
    context_history: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_cron_next_run", "next_run", sqlite_where=enabled.is_(True)),
        Index("idx_cron_channel", "channel", "account_id", "chat_id"),
    )
