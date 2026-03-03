"""技能配置管理器"""

import json
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from backend.modules.agent.skills_schema import SkillConfigSchema
from backend.utils.paths import APPLICATION_ROOT

# 默认内置技能目录
BUILTIN_SKILLS_DIR = APPLICATION_ROOT / "skills"


class SkillConfigManager:
    """技能配置管理器 - 只读取和写入现有的config.json文件"""
    
    def __init__(self, skills_dir: Path = BUILTIN_SKILLS_DIR):
        """
        初始化配置管理器
        
        Args:
            skills_dir: 技能目录路径
        """
        self.skills_dir = skills_dir
        self.schema_loader = SkillConfigSchema(skills_dir)
    
    def get_config_path(self, skill_name: str) -> Optional[Path]:
        """
        获取技能配置文件路径（保持原有路径：scripts/config.json）
        
        Args:
            skill_name: 技能名称
            
        Returns:
            Path: 配置文件路径，如果不存在则返回None
        """
        config_path = self.skills_dir / skill_name / "scripts" / "config.json"
        return config_path if config_path.exists() else None
    
    def has_config(self, skill_name: str) -> bool:
        """
        检查技能是否有配置文件
        
        Args:
            skill_name: 技能名称
            
        Returns:
            bool: 是否有配置文件
        """
        return self.get_config_path(skill_name) is not None
    
    def load_config(self, skill_name: str) -> Optional[dict]:
        """
        加载技能配置（从现有的config.json读取）
        
        Args:
            skill_name: 技能名称
            
        Returns:
            dict: 配置内容，如果不存在则返回None
        """
        config_path = self.get_config_path(skill_name)
        if not config_path:
            logger.debug(f"Config file not found for skill: {skill_name}")
            return None
        
        try:
            config = json.loads(config_path.read_text(encoding='utf-8'))
            logger.debug(f"Loaded config for skill: {skill_name}")
            return config
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config file for {skill_name}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to load config for {skill_name}: {e}")
            return None
    
    def save_config(self, skill_name: str, config: dict) -> bool:
        """
        保存技能配置（写入到现有的config.json）
        
        Args:
            skill_name: 技能名称
            config: 配置内容
            
        Returns:
            bool: 是否成功
        """
        config_path = self.get_config_path(skill_name)
        if not config_path:
            logger.error(f"Config file not found for skill: {skill_name}")
            return False
        
        try:
            # 保存配置（保持原有格式）
            config_path.write_text(
                json.dumps(config, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )
            
            # 设置文件权限为仅所有者可读写（安全措施）
            try:
                config_path.chmod(0o600)
            except Exception as e:
                logger.warning(f"Failed to set file permissions: {e}")
            
            logger.info(f"Saved config for skill: {skill_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save config for {skill_name}: {e}")
            return False
    
    def get_config_status(self, skill_name: str) -> tuple[str, list[str]]:
        """
        检查配置状态
        
        Args:
            skill_name: 技能名称
            
        Returns:
            tuple: (status, missing_fields)
                status: 'no_schema' | 'not_configured' | 'invalid_format' | 'missing_fields' | 'valid'
                missing_fields: 缺失或错误的字段列表
        """
        # 1. 检查是否有Schema
        if not self.schema_loader.has_schema(skill_name):
            return 'no_schema', []
        
        # 2. 检查配置文件是否存在
        if not self.has_config(skill_name):
            return 'not_configured', []
        
        # 3. 检查JSON格式
        config = self.load_config(skill_name)
        if config is None:
            return 'invalid_format', []
        
        # 4. 验证配置
        is_valid, errors = self.schema_loader.validate_config(skill_name, config)
        
        if not is_valid:
            return 'missing_fields', errors
        
        return 'valid', []
    
    def auto_fix_config(self, skill_name: str) -> bool:
        """
        自动修复配置文件
        - 添加缺失的字段（使用默认值）
        - 保留现有的有效字段
        - 不删除Schema中不存在的字段（保持兼容性）
        
        注意：只修复现有的config.json，不创建新文件
        
        Args:
            skill_name: 技能名称
            
        Returns:
            bool: 是否成功
        """
        schema = self.schema_loader.load_schema(skill_name)
        if not schema:
            logger.error(f"Schema not found for skill: {skill_name}")
            return False
        
        config_path = self.get_config_path(skill_name)
        if not config_path:
            logger.error(f"Config file not found for skill: {skill_name}")
            return False
        
        try:
            # 加载现有配置
            config = self.load_config(skill_name)
            if config is None:
                logger.error(f"Cannot load config for skill: {skill_name}")
                return False
            
            # 添加缺失的字段
            self._add_missing_fields(config, schema.get('fields', []))
            
            # 保存修复后的配置
            return self.save_config(skill_name, config)
            
        except Exception as e:
            logger.error(f"Failed to auto-fix config for {skill_name}: {e}")
            return False
    
    def _add_missing_fields(self, config: dict, fields: list[dict]) -> None:
        """
        递归添加缺失的字段
        
        Args:
            config: 配置字典
            fields: 字段定义列表
        """
        for field in fields:
            key = field['key']
            
            if key not in config:
                # 字段缺失，添加默认值
                if field['type'] == 'object':
                    config[key] = {}
                    nested_fields = field.get('fields', [])
                    self._add_missing_fields(config[key], nested_fields)
                elif 'default' in field:
                    config[key] = field['default']
                elif field.get('required'):
                    # 必填字段没有默认值，使用空值
                    config[key] = self._get_empty_value(field['type'])
            elif field['type'] == 'object' and isinstance(config[key], dict):
                # 递归处理嵌套对象
                nested_fields = field.get('fields', [])
                self._add_missing_fields(config[key], nested_fields)
    
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
    
    def get_help_content(self, skill_name: str) -> Optional[str]:
        """
        获取配置帮助文档内容
        
        Args:
            skill_name: 技能名称
            
        Returns:
            str: 帮助文档内容，如果不存在则返回None
        """
        help_path = self.skills_dir / skill_name / "config.help.md"
        
        if not help_path.exists():
            logger.debug(f"Help file not found for skill: {skill_name}")
            return None
        
        try:
            content = help_path.read_text(encoding='utf-8')
            logger.debug(f"Loaded help content for skill: {skill_name}")
            return content
        except Exception as e:
            logger.error(f"Failed to load help content for {skill_name}: {e}")
            return None
