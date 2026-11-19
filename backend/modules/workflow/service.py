"""Dynamic Workflow 的运行控制与预算。"""

import asyncio
from typing import Any, Dict, Optional

from backend.modules.agent.task_manager import CancellationToken
from backend.modules.tools.execution import (
    ErrorCategory,
    ExecutionState,
    SideEffectState,
    ToolResult,
)
from backend.modules.workflow.engine import DynamicWorkflowEngine
from backend.modules.workflow.program import ProgramError, compile_program, preview_program


class DynamicWorkflowService:
    """统一 run 创建、执行、取消与恢复入口；planner 只能走这里。"""

    def __init__(self, driver_factory, journal) -> None:
        self.driver_factory = driver_factory
        self.journal = journal
        self.runs: Dict[str, Dict[str, Any]] = {}

    def compile(self, program: Dict[str, Any]) -> Dict[str, Any]:
        compiled = compile_program(program)
        return preview_program(compiled)

    async def start(self, *, run_id: str, owner_id: Optional[str], session_id: Optional[str],
                    workspace: str, program: Dict[str, Any], resumed_from=None, user=None,
                    runtime=None, confirmed: bool = True, resume_existing: bool = False) -> ToolResult:
        try:
            compiled = compile_program(program)
        except ProgramError as exc:
            return ToolResult.failure(
                ErrorCategory.VALIDATION,
                str(exc),
                side_effect_state=SideEffectState.NOT_ATTEMPTED,
            )
        existing = await self.journal.get_run(run_id, owner_id=owner_id)
        if existing is not None and not resume_existing:
            return ToolResult.failure(
                ErrorCategory.VALIDATION,
                f"Workflow run already exists: {run_id}",
                side_effect_state=SideEffectState.NOT_ATTEMPTED,
            )
        if not confirmed:
            return ToolResult.failure(
                ErrorCategory.PERMISSION,
                "Dynamic Workflow requires confirmation before execution.",
                side_effect_state=SideEffectState.NOT_ATTEMPTED,
            )
        if resume_existing:
            await self.journal.reopen_run(
                run_id=run_id,
                owner_id=owner_id,
                session_id=session_id,
                workspace=workspace,
                program=compiled,
                caps=compiled["limits"],
                resumed_from=resumed_from,
            )
        else:
            await self.journal.create_run(
                run_id=run_id,
                owner_id=owner_id,
                session_id=session_id,
                workspace=workspace,
                program=compiled,
                caps=compiled["limits"],
                resumed_from=resumed_from,
            )
        token = CancellationToken()
        self.runs[run_id] = {"owner_id": owner_id, "token": token, "status": "running"}
        for declaration in compiled["agents"]:
            if user is not None and declaration.get("model_ref") is not None:
                from backend.modules.multiuser.effective import resolve_model_ref_for_user
                await resolve_model_ref_for_user(
                    user,
                    declaration["model_ref"]["provider"],
                    declaration["model_ref"]["model"],
                )
            await self.journal.create_actor(
                run_id=run_id,
                actor_id=declaration["id"],
                persona={"system": declaration["persona"]},
                model_ref=declaration.get("model_ref"),
            )
        driver = self.driver_factory(
            run_id=run_id,
            owner_id=owner_id,
            program=compiled,
            journal=self.journal,
            lineage=(resumed_from,) if resumed_from else (),
            user=user,
            runtime=runtime,
        )
        timeout = compiled["limits"].get("wall_clock_timeout")
        try:
            if timeout:
                async with asyncio.timeout(timeout):
                    result = await DynamicWorkflowEngine(compiled, driver, cancel_token=token).run()
            else:
                result = await DynamicWorkflowEngine(compiled, driver, cancel_token=token).run()
        except asyncio.TimeoutError:
            result = ToolResult.unknown_outcome(
                ErrorCategory.TIMEOUT,
                "Workflow exceeded its wall-clock budget; side effects may have occurred.",
            )
        self.runs[run_id]["status"] = result.state.value
        await self.journal.settle_run(
            run_id=run_id,
            status=result.state.value.lower(),
            result=result,
        )
        return result

    async def save_template(self, *, template_id: str, owner_id: Optional[str],
                            name: str, program: Dict[str, Any]) -> Dict[str, Any]:
        compiled = self.compile(program)
        await self.journal.save_template(
            template_id=template_id,
            owner_id=owner_id,
            name=name,
            program=compiled,
        )
        return {"id": template_id, "name": name, "preview": compiled}

    async def get_template(self, template_id: str, *, owner_id: Optional[str]):
        return await self.journal.get_template(template_id, owner_id=owner_id)

    async def get_run(self, run_id: str, *, owner_id: Optional[str]):
        return await self.journal.get_run(run_id, owner_id=owner_id)

    async def resume(self, *, run_id: str, owner_id: Optional[str], user=None, runtime=None) -> ToolResult:
        record = await self.journal.get_run(run_id, owner_id=owner_id)
        if record is None:
            return ToolResult.failure(
                ErrorCategory.PERMISSION,
                "Workflow run was not found.",
                side_effect_state=SideEffectState.NOT_ATTEMPTED,
            )
        if record["status"] not in {"cancelled", "failed", "unknown_outcome"}:
            return ToolResult.failure(
                ErrorCategory.VALIDATION,
                f"Run in state {record['status']} cannot be resumed.",
                side_effect_state=SideEffectState.NOT_ATTEMPTED,
            )
        return await self.start(
            run_id=run_id,
            owner_id=owner_id,
            session_id=record["session_id"],
            workspace=record["workspace"],
            program=record["program"],
            resumed_from=None,
            user=user,
            runtime=runtime,
            resume_existing=True,
        )

    async def amend(self, *, run_id: str, owner_id: Optional[str], program: Dict[str, Any],
                    user=None, runtime=None) -> ToolResult:
        record = await self.journal.get_run(run_id, owner_id=owner_id)
        if record is None:
            return ToolResult.failure(
                ErrorCategory.PERMISSION,
                "Workflow run was not found.",
                side_effect_state=SideEffectState.NOT_ATTEMPTED,
            )
        amended_id = f"{run_id}:amend-{len(self.runs) + 1}"
        return await self.start(
            run_id=amended_id,
            owner_id=owner_id,
            session_id=record["session_id"],
            workspace=record["workspace"],
            program=program,
            resumed_from=run_id,
            user=user,
            runtime=runtime,
        )

    def cancel(self, run_id: str) -> bool:
        run = self.runs.get(run_id)
        if run is None or run["status"] != "running":
            return False
        run["token"].cancel()
        return True
