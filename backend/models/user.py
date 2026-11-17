"""多用户模型：用户、用户级配置、审计日志"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base

# 用户角色
ROLE_ADMIN = "admin"
ROLE_USER = "user"

# 用户状态
STATUS_PENDING = "pending"
STATUS_ACTIVE = "active"
STATUS_DISABLED = "disabled"


class User(Base):
    """用户表，管理员账号由 settings 表迁移生成。"""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    username: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False, default="")
    role: Mapped[str] = mapped_column(String, nullable=False, default=ROLE_USER)
    status: Mapped[str] = mapped_column(String, nullable=False, default=STATUS_PENDING)
    display_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # 可用对话模式：all / chat / agent；管理员始终 all
    chat_mode_policy: Mapped[str] = mapped_column(
        String(16), nullable=False, default="all", server_default="all"
    )
    # 共享模型可见范围：all / selected；selected 时由 shared_model_refs 收敛
    shared_model_scope: Mapped[str] = mapped_column(
        String(16), nullable=False, default="all", server_default="all"
    )
    # 允许使用的共享模型引用（JSON 文本，元素形如 shared:provider:model）
    shared_model_refs: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]"
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    approved_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_users_status", "status"),
        Index("idx_users_role", "role"),
    )


class UserConfig(Base):
    """用户级配置，管理员沿用全局 AppConfig 不写入本表。"""

    __tablename__ = "user_configs"

    user_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    config_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class AuditLog(Base):
    """管理审计日志，禁止写入密码、API Key 与完整 token。"""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    actor_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    action: Mapped[str] = mapped_column(String, nullable=False)
    target: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ip: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_audit_created", "created_at"),
        Index("idx_audit_action", "action"),
    )


# 通知渠道类型（纯出站，不建立长连接）
NOTIFY_SERVERCHAN = "serverchan"
NOTIFY_TELEGRAM = "telegram"
NOTIFY_FEISHU_WEBHOOK = "feishu_webhook"
NOTIFY_DINGTALK_WEBHOOK = "dingtalk_webhook"
NOTIFY_WECOM_WEBHOOK = "wecom_webhook"
NOTIFY_GENERIC_WEBHOOK = "generic_webhook"

# 复用管理员渠道的推送目标，只存引用不持有凭据
NOTIFY_SHARED_TARGET = "shared_target"

NOTIFY_TYPES = {
    NOTIFY_SERVERCHAN,
    NOTIFY_TELEGRAM,
    NOTIFY_FEISHU_WEBHOOK,
    NOTIFY_DINGTALK_WEBHOOK,
    NOTIFY_WECOM_WEBHOOK,
    NOTIFY_GENERIC_WEBHOOK,
}


class UserNotificationChannel(Base):
    """用户通知渠道，config_json 存凭证与目标，对外返回脱敏。"""

    __tablename__ = "user_notification_channels"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    config_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
