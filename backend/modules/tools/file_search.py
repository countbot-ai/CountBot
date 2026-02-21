"""文件搜索工具

跨平台文件搜索，支持通配符匹配、文件类型过滤和递归深度控制。
"""

import os
import fnmatch
import re
from pathlib import Path
from typing import Any
from datetime import datetime

from loguru import logger

from backend.modules.tools.base import Tool


class FileSearchTool(Tool):
    """文件搜索工具

    在指定目录中搜索文件，支持：
    - 文件名匹配（支持通配符）
    - 文件类型过滤
    - 递归深度控制
    """

    def __init__(self, default_max_results: int = 20):
        """
        初始化文件搜索工具
        
        Args:
            default_max_results: 默认最大返回结果数量
        """
        self.default_max_results = default_max_results
        logger.debug(f"FileSearchTool initialized (default_max_results: {default_max_results})")

    @property
    def name(self) -> str:
        return "file_search"

    @property
    def description(self) -> str:
        return "Search files with wildcards (*.txt, *.pdf)"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Search directory",
                },
                "pattern": {
                    "type": "string",
                    "description": "Pattern (* = any, ? = one)",
                    "default": "*",
                },
                "type": {
                    "type": "string",
                    "description": "Type filter",
                    "enum": ["file", "dir", "all"],
                    "default": "all",
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Depth (-1 = unlimited)",
                    "default": -1,
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (1-100)",
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
            # 验证搜索路径
            search_dir = Path(search_path).resolve()
            if not search_dir.exists():
                return f"Error: Path does not exist: {search_path}"
            
            if not search_dir.is_dir():
                return f"Error: Path is not a directory: {search_path}"

            logger.info(f"Searching files in: {search_path} with pattern: {pattern}")

            # 执行搜索
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
                
                # 只保存限制数量的结果
                if len(results) < limit:
                    results.append(result)

            # 格式化输出
            if not results:
                return f"No files found matching pattern '{pattern}' in: {search_path}"

            output_lines = [
                f"Found {len(results)} file(s) matching '{pattern}' in: {search_path}",
            ]
            
            # 如果还有更多结果，提示用户
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
        # 检查深度限制
        if max_depth >= 0 and current_depth > max_depth:
            return

        try:
            for item in directory.iterdir():
                try:
                    # 获取文件信息
                    is_dir = item.is_dir()
                    is_file = item.is_file()
                    
                    # 跳过符号链接以避免循环
                    if item.is_symlink():
                        continue

                    # 文件类型过滤
                    if file_type == "file" and not is_file:
                        continue
                    if file_type == "dir" and not is_dir:
                        continue

                    # 文件名匹配（不区分大小写）
                    item_name = item.name
                    matches = fnmatch.fnmatch(item_name.lower(), pattern.lower())

                    if matches:
                        # 获取文件大小
                        file_size = -1
                        if is_file:
                            try:
                                file_size = item.stat().st_size
                            except:
                                pass

                        # 返回匹配结果
                        yield {
                            "path": str(item),
                            "type": "DIR" if is_dir else "FILE",
                            "size": file_size,
                        }

                    # 递归搜索子目录
                    if is_dir:
                        yield from self._search_files(
                            item,
                            pattern,
                            file_type,
                            max_depth,
                            current_depth + 1,
                        )

                except (PermissionError, OSError) as e:
                    # 跳过无权限访问的文件/目录
                    logger.debug(f"Skipping {item}: {e}")
                    continue

        except (PermissionError, OSError) as e:
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
