"""Dynamic Workflow 的实际 actor 工厂与模型授权。"""

from pathlib import Path
from typing import Any, Dict, Optional

from backend.modules.agent.session_gate import SessionTurnGate
from backend.modules.workflow.actor import DynamicActor
from backend.modules.workflow.driver import DynamicWorkflowDriver, provider_for_user


class DynamicActorFactory:
    def __init__(self, *, subagent_manager=None, workspace: Path = None, owner_id: Optional[str], session_id: Optional[str]) -> None:
        self.manager = subagent_manager
        self.workspace = workspace
        self.owner_id = owner_id
        self.session_id = session_id
        self.gate = SessionTurnGate()

    async def create(self, *, run_id: str, declaration: Dict[str, Any], user=None,
                     manager=None, workspace=None):
        actor_id = declaration["id"]
        provider = await provider_for_user(user, declaration.get("model_ref"))
        manager = manager or self.manager
        workspace = workspace or self.workspace
        return DynamicActor(
            actor_id=actor_id,
            run_id=run_id,
            owner_id=self.owner_id,
            session_id=self.session_id,
            persona=declaration["persona"],
            provider=provider,
            model=provider.default_model,
            workspace=workspace,
            manager=manager,
            tools=None,
            gate=self.gate,
        )
    async def build_dynamic_driver(self, *, run_id: str, program, journal, user=None, lineage=(), runtime=None):
        manager = self.manager
        workspace = self.workspace
        if runtime is not None:
            manager = runtime.subagent_manager if hasattr(runtime, "subagent_manager") else runtime["subagent_manager"]
            workspace = runtime.workspace if hasattr(runtime, "workspace") else runtime["workspace"]
        actors = {}
        for declaration in program["agents"]:
            actors[declaration["id"]] = await self.create(
                run_id=run_id,
                declaration=declaration,
                user=user,
                manager=manager,
                workspace=workspace,
            )
        return DynamicWorkflowDriver(
            actors=actors,
            journal=journal,
            run_id=run_id,
            lineage=lineage,
        )
