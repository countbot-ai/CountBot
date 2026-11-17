"""工作空间管理器"""

import os
import shutil
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


def get_global_workspace_path() -> Path:
    """返回全局配置里的工作空间；配置不可用时回退管理器单例。"""
    try:
        from backend.modules.config.loader import config_loader

        configured = getattr(config_loader.config.workspace, "path", "") or ""
    except Exception:
        configured = ""

    if configured:
        candidate = Path(configured).expanduser()
        try:
            if candidate.is_dir():
                return candidate.resolve()
        except OSError as exc:
            logger.warning(f"全局工作空间不可用: {configured}, error: {exc}")

    return workspace_manager.workspace_path


# 用户数据根：默认与管理员工作空间**平级**，不嵌在管理员工作空间内部
USERS_ROOT_DIR_NAME = "users"
# 旧版（嵌套）位置：<全局工作区>/.users/<uid>，只用于一次性搬迁
LEGACY_USERS_ROOT_NAME = ".users"
# 删除用户时的归档目录：<用户数据根>/.trash/<uid>-<时间戳>
ARCHIVE_DIR_NAME = ".trash"


def get_users_root() -> Path:
    """用户数据根目录：默认与管理员的全局工作空间平级，可用 workspace.users_root 覆盖。"""
    configured = ""
    try:
        from backend.modules.config.loader import config_loader

        configured = getattr(config_loader.config.workspace, "users_root", "") or ""
    except Exception as exc:
        logger.debug(f"读取 users_root 失败，使用默认值: {exc}")

    if configured:
        root = Path(configured).expanduser()
    else:
        root = get_global_workspace_path().parent / USERS_ROOT_DIR_NAME

    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _sanitize_user_id(user_id: str) -> str:
    """用户 ID 只允许安全字符，防止路径穿越。"""
    raw = str(user_id or "").strip()
    safe = "".join(ch for ch in raw if ch.isalnum() or ch in ("-", "_"))
    if not safe:
        raise ValueError("invalid user id for workspace")
    return safe


def _legacy_user_root(user_id: str) -> Path:
    """旧版嵌套位置；仅用于搬迁与回退，不再作为默认落点。"""
    return get_global_workspace_path() / LEGACY_USERS_ROOT_NAME / _sanitize_user_id(user_id)


def _migrate_legacy_user_root(user_id: str, target_root: Path) -> None:
    """把旧版嵌在工作空间里的用户目录搬到新的用户根。

    只在目标不存在时搬一次；搬迁失败保留旧位置并告警——宁可回退也不能丢数据。
    """
    legacy = _legacy_user_root(user_id)
    if not legacy.is_dir():
        return
    try:
        target_root.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(legacy), str(target_root))
        logger.info(f"已迁移用户工作区 {user_id}: {legacy} -> {target_root}")
    except Exception as exc:
        logger.warning(f"迁移用户工作区失败（保留旧位置）{user_id}: {exc}")


def get_effective_user_root(user_id: str) -> Path:
    """该用户数据实际所在的根目录（新位置优先，旧位置兜底）。"""
    root = get_users_root() / _sanitize_user_id(user_id)
    if root.exists():
        return root

    _migrate_legacy_user_root(user_id, root)
    if root.exists():
        return root

    legacy = _legacy_user_root(user_id)
    if legacy.is_dir():
        logger.warning(f"用户 {user_id} 仍使用旧版嵌套目录: {legacy}")
        return legacy
    return root


def get_user_workspace_root(user_id: str) -> Path:
    """返回某用户的隔离根目录（不含 workspace 层）。"""
    return get_users_root() / _sanitize_user_id(user_id)


def ensure_user_workspace(user_id: str) -> Path:
    """创建并返回用户工作区 ``<用户数据根>/<uid>/workspace``。"""
    workspace = get_effective_user_root(user_id) / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "memory").mkdir(parents=True, exist_ok=True)
    (workspace / "uploads").mkdir(parents=True, exist_ok=True)
    (workspace / "temp").mkdir(parents=True, exist_ok=True)
    (workspace / "skills").mkdir(parents=True, exist_ok=True)
    (workspace / "wiki").mkdir(parents=True, exist_ok=True)
    return workspace.resolve()


def archive_user_workspace(user_id: str) -> Optional[Path]:
    """删除用户时归档其工作区，而不是直接删掉。

    归档到 ``<用户数据根>/.trash/<uid>-<时间戳>``，便于误删恢复。
    只允许操作 ``<用户数据根>`` 之内的目录，越界一律拒绝。
    """
    source = get_effective_user_root(user_id)
    if not source.is_dir():
        return None

    users_root = get_users_root().resolve()
    try:
        resolved = source.resolve()
        resolved.relative_to(users_root)
    except (OSError, ValueError):
        logger.warning(f"拒绝归档用户数据根之外的目录: {source}")
        return None

    # 已经在归档区里就不要再嵌套归档
    if resolved.parent.name == ARCHIVE_DIR_NAME:
        return None

    trash = users_root / ARCHIVE_DIR_NAME
    trash.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d%H%M%S")
    target = trash / f"{resolved.name}-{stamp}"
    try:
        shutil.move(str(resolved), str(target))
    except Exception as exc:
        logger.warning(f"归档用户工作区失败 {user_id}: {exc}")
        return None

    logger.info(f"已归档用户工作区 {user_id}: {target}")
    return target


def resolve_user_workspace(user) -> Path:
    """解析用户实际工作区。

    管理员（owner_id 为空）沿用全局工作区；普通用户强制落在其私有子树，
    不接受任何前端传入的路径，避免越界读写管理员目录。
    """
    owner_id = None
    if user is not None:
        owner_id = getattr(user, "owner_id", None)
        if owner_id is None and getattr(user, "is_admin", False):
            return get_global_workspace_path()
    if not owner_id:
        return get_global_workspace_path()
    return ensure_user_workspace(owner_id)


def is_path_within_user_workspace(path: Path, user_id: str) -> bool:
    """校验路径是否位于该用户工作区子树内。"""
    try:
        root = get_effective_user_root(user_id).resolve()
        candidate = Path(path).expanduser().resolve()
    except (OSError, ValueError):
        return False
    try:
        return candidate == root or candidate.is_relative_to(root)
    except AttributeError:  # pragma: no cover - Python < 3.9
        try:
            root.relative_to(candidate)
            return False
        except ValueError:
            return True


def resolve_session_workspace(session: Any = None, user: Any = None) -> Path:
    """解析会话实际使用的工作空间。

    普通用户强制落在自己的私有工作区，不接受会话上的自定义路径，也不回退
    到管理员工作区；否则接口会把管理员目录暴露给普通用户。会话级路径仅对
    管理员生效，路径不可用时回退全局配置。
    """
    if user is None:
        from backend.modules.multiuser.permissions import get_request_user

        user = get_request_user()
    if user is not None and not getattr(user, "is_admin", False):
        return resolve_user_workspace(user)

    custom_path = getattr(session, "workspace_path", None) if session is not None else None
    if custom_path:
        candidate = Path(str(custom_path)).expanduser()
        try:
            if candidate.is_dir():
                return candidate.resolve()
        except OSError as exc:
            logger.warning(f"会话工作空间不可用: {custom_path}, error: {exc}")

        logger.warning(f"会话工作空间不可用，回退全局: {custom_path}")

    return get_global_workspace_path()


def validate_session_workspace_path(path: str) -> Path:
    """校验会话自定义工作空间：必须是已存在的绝对目录，不自动创建。"""
    normalized = str(path or "").strip()
    if not normalized:
        raise ValueError("工作空间路径不能为空")

    candidate = Path(normalized).expanduser()
    if not candidate.is_absolute():
        raise ValueError("工作空间路径必须是绝对路径")

    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValueError(f"目录不存在: {candidate}") from exc
    except OSError as exc:
        raise ValueError(f"目录不可访问: {candidate} ({exc})") from exc

    if not resolved.is_dir():
        raise ValueError(f"路径不是目录: {resolved}")

    if not os.access(resolved, os.R_OK | os.W_OK | os.X_OK):
        raise ValueError(f"目录不可读写: {resolved}")

    return resolved
