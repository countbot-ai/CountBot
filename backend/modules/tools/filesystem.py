"""文件系统工具 - 支持行号显示、行范围读取、追加写入、按行编辑"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from backend.modules.tools.base import Tool
from backend.modules.tools.path_lock import path_write_lock
from backend.modules.tools.execution import (
    ErrorCategory,
    ExecutionState,
    RetrySafety,
    SideEffectState,
    ToolResult,
)


def _read_success(text: str) -> ToolResult:
    return ToolResult.success(
        text,
        retry_safety=RetrySafety.SAFE,
        side_effect_state=SideEffectState.NOT_APPLICABLE,
    )


def _read_failure(category: ErrorCategory, text: str) -> ToolResult:
    return ToolResult.failure(
        category,
        text,
        retry_safety=RetrySafety.SAFE,
        side_effect_state=SideEffectState.NOT_APPLICABLE,
    )


class WorkspaceValidator:
    """工作空间验证器 - 确保文件操作在工作空间内"""

    def __init__(self, workspace: Optional[Path] = None, restrict_to_workspace: Optional[bool] = None):
        # 显式传入的取值优先于配置：否则构造参数会被运行期配置静默覆盖，
        # 调用方（含测试）无法把工具限定到指定目录。未传入时跟随配置热切换。
        self._workspace = workspace.resolve() if workspace is not None else None
        self._restrict_to_workspace = restrict_to_workspace
        logger.debug(f"WorkspaceValidator initialized with workspace: {self.workspace}")

    @property
    def workspace(self) -> Path:
        if self._workspace is not None:
            return self._workspace
        try:
            from backend.modules.config.loader import config_loader
            workspace_path = config_loader.config.workspace.path
            if workspace_path:
                return Path(workspace_path).resolve()
        except Exception:
            pass
        return Path.cwd()

    @property
    def restrict_to_workspace(self) -> bool:
        if self._restrict_to_workspace is not None:
            return self._restrict_to_workspace
        try:
            from backend.modules.config.loader import config_loader
            return config_loader.config.security.restrict_to_workspace
        except Exception:
            return True

    def validate_path(self, path: str) -> Path:
        current_workspace = self.workspace
        if Path(path).is_absolute():
            resolved = Path(path).resolve()
        else:
            resolved = (current_workspace / path).resolve()
        if not self.restrict_to_workspace:
            return resolved
        try:
            resolved.relative_to(current_workspace)
        except ValueError:
            error_msg = f"Path '{path}' is outside workspace '{current_workspace}'"
            logger.error(error_msg)
            raise ValueError(error_msg)
        return resolved


class ReadFileTool(Tool):
    """读取文件工具 - 支持行号显示和按行范围读取"""

    # 单次读取上限：行数与字符数先到者生效。未设上限时一次读取超大文件会把
    # 整份内容塞进上下文，直接耗尽模型窗口。
    MAX_LINES = 2000
    MAX_CHARS = 50000

    def __init__(
        self,
        workspace: Path,
        skills_loader=None,
        restrict_to_workspace: bool = True,
        max_lines: Optional[int] = None,
        max_chars: Optional[int] = None,
    ):
        self.validator = WorkspaceValidator(workspace, restrict_to_workspace)
        self.skills_loader = skills_loader
        self.max_lines = max_lines if max_lines is not None else self.MAX_LINES
        self.max_chars = max_chars if max_chars is not None else self.MAX_CHARS
        logger.debug("ReadFileTool initialized")

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return (
            "Read one file or many files. Single-file mode supports optional 1-based "
            f"line ranges. Output is capped at {self.max_lines} lines or "
            f"{self.max_chars // 1000}KB; use start_line/end_line to continue."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Single file path.",
                },
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Multiple file paths.",
                },
                "start_line": {
                    "type": "integer",
                    "description": "1-based start line.",
                },
                "end_line": {
                    "type": "integer",
                    "description": "1-based end line.",
                },
                "show_line_numbers": {
                    "type": "boolean",
                    "description": "Show line numbers.",
                },
            },
            "oneOf": [
                {"required": ["path"]},
                {"required": ["paths"]}
            ],
        }

    async def execute_outcome(self, **kwargs: Any) -> ToolResult:
        path_str = kwargs.get("path")
        paths_list = kwargs.get("paths")
        start_line = kwargs.get("start_line")
        end_line = kwargs.get("end_line")
        show_line_numbers = kwargs.get("show_line_numbers", True)

        if not path_str and not paths_list:
            return _read_failure(ErrorCategory.VALIDATION, "Error: Either 'path' or 'paths' parameter is required")
        if path_str and paths_list:
            return _read_failure(ErrorCategory.VALIDATION, "Error: Provide either 'path' or 'paths', not both")
        if paths_list:
            if not isinstance(paths_list, list):
                return _read_failure(ErrorCategory.VALIDATION, "Error: 'paths' must be an array of strings")
            if not paths_list:
                return _read_failure(ErrorCategory.VALIDATION, "Error: 'paths' array is empty")
            if start_line is not None or end_line is not None:
                return _read_failure(
                    ErrorCategory.VALIDATION,
                    "Error: Line range parameters (start_line/end_line) are not supported in batch mode",
                )
            return await self._read_multiple_files_outcome(paths_list, show_line_numbers)
        return await self._read_single_file_outcome(path_str, start_line, end_line, show_line_numbers)

    async def _read_single_file_outcome(
        self,
        path_str: str,
        start_line: Optional[int],
        end_line: Optional[int],
        show_line_numbers: bool,
    ) -> ToolResult:
        if not path_str:
            return _read_failure(ErrorCategory.VALIDATION, "Error: Path parameter is required")
        try:
            if self.skills_loader:
                check_path = Path(path_str)
                check_path = (
                    (self.validator.workspace / check_path).resolve()
                    if not check_path.is_absolute()
                    else check_path.resolve()
                )
                if check_path.name == "SKILL.md":
                    skill = self.skills_loader.get_skill(check_path.parent.name)
                    if skill and not skill.enabled:
                        return _read_failure(
                            ErrorCategory.PERMISSION,
                            f"Error: Skill '{check_path.parent.name}' is disabled. Enable it first.",
                        )
            file_path = self.validator.validate_path(path_str)
            if not file_path.exists():
                return _read_failure(
                    ErrorCategory.VALIDATION,
                    f"Error: File not found: {path_str}. Next: run list_dir to see existing files.",
                )
            if not file_path.is_file():
                return _read_failure(ErrorCategory.VALIDATION, f"Error: Not a file: {path_str}")
            content = self._read_text_content(file_path, path_str)
            lines = content.splitlines()
            total = len(lines)
            start = max(1, int(start_line)) if start_line is not None else 1
            end = min(total, int(end_line)) if end_line is not None else total
            if start > total:
                return _read_failure(ErrorCategory.VALIDATION, f"Error: start_line ({start}) exceeds total lines ({total})")
            if start > end:
                return _read_failure(ErrorCategory.VALIDATION, f"Error: start_line ({start}) > end_line ({end})")

            # 未显式指定范围时套用默认窗口；显式范围仍受同一上限约束，
            # 避免调用方传入超大区间绕过保护。
            requested_end = end
            clipped_by_lines = False
            if end - start + 1 > self.max_lines:
                end = start + self.max_lines - 1
                clipped_by_lines = True

            output_lines, clipped_by_chars = self._clip_by_chars(
                lines[start - 1:end],
            )

            if show_line_numbers:
                width = len(str(end))
                rendered = [
                    f"{start + i:>{width}}| {line}" for i, line in enumerate(output_lines)
                ]
            else:
                rendered = list(output_lines)

            header = f"[File: {path_str} | Lines: {total}"
            if start != 1 or end != total:
                header += f" | Showing: {start}-{end}"
            header += "]"

            body = header + "\n" + "\n".join(rendered)

            # 有剩余内容时给出可直接执行的续读参数，避免模型自行猜测行号。
            # 仅因单行超长被字符预算裁切时不存在「下一行」，给行号提示会误导模型。
            next_start = start + len(output_lines)
            has_remaining_lines = next_start <= min(requested_end, total)
            if clipped_by_lines or (clipped_by_chars and has_remaining_lines) or end < requested_end:
                body += (
                    f"\n\n[Showing lines {start}-{next_start - 1} of {total}. "
                    f"Use start_line={next_start} to continue.]"
                )
            if clipped_by_chars:
                body += (
                    f"\n[Output truncated at {self.max_chars} characters. "
                    "Read a narrower line range if you need the remainder.]"
                )
            return _read_success(body)
        except PermissionError as exc:
            return _read_failure(ErrorCategory.PERMISSION, f"Error: {exc}")
        except ValueError as exc:
            return _read_failure(ErrorCategory.VALIDATION, f"Error: {exc}")
        except Exception as exc:
            return _read_failure(ErrorCategory.EXECUTION, f"Error reading file: {exc}")

    def _clip_by_chars(self, lines: List[str]) -> tuple:
        """按字符预算截断行窗口。

        行数与字符数是两个独立预算：压缩过的单行长文本可能行数很少但体积很大。
        返回裁剪后的行与是否因字符数被截断。
        """
        budget = self.max_chars
        kept: List[str] = []
        used = 0
        for line in lines:
            cost = len(line) + 1
            if kept and used + cost > budget:
                return kept, True
            if not kept and cost > budget:
                # 首行本身就超预算：按字符硬切，保证至少返回部分内容
                return [line[:budget]], True
            kept.append(line)
            used += cost
        return kept, False

    async def _read_multiple_files_outcome(self, paths_list: List[str], show_line_numbers: bool) -> ToolResult:
        rendered: List[str] = []
        failures: List[ErrorCategory] = []
        # 单文件限额之外还需总量控制：批量读几十个文件时，逐文件限额会累加成
        # 远超窗口的体积。超出预算后剩余文件只给提示，不再展开内容。
        batch_budget = self.max_chars * 2
        used = 0
        skipped = 0
        for path_str in paths_list:
            if used >= batch_budget:
                skipped = len(paths_list) - len(rendered)
                break
            item = await self._read_single_file_outcome(path_str, None, None, show_line_numbers)
            rendered.append(item.display_text)
            used += len(item.display_text)
            if item.state is not ExecutionState.SUCCEEDED:
                failures.append(item.error_category or ErrorCategory.EXECUTION)
        summary = (
            f"\n{'=' * 60}\n[Batch Read Summary: {len(rendered) - len(failures)} succeeded, "
            f"{len(failures)} failed]\n{'=' * 60}"
        )
        if skipped:
            summary += (
                f"\n[Batch output budget reached; {skipped} file(s) not read. "
                "Read them in a separate call.]"
            )
        display_text = "\n\n".join(rendered) + summary
        if not failures:
            return _read_success(display_text)
        category = ErrorCategory.PERMISSION if ErrorCategory.PERMISSION in failures else failures[0]
        return _read_failure(category, display_text)

    @staticmethod
    def _read_text_content(file_path: Path, path_str: str) -> str:
        """读取 UTF-8 文本文件，遇到二进制内容时返回更明确的错误。"""
        data = file_path.read_bytes()
        if b"\x00" in data:
            raise ValueError(
                f"File appears to be binary and cannot be read as UTF-8 text: {path_str}"
            )

        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError(
                f"File appears to be binary or uses a non-UTF-8 encoding and cannot be read as text: {path_str}"
            ) from None


class WriteFileTool(Tool):
    """写入文件工具 - 支持覆盖和追加模式，大文件请分段追加写入"""

    def __init__(self, workspace: Path, restrict_to_workspace: bool = True):
        self.validator = WorkspaceValidator(workspace, restrict_to_workspace)
        logger.debug("WriteFileTool initialized")

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return (
            "Write text to a file. Modes: `overwrite` or `append`. "
            "For large HTML/code/text, write in small chunks and use `append` "
            "after the first chunk."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path.",
                },
                "content": {
                    "type": "string",
                    "description": (
                        "Text to write. For large HTML/code/text, keep each chunk small "
                        "(recommended <= 800 chars) and append subsequent chunks."
                    ),
                },
                "mode": {
                    "type": "string",
                    "enum": ["overwrite", "append"],
                    "description": (
                        "Write mode. Use `overwrite` for the first chunk and `append` "
                        "for later chunks."
                    ),
                },
            },
            "required": ["path", "content"],
        }

    async def execute_outcome(self, **kwargs: Any) -> ToolResult:
        path_str = kwargs.get("path", "")
        content = kwargs.get("content", "")
        mode = kwargs.get("mode", "overwrite")
        if not path_str:
            return ToolResult.failure(
                ErrorCategory.VALIDATION,
                "Error: Path parameter is required",
                retry_safety=RetrySafety.UNSAFE,
                side_effect_state=SideEffectState.NOT_ATTEMPTED,
            )
        effect_started = False
        try:
            file_path = self.validator.validate_path(path_str)
            # 追加模式是读-改-写：读与写之间若插入另一个写入者，会基于旧内容
            # 覆盖对方结果。整段串行化以避免丢失更新。
            async with path_write_lock(file_path):
                # 已存在文件的追加先读取原内容。这属于准备而非修改；读取或权限失败时，
                # 可以确定副作用尚未开始。
                existing = None
                if mode == "append" and file_path.exists():
                    existing = file_path.read_text(encoding="utf-8")
                effect_started = True
                file_path.parent.mkdir(parents=True, exist_ok=True)
                if existing is not None:
                    file_path.write_text(existing + content, encoding="utf-8")
                    display = f"Appended {len(content)} chars to {path_str} (total: {len(existing) + len(content)})"
                elif mode == "append":
                    file_path.write_text(content, encoding="utf-8")
                    display = f"Created {path_str} with {len(content)} chars (file was new)"
                else:
                    file_path.write_text(content, encoding="utf-8")
                    display = f"Wrote {len(content)} chars to {path_str}"
            return ToolResult.success(
                display,
                retry_safety=RetrySafety.UNSAFE,
                side_effect_state=SideEffectState.COMMITTED,
            )
        except PermissionError as exc:
            if not effect_started:
                return ToolResult.failure(
                    ErrorCategory.PERMISSION,
                    f"Error: {exc}",
                    retry_safety=RetrySafety.UNSAFE,
                    side_effect_state=SideEffectState.NOT_ATTEMPTED,
                )
            return ToolResult.unknown_outcome(ErrorCategory.EXECUTION, f"Error: {exc}", retry_safety=RetrySafety.UNSAFE)
        except ValueError as exc:
            if not effect_started:
                return ToolResult.failure(
                    ErrorCategory.VALIDATION,
                    f"Error: {exc}",
                    retry_safety=RetrySafety.UNSAFE,
                    side_effect_state=SideEffectState.NOT_ATTEMPTED,
                )
            return ToolResult.unknown_outcome(ErrorCategory.EXECUTION, f"Error: {exc}", retry_safety=RetrySafety.UNSAFE)
        except Exception as exc:
            if effect_started:
                return ToolResult.unknown_outcome(
                    ErrorCategory.EXECUTION,
                    f"Error writing file: {exc}",
                    retry_safety=RetrySafety.UNSAFE,
                )
            return ToolResult.failure(
                ErrorCategory.EXECUTION,
                f"Error writing file: {exc}",
                retry_safety=RetrySafety.UNSAFE,
                side_effect_state=SideEffectState.NOT_ATTEMPTED,
            )


class EditFileTool(Tool):
    """编辑文件工具 - 支持文本替换和按行号编辑"""

    def __init__(self, workspace: Path, restrict_to_workspace: bool = True):
        self.validator = WorkspaceValidator(workspace, restrict_to_workspace)
        logger.debug("EditFileTool initialized")

    @property
    def name(self) -> str:
        return "edit_file"

    @property
    def description(self) -> str:
        return "Edit a file by text replace or 1-based line range."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path.",
                },
                "old_text": {
                    "type": "string",
                    "description": "Text to replace.",
                },
                "new_text": {
                    "type": "string",
                    "description": "New text.",
                },
                "start_line": {
                    "type": "integer",
                    "description": "1-based start line.",
                },
                "end_line": {
                    "type": "integer",
                    "description": "1-based end line.",
                },
                "insert": {
                    "type": "boolean",
                    "description": "Insert before start_line.",
                },
            },
            "required": ["path"],
        }

    async def execute_outcome(self, **kwargs: Any) -> ToolResult:
        path_str = kwargs.get("path", "")
        old_text = kwargs.get("old_text")
        new_text = kwargs.get("new_text", "")
        start_line = kwargs.get("start_line")
        end_line = kwargs.get("end_line")
        insert_mode = kwargs.get("insert", False)
        if not path_str:
            return ToolResult.failure(
                ErrorCategory.VALIDATION,
                "Error: Path parameter is required",
                retry_safety=RetrySafety.UNSAFE,
                side_effect_state=SideEffectState.NOT_ATTEMPTED,
            )
        # 用可变容器把「是否已进入写入」回传给异常分支：编辑被拆到独立方法后，
        # 局部变量无法跨方法共享，而副作用是否已发生决定了失败能否重试。
        effect = {"started": False}
        try:
            file_path = self.validator.validate_path(path_str)
            # 编辑同样是读-改-写：先读全文、改完再整体覆盖写回。若不串行化，
            # 并发编辑会基于同一份旧内容各自计算，后写者覆盖前者的改动。
            async with path_write_lock(file_path):
                return self._apply_edit(
                    file_path, path_str, old_text, new_text,
                    start_line, end_line, insert_mode, effect,
                )
        except (ValueError, PermissionError) as exc:
            if effect["started"]:
                return ToolResult.unknown_outcome(ErrorCategory.EXECUTION, f"Error: {exc}", retry_safety=RetrySafety.UNSAFE)
            return ToolResult.failure(ErrorCategory.PERMISSION if isinstance(exc, PermissionError) else ErrorCategory.VALIDATION, f"Error: {exc}", retry_safety=RetrySafety.UNSAFE, side_effect_state=SideEffectState.NOT_ATTEMPTED)
        except Exception as exc:
            if effect["started"]:
                return ToolResult.unknown_outcome(ErrorCategory.EXECUTION, f"Error editing file: {exc}", retry_safety=RetrySafety.UNSAFE)
            return ToolResult.failure(ErrorCategory.EXECUTION, f"Error editing file: {exc}", retry_safety=RetrySafety.UNSAFE, side_effect_state=SideEffectState.NOT_ATTEMPTED)

    def _apply_edit(
        self,
        file_path: Path,
        path_str: str,
        old_text: Optional[str],
        new_text: str,
        start_line: Optional[int],
        end_line: Optional[int],
        insert_mode: bool,
        effect: dict,
    ) -> ToolResult:
        """在持有路径锁的前提下执行编辑。

        ``effect`` 在进入写入前被置为 True，供调用方在异常时判定副作用是否已发生。
        """
        if not file_path.exists():
            return ToolResult.failure(
                ErrorCategory.VALIDATION,
                f"Error: File not found: {path_str}. Next: run list_dir to see existing files.",
                retry_safety=RetrySafety.UNSAFE,
                side_effect_state=SideEffectState.NOT_ATTEMPTED,
            )
        content = file_path.read_text(encoding="utf-8")
        if start_line is None and old_text is None:
            return ToolResult.failure(
                ErrorCategory.VALIDATION,
                "Error: Provide 'old_text' (text mode) or 'start_line' (line mode)",
                retry_safety=RetrySafety.UNSAFE,
                side_effect_state=SideEffectState.NOT_ATTEMPTED,
            )
        if start_line is None:
            if not old_text:
                return ToolResult.failure(ErrorCategory.VALIDATION, "Error: old_text is required for text replace mode", retry_safety=RetrySafety.UNSAFE, side_effect_state=SideEffectState.NOT_ATTEMPTED)
            if old_text not in content:
                return ToolResult.failure(ErrorCategory.VALIDATION, f"Error: old_text not found in file ({len(content.splitlines())} lines, {len(content)} chars). Use read_file to check exact content.", retry_safety=RetrySafety.UNSAFE, side_effect_state=SideEffectState.NOT_ATTEMPTED)
            count = content.count(old_text)
            if count > 1:
                return ToolResult.failure(ErrorCategory.VALIDATION, f"Warning: old_text found {count} times. Add more context to make it unique.", retry_safety=RetrySafety.UNSAFE, side_effect_state=SideEffectState.NOT_ATTEMPTED)
            effect["started"] = True
            file_path.write_text(content.replace(old_text, new_text, 1), encoding="utf-8")
            return ToolResult.success(f"Edited {path_str} (replaced 1 occurrence)", retry_safety=RetrySafety.UNSAFE, side_effect_state=SideEffectState.COMMITTED)

        lines = content.splitlines(keepends=True)
        total = len(lines)
        start = int(start_line)
        end = int(end_line) if end_line is not None else start
        if start < 1 or start > total + 1:
            return ToolResult.failure(ErrorCategory.VALIDATION, f"Error: start_line ({start}) out of range (1-{total})", retry_safety=RetrySafety.UNSAFE, side_effect_state=SideEffectState.NOT_ATTEMPTED)
        if not insert_mode and end < start:
            return ToolResult.failure(ErrorCategory.VALIDATION, f"Error: end_line ({end}) < start_line ({start})", retry_safety=RetrySafety.UNSAFE, side_effect_state=SideEffectState.NOT_ATTEMPTED)
        if not insert_mode and end > total:
            return ToolResult.failure(ErrorCategory.VALIDATION, f"Error: end_line ({end}) exceeds total lines ({total})", retry_safety=RetrySafety.UNSAFE, side_effect_state=SideEffectState.NOT_ATTEMPTED)

        new_lines = new_text.splitlines(keepends=True) if new_text else []
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] += "\n"
        if insert_mode:
            result = lines[: start - 1] + new_lines + lines[start - 1 :]
            display = f"Inserted {len(new_lines)} lines before line {start} in {path_str}"
        else:
            result = lines[: start - 1] + new_lines + lines[end:]
            action = f"Deleted lines {start}-{end}" if not new_text else f"Replaced lines {start}-{end} with {len(new_lines)} lines"
            display = f"Edited {path_str}: {action}"
        effect["started"] = True
        file_path.write_text("".join(result), encoding="utf-8")
        return ToolResult.success(display, retry_safety=RetrySafety.UNSAFE, side_effect_state=SideEffectState.COMMITTED)

class ListDirTool(Tool):
    """列出目录工具"""

    def __init__(self, workspace: Path, restrict_to_workspace: bool = True):
        self.validator = WorkspaceValidator(workspace, restrict_to_workspace)
        logger.debug("ListDirTool initialized")

    @property
    def name(self) -> str:
        return "list_dir"

    @property
    def description(self) -> str:
        return "List files and subdirectories in a directory."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path.",
                    "default": ".",
                },
            },
        }

    async def execute_outcome(self, **kwargs: Any) -> ToolResult:
        path_str = kwargs.get("path", ".")
        try:
            dir_path = self.validator.validate_path(path_str)
            if not dir_path.exists():
                return _read_failure(ErrorCategory.VALIDATION, f"Directory not found: {path_str}")
            if not dir_path.is_dir():
                return _read_failure(ErrorCategory.VALIDATION, f"Not a directory: {path_str}")
            items = []
            for item in sorted(dir_path.iterdir()):
                item_type = "dir" if item.is_dir() else "file"
                size = item.stat().st_size if item.is_file() else 0
                items.append(f"{item_type:4} {item.name:40} {size:>10} bytes")
            return _read_success(f"Contents of {path_str}:\n" + "\n".join(items))
        except PermissionError as exc:
            return _read_failure(ErrorCategory.PERMISSION, f"Failed to list directory '{path_str}': {exc}")
        except ValueError as exc:
            return _read_failure(ErrorCategory.VALIDATION, f"Failed to list directory '{path_str}': {exc}")
        except Exception as exc:
            return _read_failure(ErrorCategory.EXECUTION, f"Unexpected error listing directory '{path_str}': {exc}")
