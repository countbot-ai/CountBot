"""文件系统工具 - 支持行号显示、行范围读取、追加写入、按行编辑"""

from pathlib import Path
from typing import Any

from loguru import logger

from backend.modules.tools.base import Tool


class WorkspaceValidator:
    """工作空间验证器 - 确保文件操作在工作空间内"""

    def __init__(self, workspace: Path, restrict_to_workspace: bool = True):
        self._workspace = workspace.resolve()
        self._restrict_to_workspace = restrict_to_workspace
        logger.debug(f"WorkspaceValidator initialized with workspace: {self._workspace}")

    @property
    def workspace(self) -> Path:
        try:
            from backend.modules.config.loader import config_loader
            workspace_path = config_loader.config.workspace.path
            if workspace_path:
                return Path(workspace_path).resolve()
        except Exception:
            pass
        return self._workspace

    @property
    def restrict_to_workspace(self) -> bool:
        try:
            from backend.modules.config.loader import config_loader
            return config_loader.config.security.restrict_to_workspace
        except Exception:
            return self._restrict_to_workspace

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

    def __init__(self, workspace: Path, skills_loader=None, restrict_to_workspace: bool = True):
        self.validator = WorkspaceValidator(workspace, restrict_to_workspace)
        self.skills_loader = skills_loader
        logger.debug("ReadFileTool initialized")

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return (
            "Read file contents with line numbers. "
            "Supports reading specific line ranges with start_line/end_line (1-based, inclusive). "
            "Examples: read full file → read_file(path='a.py'); "
            "read lines 10-20 → read_file(path='a.py', start_line=10, end_line=20); "
            "read from line 50 → read_file(path='a.py', start_line=50)"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file (relative to workspace or absolute)",
                },
                "start_line": {
                    "type": "integer",
                    "description": "Start line number (1-based, inclusive). Omit to start from beginning.",
                },
                "end_line": {
                    "type": "integer",
                    "description": "End line number (1-based, inclusive). Omit to read to end.",
                },
                "show_line_numbers": {
                    "type": "boolean",
                    "description": "Show line numbers in output (default: true)",
                },
            },
            "required": ["path"],
        }

    async def execute(self, **kwargs: Any) -> str:
        path_str = kwargs.get("path", "")
        start_line = kwargs.get("start_line")
        end_line = kwargs.get("end_line")
        show_line_numbers = kwargs.get("show_line_numbers", True)

        if not path_str:
            return "Error: Path parameter is required"

        try:
            # 禁用技能检查
            if self.skills_loader:
                file_path_check = Path(path_str)
                if not file_path_check.is_absolute():
                    file_path_check = (self.validator.workspace / path_str).resolve()
                else:
                    file_path_check = file_path_check.resolve()
                if file_path_check.name == "SKILL.md":
                    skill_name = file_path_check.parent.name
                    skill = self.skills_loader.get_skill(skill_name)
                    if skill and not skill.enabled:
                        logger.warning(f"Blocked read of disabled skill: {skill_name}")
                        return f"Error: Skill '{skill_name}' is disabled. Enable it first."

            file_path = self.validator.validate_path(path_str)
            if not file_path.exists():
                return f"Error: File not found: {path_str}"
            if not file_path.is_file():
                return f"Error: Not a file: {path_str}"

            content = file_path.read_text(encoding="utf-8")
            lines = content.splitlines()
            total = len(lines)

            # 解析行范围
            s = max(1, int(start_line)) if start_line is not None else 1
            e = min(total, int(end_line)) if end_line is not None else total

            if s > total:
                return f"Error: start_line ({s}) exceeds total lines ({total})"
            if s > e:
                return f"Error: start_line ({s}) > end_line ({e})"

            selected = lines[s - 1:e]

            # 格式化
            if show_line_numbers:
                w = len(str(e))
                output_lines = [f"{s + i:>{w}}| {line}" for i, line in enumerate(selected)]
            else:
                output_lines = selected

            header = f"[File: {path_str} | Lines: {total}"
            if s != 1 or e != total:
                header += f" | Showing: {s}-{e}"
            header += "]"

            logger.info(f"Read file: {path_str} (lines {s}-{e} of {total})")
            return header + "\n" + "\n".join(output_lines)

        except ValueError as ve:
            logger.error(f"Failed to read file '{path_str}': {ve}")
            return f"Error: {ve}"
        except Exception as ex:
            logger.error(f"Unexpected error reading file '{path_str}': {ex}")
            return f"Error reading file: {str(ex)}"


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
            "Write content to a file. Two modes:\n"
            "- mode='overwrite' (default): create or overwrite the file\n"
            "- mode='append': append to end of file (creates if not exists)\n"
            "IMPORTANT: For large content (>2000 chars), you MUST split into multiple calls:\n"
            "  1. write_file(path='a.html', content='<first part>') → create\n"
            "  2. write_file(path='a.html', content='<second part>', mode='append')\n"
            "  3. write_file(path='a.html', content='<third part>', mode='append')\n"
            "This prevents token limit truncation errors."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file (relative to workspace or absolute)",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write",
                },
                "mode": {
                    "type": "string",
                    "enum": ["overwrite", "append"],
                    "description": "Write mode: 'overwrite' (default) or 'append'",
                },
            },
            "required": ["path", "content"],
        }

    async def execute(self, **kwargs: Any) -> str:
        path_str = kwargs.get("path", "")
        content = kwargs.get("content", "")
        mode = kwargs.get("mode", "overwrite")

        if not path_str:
            return "Error: Path parameter is required"

        try:
            file_path = self.validator.validate_path(path_str)
            file_path.parent.mkdir(parents=True, exist_ok=True)

            if mode == "append":
                if file_path.exists():
                    existing = file_path.read_text(encoding="utf-8")
                    file_path.write_text(existing + content, encoding="utf-8")
                    total = len(existing) + len(content)
                    logger.info(f"Appended to file: {path_str} (+{len(content)} chars, total: {total})")
                    return f"Appended {len(content)} chars to {path_str} (total: {total})"
                else:
                    file_path.write_text(content, encoding="utf-8")
                    logger.info(f"Created file (append, new): {path_str} ({len(content)} chars)")
                    return f"Created {path_str} with {len(content)} chars (file was new)"
            else:
                file_path.write_text(content, encoding="utf-8")
                logger.info(f"Wrote file: {path_str} ({len(content)} chars)")
                return f"Wrote {len(content)} chars to {path_str}"

        except ValueError as ve:
            logger.error(f"Failed to write file '{path_str}': {ve}")
            return f"Error: {ve}"
        except Exception as ex:
            logger.error(f"Unexpected error writing file '{path_str}': {ex}")
            return f"Error writing file: {str(ex)}"


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
        return (
            "Edit a file. Two modes:\n"
            "1. Text replace: edit_file(path, old_text='X', new_text='Y')\n"
            "2. Line edit (use read_file to see line numbers first):\n"
            "   - Replace lines: edit_file(path, start_line=5, end_line=8, new_text='...')\n"
            "   - Insert before line: edit_file(path, start_line=5, new_text='...', insert=true)\n"
            "   - Delete lines: edit_file(path, start_line=5, end_line=8, new_text='')"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to edit",
                },
                "old_text": {
                    "type": "string",
                    "description": "Text to find and replace (text replace mode)",
                },
                "new_text": {
                    "type": "string",
                    "description": "Replacement text (both modes)",
                },
                "start_line": {
                    "type": "integer",
                    "description": "Start line number (1-based, line edit mode)",
                },
                "end_line": {
                    "type": "integer",
                    "description": "End line number (1-based, defaults to start_line)",
                },
                "insert": {
                    "type": "boolean",
                    "description": "Insert before start_line instead of replacing (default: false)",
                },
            },
            "required": ["path"],
        }

    async def execute(self, **kwargs: Any) -> str:
        path_str = kwargs.get("path", "")
        old_text = kwargs.get("old_text")
        new_text = kwargs.get("new_text", "")
        start_line = kwargs.get("start_line")
        end_line = kwargs.get("end_line")
        insert_mode = kwargs.get("insert", False)

        if not path_str:
            return "Error: Path parameter is required"

        try:
            file_path = self.validator.validate_path(path_str)
            if not file_path.exists():
                return f"Error: File not found: {path_str}"

            content = file_path.read_text(encoding="utf-8")

            if start_line is not None:
                return self._edit_by_lines(
                    file_path, path_str, content,
                    int(start_line),
                    int(end_line) if end_line is not None else None,
                    new_text, insert_mode
                )
            elif old_text is not None:
                return self._edit_by_text(file_path, path_str, content, old_text, new_text)
            else:
                return "Error: Provide 'old_text' (text mode) or 'start_line' (line mode)"

        except ValueError as ve:
            logger.error(f"Failed to edit file '{path_str}': {ve}")
            return f"Error: {ve}"
        except Exception as ex:
            logger.error(f"Unexpected error editing file '{path_str}': {ex}")
            return f"Error editing file: {str(ex)}"

    def _edit_by_text(self, file_path: Path, path_str: str, content: str,
                      old_text: str, new_text: str) -> str:
        if not old_text:
            return "Error: old_text is required for text replace mode"
        if old_text not in content:
            total = len(content.splitlines())
            return (
                f"Error: old_text not found in file ({total} lines, {len(content)} chars). "
                f"Use read_file to check exact content."
            )
        count = content.count(old_text)
        if count > 1:
            return f"Warning: old_text found {count} times. Add more context to make it unique."

        new_content = content.replace(old_text, new_text, 1)
        file_path.write_text(new_content, encoding="utf-8")
        logger.info(f"Edited file (text replace): {path_str}")
        return f"Edited {path_str} (replaced 1 occurrence)"

    def _edit_by_lines(self, file_path: Path, path_str: str, content: str,
                       start_line: int, end_line: int | None,
                       new_text: str, insert_mode: bool) -> str:
        lines = content.splitlines(keepends=True)
        total = len(lines)

        if start_line < 1 or start_line > total + 1:
            return f"Error: start_line ({start_line}) out of range (1-{total})"

        if insert_mode:
            new_lines = new_text.splitlines(keepends=True)
            if new_lines and not new_lines[-1].endswith("\n"):
                new_lines[-1] += "\n"
            idx = start_line - 1
            result = lines[:idx] + new_lines + lines[idx:]
            file_path.write_text("".join(result), encoding="utf-8")
            logger.info(f"Inserted {len(new_lines)} lines before line {start_line}: {path_str}")
            return f"Inserted {len(new_lines)} lines before line {start_line} in {path_str}"

        if end_line is None:
            end_line = start_line
        if end_line < start_line:
            return f"Error: end_line ({end_line}) < start_line ({start_line})"
        if end_line > total:
            return f"Error: end_line ({end_line}) exceeds total lines ({total})"

        if new_text:
            new_lines = new_text.splitlines(keepends=True)
            if new_lines and not new_lines[-1].endswith("\n"):
                new_lines[-1] += "\n"
        else:
            new_lines = []

        result = lines[:start_line - 1] + new_lines + lines[end_line:]
        file_path.write_text("".join(result), encoding="utf-8")

        if not new_text:
            action = f"Deleted lines {start_line}-{end_line}"
        else:
            action = f"Replaced lines {start_line}-{end_line} with {len(new_lines)} lines"
        logger.info(f"Line edit: {path_str} - {action}")
        return f"Edited {path_str}: {action}"


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
        return "List contents of a directory. Returns files and subdirectories with sizes."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path (relative or absolute). Use '.' for workspace root.",
                    "default": ".",
                },
            },
        }

    async def execute(self, **kwargs: Any) -> str:
        path_str = kwargs.get("path", ".")
        try:
            dir_path = self.validator.validate_path(path_str)
            if not dir_path.exists():
                raise FileNotFoundError(f"Directory not found: {path_str}")
            if not dir_path.is_dir():
                raise ValueError(f"Not a directory: {path_str}")

            items = []
            for item in sorted(dir_path.iterdir()):
                item_type = "dir" if item.is_dir() else "file"
                size = item.stat().st_size if item.is_file() else 0
                items.append(f"{item_type:4} {item.name:40} {size:>10} bytes")

            result = f"Contents of {path_str}:\n" + "\n".join(items)
            logger.info(f"Listed directory: {path_str} ({len(items)} items)")
            return result

        except (ValueError, FileNotFoundError) as e:
            logger.error(f"Failed to list directory '{path_str}': {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error listing directory '{path_str}': {e}")
            raise
