"""技能分层模型：系统 / 共享 / 私有技能的注册表与用户启用状态表；撤回只改状态、不删文件。"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base

# 技能归属层级
SCOPE_SYSTEM = "system"
SCOPE_USER = "user"

# 可见范围
VISIBILITY_PRIVATE = "private"
VISIBILITY_SHARED = "shared"

# 审核状态流转
STATUS_DRAFT = "draft"
STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_REVOKED = "revoked"


class SkillRegistry(Base):
    """技能注册表：系统 / 共享 / 私有技能的统一登记处。"""

    __tablename__ = "skills_registry"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # 发布者；为空表示系统技能（admin/内置）
    owner_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    scope: Mapped[str] = mapped_column(String(16), nullable=False, default=SCOPE_USER)
    visibility: Mapped[str] = mapped_column(
        String(16), nullable=False, default=VISIBILITY_PRIVATE
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=STATUS_DRAFT)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # 版本与内容指纹：审核通过后的版本不可变，重新提交才递增
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    # 快照目录（相对全局工作区根），如 .shared-skills/<id>/1
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False, default="")

    # 可见范围：JSON 数组存用户 id；为空表示全站可见
    audience_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    reject_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    approved_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        Index("idx_skills_registry_owner", "owner_id", "scope", "status"),
        Index("idx_skills_registry_name", "name"),
        Index("idx_skills_registry_status", "status"),
    )


class UserSkillState(Base):
    """记录用户对可见技能的启用状态，用于跨工作区同步。"""

    __tablename__ = "user_skill_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    skill_id: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        Index("idx_user_skill_states_user", "user_id", "skill_id", unique=True),
    )
