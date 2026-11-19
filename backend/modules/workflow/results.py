"""受限 JSON Schema 校验与 ask 结构化结果。"""

from typing import Any, Dict, List

from backend.modules.tools.execution import (
    ErrorCategory,
    SideEffectState,
    ToolResult,
)

_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "integer": int,
    "number": (int, float),
}


def validate_result(value: Any, schema: Dict[str, Any], path: str = "$") -> List[str]:
    """校验 planner 可声明的 JSON 子集，拒绝把任意 Python 当结果。"""
    if not isinstance(schema, dict):
        return [f"{path}: result schema must be an object"]
    expected = schema.get("type")
    if expected not in _TYPES:
        return [f"{path}: unsupported result schema type {expected!r}"]
    if expected == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
        return [f"{path}: expected integer"]
    if expected == "number" and (not isinstance(value, (int, float)) or isinstance(value, bool)):
        return [f"{path}: expected number"]
    if expected not in {"integer", "number"} and not isinstance(value, _TYPES[expected]):
        return [f"{path}: expected {expected}"]
    if "enum" in schema and value not in schema["enum"]:
        return [f"{path}: expected one of {schema['enum']!r}"]

    errors: List[str] = []
    if expected == "object":
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            return [f"{path}: properties must be an object"]
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}.{key}: required property is missing")
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    errors.append(f"{path}.{key}: unknown property")
        for key, child in properties.items():
            if key in value:
                errors.extend(validate_result(value[key], child, f"{path}.{key}"))
    elif expected == "array" and "items" in schema:
        for index, item in enumerate(value):
            errors.extend(validate_result(item, schema["items"], f"{path}[{index}]"))
    return errors


def validate_schema(schema: Any) -> List[str]:
    """校验 schema 自身，不把对象结果缺字段误当成 schema 不合法。"""
    if not isinstance(schema, dict):
        return ["result schema must be an object"]
    if schema.get("type") not in _TYPES:
        return [f"unsupported result schema type {schema.get('type')!r}"]
    errors = []
    if schema["type"] == "object":
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            return ["object properties must be an object"]
        required = schema.get("required", [])
        if not isinstance(required, list) or not all(isinstance(key, str) for key in required):
            errors.append("required must be an array of property names")
        for key, child in properties.items():
            errors.extend(f"{key}: {error}" for error in validate_schema(child))
    elif schema["type"] == "array" and "items" in schema:
        errors.extend(f"items: {error}" for error in validate_schema(schema["items"]))
    if "enum" in schema and not isinstance(schema["enum"], list):
        errors.append("enum must be an array")
    return errors


def result_submission(value: Any, schema: Dict[str, Any]) -> ToolResult:
    errors = validate_result(value, schema)
    if errors:
        return ToolResult.failure(
            ErrorCategory.RESULT_CONTRACT,
            "Structured result failed schema validation: " + "; ".join(errors),
            side_effect_state=SideEffectState.NOT_ATTEMPTED,
        )
    return ToolResult.success(value)
