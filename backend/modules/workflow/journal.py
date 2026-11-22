"""SQLite journal：跨进程恢复的事实源，与工具内 ledger 分离。"""

import hashlib
import json
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.database import Base
from backend.models.workflow_run import (
    WorkflowActor,
    WorkflowAsk,
    WorkflowEvent,
    WorkflowRun,
    WorkflowTemplate,
)
from backend.modules.workflow.ask_result import AskResult
from backend.modules.tools.execution import (
    ErrorCategory,
    ExecutionState,
    SideEffectState,
    ToolResult,
)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def input_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class WorkflowJournal:
    def __init__(self, session_factory, engine=None) -> None:
        self._sessions = session_factory
        self.engine = engine

    @classmethod
    def memory(cls):
        """独立内存 SQLite；不读取或污染应用开发数据库。"""
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        journal = cls(factory, engine)
        return journal

    async def init(self) -> None:
        if self.engine is not None:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

    async def create_run(self, *, run_id: str, owner_id: Optional[str], session_id: Optional[str],
                         workspace: str, program: Dict[str, Any], caps: Dict[str, Any],
                         resumed_from: Optional[str] = None) -> None:
        async with self._sessions() as db:
            db.add(WorkflowRun(
                id=run_id,
                owner_id=owner_id,
                session_id=session_id,
                workspace=workspace,
                program_json=canonical_json(program),
                program_hash=input_hash(program),
                args_json=canonical_json(program.get("args", {})),
                caps_json=canonical_json(caps),
                resumed_from=resumed_from,
            ))
            await db.commit()

    async def reopen_run(self, *, run_id: str, owner_id: Optional[str], session_id: Optional[str],
                         workspace: str, program: Dict[str, Any], caps: Dict[str, Any],
                         resumed_from: Optional[str] = None) -> None:
        async with self._sessions() as db:
            run = await db.get(WorkflowRun, run_id)
            if run is None:
                raise ValueError(f"Unknown run: {run_id}")
            run.owner_id = owner_id
            run.session_id = session_id
            run.workspace = workspace
            run.program_json = canonical_json(program)
            run.program_hash = input_hash(program)
            run.caps_json = canonical_json(caps)
            run.resumed_from = resumed_from
            run.status = "running"
            run.stop_reason = None
            run.failure_json = None
            run.result_json = None
            await db.commit()

    async def create_actor(self, *, run_id: str, actor_id: str, persona: Dict[str, Any],
                           model_ref: Optional[Dict[str, str]] = None) -> None:
        async with self._sessions() as db:
            existing = await db.get(WorkflowActor, f"{run_id}:{actor_id}")
            if existing is not None:
                existing.persona_json = canonical_json(persona)
                existing.resolved_model_ref = (
                    canonical_json(model_ref) if model_ref else None
                )
            else:
                db.add(WorkflowActor(
                    id=f"{run_id}:{actor_id}",
                    run_id=run_id,
                    actor_id=actor_id,
                    site_id=f"actor:{actor_id}",
                    ordinal=1,
                    persona_json=canonical_json(persona),
                    resolved_model_ref=canonical_json(model_ref) if model_ref else None,
                ))
            await db.commit()

    async def completed_ask(self, run_id: str, site_id: str, ordinal: int,
                            instructions: str, *, lineage: tuple = ()) -> Optional[ToolResult]:
        async with self._sessions() as db:
            row = await db.scalar(select(WorkflowAsk).where(
                WorkflowAsk.run_id.in_((run_id, *lineage)),
                WorkflowAsk.site_id == site_id,
                WorkflowAsk.ordinal == ordinal,
                WorkflowAsk.status.in_(("completed", "succeeded")),
            ).order_by(WorkflowAsk.ended_at.desc()))
        if row is None or row.status != "completed":
            return None
        if row.instructions_hash != input_hash(instructions):
            raise ValueError(f"Input hash mismatch at {site_id}@{ordinal}")
        if row.status == "completed":
            return AskResult.success_value(json.loads(row.result_json))
        error = json.loads(row.error_json or "{}")
        category = ErrorCategory(error.get("category") or ErrorCategory.EXECUTION.value)
        if row.status == ExecutionState.CANCELLED.value.lower():
            return ToolResult.cancelled(error.get("message") or "Ask was cancelled.")
        if row.status == ExecutionState.UNKNOWN_OUTCOME.value.lower():
            return ToolResult.unknown_outcome(
                category,
                error.get("message") or "Ask outcome is unknown.",
            )
        return ToolResult.failure(
            category,
            error.get("message") or "Ask failed.",
            side_effect_state=SideEffectState(
                error.get("side_effect_state") or SideEffectState.NOT_ATTEMPTED.value
            ),
        )

    async def begin_ask(self, *, run_id: str, site_id: str, ordinal: int,
                        actor_id: str, instructions: str, schema=None) -> bool:
        """先写 running，保证崩溃后有未完成事实可恢复。

        对已完成（completed）的 ask 返回 False 以触发 replay。
        对失败/取消/未知的 ask 重置为 running，允许 resume 重试。
        """
        async with self._sessions() as db:
            row = await db.get(WorkflowAsk, f"{run_id}:{site_id}:{ordinal}")
            if row is not None:
                if row.instructions_hash != input_hash(instructions):
                    raise ValueError(f"Input hash mismatch at {site_id}@{ordinal}")
                if row.actor_id != actor_id:
                    raise ValueError(
                        f"Ask actor mismatch at {site_id}@{ordinal}: "
                        f"{row.actor_id} != {actor_id}"
                    )
                if row.status == "completed":
                    return False
                # failed / cancelled / unknown_outcome / running：重置为 running
                row.status = "running"
                row.result_json = None
                row.error_json = None
                row.ended_at = None
            actor = await db.scalar(select(WorkflowActor).where(
                WorkflowActor.run_id == run_id,
                WorkflowActor.actor_id == actor_id,
            ))
            if actor is None:
                raise ValueError(f"Actor is not registered: {actor_id}")
            if row is None:
                row = WorkflowAsk(
                    id=f"{run_id}:{site_id}:{ordinal}",
                    run_id=run_id,
                    site_id=site_id,
                    ordinal=ordinal,
                    actor_id=actor_id,
                    actor_seq=actor.next_ask_seq + 1,
                    instructions_hash=input_hash(instructions),
                    input_json=canonical_json(instructions),
                    schema_json=canonical_json(schema) if schema is not None else None,
                    status="running",
                    started_at=datetime.utcnow(),
                )
                db.add(row)
            await db.commit()
        return True

    async def record_ask(self, *, run_id: str, site_id: str, ordinal: int,
                         actor_id: str, instructions: str, result: ToolResult) -> None:
        succeeded = result.state is ExecutionState.SUCCEEDED
        now = datetime.utcnow()
        async with self._sessions() as db:
            row = await db.get(WorkflowAsk, f"{run_id}:{site_id}:{ordinal}")
            if row is None:
                raise ValueError(f"Ask was not admitted: {site_id}@{ordinal}")
            if row.instructions_hash != input_hash(instructions):
                raise ValueError(f"Input hash mismatch at {site_id}@{ordinal}")
            if row.actor_id != actor_id:
                raise ValueError(f"Ask actor mismatch at {site_id}@{ordinal}")
            row.actor_seq = row.actor_seq
            actor = await db.scalar(select(WorkflowActor).where(
                WorkflowActor.run_id == run_id,
                WorkflowActor.actor_id == actor_id,
            ))
            if actor is None:
                raise ValueError(f"Actor is not registered: {actor_id}")
            actor.next_ask_seq = max(actor.next_ask_seq, row.actor_seq)
            row.instructions_hash = input_hash(instructions)
            row.input_json = canonical_json(instructions)
            row.schema_json = None
            row.status = "completed" if succeeded else result.state.value.lower()
            row.result_json = canonical_json(getattr(result, "value", result.output)) if succeeded else None
            row.error_json = None if succeeded else canonical_json({
                "category": result.error_category.value if result.error_category else None,
                "message": result.display_text,
                "side_effect_state": result.side_effect_state.value,
            })
            row.ended_at = now
            await db.commit()

    async def save_template(self, *, template_id: str, owner_id: Optional[str],
                            name: str, program: Dict[str, Any]) -> None:
        async with self._sessions() as db:
            row = await db.get(WorkflowTemplate, template_id)
            if row is None:
                row = WorkflowTemplate(id=template_id, owner_id=owner_id)
                db.add(row)
            if row.owner_id != owner_id:
                raise PermissionError("Cannot modify another user's template")
            row.name = name
            row.program_json = canonical_json(program)
            row.program_hash = input_hash(program)
            await db.commit()

    async def get_template(self, template_id: str, *, owner_id: Optional[str]) -> Optional[Dict[str, Any]]:
        async with self._sessions() as db:
            row = await db.scalar(select(WorkflowTemplate).where(
                WorkflowTemplate.id == template_id,
                WorkflowTemplate.owner_id.is_(owner_id),
            ))
            if row is None:
                return None
            return {
                "id": row.id,
                "owner_id": row.owner_id,
                "name": row.name,
                "program": json.loads(row.program_json),
                "program_hash": row.program_hash,
            }

    async def get_asks(self, run_id: str) -> list:
        async with self._sessions() as db:
            rows = (
                await db.scalars(
                    select(WorkflowAsk)
                    .where(WorkflowAsk.run_id == run_id)
                    .order_by(WorkflowAsk.ended_at, WorkflowAsk.site_id, WorkflowAsk.ordinal)
                )
            ).all()
            return rows

    async def get_run(self, run_id: str, *, owner_id: Optional[str] = None,
                      any_owner: bool = False) -> Optional[Dict[str, Any]]:
        async with self._sessions() as db:
            query = select(WorkflowRun).where(WorkflowRun.id == run_id)
            if not any_owner:
                query = query.where(WorkflowRun.owner_id.is_(owner_id))
            run = await db.scalar(query)
            if run is None:
                return None
            return {
                "id": run.id,
                "owner_id": run.owner_id,
                "session_id": run.session_id,
                "workspace": run.workspace,
                "program": json.loads(run.program_json),
                "program_hash": run.program_hash,
                "status": run.status,
                "stop_reason": run.stop_reason,
                "caps": json.loads(run.caps_json),
                "result": json.loads(run.result_json) if run.result_json else None,
                "failure": json.loads(run.failure_json) if run.failure_json else None,
                "resumed_from": run.resumed_from,
            }

    async def list_asks(self, run_id: str) -> list:
        async with self._sessions() as db:
            rows = (
                await db.scalars(
                    select(WorkflowAsk)
                    .where(WorkflowAsk.run_id == run_id)
                    .order_by(WorkflowAsk.site_id, WorkflowAsk.ordinal)
                )
            ).all()
            return [{
                "site_id": row.site_id,
                "ordinal": row.ordinal,
                "actor_id": row.actor_id,
                "actor_seq": row.actor_seq,
                "status": row.status,
                "result": json.loads(row.result_json) if row.result_json else None,
                "error": json.loads(row.error_json) if row.error_json else None,
            } for row in rows]

    async def mark_running(self, run_id: str) -> None:
        async with self._sessions() as db:
            run = await db.get(WorkflowRun, run_id)
            if run is None:
                raise ValueError(f"Unknown run: {run_id}")
            run.status = "running"
            run.stop_reason = None
            run.failure_json = None
            run.result_json = None
            await db.commit()

    async def settle_run(self, *, run_id: str, status: str, result: ToolResult) -> None:
        succeeded = result.state is ExecutionState.SUCCEEDED
        async with self._sessions() as db:
            run = await db.get(WorkflowRun, run_id)
            if run is None:
                raise ValueError(f"Unknown run: {run_id}")
            # cancel 可能在 engine 结束前已落终态；不要覆盖用户主动取消。
            if run.status not in ("running", status):
                return
            run.status = status
            run.result_json = canonical_json(result.output) if succeeded else None
            run.failure_json = None if succeeded else canonical_json({
                "category": result.error_category.value if result.error_category else None,
                "message": result.display_text,
                "side_effect_state": result.side_effect_state.value,
            })
            await db.commit()

    async def append_event(self, *, run_id: str, event_type: str, payload: Dict[str, Any]) -> None:
        async with self._sessions() as db:
            rows = (
                await db.scalars(
                    select(WorkflowEvent)
                    .where(WorkflowEvent.run_id == run_id)
                    .order_by(WorkflowEvent.sequence.desc())
                )
            ).all()
            sequence = rows[0].sequence + 1 if rows else 1
            db.add(WorkflowEvent(
                run_id=run_id,
                sequence=sequence,
                event_type=event_type,
                payload_json=canonical_json(payload),
            ))
            await db.commit()
