"""Tool Base Class - 工具基类"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List

from loguru import logger


class Tool(ABC):
    """工具抽象基类

    所有工具必须继承此类并实现抽象方法。
    工具是 AI Agent 可以调用的可执行函数，用于执行特定操作，
    如文件操作、Shell 命令或 Web 搜索等。
    """

    # Type mapping for parameter validation
    _TYPE_MAP = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "array": list,
        "object": dict,
    }

    @property
    @abstractmethod
    def name(self) -> str:
        """
        返回工具的唯一名称
        
        Returns:
            str: 用于识别和调用的工具名称
        """
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """
        返回工具的描述
        
        Returns:
            str: 供 LLM 理解的人类可读描述
        """
        pass

    @property
    @abstractmethod
    def parameters(self) -> Dict[str, Any]:
        """
        返回工具参数的 JSON Schema
        
        Returns:
            dict: 定义必需和可选参数的 JSON Schema
        """
        pass

    async def execute(self, **kwargs: Any) -> str:
        """执行工具，返回纯文本结果。

        默认从 ``execute_outcome`` 派生，使内建工具只需实现 canonical outcome
        一处即可，避免同一份逻辑维护两遍——此前多次出现「加固只改了其中一个
        入口」的问题。

        子类若只覆盖 ``execute``（legacy 形态），本方法会被子类覆盖而不会执行到
        这里；因此不存在两个默认实现互递归的情况。
        """
        outcome = await self.execute_outcome(**kwargs)
        return getattr(outcome, "display_text", str(outcome))

    async def execute_outcome(self, **kwargs: Any) -> Any:
        """为 canonical execution 返回显式 ``ToolResult``。

        子类未覆盖本方法时，退化为调用其 ``execute`` 并原样返回结果，由 Registry
        判定为 ``RESULT_CONTRACT`` 失败——保留 legacy 工具可被拒绝而非误判成功
        的既有契约。已迁移的 Tool 必须覆盖本方法返回 ``ToolResult``。
        """
        # 若子类两个方法都没覆盖，调用本方法会经由 execute 再次回到这里，
        # 直接报错而不是无限递归。
        if type(self).execute is Tool.execute:
            raise NotImplementedError(
                f"{type(self).__name__} must implement execute or execute_outcome"
            )
        return await self.execute(**kwargs)

    def validate_params(self, params: Dict[str, Any]) -> List[str]:
        """验证工具参数是否符合 JSON Schema

        Args:
            params: 要验证的参数字典

        Returns:
            List[str]: 错误列表（空列表表示验证通过）
        """
        schema = self.parameters or {}
        if schema.get("type", "object") != "object":
            raise ValueError(f"Schema must be object type, got {schema.get('type')!r}")
        return self._validate(params, {**schema, "type": "object"}, "")

    def _validate(self, val: Any, schema: Dict[str, Any], path: str) -> List[str]:
        """
        递归验证值是否符合 schema
        
        Args:
            val: 要验证的值
            schema: JSON Schema
            path: 当前路径（用于错误消息）
            
        Returns:
            List[str]: 错误列表
        """
        t, label = schema.get("type"), path or "parameter"

        # Type check
        if t in self._TYPE_MAP and not isinstance(val, self._TYPE_MAP[t]):
            return [f"{label} should be {t}"]

        errors = []

        # Enum check
        if "enum" in schema and val not in schema["enum"]:
            errors.append(f"{label} must be one of {schema['enum']}")

        # Number constraints
        if t in ("integer", "number"):
            if "minimum" in schema and val < schema["minimum"]:
                errors.append(f"{label} must be >= {schema['minimum']}")
            if "maximum" in schema and val > schema["maximum"]:
                errors.append(f"{label} must be <= {schema['maximum']}")

        # String constraints
        if t == "string":
            if "minLength" in schema and len(val) < schema["minLength"]:
                errors.append(f"{label} must be at least {schema['minLength']} chars")
            if "maxLength" in schema and len(val) > schema["maxLength"]:
                errors.append(f"{label} must be at most {schema['maxLength']} chars")

        # Object validation
        if t == "object":
            props = schema.get("properties", {})
            additional_properties = schema.get("additionalProperties", True)

            # Check required fields
            for k in schema.get("required", []):
                if k not in val:
                    errors.append(f"missing required {path + '.' + k if path else k}")

            # Check unknown fields when additionalProperties is disabled
            if additional_properties is False:
                for k in val:
                    if k not in props:
                        errors.append(
                            f"unknown parameter {path + '.' + k if path else k}"
                        )

            # Validate each property
            for k, v in val.items():
                if k in props:
                    errors.extend(
                        self._validate(v, props[k], path + "." + k if path else k)
                    )

            # Support simple JSON Schema oneOf usage for object params
            if "oneOf" in schema:
                match_count = 0
                child_errors: List[List[str]] = []
                base_schema = dict(schema)
                base_schema.pop("oneOf", None)
                base_required = list(base_schema.get("required", []))

                for option in schema["oneOf"]:
                    merged_schema = dict(base_schema)
                    merged_required = base_required + list(option.get("required", []))
                    if merged_required:
                        merged_schema["required"] = list(dict.fromkeys(merged_required))
                    option_errors = self._validate(val, merged_schema, path)
                    if not option_errors:
                        match_count += 1
                    else:
                        child_errors.append(option_errors)

                if match_count != 1:
                    if match_count == 0:
                        errors.append(f"{label} must match exactly one schema option")
                    else:
                        errors.append(f"{label} matches multiple schema options")

        # Array validation
        if t == "array" and "items" in schema:
            for i, item in enumerate(val):
                errors.extend(
                    self._validate(
                        item, schema["items"], f"{path}[{i}]" if path else f"[{i}]"
                    )
                )

        return errors

    def get_definition(self) -> Dict[str, Any]:
        """
        获取完整的工具定义，用于 LLM 函数调用
        
        Returns:
            dict: 包含 name、description 和 parameters 的工具定义
        """
        definition = {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
        
        logger.debug(f"Generated definition for tool: {self.name}")
        return definition

    def to_schema(self) -> Dict[str, Any]:
        """转换为 OpenAI 函数 schema 格式（别名方法）"""
        return self.get_definition()
