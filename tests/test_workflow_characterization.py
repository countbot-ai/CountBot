"""Multi-Agent 工作流的行为基线（characterization tests）。

这三种编排模式目前没有任何直接测试：``tests/`` 里对 ``run_pipeline`` /
``run_council`` 的调用数为 0。重构执行器之前先把「模型实际收到的 prompt」和
「用户实际看到的输出」逐字节固定下来，作为等价性护栏。

这些用例刻意断言**当前**行为（包括那些看起来不优雅的空白和格式），目的不是
评价它，而是让重构后的差异无处可藏。要改行为请显式改这里，而不是让重构悄悄改掉。
"""

import json
from types import SimpleNamespace

import pytest

from backend.modules.agent.workflow import WorkflowEngine
from backend.modules.tools.execution import (
    ErrorCategory,
    ExecutionState,
    ToolResult,
)

PIPELINE_HEADER = "# Pipeline Workflow Results"
GRAPH_HEADER = "# Graph Workflow Results"


class _ScriptedManager:
    """记录每次子任务调用，并按脚本回放输出。"""

    def __init__(self, outputs=(), failures=None):
        self.calls = []
        self.running_tasks = {}
        self._outputs = list(outputs)
        self._failures = dict(failures or {})

    def create_task(self, **kwargs):
        self.calls.append(kwargs)
        return f"task-{len(self.calls) - 1}"

    async def execute_task(self, task_id):
        pass

    def get_task(self, task_id):
        index = int(task_id.rsplit("-", 1)[1])
        if index in self._failures:
            return SimpleNamespace(outcome=self._failures[index], result=None)
        output = self._outputs[index] if index < len(self._outputs) else f"output-{index}"
        return SimpleNamespace(outcome=ToolResult.success(output), result=output)


def _split_metadata(text):
    """拆出正文与 WORKFLOW_EXEC 注释里的执行数据。"""
    marker = "<!--WORKFLOW_EXEC:"
    assert marker in text, "workflow output must carry execution metadata"
    body, _, rest = text.partition("\n\n" + marker)
    payload = rest.split(":WORKFLOW_EXEC-->", 1)[0]
    return body, json.loads(payload)


def _sections(body):
    return body.split("\n\n---\n\n")


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_prompts_and_output_are_pinned():
    manager = _ScriptedManager(["A", "B"])
    engine = WorkflowEngine(manager)
    stages = [
        {"id": "researcher", "role": "Researcher", "task": "Do research"},
        {"id": "writer", "role": "Writer", "task": "Do writing"},
    ]

    text = await engine.run_pipeline("Ship it", stages)

    assert manager.calls[0]["message"] == (
        "# Workflow Goal\nShip it\n\n"
        "# Your Task\nDo research\n\n"
        "Complete your task thoroughly and provide a clear, detailed output."
    )
    # 第 2 阶段必须拿到第 1 阶段全文，且前缀与空行形式固定
    assert manager.calls[1]["message"] == (
        "# Workflow Goal\nShip it\n\n"
        "# Your Task\nDo writing"
        "\n\n## Outputs from previous stages:\n\n### Researcher:\nA"
        "\n\nComplete your task thoroughly and provide a clear, detailed output."
    )
    assert manager.calls[0]["system_prompt"] == (
        "You are Researcher. You are participating in a multi-agent pipeline workflow. "
        "Your responsibility: Do research. "
        "Focus exclusively on your assigned task and deliver a complete, precise result."
    )

    body, metadata = _split_metadata(text)
    assert _sections(body) == [
        "# Pipeline Workflow Results\n\n**Goal:** Ship it\n",
        "## Researcher\n\nA",
        "## Writer\n\nB",
    ]
    assert [entry["result"] for entry in metadata.values()] == ["A", "B"]


@pytest.mark.asyncio
async def test_pipeline_keeps_legacy_embedded_system_prompt():
    """旧团队把整段人设塞在 task 里，必须继续被识别为 system prompt。"""
    manager = _ScriptedManager(["A"])
    engine = WorkflowEngine(manager)
    persona = (
        "你是资深研究员。\n\n"
        "输出要求：\n1. 结构化输出\n2. 引用来源\n3. 标注不确定项\n"
        "4. 每个结论都要给出依据和反例\n5. 不确定的地方要显式标注\n\n"
        "记住：不要编造任何数据。"
    )
    assert len(persona.strip()) >= 80
    stages = [{"id": "r", "role": "Researcher", "task": persona}]

    await engine.run_pipeline("goal", stages)

    assert manager.calls[0]["system_prompt"] == persona
    assert (
        "围绕工作流目标完成“Researcher”阶段，给出清晰、可执行、便于下游继续处理的结果。"
        in manager.calls[0]["message"]
    )
    assert persona not in manager.calls[0]["message"]


@pytest.mark.asyncio
async def test_pipeline_child_failure_is_terminal_and_aborts_remaining_stages():
    failure = ToolResult.failure(ErrorCategory.EXECUTION, "stage exploded")
    manager = _ScriptedManager(["A"], failures={1: failure})
    engine = WorkflowEngine(manager)
    stages = [
        {"id": "one", "role": "One", "task": "first"},
        {"id": "two", "role": "Two", "task": "second"},
        {"id": "three", "role": "Three", "task": "third"},
    ]

    result = await engine.run_outcome("pipeline", "goal", stages)

    assert result.state is ExecutionState.FAILED
    assert result.error_category is ErrorCategory.EXECUTION
    assert result.display_text == "stage exploded"
    # 失败即中止：没有继续跑第三阶段
    assert len(manager.calls) == 2


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_graph_context_is_direct_dependencies_only():
    manager = _ScriptedManager(["A", "B", "C"])
    engine = WorkflowEngine(manager)
    slots = [
        {"id": "a", "task": "alpha"},
        {"id": "b", "task": "beta", "depends_on": ["a"]},
        {"id": "c", "task": "gamma", "depends_on": ["b"]},
    ]

    await engine.run_graph("goal", slots)

    assert "# Outputs from upstream agents:" not in manager.calls[0]["message"]
    # 下游只看到直接依赖（label 取 role，缺省为 id）
    assert "### a:\nA" in manager.calls[1]["message"]
    assert "### a:\nA" not in manager.calls[2]["message"]
    assert "### b:\nB" in manager.calls[2]["message"]


@pytest.mark.asyncio
async def test_graph_output_marks_each_slot_status():
    manager = _ScriptedManager(["A", "B"])
    engine = WorkflowEngine(manager)
    slots = [
        {"id": "a", "role": "Alpha", "task": "alpha"},
        {"id": "b", "role": "Beta", "task": "beta", "depends_on": ["a"]},
    ]

    text = await engine.run_graph("goal", slots)

    body, _ = _split_metadata(text)
    # 注意：状态行与正文是相邻但不相同的段落（渲染器按段落拼 ---）
    assert _sections(body) == [
        "# Graph Workflow Results\n\n**Goal:** goal\n",
        "## ✅ Alpha (Done)",
        "A",
        "## ✅ Beta (Done)",
        "B",
    ]


@pytest.mark.asyncio
async def test_graph_rejects_cycles_and_unknown_dependencies():
    engine = WorkflowEngine(_ScriptedManager())

    cyclic = await engine.run_outcome("graph", "goal", [
        {"id": "a", "task": "a", "depends_on": ["b"]},
        {"id": "b", "task": "b", "depends_on": ["a"]},
    ])
    assert cyclic.state is ExecutionState.FAILED
    assert cyclic.error_category is ErrorCategory.VALIDATION
    assert "cycle" in cyclic.display_text

    unknown = await engine.run_outcome("graph", "goal", [
        {"id": "a", "task": "a", "depends_on": ["ghost"]},
    ])
    assert unknown.state is ExecutionState.FAILED
    assert "unknown slot 'ghost'" in unknown.display_text


@pytest.mark.asyncio
async def test_graph_condition_skip_runs_nothing_and_is_visible():
    manager = _ScriptedManager(["A"])
    engine = WorkflowEngine(manager)
    slots = [
        {"id": "a", "role": "Alpha", "task": "alpha"},
        {
            "id": "b",
            "role": "Beta",
            "task": "beta",
            "depends_on": ["a"],
            "condition": {"type": "output_contains", "node": "a", "text": "ABSENT"},
        },
    ]

    text = await engine.run_graph("goal", slots)

    assert len(manager.calls) == 1
    body, _ = _split_metadata(text)
    sections = _sections(body)
    assert "## ⏭️ Beta (Skipped)" in sections
    assert "[Skipped: condition not met]" in sections


@pytest.mark.asyncio
async def test_graph_failure_blocks_dependents_but_marks_them_failed():
    failure = ToolResult.failure(ErrorCategory.EXECUTION, "slot exploded")
    manager = _ScriptedManager(failures={0: failure})
    engine = WorkflowEngine(manager)
    slots = [
        {"id": "a", "role": "Alpha", "task": "alpha"},
        {"id": "b", "role": "Beta", "task": "beta", "depends_on": ["a"]},
    ]

    result = await engine.run_outcome("graph", "goal", slots)

    assert result.state is ExecutionState.FAILED
    assert result.error_category is ErrorCategory.EXECUTION
    body, _ = _split_metadata(result.display_text)
    sections = _sections(body)
    assert "## ❌ Alpha (Failed)" in sections
    assert "*Error: slot exploded*" in sections
    assert "## ❌ Beta (Failed)" in sections
    assert "*Error: Blocked by upstream failure*" in sections


# ---------------------------------------------------------------------------
# Council
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_council_independent_mode_is_one_round_only():
    manager = _ScriptedManager(["POS-A", "POS-B"])
    engine = WorkflowEngine(manager)
    members = [
        {"id": "a", "perspective": "optimist"},
        {"id": "b", "perspective": "skeptic"},
    ]

    text = await engine.run_council("Should we ship?", members, cross_review=False)

    assert len(manager.calls) == 2
    assert manager.calls[0]["message"] == (
        "# Council Question\nShould we ship?\n\n"
        "# Your Perspective\noptimist\n\n"
        "Analyze this question thoroughly from your specific perspective. "
        "Provide a well-reasoned, detailed response."
    )
    body, metadata = _split_metadata(text)
    assert body.startswith("# 多视角分析结果（独立模式）")
    assert "### optimist\n\nPOS-A" in body
    assert "*分析完成 — 共 2 位成员独立分析，无交叉评审。*" in body
    assert set(metadata) == {"a:R1", "b:R1"}


@pytest.mark.asyncio
async def test_council_cross_review_injects_other_members_positions():
    manager = _ScriptedManager(["POS-A", "POS-B", "REV-A", "REV-B"])
    engine = WorkflowEngine(manager)
    members = [
        {"id": "a", "perspective": "optimist"},
        {"id": "b", "perspective": "skeptic"},
    ]

    text = await engine.run_council("Should we ship?", members, cross_review=True)

    assert len(manager.calls) == 4
    # 第 2 轮必须看到对方第 1 轮立场，并保留自己的立场小节
    assert manager.calls[2]["message"] == (
        "# Council Question\nShould we ship?\n\n"
        "# Your Perspective\noptimist\n\n"
        "# Your Initial Position\nPOS-A\n\n"
        "# Other Members' Positions\n**skeptic (b):**\nPOS-B\n\n"
        "Review the other positions carefully. "
        "Do you agree or disagree with their analyses? "
        "What did they miss or get right? "
        "Refine or defend your position in light of their input."
    )
    labels = [call["label"] for call in manager.calls]
    assert labels == [
        "optimist — 第1轮",
        "skeptic — 第1轮",
        "optimist — 交叉评审",
        "skeptic — 交叉评审",
    ]

    body, metadata = _split_metadata(text)
    assert body.startswith("# 多视角评审结果（交叉模式）")
    assert "**第1轮立场：**\n\nPOS-A" in body
    assert "**交叉评审：**\n\nREV-A" in body
    # 现有语义：不做最终综合，交给主 Agent 原样呈现
    assert "请将以上每位成员的完整分析内容如实呈现给用户，不要省略或替换为简短摘要。" in body
    assert set(metadata) == {"a:R1", "a:R2", "b:R1", "b:R2"}


@pytest.mark.asyncio
async def test_council_failure_surfaces_child_outcome_instead_of_partial_text():
    failure = ToolResult.failure(ErrorCategory.EXECUTION, "member exploded")
    manager = _ScriptedManager(["POS-A"], failures={1: failure})
    engine = WorkflowEngine(manager)
    members = [
        {"id": "a", "perspective": "optimist"},
        {"id": "b", "perspective": "skeptic"},
    ]

    result = await engine.run_outcome("council", "q", members)

    assert result.state is ExecutionState.FAILED
    assert result.display_text == "member exploded"
