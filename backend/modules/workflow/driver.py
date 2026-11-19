"""Engine 与 Dynamic actor、模型授权、journal 之间的 driver 协议。"""

from typing import Any, Dict, Optional

from backend.modules.multiuser.effective import build_provider, resolve_model_for_user
from backend.modules.tools.execution import ExecutionState


class DynamicWorkflowDriver:
    def __init__(self, *, actors, journal=None, run_id=None, lineage=(), event_callback=None) -> None:
        self.actors = actors
        self.journal = journal
        self.run_id = run_id
        self.lineage = tuple(lineage)
        self.event_callback = event_callback

    async def ask(self, *, actor_id: str, site_id: str, ordinal: int,
                  instructions: str, result_schema=None, cancel_token=None):
        if actor_id not in self.actors:
            raise ValueError(f"Unknown actor {actor_id}")
        if self.journal is not None:
            if self.lineage:
                record = await self.journal.get_run(self.lineage[0], any_owner=True)
                if record is None:
                    raise ValueError(f"Unknown predecessor run: {self.lineage[0]}")
            replay = await self.journal.completed_ask(
                self.run_id, site_id, ordinal, instructions, lineage=self.lineage,
            )
            if replay is not None:
                return replay
        if self.journal is not None:
            admitted = await self.journal.begin_ask(
                run_id=self.run_id,
                site_id=site_id,
                ordinal=ordinal,
                actor_id=actor_id,
                instructions=instructions,
                schema=result_schema,
            )
            if not admitted:
                raise ValueError(f"Ask already settled: {site_id}@{ordinal}")
        actor = self.actors[actor_id]
        if self.event_callback is not None:
            await self.event_callback("workflow_agent_start", {
                "agent_id": f"{actor_id}:{ordinal}",
                "agent_label": f"{actor_id} · ask {ordinal}",
            })
        result = await actor.ask(
            instructions,
            result_schema=result_schema,
            cancel_token=cancel_token,
        )
        if self.journal is not None:
            await self.journal.record_ask(
                run_id=self.run_id,
                site_id=site_id,
                ordinal=ordinal,
                actor_id=actor_id,
                instructions=instructions,
                result=result,
            )
        if self.event_callback is not None:
            await self.event_callback("workflow_agent_complete" if result.state is ExecutionState.SUCCEEDED else "workflow_agent_failed", {
                "agent_id": f"{actor_id}:{ordinal}",
                "agent_label": f"{actor_id} · ask {ordinal}",
                "result": result.display_text,
                "status": "success" if result.state is ExecutionState.SUCCEEDED else result.state.value.lower(),
                "state": result.state.value,
                "side_effect_state": result.side_effect_state.value,
            })
        return result


async def provider_for_user(user, model_ref: Optional[Dict[str, str]] = None):
    """只接受当前身份或显式授权的模型，不接收 actor 提供的 Key。"""
    if user is None:
        from backend.modules.multiuser.identity import anonymous_admin
        user = anonymous_admin()
    if model_ref is None:
        resolved = await resolve_model_for_user(user)
    else:
        from backend.modules.multiuser.effective import resolve_model_ref_for_user
        resolved = await resolve_model_ref_for_user(
            user, model_ref["provider"], model_ref["model"],
        )
    return build_provider(resolved)
