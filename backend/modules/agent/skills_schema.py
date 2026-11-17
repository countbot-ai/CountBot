"""技能配置Schema定义 - 固定Schema方法"""

import re
from pathlib import Path
from typing import Any, List, Optional, Tuple

from loguru import logger

from backend.modules.agent.skill_schemas_data import SKILL_SCHEMAS


class SkillConfigSchema:
    """技能配置Schema加载器 - 使用固定Schema定义"""
    
    def __init__(self, skills_dir: Path):
        """
        初始化Schema加载器
        
        Args:
            skills_dir: 技能目录路径
        """
        self.skills_dir = skills_dir
    
    def has_schema(self, skill_name: str) -> bool:
        """
        检查技能是否有Schema定义
        
        Args:
            skill_name: 技能名称
            
        Returns:
            bool: 是否有Schema
        """
        return skill_name in SKILL_SCHEMAS
    
    def load_schema(self, skill_name: str) -> Optional[dict]:
        """
        加载技能配置Schema
        
        Args:
            skill_name: 技能名称
            
        Returns:
            dict: Schema定义，如果不存在则返回None
        """
        if not self.has_schema(skill_name):
            logger.debug(f"No schema defined for skill: {skill_name}")
            return None
        
        return SKILL_SCHEMAS[skill_name]
    
    def validate_config(self, skill_name: str, config: dict) -> Tuple[bool, List[str]]:
        """
        验证配置是否符合Schema
        
        Args:
            skill_name: 技能名称
            config: 配置内容
            
        Returns:
            tuple: (is_valid, errors)
        """
        schema = self.load_schema(skill_name)
        if not schema:
            return False, ["Schema not found"]
        
        errors = []
        self._validate_fields(config, schema.get('fields', []), errors, "")
        
        return len(errors) == 0, errors
    
    def _validate_fields(
        self, 
        config: dict, 
        fields: List[dict], 
        errors: List[str],
        prefix: str = ""
    ) -> None:
        """
        递归验证字段
        
        Args:
            config: 配置字典
            fields: 字段定义列表
            errors: 错误列表
            prefix: 字段路径前缀
        """
        for field in fields:
            key = field['key']
            full_key = f"{prefix}.{key}" if prefix else key
            
            # 检查必填字段
            if field.get('required') and key not in config:
                errors.append(f"缺少必填字段: {full_key}")
                continue
            
            if key not in config:
                continue
            
            value = config[key]
            field_type = field['type']
            
            # 类型验证
            if field_type == 'string' or field_type == 'email' or field_type == 'password':
                if not isinstance(value, str):
                    errors.append(f"字段 {full_key} 类型错误，应为字符串")
                elif field_type == 'email' and not self._is_valid_email(value):
                    errors.append(f"字段 {full_key} 不是有效的邮箱地址")
                elif field.get('validation') and not re.match(field['validation'], value):
                    errors.append(f"字段 {full_key} 格式不正确")
            
            elif field_type == 'number':
                if not isinstance(value, (int, float)):
                    errors.append(f"字段 {full_key} 类型错误，应为数字")
                else:
                    if 'min' in field and value < field['min']:
                        errors.append(f"字段 {full_key} 小于最小值 {field['min']}")
                    if 'max' in field and value > field['max']:
                        errors.append(f"字段 {full_key} 大于最大值 {field['max']}")
            
            elif field_type == 'boolean':
                if not isinstance(value, bool):
                    errors.append(f"字段 {full_key} 类型错误，应为布尔值")
            
            elif field_type == 'select':
                options = field.get('options', [])
                valid_values = [opt['value'] for opt in options]
                if value not in valid_values:
                    errors.append(f"字段 {full_key} 值无效，应为: {', '.join(valid_values)}")
            
            elif field_type == 'object':
                if not isinstance(value, dict):
                    errors.append(f"字段 {full_key} 类型错误，应为对象")
                else:
                    nested_fields = field.get('fields', [])
                    self._validate_fields(value, nested_fields, errors, full_key)
    
    def _is_valid_email(self, email: str) -> bool:
        """
        验证邮箱地址格式
        
        Args:
            email: 邮箱地址
            
        Returns:
            bool: 是否有效
        """
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    def generate_default_config(self, skill_name: str) -> Optional[dict]:
        """
        生成默认配置
        
        Args:
            skill_name: 技能名称
            
        Returns:
            dict: 默认配置，如果不存在Schema则返回None
        """
        schema = self.load_schema(skill_name)
        if not schema:
            return None
        
        config = {}
        self._generate_default_fields(config, schema.get('fields', []))
        return config
    
    def _generate_default_fields(self, config: dict, fields: List[dict]) -> None:
        """
        递归生成默认字段值
        
        Args:
            config: 配置字典
            fields: 字段定义列表
        """
        for field in fields:
            key = field['key']
            
            if field['type'] == 'object':
                config[key] = {}
                nested_fields = field.get('fields', [])
                self._generate_default_fields(config[key], nested_fields)
            elif 'default' in field:
                config[key] = field['default']
            elif field.get('required'):
                # 必填字段没有默认值，使用空值
                config[key] = self._get_empty_value(field['type'])
    
    def _get_empty_value(self, field_type: str) -> Any:
        """
        获取字段类型的空值
        
        Args:
            field_type: 字段类型
            
        Returns:
            Any: 空值
        """
        if field_type == 'number':
            return 0
        elif field_type == 'boolean':
            return False
        elif field_type == 'object':
            return {}
        else:
            return ""
