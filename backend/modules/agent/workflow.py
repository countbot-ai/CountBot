"""WorkflowEngine：CountBot的多智能体编排引擎。

执行模式：
  pipeline - 顺序执行（上下文传递）
  graph    - 依赖DAG（自动并行）
  council  - 多视角审议（立场→评审→合成）
"""

import asyncio
import json as _json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from loguru import logger


class WorkflowMode(Enum):
    PIPELINE = "pipeline"
    GRAPH = "graph"
    COUNCIL = "council"


class SlotPhase(Enum):
    WAITING = "waiting"
    ACTIVE = "active"
    DONE = "done"
    FAILED = "failed"


@dataclass
class AgentSlot:
    """智能体在工作流图中的节点"""

    slot_id: str
    label: str
    prompt_template: str
    depends_on: list[str] = field(default_factory=list)
    phase: SlotPhase = SlotPhase.WAITING
    output: str | None = None
    error: str | None = None


class WorkflowEngine:
    """多智能体工作流引擎 — 编排 Pipeline / Graph / Council 三种执行模式。"""

    def __init__(self, subagent_manager, session_id: str | None = None, cancel_token=None, skills=None) -> None:
        self._mgr = subagent_manager
        self._session_id = session_id
        self._cancel_token = cancel_token
        self._skills = skills  # 技能系统实例
        # 每个 agent 的执行数据（工具调用 + 结论），最终序列化到结果中用于持久化
        self._execution_data: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # 内部辅助方法
    # ------------------------------------------------------------------

    async def _emit_ws(self, event_type: str, **data: Any) -> None:
        """通过 WebSocket 推送工作流生命周期事件（fire-and-forget）。"""
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
        """检查取消令牌是否已触发。"""
        return bool(self._cancel_token and self._cancel_token.is_cancelled)

    async def _invoke_agent(
        self,
        prompt: str,
        label: str = "",
        system_prompt: str | None = None,
        agent_id: str = "",
        enable_skills: bool = False,
    ) -> str:
        """同步执行单个子 Agent 并返回其最终输出。"""
        if self._is_cancelled():
            raise asyncio.CancelledError("Workflow cancelled before agent start")

        short_label = label or (prompt[:40] + ("..." if len(prompt) > 40 else ""))
        aid = agent_id or short_label

        self._execution_data[aid] = {
            "label": label or aid,
            "toolCalls": [],
            "result": "",
        }

        # 通知前端：agent 启动
        await self._emit_ws(
            "workflow_agent_start",
            agent_id=aid,
            agent_label=label or aid,
        )

        # 工具调用回调 — 实时推送到前端 + 收集数据用于持久化
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
                    tool=tool_name,
                    arguments=data if isinstance(data, dict) else {},
                )
            elif event == "tool_result":
                result_preview = str(data)[:2000] if data else ""
                # 更新最近一个 running 状态的同名工具调用
                calls = self._execution_data[aid]["toolCalls"]
                for i in range(len(calls) - 1, -1, -1):
                    if calls[i]["tool"] == tool_name and calls[i]["status"] == "running":
                        calls[i]["status"] = "success"
                        calls[i]["result"] = result_preview
                        break
                await self._emit_ws(
                    "workflow_agent_tool_result",
                    agent_id=aid,
                    tool=tool_name,
                    result=result_preview,
                )
            elif event == "chunk":
                # data 为文本 chunk，实时推送给前端用于流式展示
                await self._emit_ws(
                    "workflow_agent_chunk",
                    agent_id=aid,
                    chunk=str(data),
                )

        task_id = self._mgr.create_task(
            label=short_label,
            message=prompt,
            system_prompt=system_prompt,
            event_callback=_tool_event,
            enable_skills=enable_skills,  # 传递技能开关
        )
        await self._mgr.execute_task(task_id)          # schedules asyncio.Task
        bg = self._mgr.running_tasks.get(task_id)
        if bg:
            await bg                                    # wait for completion
        record = self._mgr.get_task(task_id)
        if record is None:
            raise RuntimeError(f"Sub-agent task {task_id} disappeared unexpectedly")
        if record.status.value == "failed":
            raise RuntimeError(record.error or "Sub-agent failed without error message")
        result = record.result or ""

        self._execution_data[aid]["result"] = result

        # 通知前端：agent 完成（发送完整结论，前端 Markdown 渲染）
        await self._emit_ws(
            "workflow_agent_complete",
            agent_id=aid,
            agent_label=label or aid,
            result=result,
        )
        return result

    def _detect_cycle(self, dep_map: dict[str, list[str]]) -> bool:
        """检测依赖图是否包含环。"""
        visited: set[str] = set()
        in_stack: set[str] = set()

        def _dfs(node: str) -> bool:
            visited.add(node)
            in_stack.add(node)
            for parent in dep_map.get(node, []):
                if parent not in visited:
                    if _dfs(parent):
                        return True
                elif parent in in_stack:
                    return True
            in_stack.discard(node)
            return False

        return any(_dfs(n) for n in dep_map if n not in visited)

    def _build_exec_metadata(self) -> str:
        """将执行数据序列化为 HTML 注释块，嵌入 result 以便刷新后恢复面板状态。"""
        if not self._execution_data:
            return ""
        try:
            payload = _json.dumps(self._execution_data, ensure_ascii=False)
            return f"\n\n<!--WORKFLOW_EXEC:{payload}:WORKFLOW_EXEC-->"
        except Exception:
            return ""

    # ------------------------------------------------------------------
    # Pipeline 流水线模式
    # ------------------------------------------------------------------

    async def run_pipeline(self, goal: str, stages: list[dict[str, Any]], enable_skills: bool = False) -> str:
        """顺序流水线 — 每个阶段继承前序所有输出。"""
        if not stages:
            return "No pipeline stages defined."

        accumulated: str = ""
        stage_outputs: list[dict] = []

        for idx, stage in enumerate(stages):
            # 每个阶段启动前检查取消令牌
            if self._is_cancelled():
                logger.info("[Workflow/Pipeline] 用户取消，终止流水线")
                break
            role = stage.get("role", f"Stage-{idx + 1}")
            task_desc = stage.get("task", "")
            custom_sp = stage.get("system_prompt") or None

            prior_ctx = (
                f"\n\n## Outputs from previous stages:\n{accumulated}"
                if accumulated
                else ""
            )
            prompt = (
                f"# Workflow Goal\n{goal}\n\n"
                f"# Your Task\n{task_desc}"
                f"{prior_ctx}\n\n"
                "Complete your task thoroughly and provide a clear, detailed output."
            )
            system_prompt = custom_sp or (
                f"You are {role}. "
                f"You are participating in a multi-agent pipeline workflow. "
                f"Your responsibility: {task_desc}. "
                "Focus exclusively on your assigned task and deliver a complete, precise result."
            )

            logger.info(f"[Workflow/Pipeline] Stage {idx + 1}/{len(stages)}: {role}")
            output = await self._invoke_agent(
                prompt, label=role, system_prompt=system_prompt,
                agent_id=stage.get("id", role),
                enable_skills=enable_skills,  # 传递技能开关
            )

            stage_outputs.append({"role": role, "output": output})
            accumulated += f"\n### {role}:\n{output}"

        lines = [f"# Pipeline Workflow Results\n\n**Goal:** {goal}\n"]
        for entry in stage_outputs:
            lines.append(f"## {entry['role']}\n\n{entry['output']}")
        return "\n\n---\n\n".join(lines) + self._build_exec_metadata()

    # ------------------------------------------------------------------
    # Graph 依赖图模式
    # ------------------------------------------------------------------

    async def run_graph(self, goal: str, slots: list[dict[str, Any]], enable_skills: bool = False) -> str:
        """依赖 DAG — 自动并行调度无依赖的节点。"""
        if not slots:
            return "No graph slots defined."

        # 按 slot ID 索引系统提示词
        slot_system_prompts: dict[str, str | None] = {}
        slot_map: dict[str, AgentSlot] = {}
        dep_map: dict[str, list[str]] = {}

        for s in slots:
            sid = s.get("id", "")
            if not sid:
                return "Error: every slot must have a non-empty 'id' field."
            deps = s.get("depends", [])
            role = s.get("role", sid)
            task_desc = s.get("task", "")
            custom_sp = s.get("system_prompt") or None
            slot_system_prompts[sid] = custom_sp or (
                f"You are {role}. "
                "You are a specialist agent inside a dependency-graph workflow. "
                f"Your responsibility: {task_desc}. "
                "Deliver a complete, precise result focused exclusively on your task."
            )
            slot_map[sid] = AgentSlot(
                slot_id=sid,
                label=role,
                prompt_template=task_desc,
                depends_on=list(deps),
            )
            dep_map[sid] = list(deps)

        # 验证依赖引用
        for sid, slot in slot_map.items():
            for dep in slot.depends_on:
                if dep not in slot_map:
                    return f"Error: slot '{sid}' depends on unknown slot '{dep}'."

        if self._detect_cycle(dep_map):
            return "Error: the dependency graph contains a cycle."

        # 调度循环 — 每轮并发执行所有无阻塞节点
        while any(s.phase == SlotPhase.WAITING for s in slot_map.values()):
            if self._is_cancelled():
                logger.info("[Workflow/Graph] 用户取消，终止依赖图调度")
                break
            ready = [
                s for s in slot_map.values()
                if s.phase == SlotPhase.WAITING
                and all(slot_map[d].phase == SlotPhase.DONE for d in s.depends_on)
            ]
            if not ready:
                # 上游失败 → 标记下游为失败
                for s in slot_map.values():
                    if s.phase == SlotPhase.WAITING and any(
                        slot_map[d].phase == SlotPhase.FAILED for d in s.depends_on
                    ):
                        s.phase = SlotPhase.FAILED
                        s.error = "Blocked by upstream failure"
                break

            for s in ready:
                s.phase = SlotPhase.ACTIVE
            logger.info(
                f"[Workflow/Graph] Dispatching {len(ready)} slot(s) in parallel: "
                f"{[s.slot_id for s in ready]}"
            )

            async def _run_slot(slot: AgentSlot) -> None:  # noqa: E306
                dep_ctx = ""
                if slot.depends_on:
                    dep_parts = [
                        f"### {slot_map[d].label}:\n{slot_map[d].output}"
                        for d in slot.depends_on
                        if slot_map[d].output
                    ]
                    if dep_parts:
                        dep_ctx = "\n\n## Outputs from upstream agents:\n" + "\n\n".join(dep_parts)
                prompt = (
                    f"# Workflow Goal\n{goal}\n\n"
                    f"# Your Task\n{slot.prompt_template}"
                    f"{dep_ctx}\n\n"
                    "Complete your task thoroughly and provide a clear, detailed output."
                )
                try:
                    slot.output = await self._invoke_agent(
                        prompt,
                        label=slot.label,
                        system_prompt=slot_system_prompts.get(slot.slot_id),
                        agent_id=slot.slot_id,
                        enable_skills=enable_skills,  # 传递技能开关
                    )
                    slot.phase = SlotPhase.DONE
                except Exception as exc:
                    slot.phase = SlotPhase.FAILED
                    slot.error = str(exc)
                    logger.error(f"[Workflow/Graph] Slot '{slot.slot_id}' failed: {exc}")

            await asyncio.gather(*[_run_slot(s) for s in ready])

        lines = [f"# Graph Workflow Results\n\n**Goal:** {goal}\n"]
        for slot in slot_map.values():
            icon = "✅" if slot.phase == SlotPhase.DONE else "❌"
            lines.append(f"## {icon} {slot.label}")
            if slot.output:
                lines.append(slot.output)
            elif slot.error:
                lines.append(f"*Error: {slot.error}*")
        return "\n\n---\n\n".join(lines) + self._build_exec_metadata()

    # ------------------------------------------------------------------
    # Council 多视角评审模式
    # ------------------------------------------------------------------

    async def run_council(self, question: str, members: list[dict[str, Any]], cross_review: bool = True, enable_skills: bool = False) -> str:
        """多视角评审：立场陈述 → [可选]交叉评审 → 综合输出。
        
        Args:
            question: 评审问题
            members: 成员列表
            cross_review: 是否启用交叉评审（True=交叉模式，False=独立模式）
            enable_skills: 是否启用技能系统
        """
        if not members:
            return "No council members defined."

        member_map: dict[str, str] = {
            m["id"]: m.get("perspective", "neutral analyst") for m in members
        }
        # 预构建每位成员的系统提示词
        member_system_prompts: dict[str, str] = {}
        for m in members:
            mid = m["id"]
            perspective = member_map[mid]
            custom_sp = m.get("system_prompt") or None
            member_system_prompts[mid] = custom_sp or (
                f"You are a council member representing the perspective of: {perspective}. "
                "You analyse questions rigorously from that viewpoint, defend your position "
                "with evidence, and engage constructively with other members' arguments."
            )

        # 第1轮 — 各成员陈述立场（并发）
        async def _initial(member: dict) -> tuple[str, str]:
            mid = member["id"]
            perspective = member_map[mid]
            prompt = (
                f"# Council Question\n{question}\n\n"
                f"# Your Perspective\n{perspective}\n\n"
                "Analyze this question thoroughly from your specific perspective. "
                "Provide a well-reasoned, detailed response."
            )
            logger.info(f"[Workflow/Council] Round-1: {mid}")
            result = await self._invoke_agent(
                prompt,
                label=f"{perspective} — 第1轮",
                system_prompt=member_system_prompts[mid],
                agent_id=f"{mid}:R1",
                enable_skills=enable_skills,  # 传递技能开关
            )
            return mid, result

        round1: dict[str, str] = dict(
            await asyncio.gather(*[_initial(m) for m in members])
        )

        # 检查是否在第1轮完成后被取消
        if self._is_cancelled():
            logger.info("[Workflow/Council] 用户取消，终止于第1轮完成后")
            return "Workflow cancelled after round 1."

        # 如果不启用交叉评审，直接返回第1轮结果
        if not cross_review:
            logger.info("[Workflow/Council] 独立模式，跳过交叉评审")
            blocks = []
            for m in members:
                mid = m["id"]
                persp = member_map[mid]
                blocks.append(f"### {persp}\n\n{round1.get(mid, '')}")
            
            body = "\n\n---\n\n".join(blocks)
            return (
                f"# 多视角分析结果（独立模式）\n\n"
                f"**议题：** {question}\n\n"
                f"## 各成员独立分析\n\n"
                f"{body}\n\n"
                f"---\n\n"
                f"*分析完成 — 共 {len(members)} 位成员独立分析，无交叉评审。*"
            ) + self._build_exec_metadata()

        # 第2轮 — 交叉评审（并发）
        async def _cross_review(member: dict) -> tuple[str, str]:
            mid = member["id"]
            perspective = member_map[mid]
            others = "\n\n".join(
                f"**{member_map[oid]} ({oid}):**\n{pos}"
                for oid, pos in round1.items()
                if oid != mid
            )
            prompt = (
                f"# Council Question\n{question}\n\n"
                f"# Your Perspective\n{perspective}\n\n"
                f"# Your Initial Position\n{round1[mid]}\n\n"
                f"# Other Members' Positions\n{others}\n\n"
                "Review the other positions carefully. "
                "Do you agree or disagree with their analyses? "
                "What did they miss or get right? "
                "Refine or defend your position in light of their input."
            )
            logger.info(f"[Workflow/Council] Round-2 cross-review: {mid}")
            result = await self._invoke_agent(
                prompt,
                label=f"{perspective} — 交叉评审",
                system_prompt=member_system_prompts[mid],
                agent_id=f"{mid}:R2",
                enable_skills=enable_skills,  # 传递技能开关
            )
            return mid, result

        round2: dict[str, str] = dict(
            await asyncio.gather(*[_cross_review(m) for m in members])
        )

        # Synthesis — 结构化中文输出，完整保留每位成员的分析内容
        blocks = []
        for m in members:
            mid = m["id"]
            persp = member_map[mid]
            blocks.append(
                f"### {persp}\n\n"
                f"**第1轮立场：**\n\n{round1.get(mid, '')}\n\n"
                f"**交叉评审：**\n\n{round2.get(mid, '')}"
            )

        body = "\n\n---\n\n".join(blocks)
        return (
            f"# 多视角评审结果（交叉模式）\n\n"
            f"**议题：** {question}\n\n"
            f"## 成员立场与评审\n\n"
            f"{body}\n\n"
            f"---\n\n"
            f"*评审完成 — 共 {len(members)} 位成员，2 轮交叉讨论。*\n\n"
            f"请将以上每位成员的完整分析内容如实呈现给用户，不要省略或替换为简短摘要。"
        ) + self._build_exec_metadata()

