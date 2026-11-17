"""Agent Team model — persists user-defined multi-agent workflow templates."""

from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import Boolean, DateTime, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class AgentTeam(Base):
    """User-defined multi-agent workflow template; agents stores a JSON list of agent definitions."""

    __tablename__ = "agent_teams"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Orchestration mode: "pipeline" | "graph" | "council"
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="pipeline")

    # JSON array of agent definitions (see docstring above)
    agents: Mapped[List[Any]] = mapped_column(JSON, nullable=False, default=list)

    # Whether this team appears as an option in the UI
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Council mode only: whether to enable cross-review between members
    cross_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Whether to inject skills system into subagents
    enable_skills: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Team-level model configuration (optional)
    team_model_config: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    use_custom_model: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # 多用户归属；为空表示管理员 / 历史数据
    owner_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "mode": self.mode,
            "agents": self.agents or [],
            "is_active": self.is_active,
            "cross_review": self.cross_review,
            "enable_skills": self.enable_skills,
            "use_custom_model": self.use_custom_model,
            "owner_id": self.owner_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

