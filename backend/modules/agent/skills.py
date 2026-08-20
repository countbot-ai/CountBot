"""Skills Loader - 技能加载管理"""

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml
from loguru import logger
from backend.utils.paths import APPLICATION_ROOT

# 默认内置技能目录
BUILTIN_SKILLS_DIR = APPLICATION_ROOT / "workspace" / "skills"

# frontmatter 分隔符。兼容 CRLF（Windows 上编辑过的 SKILL.md 会是 \r\n）与结尾无换行的文件。
_FRONTMATTER_RE = re.compile(r"^---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", re.DOTALL)

# Agent Skills 开放标准：description 上限 1024 字符，name 为 kebab-case。
# 超限只告警不拒绝——宁可技能可用但有提示，也不要静默消失。
MAX_DESCRIPTION_LENGTH = 1024
MAX_NAME_LENGTH = 64
_SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _coerce_bool(value: Any) -> bool:
    """YAML 里 `always: true` 是真 bool，但手写的 `always: "yes"` 是字符串，两种都要认。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "1", "on")
    return False


def _coerce_str_list(value: Any) -> List[str]:
    """接受 YAML 列表，也接受逗号分隔的单行字符串（Claude Code 生态两种写法都有）。"""
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _coerce_requires(value: Any) -> Dict[str, List[str]]:
    """规范化 requires 为 {bins: [...], env: [...]}。"""
    if not isinstance(value, dict):
        return {}
    requires: Dict[str, List[str]] = {}
    for key in ("bins", "env"):
        items = _coerce_str_list(value.get(key))
        if items:
            requires[key] = items
    return requires


def _extract_frontmatter(content: str) -> Optional[str]:
    """取出 frontmatter 原文；没有 frontmatter 返回 None。"""
    if not content.startswith("---"):
        return None
    match = _FRONTMATTER_RE.match(content)
    return match.group(1) if match else None


def build_frontmatter(
    name: str,
    description: str,
    auto_load: bool = False,
    requirements: Optional[List[str]] = None,
) -> str:
    """生成 SKILL.md 的 frontmatter。

    必须用 yaml.safe_dump 而不是 f-string 拼接：描述里只要含 ": "、以 "#" 开头、
    或者是多行文本，裸拼出来就是非法 YAML，会让整个 frontmatter 解析失败。
    safe_dump 会按需自动加引号 / 转块标量。
    """
    payload: Dict[str, Any] = {
        "name": name,
        "description": description,
        "metadata": {
            "CountBot": {
                "always": bool(auto_load),
                "requires": {"bins": list(requirements or [])},
            }
        },
    }
    body = yaml.safe_dump(
        payload,
        allow_unicode=True,      # 中文描述不要被转义成 \uXXXX
        sort_keys=False,
        default_flow_style=False,
    )
    return f"---\n{body}---\n\n"


def _is_same_or_nested_path(path: Path, base: Path) -> bool:
    """判断 path 是否等于 base 或位于 base 之内。"""
    try:
        normalized_path = os.path.normcase(str(path))
        normalized_base = os.path.normcase(str(base))
        return os.path.commonpath([normalized_path, normalized_base]) == normalized_base
    except ValueError:
        return False


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
        self.source = source  # "workspace" or "builtin" or "openclaw"
        self.metadata = self._parse_metadata()
        # 添加 auto_load 属性，从 metadata 中获取
        self.auto_load = self.metadata.get("always", False)

    def _parse_metadata(self) -> Dict[str, Any]:
        """解析技能文件的 YAML frontmatter。

        用真正的 YAML 解析器。此前是手搓的 `split(":", 1)` 行循环，它读不了块标量
        （`description: |`）——遇到时会把 description 解析成字面量 "|"，导致技能在
        系统提示词里没有任何触发语，永远不会被激活，而且不报错。

        解析失败时降级到 legacy 行解析并记录 parse_error，而不是让整个技能失去元数据。
        """
        metadata: Dict[str, Any] = {
            "title": self.name,
            "description": "",
            "dependencies": [],
            "tags": [],
            "always": False,
            "requires": {},
            # 开放标准字段：此前被解析后丢弃
            "name": "",
            "version": "",
            "license": "",
            "allowed_tools": [],
            # 诊断信息，供 API/UI 显式暴露，不再静默 warning
            "warnings": [],
            "parse_error": "",
        }

        raw = _extract_frontmatter(self.content)
        if raw is None:
            return metadata

        try:
            data = yaml.safe_load(raw)
        except yaml.YAMLError as exc:
            detail = " ".join(str(exc).split())
            metadata["parse_error"] = f"YAML 解析失败: {detail[:200]}"
            # 降级：至少把能捞的 key 捞出来，技能不至于完全没有描述
            self._apply_legacy_frontmatter(raw, metadata)
            return metadata

        if data is None:
            return metadata
        if not isinstance(data, dict):
            metadata["parse_error"] = (
                f"frontmatter 必须是 YAML 映射（key: value），实际解析出 {type(data).__name__}"
            )
            return metadata

        self._apply_frontmatter(data, metadata)
        return metadata

    def _apply_frontmatter(self, data: Dict[str, Any], metadata: Dict[str, Any]) -> None:
        """把解析出的 YAML 映射投影到 metadata，并做开放标准的 lint。"""
        warnings: List[str] = metadata["warnings"]

        if data.get("title") is not None:
            metadata["title"] = str(data["title"]).strip()

        description = data.get("description")
        if description is not None:
            metadata["description"] = str(description).strip()

        for key in ("name", "version", "license"):
            if data.get(key) is not None:
                metadata[key] = str(data[key]).strip()

        metadata["tags"] = _coerce_str_list(data.get("tags"))
        metadata["dependencies"] = _coerce_str_list(data.get("dependencies"))

        # allowed-tools（开放标准写法）与 allowed_tools 都认。
        # 注意：解析出来只是暴露给 API/UI，运行时尚未强制执行（见 S2）。
        allowed = data.get("allowed-tools")
        if allowed is None:
            allowed = data.get("allowed_tools")
        metadata["allowed_tools"] = _coerce_str_list(allowed)

        if "always" in data:
            metadata["always"] = _coerce_bool(data["always"])

        # 顶层 requires（原生 YAML 写法）
        metadata["requires"] = _coerce_requires(data.get("requires"))

        # metadata: 既可能是 YAML 内联映射（API 写出来的 JSON 恰好是合法 YAML flow map），
        # 也可能是遗留的 JSON 字符串。两种都要认。
        nested = data.get("metadata")
        if isinstance(nested, str):
            try:
                nested = json.loads(nested)
            except (json.JSONDecodeError, TypeError):
                warnings.append("metadata 字段不是合法的 JSON/YAML 映射，已忽略")
                nested = None
        if isinstance(nested, dict):
            countbot_meta = nested.get("CountBot")
            if isinstance(countbot_meta, dict):
                if "requires" in countbot_meta:
                    # 顶层 requires 优先；仅在其缺省时回退到嵌套写法
                    nested_requires = _coerce_requires(countbot_meta.get("requires"))
                    if nested_requires and not metadata["requires"]:
                        metadata["requires"] = nested_requires
                if "always" in countbot_meta:
                    metadata["always"] = _coerce_bool(countbot_meta["always"])

        self._lint(data, metadata, warnings)

    def _lint(
        self, data: Dict[str, Any], metadata: Dict[str, Any], warnings: List[str]
    ) -> None:
        """开放标准合规检查。只告警，不让技能失效。"""
        if not metadata["description"]:
            warnings.append("缺少 description，模型将无法判断何时使用该技能")
        elif len(metadata["description"]) > MAX_DESCRIPTION_LENGTH:
            warnings.append(
                f"description 长度 {len(metadata['description'])} 超过开放标准上限 "
                f"{MAX_DESCRIPTION_LENGTH}"
            )

        declared_name = metadata["name"]
        if declared_name:
            if len(declared_name) > MAX_NAME_LENGTH:
                warnings.append(f"name 长度超过 {MAX_NAME_LENGTH} 字符")
            if not _SKILL_NAME_RE.match(declared_name):
                warnings.append(f"name '{declared_name}' 不是合法的 kebab-case")
            if declared_name != self.name:
                # 目录名才是技能身份（.skills_config.json / API 路由 / 读文件拦截都以它为键）。
                # 这里只提示，不改身份——改身份是破坏性变更。
                warnings.append(
                    f"frontmatter name '{declared_name}' 与目录名 '{self.name}' 不一致；"
                    f"系统以目录名为准"
                )

    def _apply_legacy_frontmatter(self, raw: str, metadata: Dict[str, Any]) -> None:
        """YAML 解析失败时的降级路径：老的逐行 split 解析。

        只求尽量捞回 description/title/always，不追求正确性。
        """
        for line in raw.split("\n"):
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip().strip("\"'")
            if key == "title":
                metadata["title"] = value
            elif key == "description":
                metadata["description"] = value
            elif key == "always":
                metadata["always"] = _coerce_bool(value)

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

    def __init__(
        self,
        skills_dir: Path,
        builtin_skills_dir: Optional[Path] = None,
        external_skills_dirs: Optional[List[Path]] = None,
    ):
        """
        初始化 SkillsLoader
        
        Args:
            skills_dir: 工作空间技能文件存储目录
            builtin_skills_dir: 内置技能目录 (可选)
            external_skills_dirs: 外部 OpenClaw 技能目录 (可选，主要用于测试)
        """
        self.workspace_skills = skills_dir
        self.workspace_skills.mkdir(parents=True, exist_ok=True)
        
        self.builtin_skills = builtin_skills_dir or BUILTIN_SKILLS_DIR
        self.external_skills_dirs = external_skills_dirs
        
        self.skills: Dict[str, Skill] = {}
        
        # 加载禁用配置
        self.config_file = self.workspace_skills.parent / ".skills_config.json"
        self.disabled_skills = self._load_disabled_skills()
        
        self._load_all_skills()
        
        logger.info(f"Loaded {len(self.skills)} skills")
    
    def _load_disabled_skills(self) -> Set[str]:
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

    def _discover_openclaw_skill_dirs(self) -> List[Path]:
        """发现外部 OpenClaw / 兼容技能目录"""
        if self.external_skills_dirs is not None:
            candidates = [Path(path) for path in self.external_skills_dirs]
        else:
            home = Path.home()
            candidates = [
                home / ".openclaw" / "skills",
                home / "skills",
            ]

            userprofile = os.environ.get("USERPROFILE")
            if userprofile:
                candidates.insert(0, Path(userprofile) / ".openclaw" / "skills")

        discovered: List[Path] = []
        seen: Set[str] = set()

        for candidate in candidates:
            resolved = candidate.expanduser().resolve(strict=False)
            key = str(resolved).lower() if os.name == "nt" else str(resolved)
            if key in seen:
                continue
            seen.add(key)
            discovered.append(resolved)

        return discovered

    def _iter_skill_files(self, skills_root: Path):
        """遍历技能目录中的 SKILL.md 文件"""
        if not skills_root.exists() or not skills_root.is_dir():
            return

        try:
            skill_dirs = sorted(skills_root.iterdir(), key=lambda item: item.name.lower())
        except (OSError, PermissionError) as e:
            logger.warning(f"Failed to scan skills directory {skills_root}: {e}")
            return

        for skill_dir in skill_dirs:
            try:
                if not skill_dir.is_dir():
                    continue
            except (OSError, PermissionError) as e:
                logger.warning(f"Failed to inspect skill directory {skill_dir}: {e}")
                continue

            skill_file = skill_dir / "SKILL.md"
            try:
                if skill_file.is_file():
                    yield skill_dir.name, skill_file
            except (OSError, PermissionError) as e:
                logger.warning(f"Failed to inspect skill file {skill_file}: {e}")

    def _register_skill(self, name: str, skill_file: Path, source: str) -> None:
        """注册技能，已存在同名技能时跳过"""
        if name in self.skills:
            return

        try:
            enabled = False if source == "openclaw" else name not in self.disabled_skills
            content = skill_file.read_text(encoding="utf-8")
            skill = Skill(
                name=name,
                path=skill_file,
                content=content,
                source=source,
                enabled=enabled,
            )
            self.skills[name] = skill

            parse_error = skill.metadata.get("parse_error")
            if parse_error:
                logger.error(f"Skill '{name}' frontmatter 解析失败（已降级解析）: {parse_error}")
            for warning in skill.metadata.get("warnings", []):
                logger.warning(f"Skill '{name}': {warning}")

            logger.debug(f"Loaded {source} skill: {name}")
        except Exception as e:
            logger.warning(f"Failed to load {source} skill {skill_file.parent}: {e}")

    def _import_openclaw_skill_to_workspace(self, name: str) -> Path:
        """将外部 OpenClaw 技能导入到工作空间"""
        skill = self.get_skill(name)
        if not skill:
            raise ValueError(f"Skill '{name}' not found")
        if skill.source != "openclaw":
            raise ValueError(f"Skill '{name}' is not an OpenClaw skill")

        source_skill_file = skill.path.resolve(strict=True)
        if source_skill_file.name != "SKILL.md":
            raise ValueError(f"OpenClaw skill '{name}' is missing SKILL.md")

        source_dir = source_skill_file.parent
        if not source_dir.is_dir():
            raise NotADirectoryError(f"OpenClaw skill directory is invalid: {source_dir}")

        workspace_root = self.workspace_skills.resolve(strict=False)
        target_dir = (self.workspace_skills / name).resolve(strict=False)

        if target_dir.exists():
            raise FileExistsError(f"Workspace skill directory already exists: {target_dir}")

        if _is_same_or_nested_path(source_dir, workspace_root):
            raise ValueError(
                f"Refusing to import OpenClaw skill '{name}' from inside workspace skills directory"
            )

        if _is_same_or_nested_path(target_dir, source_dir) or _is_same_or_nested_path(source_dir, target_dir):
            raise ValueError(
                f"Refusing to import OpenClaw skill '{name}' because source and target directories overlap"
            )

        try:
            shutil.copytree(source_dir, target_dir)
        except (shutil.Error, PermissionError, OSError) as e:
            raise RuntimeError(
                f"Failed to copy OpenClaw skill '{name}' into workspace: {e}"
            ) from e

        logger.info(f"Imported OpenClaw skill '{name}' to workspace: {target_dir}")
        return target_dir / "SKILL.md"

    def _load_all_skills(self) -> None:
        """加载所有技能文件（工作空间 + 内置 + OpenClaw 外部目录）"""
        try:
            # 1. 加载工作空间技能（优先级最高）
            for name, skill_file in self._iter_skill_files(self.workspace_skills) or []:
                self._register_skill(name, skill_file, "workspace")

            # 2. 加载内置技能（优先级次之）
            if self.builtin_skills:
                for name, skill_file in self._iter_skill_files(self.builtin_skills) or []:
                    self._register_skill(name, skill_file, "builtin")

            # 3. 加载外部 OpenClaw 技能（最低优先级）
            for external_dir in self._discover_openclaw_skill_dirs():
                for name, skill_file in self._iter_skill_files(external_dir) or []:
                    self._register_skill(name, skill_file, "openclaw")
            
            logger.debug(f"Loaded {len(self.skills)} skills total")
            
        except Exception as e:
            logger.error(f"Failed to load skills: {e}")

    def list_skills(self, enabled_only: bool = False, filter_unavailable: bool = False) -> List[dict]:
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
            "version": skill.metadata.get("version", ""),
            "license": skill.metadata.get("license", ""),
            "allowed_tools": list(skill.metadata.get("allowed_tools", [])),
            # 诊断信息：frontmatter 坏了要能在 UI 上看见，而不是只躺在日志里
            "warnings": list(skill.metadata.get("warnings", [])),
            "parse_error": skill.metadata.get("parse_error", ""),
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

    def get_always_skills(self) -> List[str]:
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

    def load_skills_for_context(self, skill_names: List[str]) -> str:
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
            desc = " ".join(str(desc or "").split())
            
            # 紧凑格式：优先保留技能名，标题仅在明显不同于技能名时展示
            title_suffix = ""
            if title and title != name:
                title_suffix = f" | {title}"

            if desc:
                lines.append(f"- {name}{title_suffix}: {desc}")
            else:
                lines.append(f"- {name}{title_suffix}")
        
        return "\n".join(lines) if lines else ""

    def _strip_frontmatter(self, content: str) -> str:
        """从 markdown 内容中移除 YAML frontmatter（兼容 CRLF）"""
        if content.startswith("---"):
            match = _FRONTMATTER_RE.match(content)
            if match:
                return content[match.end():].strip()
        return content

    def get_skill(self, name: str) -> Optional[Skill]:
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

        if skill.source == "openclaw":
            try:
                self._import_openclaw_skill_to_workspace(name)
                self.reload()
                skill = self.get_skill(name)
                if not skill or skill.source != "workspace":
                    logger.error(f"Imported OpenClaw skill '{name}' was not reloaded as workspace skill")
                    return False
            except Exception as e:
                logger.error(f"Failed to import OpenClaw skill '{name}' to workspace: {e}")
                return False
        
        self.disabled_skills.discard(name)
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
        
        self.disabled_skills.add(name)
        skill.enabled = False
        logger.info(f"Disabled skill: {name}")
        return True

    def check_dependencies(self, name: str) -> Tuple[bool, List[str]]:
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

    def get_auto_load_skills(self) -> List[str]:
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
        self.disabled_skills = self._load_disabled_skills()
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

            self.disabled_skills.discard(name)
            
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
            skill.auto_load = skill.metadata.get("always", False)
            
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

        if skill.source != "workspace":
            logger.warning(f"Cannot delete skill '{name}': not a workspace skill")
            return False
        
        try:
            skill_dir = skill.path.parent
            if skill_dir.exists() and skill_dir.parent == self.workspace_skills:
                shutil.rmtree(skill_dir)
            elif skill.path.exists():
                skill.path.unlink()

            self.disabled_skills.discard(name)
            del self.skills[name]
            logger.info(f"Deleted skill: {name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete skill '{name}': {e}")
            return False

    def get_stats(self) -> Dict[str, int]:
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
