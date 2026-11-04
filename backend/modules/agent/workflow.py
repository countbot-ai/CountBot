"""WorkflowEngine：CountBot 的多智能体编排引擎。

pipeline / graph / council 现在只是 :mod:`backend.modules.agent.workflow_spec`
里的三个预设：编译成统一的执行图后，本模块只负责调度、单节点执行、事件推送
和结果渲染。

因此，「新增一种模式」不再是正确动作——需要新拓扑时加节点类型（map / branch /
loop / checkpoint），不要加 mode。三种历史入参仍然保留为兼容入口，行为与重构
前逐字节一致，见 ``tests/test_workflow_characterization.py``。
"""

import asyncio
import inspect
from enum import Enum
from typing import Any, Dict, List, Optional

from loguru import logger

from backend.modules.agent.workflow_spec import (
    POLICY_ABORT,
    ChildOutcomeError,
    NodeResult,
    NodeState,
    PromptContext,
    WorkflowNode,
    WorkflowRun,
    WorkflowSpec,
    compile_council,
    compile_graph,
    compile_pipeline,
)
from backend.modules.tools.execution import (
    ErrorCategory,
    ExecutionState,
    ToolExecutionOutcome,
    ToolExecutionRejected,
    ToolResult,
)

__all__ = [
    "ChildOutcomeError",
    "WorkflowEngine",
    "WorkflowMode",
]


class WorkflowMode(Enum):
    """历史模式名。调度已统一到 spec，这里只用于兼容与后续显式校验。"""

    PIPELINE = "pipeline"
    GRAPH = "graph"
    COUNCIL = "council"


class WorkflowEngine:
    """多智能体工作流引擎 —— 唯一执行器 + 可编译的预设。"""

    def __init__(
        self,
        subagent_manager,
        session_id: Optional[str] = None,
        cancel_token=None,
        skills=None,
        team_model_config: Optional[Dict[str, Any]] = None,
        event_callback=None,
    ) -> None:
        self._mgr = subagent_manager
        self._session_id = session_id
        self._cancel_token = cancel_token
        self._skills = skills
        self._team_model_config = team_model_config
        self._event_callback = event_callback
        self._execution_data: Dict[str, dict] = {}
        self._child_failures: List[ToolResult] = []
        # 本工作流登记的子任务 ID：取消时按归属精确取消，不波及其他工作流/会话
        self._child_task_ids: set = set()

    @staticmethod
    def _with_display(result: ToolResult, display_text: str) -> ToolResult:
        return ToolResult(
            state=result.state,
            display_text=display_text,
            output=result.output,
            error_category=result.error_category,
            retryable=result.retryable,
            retry_safety=result.retry_safety,
            side_effect_state=result.side_effect_state,
        )

    async def run_outcome(self, mode: str, goal: str, agents: List[dict], *,
                          cross_review: bool = True, enable_skills: bool = False) -> ToolResult:
        """Bridge a workflow's structured child state to its parent Tool."""
        try:
            if mode == "pipeline":
                text = await self.run_pipeline(goal, agents, enable_skills=enable_skills)
            elif mode == "graph":
                text = await self.run_graph(goal, agents, enable_skills=enable_skills)
            else:
                text = await self.run_council(
                    goal, agents, cross_review=cross_review, enable_skills=enable_skills
                )
        except ChildOutcomeError as exc:
            return exc.result
        if self._child_failures:
            # Uncertainty has priority over a known failure in concurrent graph slots.
            priority = {ExecutionState.UNKNOWN_OUTCOME: 0,
                        ExecutionState.CANCELLED: 1, ExecutionState.FAILED: 2}
            result = min(self._child_failures, key=lambda item: priority[item.state])
            return self._with_display(result, text)
        return ToolResult.success(text)

    # ------------------------------------------------------------------
    # 调度器：所有预设共用
    # ------------------------------------------------------------------

    async def _run_spec(self, spec: WorkflowSpec) -> WorkflowRun:
        """按依赖调度 spec，直到没有可执行节点。

        两种失败策略沿用改造前的语义：``continue``（graph）把失败节点标红、下游
        置为 blocked；``abort``（pipeline / council）在当前波次跑完后抛出，不再
        调度后续节点。

        校验不在这里做：graph 在编译期已校验；将来从 JSON 反序列化 spec 时，
        校验应发生在解析边界（``WorkflowSpec.validate``），而不是每个节点执行前。
        """
        run = WorkflowRun(
            spec=spec,
            goal=spec.goal,
            nodes={node.node_id: NodeResult() for node in spec.nodes},
            order=list(spec.nodes),
        )

        while True:
            waiting = [
                node for node in spec.nodes
                if run.nodes[node.node_id].state is NodeState.WAITING
            ]
            if not waiting:
                break

            if self._is_cancelled():
                logger.info("[Workflow] 用户取消，终止调度")
                raise asyncio.CancelledError("Workflow cancelled")

            ready = [
                node for node in waiting
                if all(
                    run.nodes[dep].state in (NodeState.DONE, NodeState.SKIPPED)
                    for dep in node.needs
                )
            ]
            if not ready:
                # 剩下的都在等已经失败的节点：标红并停止，避免静默挂起
                for node in waiting:
                    if any(run.nodes[dep].state is NodeState.FAILED for dep in node.needs):
                        result = run.nodes[node.node_id]
                        result.state = NodeState.FAILED
                        result.error = "Blocked by upstream failure"
                break

            to_execute: List[WorkflowNode] = []
            for node in ready:
                if self._condition_met(node.condition, run):
                    to_execute.append(node)
                else:
                    result = run.nodes[node.node_id]
                    result.state = NodeState.SKIPPED
                    result.output = "[Skipped: condition not met]"
                    logger.info(f"[Workflow] Node '{node.node_id}' skipped (condition not met)")

            for node in to_execute:
                run.nodes[node.node_id].state = NodeState.ACTIVE
            if to_execute:
                logger.info(
                    "[Workflow] Dispatching "
                    f"{len(to_execute)} node(s) in parallel: "
                    f"{[node.node_id for node in to_execute]}"
                )

            results = await asyncio.gather(
                *[self._run_node(node, run, spec) for node in to_execute],
                return_exceptions=True,
            )
            for item in results:
                if isinstance(item, asyncio.CancelledError):
                    raise item
            if spec.failure_policy == POLICY_ABORT:
                for item in results:
                    if isinstance(item, BaseException):
                        raise item

        return run

    async def _run_node(
        self,
        node: WorkflowNode,
        run: WorkflowRun,
        spec: WorkflowSpec,
    ) -> None:
        """执行单个节点：拼 prompt → 派子 Agent → 记录结构化结果。"""
        result = run.nodes[node.node_id]
        try:
            prompt = node.prompt(PromptContext(goal=spec.goal, node=node, run=run))
            output = await self._invoke_agent(
                prompt,
                label=node.label,
                system_prompt=node.system_prompt,
                agent_id=node.meta.get("agent_id", node.node_id),
                enable_skills=spec.enable_skills,
            )
            result.state = NodeState.DONE
            result.output = output
        except Exception as exc:
            result.state = NodeState.FAILED
            result.error = str(exc)
            if not isinstance(exc, ChildOutcomeError):
                self._child_failures.append(ToolResult.unknown_outcome(
                    ErrorCategory.INTERNAL,
                    f"Workflow slot '{node.node_id}' failed: {exc}",
                ))
            logger.error(f"[Workflow] Node '{node.node_id}' failed: {exc}")
            if spec.failure_policy == POLICY_ABORT:
                raise

    def _condition_met(self, condition: Optional[dict], run: WorkflowRun) -> bool:
        """评估节点执行条件（沿用 graph 既有的两种判定）。"""
        if not condition:
            return True

        cond_type = condition.get("type")
        node_id = condition.get("node")
        text = condition.get("text", "")

        if not node_id or node_id not in run.nodes:
            return False

        output = run.output_of(node_id)
        if cond_type == "output_contains":
            return text in output
        if cond_type == "output_not_contains":
            return text not in output
        return True

    # ------------------------------------------------------------------
    # 预设入口（兼容三种历史调用方式）
    # ------------------------------------------------------------------

    async def run_pipeline(self, goal: str, stages: List[Dict[str, Any]], enable_skills: bool = False) -> str:
        """顺序流水线：每个阶段继承此前全部输出。"""
        spec = compile_pipeline(goal, stages, enable_skills=enable_skills)
        run = await self._run_spec(spec)
        return spec.render(run) + self._build_exec_metadata()

    async def run_graph(self, goal: str, slots: List[Dict[str, Any]], enable_skills: bool = False) -> str:
        """依赖 DAG：就绪节点并行，下游只看到直接依赖。"""
        spec = compile_graph(goal, slots, enable_skills=enable_skills)
        run = await self._run_spec(spec)
        return spec.render(run) + self._build_exec_metadata()

    async def run_council(self, question: str, members: List[Dict[str, Any]], cross_review: bool = True, enable_skills: bool = False) -> str:
        """多视角评审：立场陈述 → 可选交叉评审（不做最终综合）。"""
        spec = compile_council(
            question, members, cross_review=cross_review, enable_skills=enable_skills
        )
        run = await self._run_spec(spec)
        return spec.render(run) + self._build_exec_metadata()

    # ------------------------------------------------------------------
    # 事件与执行数据
    # ------------------------------------------------------------------

    async def _emit_ws(self, event_type: str, **data: Any) -> None:
        """推送工作流事件到前端"""
        if self._event_callback:
            try:
                maybe_result = self._event_callback(event_type, data)
                if inspect.isawaitable(maybe_result):
                    await maybe_result
            except Exception as exc:
                logger.warning(f"[Workflow] External event callback failed ({event_type}): {exc}")

        if not self._session_id:
            return
        try:
            from backend.ws.connection import send_dict_to_session
            n = await send_dict_to_session(self._session_id, {"type": event_type, **data})
            if n == 0:
                logger.warning(f"[Workflow] WS 事件未送达（{event_type}），session={self._session_id}")
            else:
                logger.debug(f"[Workflow] WS 事件已推送: {event_type} → {n} 个连接")
        except Exception as exc:
            logger.warning(f"[Workflow] WS emit '{event_type}' 失败: {exc}")

    def _is_cancelled(self) -> bool:
        """检查是否已取消"""
        is_cancelled = bool(self._cancel_token and self._cancel_token.is_cancelled)
        if is_cancelled:
            asyncio.create_task(self._cancel_all_subagents())
        return is_cancelled

    async def _cancel_all_subagents(self) -> None:
        """取消本工作流派发的所有子任务（按归属过滤，不波及其他工作流）"""
        try:
            cancelled = await self._mgr.cancel_tasks(set(self._child_task_ids))
            if cancelled > 0:
                logger.info(f"[Workflow] Cancelled {cancelled} running subagent tasks")
        except Exception as e:
            logger.warning(f"[Workflow] Failed to cancel subagent tasks: {e}")

    def _build_exec_metadata(self) -> str:
        """序列化执行数据为 HTML 注释"""
        if not self._execution_data:
            return ""
        try:
            import json

            payload = json.dumps(self._execution_data, ensure_ascii=False)
            return f"\n\n<!--WORKFLOW_EXEC:{payload}:WORKFLOW_EXEC-->"
        except Exception:
            return ""

    # ------------------------------------------------------------------
    # 单节点执行
    # ------------------------------------------------------------------

    async def _invoke_agent(
        self,
        prompt: str,
        label: str = "",
        system_prompt: Optional[str] = None,
        agent_id: str = "",
        enable_skills: bool = False,
    ) -> str:
        """执行单个子Agent并返回输出"""
        if self._is_cancelled():
            logger.info(f"[Workflow] Workflow cancelled, stopping agent '{agent_id or label}'")
            raise asyncio.CancelledError("Workflow cancelled before agent start")

        short_label = label or (prompt[:40] + ("..." if len(prompt) > 40 else ""))
        aid = agent_id or short_label

        self._execution_data[aid] = {
            "label": label or aid,
            "toolCalls": [],
            "result": "",
        }

        await self._emit_ws(
            "workflow_agent_start",
            agent_id=aid,
            agent_label=label or aid,
        )

        async def _tool_event(event: str, tool_name: str, data: Any) -> None:
            if event == "tool_call":
                self._execution_data[aid]["toolCalls"].append({
                    "tool": tool_name,
                    "arguments": data if isinstance(data, dict) else {},
                    "status": "running",
                })
                await self._emit_ws(
                    "workflow_agent_tool_call",
                    agent_id=aid,
                    agent_label=label or aid,
                    tool=tool_name,
                    arguments=data if isinstance(data, dict) else {},
                )
            elif event == "tool_rejected":
                if not isinstance(data, ToolExecutionRejected):
                    raise TypeError("Workflow rejection requires operation-level result")
                calls = self._execution_data[aid]["toolCalls"]
                for call in reversed(calls):
                    if call["tool"] == tool_name and call["status"] == "running":
                        call.update({"status": "rejected", "reason": data.reason,
                                     "operation_id": data.operation_id})
                        break
            elif event == "tool_result":
                if not isinstance(data, ToolExecutionOutcome):
                    raise TypeError("Workflow tool result requires structured child outcome")
                result_preview = data.display_text[:2000]
                result_status = "success" if data.succeeded else data.state.value.lower()
                calls = self._execution_data[aid]["toolCalls"]
                for i in range(len(calls) - 1, -1, -1):
                    if calls[i]["tool"] == tool_name and calls[i]["status"] == "running":
                        calls[i]["status"] = result_status
                        calls[i]["state"] = data.state.value
                        calls[i]["operation_id"] = data.operation_id
                        calls[i]["attempt_id"] = data.attempt_id
                        calls[i]["result"] = result_preview
                        break
                await self._emit_ws(
                    "workflow_agent_tool_result",
                    agent_id=aid,
                    agent_label=label or aid,
                    tool=tool_name,
                    result=result_preview,
                    status=result_status,
                    state=data.state.value,
                    operation_id=data.operation_id,
                    attempt_id=data.attempt_id,
                    error_category=data.error_category.value if data.error_category else None,
                    side_effect_state=data.side_effect_state.value,
                )
            elif event == "chunk":
                await self._emit_ws(
                    "workflow_agent_chunk",
                    agent_id=aid,
                    agent_label=label or aid,
                    chunk=str(data),
                )

        task_id = self._mgr.create_task(
            label=short_label,
            message=prompt,
            system_prompt=system_prompt,
            event_callback=_tool_event,
            enable_skills=enable_skills,
            model_override=self._team_model_config,
            cancel_token=self._cancel_token,
        )
        self._child_task_ids.add(task_id)  # 登记归属，供按归属取消
        await self._mgr.execute_task(task_id)
        bg = self._mgr.running_tasks.get(task_id)
        if bg:
            await bg
        record = self._mgr.get_task(task_id)
        if record is None:
            raise RuntimeError(f"Sub-agent task {task_id} disappeared unexpectedly")
        child_outcome = record.outcome
        if child_outcome is None:
            child_outcome = ToolResult.unknown_outcome(
                ErrorCategory.RESULT_CONTRACT,
                "Sub-agent finished without a structured result.",
            )
        if child_outcome.state is not ExecutionState.SUCCEEDED:
            self._child_failures.append(child_outcome)
            self._execution_data[aid]["status"] = child_outcome.state.value.lower()
            await self._emit_ws(
                "workflow_agent_failed",
                agent_id=aid,
                agent_label=label or aid,
                result=child_outcome.display_text,
                status=child_outcome.state.value.lower(),
                state=child_outcome.state.value,
                side_effect_state=child_outcome.side_effect_state.value,
            )
            raise ChildOutcomeError(child_outcome)
        result = record.result or ""

        self._execution_data[aid]["result"] = result
        self._execution_data[aid]["status"] = "success"

        await self._emit_ws(
            "workflow_agent_complete",
            agent_id=aid,
            agent_label=label or aid,
            result=result,
            status="success",
            state=ExecutionState.SUCCEEDED.value,
        )
        return result
