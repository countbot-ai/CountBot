"""受限 JSON AST 的解释执行；副作用只经 driver 协议发生。"""

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, Optional

from backend.modules.tools.execution import (
    ErrorCategory,
    ExecutionState,
    SideEffectState,
    ToolResult,
)


class _Missing:
    pass


_MISSING = _Missing()


class _AskFailedError(Exception):
    """Ask 结束于非成功状态；保留原 ToolResult 供上层按终态传播。"""

    def __init__(self, result: ToolResult) -> None:
        super().__init__(result.display_text)
        self.result = result


@dataclass
class _AskBudget:
    """跨并行分支共享的 ask 计数器，保证 max_asks 不被分支绕过。"""
    count: int = 0
    maximum: Optional[int] = None

    def try_acquire(self) -> bool:
        if self.maximum is not None and self.count >= self.maximum:
            return False
        self.count += 1
        return True


class DynamicWorkflowEngine:
    def __init__(self, program: Dict[str, Any], driver, *, cancel_token=None) -> None:
        self.program = program
        self.program.setdefault("limits", {})
        self.driver = driver
        self.cancel_token = cancel_token
        self.ordinals: Dict[str, int] = {}
        self.variables: Dict[str, Any] = dict(program.get("args", {}))
        self._returned = False
        self._return_value: Any = _MISSING
        self._branch_path = ""
        self._ask_budget = _AskBudget(
            maximum=self.program["limits"].get("max_asks"),
        )
        self._max_parallel_asks = self.program["limits"].get("max_parallel_asks")
        self._ask_semaphore = (
            asyncio.Semaphore(self._max_parallel_asks)
            if self._max_parallel_asks is not None
            else None
        )

    async def run(self) -> ToolResult:
        try:
            await self._run_statements(self.program["body"])
            output = self._return_value
            if output is _MISSING:
                output = ""
            return ToolResult.success(output)
        except _AskFailedError as exc:
            return exc.result
        except asyncio.CancelledError:
            return ToolResult.cancelled("Workflow was cancelled.")
        except Exception as exc:
            return ToolResult.unknown_outcome(
                ErrorCategory.EXECUTION,
                str(exc),
            )

    async def _run_statements(self, statements) -> None:
        for statement in statements:
            if self._returned:
                return
            await self._run_statement(statement)

    async def _run_statement(self, node: Dict[str, Any]) -> None:
        self._check_cancelled()
        kind = node["kind"]
        if kind == "assign":
            self.variables[node["name"]] = self._eval(node["value"])
        elif kind == "ask":
            await self._ask(node)
        elif kind == "if":
            branch = node["then"] if self._truthy(self._eval(node["condition"])) else node.get("else", [])
            await self._run_statements(branch)
        elif kind == "for_each":
            items = self._eval(node["items"])
            if not isinstance(items, list):
                raise ValueError(f"{node['site_id']}: for_each items must evaluate to an array")
            if len(items) > node["max_items"]:
                raise ValueError(f"{node['site_id']}: for_each exceeds max_items")
            previous = self.variables.get(node["name"], _MISSING)
            for item in items:
                self.variables[node["name"]] = item
                await self._run_statements(node["body"])
                if self._returned:
                    break
            _restore(self.variables, node["name"], previous)
        elif kind == "while":
            rounds = 0
            while self._truthy(self._eval(node["condition"])):
                if rounds >= node["max_rounds"]:
                    raise ValueError(f"{node['site_id']}: while exceeded max_rounds")
                rounds += 1
                await self._run_statements(node["body"])
                if self._returned:
                    break
        elif kind == "parallel":
            branches = []
            branch_nodes = []
            for index, statement in enumerate(node["body"]):
                child = self._branch(statement, index)
                branch_nodes.append(child)
                branches.append(child._run_statements([statement]))
            await asyncio.gather(*branches)
            for index, child in enumerate(branch_nodes):
                statement = node["body"][index]
                if statement.get("assign"):
                    self.variables[statement["assign"]] = child.variables.get(statement["assign"])
        elif kind == "return":
            self._return_value = self._eval(node["value"])
            self._returned = True
        else:
            raise ValueError(f"Unsupported statement kind: {kind}")

    async def _ask(self, node: Dict[str, Any]) -> None:
        site_id = node["site_id"]
        ordinal = self.ordinals.get(site_id, 0) + 1
        self.ordinals[site_id] = ordinal
        instance_id = f"{self._branch_path}{site_id}"
        if not self._ask_budget.try_acquire():
            raise ValueError(f"{site_id}: max_asks exceeded")
        instructions = self._eval(node["instructions"])
        if not isinstance(instructions, str) or not instructions.strip():
            raise ValueError(f"{site_id}: instructions must evaluate to non-empty text")
        result = await self._dispatch_ask(node, instructions, instance_id)
        if not isinstance(result, ToolResult):
            raise TypeError("driver.ask must return ToolResult")
        if result.state is not ExecutionState.SUCCEEDED:
            raise _AskFailedError(result)
        if node.get("assign"):
            self.variables[node["assign"]] = getattr(result, "value", result.output)

    def _branch(self, statement, index: int):
        """并行分支有独立变量作用域，join 时按声明顺序合并导出值。"""
        child = DynamicWorkflowEngine(
            self.program,
            self.driver,
            cancel_token=self.cancel_token,
        )
        child.variables = dict(self.variables)
        child.ordinals = dict(self.ordinals)
        child._branch_path = f"{self._branch_path}branch-{index}/"
        child._ask_budget = self._ask_budget
        child._ask_semaphore = self._ask_semaphore
        return child

    async def _dispatch_ask(self, node, instructions, instance_id=None):
        async def dispatch():
            return await self.driver.ask(
                actor_id=node["actor"],
                site_id=instance_id or node["site_id"],
                ordinal=self.ordinals[node["site_id"]],
                instructions=instructions,
                result_schema=node.get("result_schema"),
                cancel_token=self.cancel_token,
            )

        if self._ask_semaphore is None:
            return await dispatch()
        async with self._ask_semaphore:
            return await dispatch()

    def _eval(self, value: Any) -> Any:
        if not isinstance(value, dict):
            if isinstance(value, list):
                return [self._eval(item) for item in value]
            return value
        kind = value.get("kind")
        if kind == "literal":
            return value.get("value")
        if kind in {"var", "arg"}:
            name = value["name"]
            if name not in self.variables:
                raise ValueError(f"Unknown variable: {name}")
            return self.variables[name]
        if kind == "get":
            target = self._eval(value["value"])
            for part in value["path"]:
                if isinstance(target, dict) and isinstance(part, str):
                    target = target.get(part)
                elif isinstance(target, list) and isinstance(part, int):
                    target = target[part]
                else:
                    raise ValueError(f"Cannot read field {part!r}")
            return target
        if kind == "text":
            return str(self._eval(value["value"]))
        if kind == "truthy":
            return self._truthy(self._eval(value["value"]))
        if kind == "not":
            return not self._truthy(self._eval(value["value"]))
        left = self._eval(value.get("left"))
        right = self._eval(value.get("right"))
        if kind == "and":
            return self._truthy(left) and self._truthy(right)
        if kind == "or":
            return self._truthy(left) or self._truthy(right)
        if kind == "eq":
            return left == right
        if kind == "ne":
            return left != right
        if kind == "lt":
            return left < right
        if kind == "le":
            return left <= right
        if kind == "gt":
            return left > right
        if kind == "ge":
            return left >= right
        if kind == "contains":
            return right in left
        raise ValueError(f"Unsupported expression kind: {kind}")

    def _truthy(self, value: Any) -> bool:
        return bool(value)

    def _check_cancelled(self) -> None:
        if self.cancel_token and self.cancel_token.is_cancelled:
            raise asyncio.CancelledError("Workflow cancelled")


def _restore(variables: Dict[str, Any], name: str, previous: Any) -> None:
    if previous is _MISSING:
        variables.pop(name, None)
    else:
        variables[name] = previous