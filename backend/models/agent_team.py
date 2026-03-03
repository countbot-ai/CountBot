"""Agent Team model — persists user-defined multi-agent workflow templates."""

from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import Boolean, DateTime, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class AgentTeam(Base):
    """
    Stores a user-defined multi-agent workflow template.

    agents column holds a JSON list of agent definitions:
    [
        {
            "id": "researcher",
            "role": "Research Expert",
            "task": "Thoroughly research the given topic",
            "depends_on": []          # used only in graph mode
        },
        ...
    ]
    """

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
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

