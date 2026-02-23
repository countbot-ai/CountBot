"""Skills Loader - 技能加载管理"""

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

from loguru import logger
from backend.utils.paths import APPLICATION_ROOT

# 默认内置技能目录
BUILTIN_SKILLS_DIR = APPLICATION_ROOT / "skills"


class Skill:
    """技能数据类"""

    def __init__(
        self,
        name: str,
        path: Path,
        content: str,
        enabled: bool = True,
        source: str = "workspace",
    ):
        self.name = name
        self.path = path
        self.content = content
        self.enabled = enabled
        self.source = source  # "workspace" or "builtin"
        self.metadata = self._parse_metadata()
        # 添加 auto_load 属性，从 metadata 中获取
        self.auto_load = self.metadata.get("always", False)

    def _parse_metadata(self) -> dict[str, Any]:
        """解析技能文件的元数据（YAML frontmatter）"""
        metadata = {
            "title": self.name,
            "description": "",
            "dependencies": [],
            "tags": [],
            "always": False,
            "requires": {},
        }
        
        # 解析 YAML frontmatter
        if self.content.startswith("---"):
            match = re.match(r"^---\n(.*?)\n---", self.content, re.DOTALL)
            if match:
                yaml_content = match.group(1)
                
                # 简单的 YAML 解析
                for line in yaml_content.split("\n"):
                    if ":" in line:
                        key, value = line.split(":", 1)
                        key = key.strip()
                        value = value.strip().strip('"\'')
                        
                        if key == "title":
                            metadata["title"] = value
                        elif key == "description":
                            metadata["description"] = value
                        elif key == "always":
                            metadata["always"] = value.lower() in ("true", "yes", "1")
                        elif key == "metadata":
                            # 解析技能元数据 JSON
                            try:
                                meta_data = json.loads(value)
                                if isinstance(meta_data, dict):
                                    skill_meta = meta_data.get("CountBot", {})
                                    if "requires" in skill_meta:
                                        metadata["requires"] = skill_meta["requires"]
                                    if "always" in skill_meta:
                                        metadata["always"] = skill_meta["always"]
                            except (json.JSONDecodeError, TypeError):
                                pass
        
        return metadata

    def get_summary(self) -> str:
        """获取技能摘要"""
        title = self.metadata.get("title", self.name)
        desc = self.metadata.get("description", "")
        
        if desc:
            return f"- **{title}**: {desc}"
        return f"- **{title}**"

    def check_requirements(self) -> bool:
        """检查技能依赖是否满足"""
        requires = self.metadata.get("requires", {})
        
        # 检查二进制依赖
        for binary in requires.get("bins", []):
            if not shutil.which(binary):
                return False
        
        # 检查环境变量
        for env_var in requires.get("env", []):
            if not os.environ.get(env_var):
                return False
        
        return True

    def get_missing_requirements(self) -> str:
        """获取缺失的依赖描述"""
        requires = self.metadata.get("requires", {})
        missing = []
        
        for binary in requires.get("bins", []):
            if not shutil.which(binary):
                missing.append(f"CLI: {binary}")
        
        for env_var in requires.get("env", []):
            if not os.environ.get(env_var):
                missing.append(f"ENV: {env_var}")
        
        return ", ".join(missing)


class SkillsLoader:
    """
    技能加载器
    
    管理技能文件的加载、启用/禁用
    """

    def __init__(self, skills_dir: Path, builtin_skills_dir: Path | None = None):
        """
        初始化 SkillsLoader
        
        Args:
            skills_dir: 工作空间技能文件存储目录
            builtin_skills_dir: 内置技能目录 (可选)
        """
        self.workspace_skills = skills_dir
        self.workspace_skills.mkdir(parents=True, exist_ok=True)
        
        self.builtin_skills = builtin_skills_dir or BUILTIN_SKILLS_DIR
        
        self.skills: dict[str, Skill] = {}
        
        # 加载禁用配置
        self.config_file = self.workspace_skills.parent / ".skills_config.json"
        self.disabled_skills = self._load_disabled_skills()
        
        self._load_all_skills()
        
        logger.info(f"Loaded {len(self.skills)} skills")
    
    def _load_disabled_skills(self) -> set[str]:
        """从配置文件加载禁用的技能列表"""
        if not self.config_file.exists():
            logger.debug(f"Skills config file not found: {self.config_file}")
            return set()
        
        try:
            config = json.loads(self.config_file.read_text(encoding="utf-8"))
            disabled = set(config.get("disabled_skills", []))
            logger.debug(f"Loaded disabled skills from {self.config_file}: {disabled}")
            return disabled
        except Exception as e:
            logger.warning(f"Failed to load skills config from {self.config_file}: {e}")
            return set()

    def _load_all_skills(self) -> None:
        """加载所有技能文件（工作空间 + 内置）"""
        try:
            # 1. 加载工作空间技能（优先级最高）
            if self.workspace_skills.exists():
                for skill_dir in self.workspace_skills.iterdir():
                    if skill_dir.is_dir():
                        skill_file = skill_dir / "SKILL.md"
                        if skill_file.exists():
                            try:
                                name = skill_dir.name
                                content = skill_file.read_text(encoding="utf-8")
                                
                                skill = Skill(
                                    name=name,
                                    path=skill_file,
                                    content=content,
                                    source="workspace",
                                    enabled=name not in self.disabled_skills,
                                )
                                
                                self.skills[name] = skill
                                logger.debug(f"Loaded workspace skill: {name}")
                                
                            except Exception as e:
                                logger.warning(f"Failed to load workspace skill {skill_dir}: {e}")
            
            # 2. 加载内置技能（如果工作空间中不存在）
            if self.builtin_skills and self.builtin_skills.exists():
                for skill_dir in self.builtin_skills.iterdir():
                    if skill_dir.is_dir():
                        skill_file = skill_dir / "SKILL.md"
                        name = skill_dir.name
                        
                        # 如果工作空间中已有同名技能，跳过
                        if skill_file.exists() and name not in self.skills:
                            try:
                                content = skill_file.read_text(encoding="utf-8")
                                
                                skill = Skill(
                                    name=name,
                                    path=skill_file,
                                    content=content,
                                    source="builtin",
                                    enabled=name not in self.disabled_skills,
                                )
                                
                                self.skills[name] = skill
                                logger.debug(f"Loaded builtin skill: {name}")
                                
                            except Exception as e:
                                logger.warning(f"Failed to load builtin skill {skill_dir}: {e}")
            
            logger.debug(f"Loaded {len(self.skills)} skills total")
            
        except Exception as e:
            logger.error(f"Failed to load skills: {e}")

    def list_skills(self, enabled_only: bool = False, filter_unavailable: bool = False) -> list[dict]:
        """
        列出所有技能
        
        Args:
            enabled_only: 是否只返回已启用的技能
            filter_unavailable: 是否过滤掉依赖未满足的技能
            
        Returns:
            list: 技能信息列表
        """
        skills = []
        
        for name, skill in self.skills.items():
            if enabled_only and not skill.enabled:
                continue
            
            if filter_unavailable and not skill.check_requirements():
                continue
            
            skills.append({
                "name": name,
                "enabled": skill.enabled,
                "source": skill.source,
                "path": str(skill.path),
            })
        
        return skills
    
    def load_skill(self, name: str) -> str:
        """
        加载技能内容
        
        Args:
            name: 技能名称
            
        Returns:
            str: 技能内容
        """
        return self.read_skill(name)
    
    def get_skill_summary(self, name: str) -> dict:
        """
        获取技能摘要信息
        
        Args:
            name: 技能名称
            
        Returns:
            dict: 技能摘要
        """
        skill = self.get_skill(name)
        if not skill:
            return {}
        
        return {
            "description": skill.metadata.get("description", ""),
            "auto_load": skill.metadata.get("always", False),
            "requirements": list(skill.metadata.get("requires", {}).get("bins", [])),
        }
    
    def toggle_skill(self, name: str, enabled: bool) -> bool:
        """
        切换技能启用状态
        
        Args:
            name: 技能名称
            enabled: 是否启用
            
        Returns:
            bool: 是否成功
        """
        if enabled:
            return self.enable_skill(name)
        else:
            return self.disable_skill(name)

    def get_always_skills(self) -> list[str]:
        """
        获取标记为 always=true 且满足依赖的技能
        
        Returns:
            list: always-loaded 技能名称列表
        """
        result = []
        for name, skill in self.skills.items():
            if skill.enabled and skill.metadata.get("always") and skill.check_requirements():
                result.append(name)
        return result

    def load_skills_for_context(self, skill_names: list[str]) -> str:
        """
        加载特定技能用于包含在 agent 上下文中
        
        Args:
            skill_names: 要加载的技能名称列表
            
        Returns:
            str: 格式化的技能内容
        """
        parts = []
        for name in skill_names:
            skill = self.get_skill(name)
            if skill:
                content = self._strip_frontmatter(skill.content)
                parts.append(f"### Skill: {name}\n\n{content}")
        
        return "\n\n---\n\n".join(parts) if parts else ""

    def build_skills_summary(self) -> str:
        """
        构建所有已启用技能的摘要 - 极简版
        
        用于渐进式加载 - agent 可以在需要时使用 read_file 读取完整技能内容
        
        Returns:
            str: 简洁的技能列表，每行一个技能
        """
        if not self.skills:
            return ""
        
        lines = []
        for name, skill in sorted(self.skills.items()):
            # 只包含已启用的技能
            if not skill.enabled:
                continue
            
            # 检查依赖是否满足
            available = skill.check_requirements()
            if not available:
                continue
            
            # 获取描述
            desc = skill.metadata.get("description", "")
            title = skill.metadata.get("title", name)
            
            # 格式：- 技能名 (标题): 简短描述
            if desc:
                lines.append(f"- {name} ({title}): {desc}")
            else:
                lines.append(f"- {name} ({title})")
        
        return "\n".join(lines) if lines else ""

    def _strip_frontmatter(self, content: str) -> str:
        """从 markdown 内容中移除 YAML frontmatter"""
        if content.startswith("---"):
            match = re.match(r"^---\n.*?\n---\n", content, re.DOTALL)
            if match:
                return content[match.end():].strip()
        return content

    def get_skill(self, name: str) -> Skill | None:
        """
        获取指定技能
        
        Args:
            name: 技能名称
            
        Returns:
            Skill: 技能对象，如果不存在则返回 None
        """
        return self.skills.get(name)

    def read_skill(self, name: str) -> str:
        """
        读取技能内容
        
        Args:
            name: 技能名称
            
        Returns:
            str: 技能内容
            
        Raises:
            ValueError: 技能不存在
        """
        skill = self.get_skill(name)
        if not skill:
            raise ValueError(f"Skill '{name}' not found")
        
        return skill.content

    def enable_skill(self, name: str) -> bool:
        """
        启用技能
        
        Args:
            name: 技能名称
            
        Returns:
            bool: 是否成功
        """
        skill = self.get_skill(name)
        if not skill:
            logger.warning(f"Cannot enable skill '{name}': not found")
            return False
        
        skill.enabled = True
        logger.info(f"Enabled skill: {name}")
        return True

    def disable_skill(self, name: str) -> bool:
        """
        禁用技能
        
        Args:
            name: 技能名称
            
        Returns:
            bool: 是否成功
        """
        skill = self.get_skill(name)
        if not skill:
            logger.warning(f"Cannot disable skill '{name}': not found")
            return False
        
        skill.enabled = False
        logger.info(f"Disabled skill: {name}")
        return True

    def check_dependencies(self, name: str) -> tuple[bool, list[str]]:
        """
        检查技能依赖
        
        Args:
            name: 技能名称
            
        Returns:
            tuple: (是否满足所有依赖, 缺失的依赖列表)
        """
        skill = self.get_skill(name)
        if not skill:
            return False, [f"Skill '{name}' not found"]
        
        dependencies = skill.metadata.get("dependencies", [])
        missing = []
        
        for dep in dependencies:
            if dep not in self.skills:
                missing.append(dep)
            elif not self.skills[dep].enabled:
                missing.append(f"{dep} (disabled)")
        
        return len(missing) == 0, missing

    def get_summary(self, auto_load_only: bool = False) -> str:
        """
        获取技能摘要
        
        Args:
            auto_load_only: 是否只包含自动加载的技能
            
        Returns:
            str: 技能摘要文本
        """
        summaries = []
        
        for name, skill in sorted(self.skills.items()):
            if not skill.enabled:
                continue
            
            if auto_load_only and not skill.auto_load:
                continue
            
            summaries.append(skill.get_summary())
        
        if not summaries:
            return ""
        
        return "\n".join(summaries)

    def get_auto_load_skills(self) -> list[str]:
        """
        获取所有自动加载的技能
        
        Returns:
            list: 自动加载的技能名称列表
        """
        return [
            name
            for name, skill in self.skills.items()
            if skill.enabled and skill.auto_load
        ]

    def get_enabled_content(self, auto_load_only: bool = False) -> str:
        """
        获取所有已启用技能的内容
        
        Args:
            auto_load_only: 是否只包含自动加载的技能
            
        Returns:
            str: 合并的技能内容
        """
        contents = []
        
        for name, skill in sorted(self.skills.items()):
            if not skill.enabled:
                continue
            
            if auto_load_only and not skill.auto_load:
                continue
            
            contents.append(f"## Skill: {skill.metadata.get('title', name)}\n\n{skill.content}")
        
        return "\n\n---\n\n".join(contents)

    def reload(self) -> None:
        """重新加载所有技能"""
        logger.info("Reloading all skills")
        self.skills.clear()
        self._load_all_skills()

    def add_skill(self, name: str, content: str) -> bool:
        """
        添加新技能
        
        Args:
            name: 技能名称
            content: 技能内容（包含 frontmatter）
            
        Returns:
            bool: 是否成功
        """
        try:
            # 创建技能目录
            skill_dir = self.workspace_skills / name
            skill_dir.mkdir(parents=True, exist_ok=True)
            skill_file = skill_dir / "SKILL.md"
            
            if skill_file.exists():
                logger.warning(f"Skill '{name}' already exists")
                return False
            
            # 写入技能文件
            skill_file.write_text(content, encoding="utf-8")
            
            # 创建技能对象
            skill = Skill(
                name=name,
                path=skill_file,
                content=content,
                enabled=True,
                source="workspace",
            )
            
            # 添加到技能字典
            self.skills[name] = skill
            logger.info(f"Added new skill: {name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add skill '{name}': {e}")
            return False

    def update_skill(self, name: str, content: str) -> bool:
        """
        更新技能
        
        Args:
            name: 技能名称
            content: 技能内容（包含 frontmatter）
            
        Returns:
            bool: 是否成功
        """
        skill = self.get_skill(name)
        if not skill:
            logger.warning(f"Cannot update skill '{name}': not found")
            return False
        
        # 只能更新工作空间技能
        if skill.source != "workspace":
            logger.warning(f"Cannot update skill '{name}': not a workspace skill")
            return False
        
        try:
            # 写入技能文件
            skill.path.write_text(content, encoding="utf-8")
            
            # 更新技能对象
            skill.content = content
            skill.metadata = skill._parse_metadata()
            
            logger.info(f"Updated skill: {name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update skill '{name}': {e}")
            return False

    def delete_skill(self, name: str) -> bool:
        """
        删除技能
        
        Args:
            name: 技能名称
            
        Returns:
            bool: 是否成功
        """
        skill = self.get_skill(name)
        if not skill:
            logger.warning(f"Cannot delete skill '{name}': not found")
            return False
        
        try:
            skill.path.unlink()
            del self.skills[name]
            logger.info(f"Deleted skill: {name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete skill '{name}': {e}")
            return False

    def get_stats(self) -> dict[str, int]:
        """
        获取技能统计信息
        
        Returns:
            dict: 统计信息
        """
        return {
            "total": len(self.skills),
            "enabled": len([s for s in self.skills.values() if s.enabled]),
            "disabled": len([s for s in self.skills.values() if not s.enabled]),
            "auto_load": len([s for s in self.skills.values() if s.auto_load]),
        }
