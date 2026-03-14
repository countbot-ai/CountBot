"""技能配置Schema定义 - 固定Schema方法"""

import re
from pathlib import Path
from typing import Any, List, Optional, Tuple

from loguru import logger

# 固定Schema定义 - 为每个需要配置的技能预定义字段
SKILL_SCHEMAS = {
    "baidu-search": {
        "skill_name": "baidu-search",
        "version": "1.0.0",
        "description": "百度搜索API配置",
        "config_file": "scripts/config.json",
        "help_text": "配置百度搜索API以启用搜索功能。\n\n获取API Key：\n1. 访问百度开放平台\n2. 注册并创建应用\n3. 获取API Key\n\n配置说明：\n- API Key：必填，用于调用百度搜索API\n- 最大结果数：建议设置为10-50之间\n- 安全搜索：启用后会过滤不适宜内容",
        "fields": [
            {
                "key": "api_key",
                "type": "password",
                "label": "API Key",
                "description": "百度搜索API密钥",
                "required": True,
                "sensitive": True,
                "placeholder": "请输入百度搜索API Key",
                "help_text": "在百度开放平台创建应用后获取"
            },
            {
                "key": "default_max_results",
                "type": "number",
                "label": "默认最大结果数",
                "description": "搜索返回的默认最大结果数量",
                "default": 10,
                "min": 1,
                "max": 100,
                "help_text": "建议设置为10-50之间，过大可能影响性能"
            },
            {
                "key": "safe_search",
                "type": "boolean",
                "label": "安全搜索",
                "description": "是否启用安全搜索过滤",
                "default": False,
                "help_text": "启用后会过滤不适宜内容"
            }
        ]
    },
    "email": {
        "skill_name": "email",
        "version": "1.0.0",
        "description": "邮件服务配置",
        "config_file": "scripts/config.json",
        "help_file": "config.help.md",
        "fields": [
            {
                "key": "default_mailbox",
                "type": "select",
                "label": "默认邮箱",
                "description": "默认使用的邮箱服务",
                "default": "qq",
                "options": [
                    {"value": "qq", "label": "QQ邮箱"},
                    {"value": "163", "label": "163邮箱"}
                ]
            },
            {
                "key": "qq_email",
                "type": "object",
                "label": "QQ邮箱配置",
                "description": "QQ邮箱服务器配置",
                "collapsible": True,
                "fields": [
                    {
                        "key": "email",
                        "type": "email",
                        "label": "邮箱地址",
                        "description": "QQ邮箱地址",
                        "required": True,
                        "placeholder": "example@qq.com"
                    },
                    {
                        "key": "auth_code",
                        "type": "password",
                        "label": "授权码",
                        "description": "QQ邮箱授权码",
                        "required": True,
                        "sensitive": True,
                        "placeholder": "请输入授权码"
                    },
                    {
                        "key": "imap_server",
                        "type": "string",
                        "label": "IMAP服务器",
                        "description": "IMAP服务器地址",
                        "default": "imap.qq.com"
                    },
                    {
                        "key": "imap_port",
                        "type": "number",
                        "label": "IMAP端口",
                        "description": "IMAP服务器端口",
                        "default": 993,
                        "min": 1,
                        "max": 65535
                    },
                    {
                        "key": "smtp_server",
                        "type": "string",
                        "label": "SMTP服务器",
                        "description": "SMTP服务器地址",
                        "default": "smtp.qq.com"
                    },
                    {
                        "key": "smtp_port",
                        "type": "number",
                        "label": "SMTP端口",
                        "description": "SMTP服务器端口",
                        "default": 465,
                        "min": 1,
                        "max": 65535
                    }
                ]
            },
            {
                "key": "163_email",
                "type": "object",
                "label": "163邮箱配置",
                "description": "163邮箱服务器配置",
                "collapsible": True,
                "fields": [
                    {
                        "key": "email",
                        "type": "email",
                        "label": "邮箱地址",
                        "description": "163邮箱地址",
                        "required": True,
                        "placeholder": "example@163.com"
                    },
                    {
                        "key": "auth_password",
                        "type": "password",
                        "label": "授权密码",
                        "description": "163邮箱授权密码",
                        "required": True,
                        "sensitive": True,
                        "placeholder": "请输入授权密码"
                    },
                    {
                        "key": "pop_server",
                        "type": "string",
                        "label": "POP服务器",
                        "description": "POP服务器地址",
                        "default": "pop.163.com"
                    },
                    {
                        "key": "pop_port",
                        "type": "number",
                        "label": "POP端口",
                        "description": "POP服务器端口",
                        "default": 995,
                        "min": 1,
                        "max": 65535
                    },
                    {
                        "key": "smtp_server",
                        "type": "string",
                        "label": "SMTP服务器",
                        "description": "SMTP服务器地址",
                        "default": "smtp.163.com"
                    },
                    {
                        "key": "smtp_port",
                        "type": "number",
                        "label": "SMTP端口",
                        "description": "SMTP服务器端口",
                        "default": 465,
                        "min": 1,
                        "max": 65535
                    }
                ]
            },
            {
                "key": "last_check_time",
                "type": "string",
                "label": "最后检查时间",
                "description": "最后一次检查邮件的时间",
                "readonly": True
            }
        ]
    },
    "image-analysis": {
        "skill_name": "image-analysis",
        "version": "1.0.0",
        "description": "图像分析服务配置",
        "config_file": "scripts/config.json",
        "help_file": "config.help.md",
        "fields": [
            {
                "key": "default_model",
                "type": "select",
                "label": "默认模型",
                "description": "默认使用的图像分析模型",
                "default": "qwen",
                "options": [
                    {"value": "qwen", "label": "通义千问"},
                    {"value": "zhipu", "label": "智谱AI"}
                ]
            },
            {
                "key": "zhipu",
                "type": "object",
                "label": "智谱AI配置",
                "description": "智谱AI图像分析配置",
                "collapsible": True,
                "fields": [
                    {
                        "key": "api_key",
                        "type": "password",
                        "label": "API Key",
                        "description": "智谱AI API密钥",
                        "required": True,
                        "sensitive": True,
                        "placeholder": "请输入API Key"
                    },
                    {
                        "key": "model",
                        "type": "string",
                        "label": "模型名称",
                        "description": "使用的模型名称",
                        "default": "glm-4.6v-flash"
                    },
                    {
                        "key": "base_url",
                        "type": "string",
                        "label": "API端点",
                        "description": "API端点URL",
                        "default": "https://open.bigmodel.cn/api/paas/v4/chat/completions"
                    }
                ]
            },
            {
                "key": "qwen",
                "type": "object",
                "label": "通义千问配置",
                "description": "通义千问图像分析配置",
                "collapsible": True,
                "fields": [
                    {
                        "key": "api_key",
                        "type": "password",
                        "label": "API Key",
                        "description": "通义千问API密钥",
                        "required": True,
                        "sensitive": True,
                        "placeholder": "请输入API Key"
                    },
                    {
                        "key": "model",
                        "type": "string",
                        "label": "模型名称",
                        "description": "使用的模型名称",
                        "default": "qwen3-omni-flash-2025-12-01"
                    },
                    {
                        "key": "base_url",
                        "type": "string",
                        "label": "API端点",
                        "description": "API端点URL",
                        "default": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
                    },
                    {
                        "key": "region",
                        "type": "string",
                        "label": "区域",
                        "description": "服务区域",
                        "default": "beijing"
                    }
                ]
            }
        ]
    },
    "image-gen": {
        "skill_name": "image-gen",
        "version": "1.0.0",
        "description": "图像生成服务配置",
        "config_file": "scripts/config.json",
        "help_file": "config.help.md",
        "fields": [
            {
                "key": "api_token",
                "type": "password",
                "label": "API Token",
                "description": "图像生成服务API令牌",
                "required": True,
                "sensitive": True,
                "placeholder": "请输入API Token"
            }
        ]
    },
    "map": {
        "skill_name": "map",
        "version": "1.0.0",
        "description": "地图服务配置",
        "config_file": "scripts/config.json",
        "help_file": "config.help.md",
        "fields": [
            {
                "key": "amap_key",
                "type": "password",
                "label": "高德地图API Key",
                "description": "高德地图API密钥",
                "required": True,
                "sensitive": True,
                "placeholder": "请输入高德地图API Key"
            }
        ]
    },
    "web-design": {
        "skill_name": "web-design",
        "version": "1.0.0",
        "description": "网页设计服务配置",
        "config_file": "scripts/config.json",
        "help_file": "config.help.md",
        "fields": [
            {
                "key": "api_token",
                "type": "password",
                "label": "API Token",
                "description": "网页设计服务API令牌",
                "required": True,
                "sensitive": True,
                "placeholder": "请输入API Token"
            }
        ]
    }
}


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
