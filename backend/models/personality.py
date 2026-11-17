"""性格模型"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import JSON, Boolean, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class Personality(Base):
    """性格表：内置预设与用户自建性格共用一张表"""

    __tablename__ = "personalities"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    traits: Mapped[List[str]] = mapped_column(JSON, nullable=False)  # ["暴躁", "嘴硬心软"]
    speaking_style: Mapped[str] = mapped_column(Text, nullable=False)
    icon: Mapped[str] = mapped_column(String(50), nullable=False, default="Smile")
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # 多用户归属；为空表示内置 / 管理员
    owner_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # --- 克隆人格的扩展字段（均可为空） ---
    mental_models: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSON, nullable=True)
    heuristics: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSON, nullable=True)
    expression_dna: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    # 列名避开 SQLite 保留字 values
    values: Mapped[Optional[List[str]]] = mapped_column("core_values", JSON, nullable=True)
    anti_patterns: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    tensions: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    honesty_boundaries: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    memory_anchors: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSON, nullable=True)
    # 遇到需要事实的问题时优先查证的方向，从心智模型反推
    research_dimensions: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSON, nullable=True)
    response_profile: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    # personal / public / self；为空表示普通预设
    source_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # 生成时的语料统计，用于回看与判断可信度
    source_stats: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    # 克隆产物：关系记忆、五层人格、拼接后的完整档案
    memory_doc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    persona_doc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    combined_doc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    @property
    def is_cloned(self) -> bool:
        """是否为素材克隆出来的人格，而不是普通语气预设。"""
        return bool(self.source_type) or bool(self.mental_models)

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
            "is_cloned": self.is_cloned,
            "mental_models": self.mental_models,
            "heuristics": self.heuristics,
            "expression_dna": self.expression_dna,
            "values": self.values,
            "anti_patterns": self.anti_patterns,
            "tensions": self.tensions,
            "honesty_boundaries": self.honesty_boundaries,
            "memory_anchors": self.memory_anchors,
            "research_dimensions": self.research_dimensions,
            "response_profile": self.response_profile,
            "source_type": self.source_type,
            "source_stats": self.source_stats,
            "memory_doc": self.memory_doc,
            "persona_doc": self.persona_doc,
            "combined_doc": self.combined_doc,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class PersonalityVersion(Base):
    """克隆人格的版本存档：追加素材、纠正、回滚都留一份完整快照。"""

    __tablename__ = "personality_versions"
    __table_args__ = (Index("idx_personality_versions_pid", "personality_id", "version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    personality_id: Mapped[str] = mapped_column(String(50), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    # create / append / correct / rollback
    action: Mapped[str] = mapped_column(String(20), nullable=False, default="edit")
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    memory_doc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    persona_doc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    combined_doc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # 完整字段快照，回滚时一次性恢复
    snapshot: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def to_dict(self, *, with_documents: bool = False) -> dict:
        data = {
            "id": self.id,
            "personality_id": self.personality_id,
            "version": self.version,
            "action": self.action,
            "note": self.note,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if with_documents:
            data.update(
                {
                    "memory_doc": self.memory_doc,
                    "persona_doc": self.persona_doc,
                    "combined_doc": self.combined_doc,
                }
            )
        return data


class PersonaSessionNote(Base):
    """克隆人格的对话摘要：下次聊天时用来延续关系状态。"""

    __tablename__ = "persona_session_notes"
    __table_args__ = (Index("idx_persona_session_notes", "personality_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    personality_id: Mapped[str] = mapped_column(String(50), nullable=False)
    session_id: Mapped[str] = mapped_column(String, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    mood: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    key_points: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    next_topics: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    # 生成这条摘要时会话里的消息数，用来判断是否需要再总结一次
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "personality_id": self.personality_id,
            "session_id": self.session_id,
            "summary": self.summary,
            "mood": self.mood,
            "key_points": self.key_points or [],
            "next_topics": self.next_topics or [],
            "message_count": self.message_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
