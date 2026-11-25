"""Dynamic Workflow 的 JSON AST 编译与能力校验。"""

from typing import Any, Dict, List, Optional

from backend.modules.workflow.results import validate_schema


class ProgramError(ValueError):
    def __init__(self, message: str, site_id: Optional[str] = None) -> None:
        self.site_id = site_id
        super().__init__(f"{site_id}: {message}" if site_id else message)


def compile_program(program: Any) -> Dict[str, Any]:
    if not isinstance(program, dict) or program.get("version") != 1:
        raise ProgramError("program must declare version=1")
    agents = program.get("agents")
    if not isinstance(agents, list) or not agents:
        raise ProgramError("agents must be a non-empty array")
    actor_ids = set()
    for agent in agents:
        if not isinstance(agent, dict):
            raise ProgramError("agent declaration must be an object")
        actor_id = agent.get("id")
        _identifier(actor_id, "agent id")
        if actor_id in actor_ids:
            raise ProgramError(f"duplicate agent id {actor_id!r}")
        actor_ids.add(actor_id)
        if not isinstance(agent.get("persona"), str) or not agent["persona"].strip():
            raise ProgramError("persona is required", actor_id)
        model_ref = agent.get("model_ref")
        if model_ref is not None and (
            not isinstance(model_ref, dict)
            or not isinstance(model_ref.get("provider"), str)
            or not isinstance(model_ref.get("model"), str)
        ):
            raise ProgramError("model_ref must name provider and model", actor_id)

    statements = program.get("body")
    if not isinstance(statements, list) or not statements:
        raise ProgramError("body must be a non-empty array")
    limits = program.get("limits", {})
    if not isinstance(limits, dict):
        raise ProgramError("limits must be an object")
    for name in ("max_parallel_asks", "max_asks", "max_loop_iterations", "max_tokens", "wall_clock_timeout"):
        value = limits.get(name)
        if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 1):
            raise ProgramError(f"{name} must be a positive integer")

    site_ids = set()
    for statement in statements:
        _validate_statement(statement, actor_ids, site_ids, limits)
    return {
        "version": 1,
        "agents": agents,
        "args": program.get("args", {}),
        "limits": limits,
        "body": statements,
    }


def preview_program(program: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "version": program["version"],
        "agents": program["agents"],
        "limits": program["limits"],
        "body": program["body"],
        "static": True,
    }


def _identifier(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value or not all(
        char.isalnum() or char in "_-" for char in value
    ):
        raise ProgramError(f"{label} must be a non-empty identifier using letters, digits, _ or -")


def _validate_statement(node: Any, actors: set, sites: set, limits: Dict[str, Any]) -> None:
    if not isinstance(node, dict):
        raise ProgramError("statement must be an object")
    kind = node.get("kind")
    site_id = node.get("site_id")
    if kind != "assign":
        _identifier(site_id, "site_id")
        if site_id in sites:
            raise ProgramError(f"duplicate site_id {site_id!r}")
        sites.add(site_id)
    if kind == "ask":
        if node.get("actor") not in actors:
            raise ProgramError("unknown actor", site_id)
        _expression(node.get("instructions"))
        schema = node.get("result_schema")
        if schema is not None:
            errors = validate_schema(schema)
            if errors:
                raise ProgramError("; ".join(errors), site_id)
        if "await" in node and not isinstance(node["await"], bool):
            raise ProgramError("await must be boolean", site_id)
    elif kind == "assign":
        _identifier(node.get("name"), "variable name")
        _expression(node.get("value"))
    elif kind == "if":
        _expression(node.get("condition"))
        _statement_list(node.get("then"), actors, sites, limits)
        _statement_list(node.get("else", []), actors, sites, limits)
    elif kind == "for_each":
        _identifier(node.get("name"), "loop variable")
        _expression(node.get("items"))
        if not isinstance(node.get("max_items"), int) or node["max_items"] < 1:
            raise ProgramError("for_each requires max_items >= 1", site_id)
        _statement_list(node.get("body"), actors, sites, limits)
    elif kind == "while":
        _expression(node.get("condition"))
        if not isinstance(node.get("max_rounds"), int) or node["max_rounds"] < 1:
            raise ProgramError("while requires max_rounds >= 1", site_id)
        _statement_list(node.get("body"), actors, sites, limits)
    elif kind == "parallel":
        _statement_list(node.get("body"), actors, sites, limits)
    elif kind == "return":
        _expression(node.get("value"))
    else:
        raise ProgramError(f"unsupported statement kind {kind!r}", site_id)


def _statement_list(value: Any, actors: set, sites: set, limits: Dict[str, Any]) -> None:
    if not isinstance(value, list):
        raise ProgramError("statement body must be an array")
    for node in value:
        _validate_statement(node, actors, sites, limits)


def _expression(value: Any) -> None:
    if value is None or isinstance(value, (str, int, float, bool, list)):
        if isinstance(value, list):
            for item in value:
                _expression(item)
        return
    if not isinstance(value, dict):
        raise ProgramError("expression must be a JSON value or expression object")
    kind = value.get("kind")
    if kind in {"literal", "var", "arg", "get", "text"}:
        if kind in {"var", "arg"} and not isinstance(value.get("name"), str):
            raise ProgramError(f"{kind} requires a name")
        if kind == "get":
            if not isinstance(value.get("path"), list) or not all(
                isinstance(item, (str, int)) for item in value["path"]
            ):
                raise ProgramError("get path must contain strings and indexes")
            _expression(value.get("value"))
        if kind == "text":
            _expression(value.get("value"))
        return
    if kind in {"not", "truthy"}:
        _expression(value.get("value"))
        return
    if kind in {"and", "or", "eq", "ne", "lt", "le", "gt", "ge", "contains"}:
        _expression(value.get("left"))
        _expression(value.get("right"))
        return
    raise ProgramError(f"unsupported expression kind {kind!r}")
