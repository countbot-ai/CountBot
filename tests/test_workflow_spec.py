"""WorkflowSpec 编译器与校验的行为测试。

三种历史模式现在只是同一份 spec 的预设。这个文件锁住编译结果的结构：节点、
依赖、失败策略、council 的两轮形状——它们是后续加 map / branch / loop 节点时
的地基，也是「新增拓扑不要新增 mode」这条约定的可执行版本。
"""

import pytest

from backend.modules.agent import workflow_spec as spec_module
from backend.modules.agent.workflow_spec import (
    POLICY_ABORT,
    POLICY_CONTINUE,
    ChildOutcomeError,
    NodeState,
    WorkflowNode,
    WorkflowRun,
    WorkflowSpec,
    compile_council,
    compile_graph,
    compile_pipeline,
    has_cycle,
)


def _node(node_id, needs=()):
    return WorkflowNode(node_id=node_id, label=node_id, prompt=lambda ctx: "", needs=tuple(needs))


def test_pipeline_compiles_to_a_linear_chain():
    spec = compile_pipeline("goal", [
        {"id": "a", "role": "A", "task": "first"},
        {"id": "b", "role": "B", "task": "second"},
        {"id": "c", "role": "C", "task": "third"},
    ])

    assert spec.preset == "pipeline"
    assert spec.failure_policy == POLICY_ABORT
    # 内部节点 id 由下标生成，保证不随用户数据冲突；对外的 agent id 仍是 role/id
    assert [node.node_id for node in spec.nodes] == ["stage-0", "stage-1", "stage-2"]
    assert [node.meta["agent_id"] for node in spec.nodes] == ["a", "b", "c"]
    assert [node.needs for node in spec.nodes] == [
        (),
        ("stage-0",),
        ("stage-0", "stage-1"),
    ]


def test_pipeline_tolerates_duplicate_roles():
    """同名角色是合法的：两个阶段都要跑，且各自渲染各自的输出。"""
    spec = compile_pipeline("goal", [
        {"role": "Researcher", "task": "first"},
        {"role": "Researcher", "task": "second"},
    ])

    assert [node.node_id for node in spec.nodes] == ["stage-0", "stage-1"]
    assert [node.label for node in spec.nodes] == ["Researcher", "Researcher"]
    # 对外的 agent id 与改造前一致（role），因此 execution_data 仍会合并同名项
    assert [node.meta["agent_id"] for node in spec.nodes] == ["Researcher", "Researcher"]


def test_pipeline_rejects_an_empty_stage_list():
    with pytest.raises(ChildOutcomeError) as raised:
        compile_pipeline("goal", [])

    assert "No pipeline stages defined" in raised.value.result.display_text


def test_graph_compiles_to_a_dag_and_keeps_declaration_order():
    spec = compile_graph("goal", [
        {"id": "a", "task": "alpha"},
        {"id": "b", "task": "beta", "depends": ["a"]},
        {"id": "c", "task": "gamma", "depends_on": ["a"]},
    ])

    assert spec.preset == "graph"
    assert spec.failure_policy == POLICY_CONTINUE
    assert [node.node_id for node in spec.nodes] == ["a", "b", "c"]
    assert [node.needs for node in spec.nodes] == [(), ("a",), ("a",)]


def test_graph_validation_rejects_unknown_dependencies_and_cycles():
    with pytest.raises(ChildOutcomeError) as unknown:
        compile_graph("goal", [{"id": "a", "task": "a", "depends_on": ["ghost"]}])
    assert "unknown slot 'ghost'" in unknown.value.result.display_text

    with pytest.raises(ChildOutcomeError) as cyclic:
        compile_graph("goal", [
            {"id": "a", "task": "a", "depends_on": ["b"]},
            {"id": "b", "task": "b", "depends_on": ["a"]},
        ])
    assert "cycle" in cyclic.value.result.display_text


def test_spec_validation_rejects_duplicate_ids():
    spec = WorkflowSpec(
        goal="goal",
        nodes=[_node("a"), _node("a")],
        render=lambda run: "",
    )

    with pytest.raises(ChildOutcomeError) as raised:
        spec.validate()

    assert "Duplicate slot id 'a'" in raised.value.result.display_text


def test_has_cycle_handles_diamonds_and_self_loops():
    assert has_cycle({"a": ["b", "c"], "b": ["d"], "c": ["d"], "d": []}) is False
    assert has_cycle({"a": ["a"]}) is True
    assert has_cycle({"a": ["b"], "b": ["c"], "c": ["a"]}) is True


def test_council_compiles_to_two_rounds_with_peer_review():
    spec = compile_council("question", [
        {"id": "a", "perspective": "optimist"},
        {"id": "b", "perspective": "skeptic"},
    ])

    assert spec.preset == "council"
    assert spec.failure_policy == POLICY_ABORT
    assert spec.cross_review is True
    assert [node.node_id for node in spec.nodes] == ["a:R1", "b:R1", "a:R2", "b:R2"]
    # 第 2 轮必须等所有第 1 轮完成
    assert [node.needs for node in spec.nodes[2:]] == [("a:R1", "b:R1"), ("a:R1", "b:R1")]
    assert spec.members == [("a", "optimist"), ("b", "skeptic")]


def test_council_without_cross_review_only_compiles_round_one():
    spec = compile_council("question", [{"id": "a", "perspective": "optimist"}],
                           cross_review=False)

    assert [node.node_id for node in spec.nodes] == ["a:R1"]
    assert spec.cross_review is False


def test_round_two_prompt_injects_only_the_other_members_position():
    spec = compile_council("q", [
        {"id": "a", "perspective": "optimist"},
        {"id": "b", "perspective": "skeptic"},
    ])
    run = WorkflowRun(
        spec=spec,
        goal="q",
        order=spec.nodes,
        nodes={
            "a:R1": spec_module.NodeResult(state=NodeState.DONE, output="POS-A"),
            "b:R1": spec_module.NodeResult(state=NodeState.DONE, output="POS-B"),
        },
    )
    round_two = next(node for node in spec.nodes if node.node_id == "a:R2")

    prompt = round_two.prompt(spec_module.PromptContext(goal="q", node=round_two, run=run))

    assert "# Your Initial Position\nPOS-A" in prompt
    assert "**skeptic (b):**\nPOS-B" in prompt
    assert "POS-A" not in prompt.split("# Other Members' Positions")[1]
