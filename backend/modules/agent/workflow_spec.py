"""工作流的唯一表示：一份 spec，模式只是预设。

现在 ``pipeline`` / ``graph`` / ``council`` 三种 mode 各自实现了一遍调度、上下文
规则、失败聚合和渲染，于是：混合拓扑表达不了（并行调研 → 收敛 → 串行实现 →
回环评审），加一种模式要同时改 model、两处 pydantic、dispatch 和四个前端表单，
而三份实现里任何一处修 bug 都要记得另外两处。

这里把拓扑搬进数据：``WorkflowSpec`` 是唯一执行入口，三种模式由编译器翻译成
spec，行为逐字节保持一致（``tests/test_workflow_characterization.py`` 是护栏）。
后续要加的 ``map`` / ``branch`` / ``loop`` / ``checkpoint`` 节点也说同一套话，
不再新增 mode。

设计上刻意不做的事：

- 不在这里执行任何用户/模型生成的代码（Python 没有 ``node:vm`` 等价物）；
- 不把渲染写进执行器——``render`` 是 spec 上的一个可调用对象，三种预设各自保留
  既有输出格式，便于「行为不变」这条约束可验证。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from backend.modules.tools.execution import (
    ErrorCategory,
    SideEffectState,
    ToolResult,
)

# 失败策略：continue = 标记失败并让下游 blocked（graph）；
# abort = 本轮结束后立刻抛出（pipeline / council，两者的「轮」大小不同但语义一致）
POLICY_CONTINUE = "continue"
POLICY_ABORT = "abort"


class ChildOutcomeError(RuntimeError):
    """A child completed with a structured non-success outcome."""

    def __init__(self, result: ToolResult):
        super().__init__(result.display_text)
        self.result = result


class NodeState(Enum):
    WAITING = "waiting"
    ACTIVE = "active"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class NodeResult:
    state: NodeState = NodeState.WAITING
    output: str = ""
    error: Optional[str] = None


@dataclass
class WorkflowNode:
    """执行图上的一个节点。

    ``prompt`` 是 ``(PromptContext) -> str``：把「这个节点该看到什么」交给编译期
    决定，执行器只负责何时调用、失败怎么办。
    """

    node_id: str
    label: str
    prompt: Callable[["PromptContext"], str]
    system_prompt: Optional[str] = None
    needs: Tuple[str, ...] = ()
    condition: Optional[Dict[str, Any]] = None
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowRun:
    spec: "WorkflowSpec"
    goal: str
    nodes: Dict[str, NodeResult]
    order: List[WorkflowNode]

    def output_of(self, node_id: str) -> str:
        result = self.nodes.get(node_id)
        return (result.output or "") if result is not None else ""

    def state_of(self, node_id: str) -> NodeState:
        result = self.nodes.get(node_id)
        return result.state if result is not None else NodeState.WAITING


@dataclass
class PromptContext:
    goal: str
    node: WorkflowNode
    run: WorkflowRun


@dataclass
class WorkflowSpec:
    """一次工作流的完整定义。唯一执行入口。"""

    goal: str
    nodes: List[WorkflowNode]
    render: Callable[[WorkflowRun], str]
    failure_policy: str = POLICY_CONTINUE
    enable_skills: bool = False
    # 兼容字段：仅用于日志/诊断，不参与调度
    preset: str = ""
    # council 预设专用（渲染时按声明顺序还原成员视角）
    members: List[Tuple[str, str]] = field(default_factory=list)
    cross_review: bool = True

    def validate(self) -> None:
        seen = set()
        for node in self.nodes:
            if not node.node_id:
                raise ChildOutcomeError(ToolResult.failure(
                    ErrorCategory.VALIDATION,
                    "Every slot must have a non-empty 'id' field.",
                    side_effect_state=SideEffectState.NOT_ATTEMPTED,
                ))
            if node.node_id in seen:
                raise ChildOutcomeError(ToolResult.failure(
                    ErrorCategory.VALIDATION,
                    f"Duplicate slot id '{node.node_id}'.",
                    side_effect_state=SideEffectState.NOT_ATTEMPTED,
                ))
            seen.add(node.node_id)

        for node in self.nodes:
            for dep in node.needs:
                if dep not in seen:
                    raise ChildOutcomeError(ToolResult.failure(
                        ErrorCategory.VALIDATION,
                        f"Slot '{node.node_id}' depends on unknown slot '{dep}'.",
                        side_effect_state=SideEffectState.NOT_ATTEMPTED,
                    ))

        if has_cycle({node.node_id: list(node.needs) for node in self.nodes}):
            raise ChildOutcomeError(ToolResult.failure(
                ErrorCategory.VALIDATION,
                "The dependency graph contains a cycle.",
                side_effect_state=SideEffectState.NOT_ATTEMPTED,
            ))


def has_cycle(dep_map: Dict[str, List[str]]) -> bool:
    """拓扑检测：存在环则返回 True。"""
    visited: Dict[str, int] = {}

    def visit(node: str) -> bool:
        state = visited.get(node, 0)
        if state == 1:
            return True
        if state == 2:
            return False
        visited[node] = 1
        for dep in dep_map.get(node, ()):
            if visit(dep):
                return True
        visited[node] = 2
        return False

    return any(visit(node) for node in list(dep_map))


# ---------------------------------------------------------------------------
# 共享的 prompt 片段
# ---------------------------------------------------------------------------


def _looks_like_embedded_system_prompt(text: str) -> bool:
    """Detect legacy teams that stored persona-like prompt blocks in task."""
    normalized = (text or "").strip()
    if len(normalized) < 80:
        return False

    prompt_markers = (
        normalized.startswith("你是"),
        normalized.startswith("# 角色"),
        "输出要求" in normalized,
        "工作流程" in normalized,
        "记住：" in normalized,
        "记住:" in normalized,
        normalized.count("\n") >= 3,
    )
    return any(prompt_markers)


def _split_legacy_persona(role: str, task_desc: str) -> Tuple[Optional[str], str]:
    """把旧团队塞在 task 里的人设还原成 (system_prompt, 有效 task)。"""
    if not _looks_like_embedded_system_prompt(task_desc):
        return None, task_desc
    return (
        task_desc,
        f"围绕工作流目标完成“{role}”阶段，"
        "给出清晰、可执行、便于下游继续处理的结果。",
    )


# ---------------------------------------------------------------------------
# pipeline
# ---------------------------------------------------------------------------


def compile_pipeline(goal: str, stages: List[Dict[str, Any]], *, enable_skills: bool = False) -> WorkflowSpec:
    if not stages:
        raise ChildOutcomeError(ToolResult.failure(
            ErrorCategory.VALIDATION,
            "No pipeline stages defined.",
            side_effect_state=SideEffectState.NOT_ATTEMPTED,
        ))

    nodes: List[WorkflowNode] = []
    labels: Dict[str, str] = {}

    for index, stage in enumerate(stages):
        role = stage.get("role", f"Stage-{index + 1}")
        task_desc = stage.get("task", "")
        # 节点 id 必须唯一且不能依赖用户输入：两个阶段同名 role/id 是合法的
        # （用户自定义团队里很常见），但 ExecutionData 的 key 仍是 role/id，
        # 与改造前保持一致。
        node_id = f"stage-{index}"
        agent_id = stage.get("id", role)
        custom = stage.get("system_prompt") or None
        effective = task_desc
        if not custom:
            custom, effective = _split_legacy_persona(role, task_desc)

        system_prompt = custom or (
            f"You are {role}. "
            f"You are participating in a multi-agent pipeline workflow. "
            f"Your responsibility: {task_desc}. "
            "Focus exclusively on your assigned task and deliver a complete, precise result."
        )

        previous_ids = tuple(labels)
        effective_task = effective

        def build(
            ctx: PromptContext,
            _task: str = effective_task,
            _previous: Tuple[str, ...] = previous_ids,
        ) -> str:
            accumulated = "".join(
                f"\n### {labels[pid]}:\n{ctx.run.output_of(pid)}" for pid in _previous
            )
            prior = (
                f"\n\n## Outputs from previous stages:\n{accumulated}"
                if accumulated
                else ""
            )
            return (
                f"# Workflow Goal\n{ctx.goal}\n\n"
                f"# Your Task\n{_task}"
                f"{prior}\n\n"
                "Complete your task thoroughly and provide a clear, detailed output."
            )

        labels[node_id] = role
        nodes.append(WorkflowNode(
            node_id=node_id,
            label=role,
            prompt=build,
            system_prompt=system_prompt,
            needs=previous_ids,
            meta={"agent_id": agent_id},
        ))

    return WorkflowSpec(
        goal=goal,
        nodes=nodes,
        render=render_pipeline,
        failure_policy=POLICY_ABORT,
        enable_skills=enable_skills,
        preset="pipeline",
    )


def render_pipeline(run: WorkflowRun) -> str:
    lines = [f"# Pipeline Workflow Results\n\n**Goal:** {run.goal}\n"]
    for node in run.order:
        lines.append(f"## {node.label}\n\n{run.output_of(node.node_id)}")
    return "\n\n---\n\n".join(lines)


# ---------------------------------------------------------------------------
# graph
# ---------------------------------------------------------------------------


def compile_graph(goal: str, slots: List[Dict[str, Any]], *, enable_skills: bool = False) -> WorkflowSpec:
    if not slots:
        raise ChildOutcomeError(ToolResult.failure(
            ErrorCategory.VALIDATION,
            "No graph slots defined.",
            side_effect_state=SideEffectState.NOT_ATTEMPTED,
        ))

    # 与改造前的 slot_map 一致：重复 id 折叠为一项（后者覆盖、位置保留），
    # 而不是静默产生两个互不相干的节点。
    built: Dict[str, WorkflowNode] = {}
    labels: Dict[str, str] = {}

    for slot in slots:
        slot_id = slot.get("id", "")
        if not slot_id:
            raise ChildOutcomeError(ToolResult.failure(
                ErrorCategory.VALIDATION,
                "Every slot must have a non-empty 'id' field.",
                side_effect_state=SideEffectState.NOT_ATTEMPTED,
            ))
        depends = list(slot.get("depends_on", slot.get("depends", [])))
        role = slot.get("role", slot_id)
        task_desc = slot.get("task", "")
        custom = slot.get("system_prompt") or None
        effective = task_desc
        if not custom:
            custom, effective = _split_legacy_persona(role, task_desc)

        system_prompt = custom or (
            f"You are {role}. "
            "You are a specialist agent inside a dependency-graph workflow. "
            f"Your responsibility: {task_desc}. "
            "Deliver a complete, precise result focused exclusively on your task."
        )

        def build(
            ctx: PromptContext,
            _task: str = effective,
            _needs: Tuple[str, ...] = tuple(depends),
        ) -> str:
            parts = [
                f"### {labels[dep]}:\n{ctx.run.output_of(dep)}"
                for dep in _needs
                if ctx.run.output_of(dep) and ctx.run.state_of(dep) is not NodeState.SKIPPED
            ]
            dep_ctx = (
                "\n\n## Outputs from upstream agents:\n" + "\n\n".join(parts)
                if parts
                else ""
            )
            return (
                f"# Workflow Goal\n{ctx.goal}\n\n"
                f"# Your Task\n{_task}"
                f"{dep_ctx}\n\n"
                "Complete your task thoroughly and provide a clear, detailed output."
            )

        labels[slot_id] = role
        built[slot_id] = WorkflowNode(
            node_id=slot_id,
            label=role,
            prompt=build,
            system_prompt=system_prompt,
            needs=tuple(depends),
            condition=slot.get("condition"),
        )

    nodes = list(built.values())
    _validate_dependencies(nodes)

    return WorkflowSpec(
        goal=goal,
        nodes=nodes,
        render=render_graph,
        failure_policy=POLICY_CONTINUE,
        enable_skills=enable_skills,
        preset="graph",
    )


def _validate_dependencies(nodes: List[WorkflowNode]) -> None:
    """校验依赖存在且无环（与改造前的检查顺序、文案一致）。"""
    known = {node.node_id for node in nodes}
    for node in nodes:
        for dep in node.needs:
            if dep not in known:
                raise ChildOutcomeError(ToolResult.failure(
                    ErrorCategory.VALIDATION,
                    f"Slot '{node.node_id}' depends on unknown slot '{dep}'.",
                    side_effect_state=SideEffectState.NOT_ATTEMPTED,
                ))
    if has_cycle({node.node_id: list(node.needs) for node in nodes}):
        raise ChildOutcomeError(ToolResult.failure(
            ErrorCategory.VALIDATION,
            "The dependency graph contains a cycle.",
            side_effect_state=SideEffectState.NOT_ATTEMPTED,
        ))


def render_graph(run: WorkflowRun) -> str:
    lines = [f"# Graph Workflow Results\n\n**Goal:** {run.goal}\n"]
    for node in run.order:
        result = run.nodes[node.node_id]
        if result.state is NodeState.SKIPPED:
            icon, status = "⏭️", "Skipped"
        elif result.state is NodeState.DONE:
            icon, status = "✅", "Done"
        else:
            icon, status = "❌", "Failed"
        lines.append(f"## {icon} {node.label} ({status})")
        if result.output:
            lines.append(result.output)
        elif result.error:
            lines.append(f"*Error: {result.error}*")
    return "\n\n---\n\n".join(lines)


# ---------------------------------------------------------------------------
# council
# ---------------------------------------------------------------------------


def compile_council(
    question: str,
    members: List[Dict[str, Any]],
    *,
    cross_review: bool = True,
    enable_skills: bool = False,
) -> WorkflowSpec:
    if not members:
        raise ChildOutcomeError(ToolResult.failure(
            ErrorCategory.VALIDATION,
            "No council members defined.",
            side_effect_state=SideEffectState.NOT_ATTEMPTED,
        ))

    perspectives = {m["id"]: m.get("perspective", "neutral analyst") for m in members}
    # 与改造前的 member_map 一致：重复 id 折叠为一项
    built: Dict[str, WorkflowNode] = {}

    for member in members:
        mid = member["id"]
        perspective = perspectives[mid]
        custom = member.get("system_prompt") or None
        system_prompt = custom or (
            f"You are a council member representing the perspective of: {perspective}. "
            "You analyse questions rigorously from that viewpoint, defend your position "
            "with evidence, and engage constructively with other members' arguments."
        )

        def build(ctx: PromptContext, _perspective: str = perspective) -> str:
            return (
                f"# Council Question\n{ctx.goal}\n\n"
                f"# Your Perspective\n{_perspective}\n\n"
                "Analyze this question thoroughly from your specific perspective. "
                "Provide a well-reasoned, detailed response."
            )

        built[f"{mid}:R1"] = WorkflowNode(
            node_id=f"{mid}:R1",
            label=f"{perspective} — 第1轮",
            prompt=build,
            system_prompt=system_prompt,
            meta={"member": mid, "perspective": perspective, "round": 1},
        )

    if cross_review:
        for member in members:
            mid = member["id"]
            perspective = perspectives[mid]
            custom = member.get("system_prompt") or None
            system_prompt = custom or (
                f"You are a council member representing the perspective of: {perspective}. "
                "You analyse questions rigorously from that viewpoint, defend your position "
                "with evidence, and engage constructively with other members' arguments."
            )
            others = tuple(
                (other["id"], perspectives[other["id"]])
                for other in members
                if other["id"] != mid
            )

            def build(
                ctx: PromptContext,
                _mid: str = mid,
                _perspective: str = perspective,
                _others: Tuple[Tuple[str, str], ...] = others,
            ) -> str:
                others_text = "\n\n".join(
                    f"**{label} ({oid}):**\n{ctx.run.output_of(oid + ':R1')}"
                    for oid, label in _others
                )
                return (
                    f"# Council Question\n{ctx.goal}\n\n"
                    f"# Your Perspective\n{_perspective}\n\n"
                    f"# Your Initial Position\n{ctx.run.output_of(_mid + ':R1')}\n\n"
                    f"# Other Members' Positions\n{others_text}\n\n"
                    "Review the other positions carefully. "
                    "Do you agree or disagree with their analyses? "
                    "What did they miss or get right? "
                    "Refine or defend your position in light of their input."
                )

            built[f"{mid}:R2"] = WorkflowNode(
                node_id=f"{mid}:R2",
                label=f"{perspective} — 交叉评审",
                prompt=build,
                system_prompt=system_prompt,
                needs=tuple(f"{m['id']}:R1" for m in members),
                meta={"member": mid, "perspective": perspective, "round": 2},
            )

    nodes = list(built.values())
    return WorkflowSpec(
        goal=question,
        nodes=nodes,
        render=render_council,
        failure_policy=POLICY_ABORT,
        enable_skills=enable_skills,
        preset="council",
        members=[(m["id"], perspectives[m["id"]]) for m in members],
        cross_review=bool(cross_review),
    )


def render_council(run: WorkflowRun) -> str:
    spec = run.spec
    members = spec.members
    cross_review = spec.cross_review

    if not cross_review:
        blocks = [
            f"### {perspective}\n\n{run.output_of(f'{mid}:R1')}"
            for mid, perspective in members
        ]
        body = "\n\n---\n\n".join(blocks)
        return (
            "# 多视角分析结果（独立模式）\n\n"
            f"**议题：** {run.goal}\n\n"
            "## 各成员独立分析\n\n"
            f"{body}\n\n"
            "---\n\n"
            f"*分析完成 — 共 {len(members)} 位成员独立分析，无交叉评审。*"
        )

    blocks = []
    for mid, perspective in members:
        blocks.append(
            f"### {perspective}\n\n"
            f"**第1轮立场：**\n\n{run.output_of(f'{mid}:R1')}\n\n"
            f"**交叉评审：**\n\n{run.output_of(f'{mid}:R2')}"
        )
    body = "\n\n---\n\n".join(blocks)
    return (
        "# 多视角评审结果（交叉模式）\n\n"
        f"**议题：** {run.goal}\n\n"
        "## 成员立场与评审\n\n"
        f"{body}\n\n"
        "---\n\n"
        f"*评审完成 — 共 {len(members)} 位成员，2 轮交叉讨论。*\n\n"
        "请将以上每位成员的完整分析内容如实呈现给用户，不要省略或替换为简短摘要。"
    )
