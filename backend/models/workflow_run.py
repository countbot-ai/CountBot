"""Dynamic Workflow 的持久化运行记录。"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    session_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    workspace: Mapped[str] = mapped_column(Text, nullable=False)
    program_json: Mapped[str] = mapped_column(Text, nullable=False)
    program_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    args_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(String, nullable=False, default="running")
    stop_reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    caps_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    spent_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    failure_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resumed_from: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow,
    )

    __table_args__ = (
        Index("idx_workflow_runs_owner", "owner_id", "created_at"),
        Index("idx_workflow_runs_session", "session_id", "created_at"),
    )


class WorkflowTemplate(Base):
    __tablename__ = "workflow_templates"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    program_json: Mapped[str] = mapped_column(Text, nullable=False)
    program_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow,
    )

    __table_args__ = (
        Index("idx_workflow_templates_owner", "owner_id", "name"),
    )


class WorkflowActor(Base):
    __tablename__ = "workflow_actors"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(String, nullable=False)
    actor_id: Mapped[str] = mapped_column(String, nullable=False)
    site_id: Mapped[str] = mapped_column(String, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    persona_json: Mapped[str] = mapped_column(Text, nullable=False)
    resolved_model_ref: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    session_ref: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    next_ask_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_workflow_actors_run_actor", "run_id", "actor_id", unique=True),
    )


class WorkflowAsk(Base):
    __tablename__ = "workflow_asks"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(String, nullable=False)
    site_id: Mapped[str] = mapped_column(String, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_id: Mapped[str] = mapped_column(String, nullable=False)
    actor_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    instructions_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    input_json: Mapped[str] = mapped_column(Text, nullable=False)
    schema_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    result_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    stats_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_workflow_asks_instance", "run_id", "site_id", "ordinal", unique=True),
        Index("idx_workflow_asks_actor_seq", "run_id", "actor_id", "actor_seq"),
    )


class WorkflowEvent(Base):
    __tablename__ = "workflow_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_workflow_events_sequence", "run_id", "sequence", unique=True),
    )
