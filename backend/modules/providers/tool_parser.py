"""工具调用文本解析器"""

import json
import re
from typing import Any
from loguru import logger


class ToolCallParser:
    
    JSON_PATTERN = re.compile(
        r'\{[\s\n]*"name"[\s\n]*:[\s\n]*"([^"]+)"[\s\n]*,[\s\n]*"arguments"[\s\n]*:[\s\n]*(\{[^}]*\})[\s\n]*\}',
        re.DOTALL
    )
    
    SIMPLE_PATTERN = re.compile(
        r'^([a-z_]+)\n((?:[a-z_]+:\s*.+\n?)+)',
        re.MULTILINE
    )
    
    @classmethod
    def parse(cls, text: str) -> dict[str, Any] | None:
        if not text or not isinstance(text, str):
            return None
        
        text = text.strip()
        
        result = cls._parse_json(text)
        if result:
            logger.debug(f"Parsed tool call (JSON): {result['name']}")
            return result
        
        result = cls._parse_simple(text)
        if result:
            logger.debug(f"Parsed tool call (simple): {result['name']}")
            return result
        
        result = cls._parse_pure_json(text)
        if result:
            logger.debug(f"Parsed tool call (pure JSON): {result['name']}")
            return result
        
        return None
    
    @classmethod
    def _parse_json(cls, text: str) -> dict[str, Any] | None:
        match = cls.JSON_PATTERN.search(text)
        if not match:
            return None
        
        try:
            name = match.group(1)
            arguments_str = match.group(2)
            arguments = json.loads(arguments_str)
            
            return {
                "name": name,
                "arguments": arguments
            }
        except (json.JSONDecodeError, IndexError) as e:
            logger.warning(f"Failed to parse JSON tool call: {e}")
            return None
    
    @classmethod
    def _parse_pure_json(cls, text: str) -> dict[str, Any] | None:
        try:
            data = json.loads(text)
            
            if isinstance(data, dict) and "name" in data:
                name = data["name"]
                arguments = data.get("arguments", {})
                
                if not isinstance(arguments, dict):
                    if isinstance(arguments, str):
                        try:
                            arguments = json.loads(arguments)
                        except json.JSONDecodeError:
                            arguments = {"value": arguments}
                    else:
                        arguments = {"value": arguments}
                
                return {
                    "name": name,
                    "arguments": arguments
                }
        except json.JSONDecodeError:
            pass
        
        return None
    
    @classmethod
    def _parse_simple(cls, text: str) -> dict[str, Any] | None:
        match = cls.SIMPLE_PATTERN.search(text)
        if not match:
            return None
        
        try:
            name = match.group(1)
            params_text = match.group(2)
            
            arguments = {}
            for line in params_text.strip().split('\n'):
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip()
                    value = value.strip().strip('"\'')
                    arguments[key] = value
            
            return {
                "name": name,
                "arguments": arguments
            }
        except (IndexError, ValueError) as e:
            logger.warning(f"Failed to parse simple tool call: {e}")
            return None
    
    @classmethod
    def is_tool_call_text(cls, text: str) -> bool:
        if not text or not isinstance(text, str):
            return False
        
        text = text.strip()
        
        indicators = [
            '"name"' in text and '"arguments"' in text,
            text.startswith('{') and text.endswith('}'),
            '\n' in text and ':' in text,
        ]
        
        return any(indicators)
