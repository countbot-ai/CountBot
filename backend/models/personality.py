"""性格模型"""

from datetime import datetime
from typing import List

from sqlalchemy import Boolean, DateTime, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class Personality(Base):
    """性格表 - 存储 AI 性格预设"""

    __tablename__ = "personalities"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    traits: Mapped[List[str]] = mapped_column(JSON, nullable=False)  # ["暴躁", "嘴硬心软"]
    speaking_style: Mapped[str] = mapped_column(Text, nullable=False)
    icon: Mapped[str] = mapped_column(String(50), nullable=False, default="Smile")
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "traits": self.traits,
            "speaking_style": self.speaking_style,
            "icon": self.icon,
            "is_builtin": self.is_builtin,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
