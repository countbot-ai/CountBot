"""跨平台文件搜索：支持通配符匹配、文件类型过滤、递归深度控制与文件内容检索。"""

import os
import fnmatch
import re
from pathlib import Path
from typing import Any, Dict, Optional
from datetime import datetime

from loguru import logger

from backend.modules.tools.base import Tool
from backend.modules.tools.execution import ErrorCategory, RetrySafety, SideEffectState, ToolResult
from backend.modules.tools.filesystem import WorkspaceValidator

# 内容检索护栏：单文件上限、片段长度、重目录
MAX_CONTENT_FILE_BYTES = 2 * 1024 * 1024
CONTENT_SNIPPET_CHARS = 240
CONTENT_SKIP_DIRS = frozenset({
    ".git", ".svn", ".hg", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", ".mypy_cache", ".pytest_cache", ".next", ".cache",
})


class FileSearchTool(Tool):
    """在指定目录中按通配符搜索文件，支持类型过滤与递归深度控制。"""

    def __init__(
        self,
        workspace: Path,
        default_max_results: int = 20,
        restrict_to_workspace: bool = True,
    ):
        """
        初始化文件搜索工具
        
        Args:
            default_max_results: 默认最大返回结果数量
        """
        self.default_max_results = default_max_results
        self.validator = WorkspaceValidator(workspace, restrict_to_workspace)
        logger.debug(f"FileSearchTool initialized (default_max_results: {default_max_results})")

    @property
    def name(self) -> str:
        return "file_search"

    @property
    def description(self) -> str:
        return (
            "Search files by wildcard pattern, or search inside file contents. "
            "Pass `content` to grep contents in one call (returns `path:line: snippet`); "
            "omit it to list matching file names."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Search path.",
                },
                "pattern": {
                    "type": "string",
                    "description": "Wildcard pattern.",
                    "default": "*",
                },
                "content": {
                    "type": "string",
                    "description": (
                        "Text or regular expression to search inside file contents. "
                        "When set, `pattern` acts as the file filter."
                    ),
                },
                "regex": {
                    "type": "boolean",
                    "description": "Treat `content` as a regular expression.",
                    "default": False,
                },
                "case_sensitive": {
                    "type": "boolean",
                    "description": "Case-sensitive content matching.",
                    "default": False,
                },
                "type": {
                    "type": "string",
                    "description": "Result type.",
                    "enum": ["file", "dir", "all"],
                    "default": "all",
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Max depth.",
                    "default": -1,
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results.",
                    "minimum": 1,
                    "maximum": 100,
                    "default": 20,
                },
            },
            "required": ["path"],
        }

    async def execute(self, **kwargs: Any) -> str:
        """
        执行文件搜索
        
        Args:
            path: 搜索路径
            pattern: 文件名模式
            type: 文件类型过滤
            max_depth: 最大递归深度
            limit: 最大结果数量
            
        Returns:
            str: 搜索结果或错误信息
        """
        search_path = kwargs.get("path", "")
        pattern = kwargs.get("pattern", "*")
        file_type = kwargs.get("type", "all")
        max_depth = kwargs.get("max_depth", -1)
        limit = kwargs.get("limit", self.default_max_results)

        if not search_path:
            return "Error: path parameter is required"

        try:
            search_dir = self.validator.validate_path(search_path)
            if not search_dir.exists():
                return f"Error: Path does not exist: {search_path}"
            
            if not search_dir.is_dir():
                return f"Error: Path is not a directory: {search_path}"

            content_text = self._content_search_if_requested(
                kwargs,
                search_dir=search_dir,
                search_path=search_path,
                pattern=pattern,
                max_depth=max_depth,
                limit=limit,
            )
            if content_text is not None:
                return content_text

            logger.info(f"Searching files in: {search_path} with pattern: {pattern}")

            results = []
            total_found = 0
            
            for result in self._search_files(
                search_dir,
                pattern,
                file_type,
                max_depth,
                0,
            ):
                total_found += 1
                
                if len(results) < limit:
                    results.append(result)

            # 格式化输出
            if not results:
                return f"No files found matching pattern '{pattern}' in: {search_path}"

            output_lines = [
                f"Found {len(results)} file(s) matching '{pattern}' in: {search_path}",
            ]
            
            if total_found > len(results):
                output_lines.append(f"(Showing first {len(results)} of {total_found} results. Use 'limit' parameter to see more)")
            
            output_lines.append("")

            for item in results:
                file_path = item["path"]
                file_type_str = item["type"]
                size_str = self._format_size(item["size"]) if item["size"] >= 0 else ""
                
                if size_str:
                    output_lines.append(f"[{file_type_str}] {file_path} ({size_str})")
                else:
                    output_lines.append(f"[{file_type_str}] {file_path}")

            result_text = "\n".join(output_lines)
            logger.info(f"File search completed: {len(results)} results shown (total found: {total_found})")
            return result_text

        except PermissionError as e:
            error_msg = f"Permission denied accessing: {search_path}"
            logger.error(error_msg)
            return f"Error: {error_msg}"
        except Exception as e:
            error_msg = f"Error during file search: {str(e)}"
            logger.error(error_msg)
            return error_msg

    async def execute_outcome(self, **kwargs: Any) -> ToolResult:
        search_path = kwargs.get("path", "")
        pattern = kwargs.get("pattern", "*")
        file_type = kwargs.get("type", "all")
        max_depth = kwargs.get("max_depth", -1)
        limit = kwargs.get("limit", self.default_max_results)
        metadata = {
            "retry_safety": RetrySafety.SAFE,
            "side_effect_state": SideEffectState.NOT_APPLICABLE,
        }
        if not search_path:
            return ToolResult.failure(ErrorCategory.VALIDATION, "Error: path parameter is required", **metadata)
        try:
            search_dir = self.validator.validate_path(search_path)
            if not search_dir.exists():
                return ToolResult.failure(ErrorCategory.VALIDATION, f"Error: Path does not exist: {search_path}", **metadata)
            if not search_dir.is_dir():
                return ToolResult.failure(ErrorCategory.VALIDATION, f"Error: Path is not a directory: {search_path}", **metadata)
            content_text = None
            try:
                content_text = self._content_search_if_requested(
                    kwargs,
                    search_dir=search_dir,
                    search_path=search_path,
                    pattern=pattern,
                    max_depth=max_depth,
                    limit=limit,
                )
            except ValueError as exc:
                return ToolResult.failure(
                    ErrorCategory.VALIDATION,
                    f"Error during content search: {exc}",
                    **metadata,
                )
            if content_text is not None:
                return ToolResult.success(content_text, **metadata)
            results = []
            total_found = 0
            for result in self._search_files(search_dir, pattern, file_type, max_depth, 0):
                total_found += 1
                if len(results) < limit:
                    results.append(result)
            if not results:
                return ToolResult.success(f"No files found matching pattern '{pattern}' in: {search_path}", **metadata)
            lines = [f"Found {len(results)} file(s) matching '{pattern}' in: {search_path}"]
            if total_found > len(results):
                lines.append(f"(Showing first {len(results)} of {total_found} results. Use 'limit' parameter to see more)")
            lines.append("")
            for item in results:
                size = self._format_size(item["size"]) if item["size"] >= 0 else ""
                lines.append(f"[{item['type']}] {item['path']}" + (f" ({size})" if size else ""))
            return ToolResult.success("\n".join(lines), **metadata)
        except PermissionError as exc:
            return ToolResult.failure(ErrorCategory.PERMISSION, f"Error: Permission denied accessing: {search_path}", **metadata)
        except ValueError as exc:
            return ToolResult.failure(ErrorCategory.VALIDATION, f"Error during file search: {exc}", **metadata)
        except Exception as exc:
            return ToolResult.failure(ErrorCategory.EXECUTION, f"Error during file search: {exc}", **metadata)

    def _content_search_if_requested(
        self,
        kwargs: Dict[str, Any],
        *,
        search_dir: Path,
        search_path: str,
        pattern: str,
        max_depth: int,
        limit: int,
    ) -> Optional[str]:
        """请求了内容检索就返回结果文本，否则返回 None。两条执行链路共用。"""
        content = str(kwargs.get("content") or "").strip()
        if not content:
            return None
        return self._content_search_text(
            search_dir=search_dir,
            search_path=search_path,
            content=content,
            file_pattern=pattern,
            use_regex=bool(kwargs.get("regex")),
            case_sensitive=bool(kwargs.get("case_sensitive")),
            max_depth=max_depth,
            limit=limit,
        )

    def _content_search_text(
        self,
        *,
        search_dir: Path,
        search_path: str,
        content: str,
        file_pattern: str,
        use_regex: bool,
        case_sensitive: bool,
        max_depth: int,
        limit: int,
    ) -> str:
        """在文件内容里检索，返回 `path:line: snippet`。"""
        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            pattern = re.compile(content if use_regex else re.escape(content), flags)
        except re.error as exc:
            raise ValueError(f"invalid regular expression '{content}': {exc}") from exc

        matches = []
        matched_files = 0
        total_matches = 0
        skipped_large = 0

        for item in self._search_files(search_dir, file_pattern, "file", max_depth, 0):
            path = Path(item["path"])
            # 只看相对搜索根的路径段：绝对路径的父目录名可能叫 dist/build
            try:
                relative_parts = path.relative_to(search_dir).parts
            except ValueError:
                relative_parts = path.parts
            if any(part in CONTENT_SKIP_DIRS for part in relative_parts):
                continue
            if item.get("size", -1) > MAX_CONTENT_FILE_BYTES:
                skipped_large += 1
                continue
            try:
                raw = path.read_bytes()
            except OSError:
                continue
            # 二进制文件（含 NUL 字节）直接跳过
            if b"\x00" in raw[:4096]:
                continue

            text = raw.decode("utf-8", errors="ignore")
            file_hit = False
            overflow = False
            for lineno, line in enumerate(text.splitlines(), start=1):
                if not pattern.search(line):
                    continue
                total_matches += 1
                file_hit = True
                if len(matches) < limit:
                    snippet = line.strip()
                    if len(snippet) > CONTENT_SNIPPET_CHARS:
                        snippet = snippet[:CONTENT_SNIPPET_CHARS] + "..."
                    try:
                        shown = str(path.relative_to(search_dir))
                    except ValueError:
                        shown = str(path)
                    matches.append(f"{shown}:{lineno}: {snippet}")
                else:
                    # 已确认还有更多，不再继续扫
                    overflow = True
                    break
            if file_hit:
                matched_files += 1
            if overflow:
                break

        if not matches:
            return f'No content matches for "{content}" in: {search_path}'

        lines = [
            f'Found {len(matches)} match(es) across {matched_files} file(s) '
            f'for "{content}" in: {search_path}',
        ]
        if total_matches > len(matches):
            lines.append(
                f"(Showing first {len(matches)} matches; more exist — "
                "raise 'limit' or narrow the pattern)"
            )
        if skipped_large:
            lines.append(
                f"(Skipped {skipped_large} file(s) larger than "
                f"{MAX_CONTENT_FILE_BYTES // (1024 * 1024)}MB)"
            )
        lines.append("")
        lines.extend(matches)
        return "\n".join(lines)

    def _search_files(
        self,
        directory: Path,
        pattern: str,
        file_type: str,
        max_depth: int,
        current_depth: int,
    ):
        """
        递归搜索文件
        
        Args:
            directory: 当前搜索目录
            pattern: 文件名模式
            file_type: 文件类型过滤
            max_depth: 最大递归深度
            current_depth: 当前递归深度
            
        Yields:
            dict: 匹配的文件信息
        """
        if max_depth >= 0 and current_depth > max_depth:
            return

        try:
            for item in directory.iterdir():
                try:
                    is_dir = item.is_dir()
                    is_file = item.is_file()
                    
                    # 跳过符号链接以避免循环
                    if item.is_symlink():
                        continue

                    # 类型过滤只影响是否产出，不能拦住递归
                    type_matches = not (
                        (file_type == "file" and not is_file)
                        or (file_type == "dir" and not is_dir)
                    )

                    item_name = item.name
                    matches = fnmatch.fnmatch(item_name.lower(), pattern.lower())

                    if type_matches and matches:
                        file_size = -1
                        if is_file:
                            try:
                                file_size = item.stat().st_size
                            except:
                                pass

                        yield {
                            "path": str(item),
                            "type": "DIR" if is_dir else "FILE",
                            "size": file_size,
                        }

                    if is_dir:
                        yield from self._search_files(
                            item,
                            pattern,
                            file_type,
                            max_depth,
                            current_depth + 1,
                        )

                except (PermissionError, OSError) as e:
                    # 根目录遍历定义了本次请求的操作边界，不能静默表示为空的成功搜索。
                    if current_depth == 0:
                        raise
                    # 嵌套目录无权限不决定根目录遍历的权威结果，保持既有跳过行为。
                    logger.debug(f"Skipping {item}: {e}")
                    continue

        except (PermissionError, OSError) as e:
            if current_depth == 0:
                raise
            logger.debug(f"Cannot access directory {directory}: {e}")

    def _format_size(self, size_bytes: int) -> str:
        """
        格式化文件大小
        
        Args:
            size_bytes: 字节数
            
        Returns:
            str: 格式化的大小字符串
        """
        if size_bytes < 0:
            return "N/A"
        
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        
        return f"{size_bytes:.2f} PB"
