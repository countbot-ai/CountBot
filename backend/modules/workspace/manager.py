"""工作空间管理器"""

import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

from loguru import logger


class WorkspaceManager:
    """工作空间管理器"""
    
    def __init__(self):
        self._workspace_path: Optional[Path] = None
        self._temp_dir: Optional[Path] = None
        self._info_cache: Optional[Dict[str, Any]] = None
        self._cache_timestamp: float = 0
        self._cache_ttl: int = 30  # 缓存30秒
    
    @property
    def workspace_path(self) -> Path:
        """获取工作空间路径"""
        if self._workspace_path is None:
            self._workspace_path = self._get_default_workspace_path()
        return self._workspace_path
    
    @property
    def temp_dir(self) -> Path:
        """获取临时文件目录"""
        if self._temp_dir is None:
            self._temp_dir = self.workspace_path / "temp"
            self._temp_dir.mkdir(parents=True, exist_ok=True)
        return self._temp_dir
    
    def get_workspace_path(self) -> Path:
        """获取工作空间路径（方法形式）"""
        return self.workspace_path
    
    def check_skills_migration_needed(self, old_workspace: Path, new_workspace: Path) -> dict:
        """检查是否需要迁移技能文件
        
        Args:
            old_workspace: 旧工作空间路径
            new_workspace: 新工作空间路径
            
        Returns:
            包含迁移信息的字典
        """
        old_skills_dir = old_workspace / "skills"
        new_skills_dir = new_workspace / "skills"
        
        def count_skills(skills_dir: Path) -> int:
            """统计包含 SKILL.md 的技能目录数量。"""
            if not skills_dir.exists() or not skills_dir.is_dir():
                return 0

            try:
                return len(
                    [
                        item
                        for item in skills_dir.iterdir()
                        if item.is_dir() and (item / "SKILL.md").is_file()
                    ]
                )
            except Exception as e:
                logger.warning(f"无法读取技能目录 {skills_dir}: {e}")
                return 0

        old_skills_count = count_skills(old_skills_dir)
        new_skills_count = count_skills(new_skills_dir)
        
        # 如果旧工作空间有技能，但新工作空间技能较少，则需要迁移
        migration_needed = old_skills_count > 0 and new_skills_count < old_skills_count
        
        return {
            "needed": migration_needed,
            "old_skills_count": old_skills_count,
            "new_skills_count": new_skills_count,
            "old_skills_path": str(old_skills_dir),
            "new_skills_path": str(new_skills_dir)
        }

    def prepare_workspace_path(self, path: Union[str, Path]) -> Path:
        """校验并准备工作空间路径，但不修改当前运行态。"""
        workspace_path = Path(path).expanduser().resolve()
        workspace_path.mkdir(parents=True, exist_ok=True)

        temp_dir = workspace_path / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        return workspace_path

    def activate_workspace_path(self, workspace_path: Union[str, Path]) -> Path:
        """激活一个已经校验通过的工作空间路径。"""
        resolved_path = Path(workspace_path).expanduser().resolve()
        temp_dir = resolved_path / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)

        self._workspace_path = resolved_path
        self._temp_dir = temp_dir

        # 路径变化时清除缓存
        self._info_cache = None
        self._cache_timestamp = 0

        logger.info(f"工作空间路径: {resolved_path}")
        return resolved_path

    def resolve_workspace_path_or_default(self, path: Optional[Union[str, Path]]) -> Tuple[Path, bool]:
        """解析工作空间路径；失败时回退到默认工作空间。"""
        if path:
            try:
                return self.prepare_workspace_path(path), False
            except Exception as e:
                logger.warning(f"工作空间路径不可用，回退到默认目录: {path}, error: {e}")

        default_workspace = self._get_default_workspace_path()
        return default_workspace, bool(path)
    
    def set_workspace_path(self, path: str) -> None:
        """设置工作空间路径"""
        workspace_path = self.prepare_workspace_path(path)
        self.activate_workspace_path(workspace_path)

    def get_workspace_path(self) -> Path:
        """获取工作空间路径（方法形式）"""
        return self.workspace_path

    
    def _get_default_workspace_path(self) -> Path:
        """获取默认工作空间路径"""
        try:
            # 获取程序目录
            if getattr(sys, 'frozen', False):
                if sys.platform == "darwin":
                    # macOS app bundle
                    app_dir = Path(sys.executable).parent.parent.parent
                else:
                    # Windows/Linux 可执行文件
                    app_dir = Path(sys.executable).parent
            else:
                # 开发环境
                current_file = Path(__file__).resolve()
                app_dir = current_file.parent.parent.parent.parent
            
            # 默认工作空间：程序目录/workspace
            default_workspace = app_dir / "workspace"
            default_workspace.mkdir(parents=True, exist_ok=True)
            
            # 创建临时目录
            temp_dir = default_workspace / "temp"
            temp_dir.mkdir(parents=True, exist_ok=True)
            
            logger.info(f"默认工作空间: {default_workspace}")
            return default_workspace
            
        except Exception as e:
            logger.warning(f"无法确定程序目录: {e}")
            # 备用方案：当前目录/workspace
            fallback_workspace = Path.cwd() / "workspace"
            fallback_workspace.mkdir(parents=True, exist_ok=True)
            (fallback_workspace / "temp").mkdir(parents=True, exist_ok=True)
            return fallback_workspace
    
    def get_temp_file(self, suffix: str = "", prefix: str = "countbot_") -> Path:
        """获取临时文件路径"""
        import uuid
        filename = f"{prefix}{uuid.uuid4().hex[:8]}{suffix}"
        return self.temp_dir / filename
    
    def clean_temp_files(self, max_age_hours: int = 24, clean_all: bool = False) -> dict:
        """清理临时文件
        
        Args:
            max_age_hours: 清理多少小时前的文件
            clean_all: 是否清理所有临时文件（忽略时间限制）
        """
        import time
        
        if not self.temp_dir.exists():
            return {"success": True, "cleaned_count": 0, "message": "临时目录不存在"}
        
        cleaned_count = 0
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        
        try:
            for file_path in self.temp_dir.iterdir():
                if file_path.is_file():
                    should_delete = False
                    
                    if clean_all:
                        should_delete = True
                    else:
                        file_age = current_time - file_path.stat().st_mtime
                        should_delete = file_age > max_age_seconds
                    
                    if should_delete:
                        try:
                            file_path.unlink()
                            cleaned_count += 1
                        except Exception as e:
                            logger.warning(f"清理临时文件失败 {file_path.name}: {e}")
        except Exception as e:
            logger.error(f"清理临时文件时出错: {e}")
            return {"success": False, "message": f"清理失败: {e}"}
        
        # 清理后使缓存失效
        self._info_cache = None
        
        if clean_all:
            message = f"已清理所有 {cleaned_count} 个临时文件" if cleaned_count > 0 else "没有临时文件需要清理"
        else:
            message = f"已清理 {cleaned_count} 个超过 {max_age_hours} 小时的临时文件" if cleaned_count > 0 else f"没有超过 {max_age_hours} 小时的临时文件需要清理"
        
        if cleaned_count > 0:
            logger.info(message)
        
        return {
            "success": True,
            "cleaned_count": cleaned_count,
            "message": message
        }
    
    def get_workspace_info(self, force_refresh: bool = False) -> dict:
        """获取工作空间信息，优化性能和稳定性
        
        Args:
            force_refresh: 是否强制刷新缓存
        """
        current_time = time.time()
        
        # 检查缓存是否有效
        if (not force_refresh and 
            self._info_cache is not None and 
            current_time - self._cache_timestamp < self._cache_ttl):
            return self._info_cache
        
        workspace = self.workspace_path
        temp_dir = self.temp_dir
        
        def get_dir_stats(path: Path, max_depth: int = 10) -> Tuple[int, int, int]:
            """获取目录统计信息（文件数、目录数、总大小）
            
            Args:
                path: 目录路径
                max_depth: 最大递归深度，防止深层目录影响性能
            """
            total_size = 0
            file_count = 0
            dir_count = 0
            
            try:
                # 使用 os.walk 提高性能，避免递归调用
                for root, dirs, files in os.walk(path):
                    # 计算当前深度
                    current_depth = root[len(str(path)):].count(os.sep)
                    if current_depth >= max_depth:
                        dirs.clear()  # 不再深入子目录
                        continue
                    
                    # 过滤隐藏目录和常见的大型目录
                    dirs[:] = [d for d in dirs if not d.startswith('.') and d not in {
                        'node_modules', '__pycache__', '.git', '.vscode', 
                        'venv', 'env', 'build', 'dist', 'target'
                    }]
                    
                    dir_count += len(dirs)
                    file_count += len(files)
                    
                    # 批量获取文件大小，跳过大文件和特殊文件
                    for file in files:
                        if file.startswith('.') or file.endswith(('.log', '.tmp', '.cache')):
                            continue
                        try:
                            file_path = os.path.join(root, file)
                            file_size = os.path.getsize(file_path)
                            # 跳过超大文件（>100MB）以提高性能
                            if file_size < 100 * 1024 * 1024:
                                total_size += file_size
                        except (OSError, IOError):
                            # 跳过无法访问的文件
                            continue
                            
            except (OSError, IOError) as e:
                logger.warning(f"无法访问目录 {path}: {e}")
                
            return file_count, dir_count, total_size
        
        def format_size(size_bytes: int) -> str:
            """格式化文件大小"""
            if size_bytes == 0:
                return "0 B"
            
            size_names = ["B", "KB", "MB", "GB", "TB"]
            import math
            i = int(math.floor(math.log(size_bytes, 1024)))
            p = math.pow(1024, i)
            s = round(size_bytes / p, 2)
            return f"{s} {size_names[i]}"
        
        # 获取工作空间统计
        try:
            if workspace.exists():
                workspace_files, workspace_dirs, workspace_size = get_dir_stats(workspace)
            else:
                workspace_files = workspace_dirs = workspace_size = 0
        except Exception as e:
            logger.error(f"获取工作空间统计失败: {e}")
            workspace_files = workspace_dirs = workspace_size = 0
        
        # 获取临时目录统计
        try:
            if temp_dir.exists():
                temp_files, _, temp_size = get_dir_stats(temp_dir, max_depth=3)  # 临时目录深度限制更严格
            else:
                temp_files = temp_size = 0
        except Exception as e:
            logger.error(f"获取临时目录统计失败: {e}")
            temp_files = temp_size = 0
        
        result = {
            "success": True,
            "workspace": {
                "path": str(workspace),
                "exists": workspace.exists(),
                "files": workspace_files,
                "directories": workspace_dirs,
                "size": workspace_size,
                "size_formatted": format_size(workspace_size)
            },
            "temp": {
                "path": str(temp_dir),
                "exists": temp_dir.exists(),
                "files": temp_files,
                "size": temp_size,
                "size_formatted": format_size(temp_size)
            }
        }
        
        # 更新缓存
        self._info_cache = result
        self._cache_timestamp = current_time
        
        return result


# 全局实例
workspace_manager = WorkspaceManager()
