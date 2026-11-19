"""受限程序的编译、表达式和 actor 编排测试。"""

import pytest

from backend.modules.tools.execution import ExecutionState, ToolResult
from backend.modules.workflow.engine import DynamicWorkflowEngine
from backend.modules.workflow.program import ProgramError, compile_program


def _program(body, **kwargs):
    return {
        "version": 1,
        "agents": [{"id": "worker", "persona": "You are a worker"}],
        "args": {"items": ["a", "b"], "rounds": 0},
        "limits": {"max_asks": 10, "max_loop_iterations": 3},
        "body": body,
        **kwargs,
    }


def _ask(actor="worker", instructions="do it", **kwargs):
    return {
        "kind": "ask", "site_id": "research", "actor": actor,
        "instructions": instructions, **kwargs,
    }


class _Driver:
    def __init__(self):
        self.calls = []

    async def ask(self, **kwargs):
        self.calls.append(kwargs)
        return ToolResult.success({"approved": True, "item": kwargs["instructions"]})


@pytest.mark.asyncio
async def test_parallel_ask_and_structured_loop_control():
    driver = _Driver()
    program = compile_program(_program([
        {"kind": "parallel", "site_id": "fanout", "body": [
            _ask(instructions="research"),
            _ask(site_id="review", instructions="review"),
        ]},
        {"kind": "if", "site_id": "gate", "condition": {"kind": "truthy", "value": True},
         "then": [{"kind": "return", "site_id": "done", "value": {"kind": "literal", "value": "approved"}}]},
    ]))
    # 明确声明 join 后的结构化值读取，变量/字段表达式由解释器执行。
    program["body"][1]["condition"] = {
        "kind": "get", "value": {"kind": "var", "name": "review_result"}, "path": ["approved"],
    }
    program["body"][0]["body"][1]["assign"] = "review_result"

    result = await DynamicWorkflowEngine(program, driver).run()

    assert result.state is ExecutionState.SUCCEEDED
    assert result.output == "approved"
    assert len(driver.calls) == 2


@pytest.mark.asyncio
async def test_for_each_binds_values_and_restores_loop_variable():
    driver = _Driver()
    program = compile_program(_program([
        {"kind": "for_each", "site_id": "loop", "name": "item", "items": {"kind": "var", "name": "items"},
         "max_items": 2, "body": [_ask(instructions={"kind": "var", "name": "item"})]},
        {"kind": "return", "site_id": "done", "value": {"kind": "literal", "value": "b"}},
    ]))

    result = await DynamicWorkflowEngine(program, driver).run()

    assert result.state is ExecutionState.SUCCEEDED
    assert [call["instructions"] for call in driver.calls] == ["a", "b"]
    assert result.output == "b"


def test_invalid_program_never_executes():
    with pytest.raises(ProgramError, match="unknown actor"):
        compile_program(_program([_ask(actor="ghost")]))
    with pytest.raises(ProgramError, match="max_rounds"):
        compile_program(_program([{
            "kind": "while", "site_id": "loop", "condition": True,
            "max_rounds": 0, "body": [],
        }]))
    with pytest.raises(ProgramError, match="unsupported result schema"):
        compile_program(_program([_ask(result_schema={"type": "python"})]))
