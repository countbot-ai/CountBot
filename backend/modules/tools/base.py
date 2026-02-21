"""Tool Base Class - 工具基类"""

from abc import ABC, abstractmethod
from typing import Any

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
    def parameters(self) -> dict[str, Any]:
        """
        返回工具参数的 JSON Schema
        
        Returns:
            dict: 定义必需和可选参数的 JSON Schema
        """
        pass

    @abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        """
        执行工具
        
        Args:
            **kwargs: 符合参数 schema 的工具特定参数
            
        Returns:
            str: 工具执行结果
            
        Raises:
            Exception: 工具执行失败时抛出
        """
        pass

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        """验证工具参数是否符合 JSON Schema

        Args:
            params: 要验证的参数字典

        Returns:
            list[str]: 错误列表（空列表表示验证通过）
        """
        schema = self.parameters or {}
        if schema.get("type", "object") != "object":
            raise ValueError(f"Schema must be object type, got {schema.get('type')!r}")
        return self._validate(params, {**schema, "type": "object"}, "")

    def _validate(self, val: Any, schema: dict[str, Any], path: str) -> list[str]:
        """
        递归验证值是否符合 schema
        
        Args:
            val: 要验证的值
            schema: JSON Schema
            path: 当前路径（用于错误消息）
            
        Returns:
            list[str]: 错误列表
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
            # Check required fields
            for k in schema.get("required", []):
                if k not in val:
                    errors.append(f"missing required {path + '.' + k if path else k}")
            # Validate each property
            for k, v in val.items():
                if k in props:
                    errors.extend(
                        self._validate(v, props[k], path + "." + k if path else k)
                    )
        
        # Array validation
        if t == "array" and "items" in schema:
            for i, item in enumerate(val):
                errors.extend(
                    self._validate(
                        item, schema["items"], f"{path}[{i}]" if path else f"[{i}]"
                    )
                )
        
        return errors

    def get_definition(self) -> dict[str, Any]:
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

    def to_schema(self) -> dict[str, Any]:
        """转换为 OpenAI 函数 schema 格式（别名方法）"""
        return self.get_definition()
