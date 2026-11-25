"""Dynamic Workflow 的运行控制与预算。"""

import asyncio
import inspect
import uuid
from dataclasses import dataclass
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


@dataclass(frozen=True)
class AmendResult(ToolResult):
    """修订会创建新 run；把新 id 一并返回给调用方。"""

    run_id: str = ""


def _amended(result: ToolResult, run_id: str) -> AmendResult:
    return AmendResult(
        state=result.state,
        display_text=result.display_text,
        output=result.output,
        error_category=result.error_category,
        retryable=result.retryable,
        retry_safety=result.retry_safety,
        side_effect_state=result.side_effect_state,
        run_id=run_id,
    )


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
        try:
            driver = self.driver_factory(
                run_id=run_id,
                owner_id=owner_id,
                program=compiled,
                journal=self.journal,
                lineage=(),
                user=user,
                runtime=runtime,
            )
            if inspect.isawaitable(driver):
                driver = await driver
        except Exception as exc:
            result = ToolResult.failure(
                ErrorCategory.PERMISSION
                if isinstance(exc, PermissionError)
                else ErrorCategory.EXECUTION,
                str(exc) or exc.__class__.__name__,
                side_effect_state=SideEffectState.NOT_ATTEMPTED,
            )
        else:
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
        if record["status"] not in {"cancelled", "failed", "unknown_outcome", "running"}:
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
        amended_id = f"{run_id}:amend-{uuid.uuid4().hex[:12]}"
        result = await self.start(
            run_id=amended_id,
            owner_id=owner_id,
            session_id=record["session_id"],
            workspace=record["workspace"],
            program=program,
            resumed_from=run_id,
            # 修订后的程序不能复用父 run 的 ask 缓存：同一 site 的输入可能已变化，
            # journal 会按旧 ask 的输入哈希误判。
            user=user,
            runtime=runtime,
        )
        return _amended(result, amended_id)

    async def cancel(self, run_id: str, *, owner_id: Optional[str] = None) -> bool:
        record = await self.journal.get_run(run_id, owner_id=owner_id)
        if record is None:
            return False
        cancelled = False
        run = self.runs.get(run_id)
        if run is not None and run["status"] == "running":
            run["token"].cancel()
            run["status"] = "CANCELLED"
            cancelled = True
        # 跨进程或重启后的 run：直接在 journal 里落终态
        if record["status"] == "running":
            await self.journal.settle_run(
                run_id=run_id,
                status="cancelled",
                result=ToolResult.cancelled("Workflow was cancelled by the user."),
            )
            cancelled = True
        return cancelled
