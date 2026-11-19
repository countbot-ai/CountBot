"""run 级 actor：多次 ask 共享消息上下文，同一 actor 串行。"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.modules.agent.session_gate import SessionTurnGate
from backend.modules.agent.subagent import SubagentTask
from backend.modules.tools.execution import (
    ErrorCategory,
    ExecutionState,
    SideEffectState,
    ToolResult,
)
from backend.modules.workflow.ask_result import AskResult
from backend.modules.workflow.results import validate_result
from backend.modules.workflow.submit_result import SubmitResultTool


@dataclass
class DynamicActor:
    actor_id: str
    run_id: str
    owner_id: Optional[str]
    session_id: Optional[str]
    persona: str
    provider: Any
    model: str
    workspace: Any
    manager: Any
    tools: Any
    gate: SessionTurnGate
    temperature: float = 0.0
    max_tokens: int = 4096
    thinking_enabled: bool = True
    stream_enabled: bool = True
    messages: List[Dict[str, Any]] = field(default_factory=list)
    next_ask_seq: int = 0

    def __post_init__(self) -> None:
        if not self.messages:
            self.messages = [{"role": "system", "content": self.persona}]

    async def ask(
        self,
        instructions: str,
        *,
        result_schema: Optional[Dict[str, Any]] = None,
        cancel_token=None,
        max_repairs: int = 3,
        max_nudges: int = 1,
    ) -> ToolResult:
        """执行一次 ask；repair/nudge 不改变 actor_seq 或业务 ask 身份。"""
        if not isinstance(instructions, str) or not instructions.strip():
            raise ValueError("ask instructions must not be empty")
        if not isinstance(max_repairs, int) or isinstance(max_repairs, bool) or max_repairs < 0:
            raise ValueError("max_repairs must be a non-negative integer")
        if not isinstance(max_nudges, int) or isinstance(max_nudges, bool) or max_nudges < 0:
            raise ValueError("max_nudges must be a non-negative integer")
        if result_schema is not None:
            from backend.modules.workflow.results import validate_schema
            schema_errors = validate_schema(result_schema)
            if schema_errors:
                raise ValueError("; ".join(schema_errors))

        await self.gate.acquire(self.actor_id)
        try:
            self.next_ask_seq += 1
            task = SubagentTask(
                task_id=f"{self.run_id}:{self.actor_id}:{self.next_ask_seq}",
                label=self.actor_id,
                message=instructions,
                session_id=self.session_id,
                system_prompt=self.persona,
            )
            task.cancel_token = cancel_token
            submitted = []
            self.messages.append({"role": "user", "content": instructions})
            tools = self.manager._build_child_tool_registry()
            tools.set_session_id(self.session_id)
            tools.set_channel("dynamic_workflow")
            if result_schema is not None:
                tools.register(SubmitResultTool(result_schema, submitted.append))

            try:
                timeout = self.manager.config_loader.config.security.subagent_timeout
                task.last_activity = time.monotonic()
                runner = asyncio.create_task(self._run_structured_ask(
                    task=task,
                    tools=tools,
                    result_schema=result_schema,
                    submitted=submitted,
                    max_repairs=max_repairs,
                    max_nudges=max_nudges,
                ))
                watchdog = asyncio.create_task(
                    self.manager._inactivity_watchdog(
                        task, runner, self.manager.inactivity_seconds,
                    )
                )
                try:
                    async with asyncio.timeout(timeout):
                        output = await runner
                finally:
                    watchdog.cancel()
                if result_schema is None:
                    if output.strip():
                        self.messages.append({"role": "assistant", "content": output})
                    return ToolResult.success(output)
                if isinstance(output, ToolResult):
                    return output
                if not submitted:
                    return ToolResult.failure(
                        ErrorCategory.RESULT_CONTRACT,
                        "The actor did not submit a structured result.",
                        side_effect_state=SideEffectState.NOT_ATTEMPTED,
                    )
                errors = validate_result(submitted[-1], result_schema)
                if errors:
                    return ToolResult.failure(
                        ErrorCategory.RESULT_CONTRACT,
                        "; ".join(errors),
                        side_effect_state=SideEffectState.NOT_ATTEMPTED,
                    )
                return AskResult.success_value(submitted[-1])
            except asyncio.TimeoutError:
                if task.tool_outcomes or task.active_tool_call:
                    return ToolResult.unknown_outcome(
                        ErrorCategory.TIMEOUT,
                        "The ask timed out after execution may have started.",
                    )
                return ToolResult.failure(
                    ErrorCategory.TIMEOUT,
                    "The ask timed out before tool execution.",
                    side_effect_state=SideEffectState.NOT_ATTEMPTED,
                )
            except asyncio.CancelledError:
                if task.tool_outcomes or task.active_tool_call:
                    return ToolResult.unknown_outcome(
                        ErrorCategory.CANCELLATION,
                        "The ask was cancelled after execution may have started.",
                    )
                return ToolResult.cancelled("The ask was cancelled before execution.")
            except Exception as exc:
                from loguru import logger
                logger.exception("Dynamic actor ask failed: {}", exc)
                if task.tool_outcomes or task.active_tool_call:
                    return ToolResult.unknown_outcome(
                        ErrorCategory.EXECUTION,
                        f"The ask failed after execution may have started: {exc}",
                    )
                return ToolResult.failure(
                    ErrorCategory.EXECUTION,
                    str(exc),
                    side_effect_state=SideEffectState.NOT_ATTEMPTED,
                )
        finally:
            self.gate.release(self.actor_id)

    async def _run_structured_ask(self, *, task, tools, result_schema, submitted,
                                  max_repairs, max_nudges) -> str:
        repairs = 0
        nudges = 0
        while True:
            before = len(submitted)
            output = await self.manager._run_message_loop(
                task=task,
                messages=self.messages,
                tools=tools,
                active_provider=self.provider,
                runtime_model=self.model,
                runtime_temperature=self.temperature,
                runtime_max_tokens=self.max_tokens,
                runtime_thinking_enabled=self.thinking_enabled,
                runtime_stream_enabled=self.stream_enabled,
                tool_timeout=self.manager._resolve_child_tool_timeout(),
                max_iterations=(
                    self.manager._resolve_child_max_iterations()
                    if result_schema is None
                    else 1
                ),
                handler=None,
            )
            if result_schema is None or len(submitted) > before:
                return output
            last_submit = next((
                record for record in reversed(task.tool_call_records)
                if record.get("name") == "submit_result"
            ), None)
            if last_submit is not None and last_submit.get("status") != "success":
                if nudges < max_nudges:
                    nudges += 1
                    self.messages.append({
                        "role": "user",
                        "content": (
                            "The previous structured result was rejected. "
                            "Correct it and call submit_result again: "
                            f"{last_submit.get('result')}"
                        ),
                    })
                    continue
                if repairs >= max_repairs:
                    return ToolResult.failure(
                        ErrorCategory.RESULT_CONTRACT,
                        "Invalid structured result: "
                        + str(last_submit.get("result") or "validation failed"),
                        side_effect_state=SideEffectState.NOT_ATTEMPTED,
                    )
                repairs += 1
                self.messages.append({
                    "role": "user",
                    "content": (
                        "The previous structured result was rejected. "
                        "Correct it and call submit_result again: "
                        f"{last_submit.get('result')}"
                    ),
                })
                continue
            if nudges < max_nudges:
                nudges += 1
                self.messages.append({
                    "role": "user",
                    "content": "Call submit_result exactly once with the final structured answer.",
                })
                continue
            return ToolResult.failure(
                ErrorCategory.RESULT_CONTRACT,
                "The actor did not submit a structured result.",
                side_effect_state=SideEffectState.NOT_ATTEMPTED,
            )


class DynamicActorManager:
    def __init__(self, gate: Optional[SessionTurnGate] = None) -> None:
        self.gate = gate or SessionTurnGate()
        self.actors: Dict[str, DynamicActor] = {}

    def register(self, actor: DynamicActor) -> DynamicActor:
        if actor.actor_id in self.actors:
            raise ValueError(f"Duplicate actor id: {actor.actor_id}")
        self.actors[actor.actor_id] = actor
        return actor
