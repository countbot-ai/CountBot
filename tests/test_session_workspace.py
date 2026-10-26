"""会话级工作空间：解析优先级、路径校验与工具路径上下文。"""

import asyncio
import types
from pathlib import Path

import pytest

from backend.modules.tools._path_resolver import resolve_path
from backend.modules.tools.execution import ToolResult
from backend.modules.tools.registry import ToolRegistry
from backend.modules.workspace import (
    resolve_session_workspace,
    validate_session_workspace_path,
)
from backend.modules.workspace import manager as workspace_manager_module


class _PathProbeTool:
    name = "path_probe"
    description = "probe resolve_path against the active workspace"

    @property
    def parameters(self):
        return {"type": "object", "properties": {}, "required": []}

    def validate_params(self, arguments):
        return []

    async def execute_outcome(self, **kwargs):
        return ToolResult.success(str(resolve_path("nested/file.txt")))

    async def execute(self, **kwargs):
        return str(resolve_path("nested/file.txt"))


def test_session_workspace_prefers_custom_path(tmp_path: Path):
    session = types.SimpleNamespace(workspace_path=str(tmp_path))
    assert resolve_session_workspace(session) == tmp_path.resolve()


def test_session_workspace_falls_back_to_global_when_missing(
    tmp_path: Path,
    monkeypatch,
):
    global_workspace = tmp_path / "global"
    global_workspace.mkdir()
    monkeypatch.setattr(
        workspace_manager_module,
        "get_global_workspace_path",
        lambda: global_workspace,
    )

    session = types.SimpleNamespace(workspace_path=str(tmp_path / "removed"))
    assert resolve_session_workspace(session) == global_workspace.resolve()


def test_validate_session_workspace_rejects_invalid_paths(tmp_path: Path):
    with pytest.raises(ValueError, match="绝对路径"):
        validate_session_workspace_path("relative/dir")

    with pytest.raises(ValueError, match="目录不存在"):
        validate_session_workspace_path(str(tmp_path / "missing"))

    file_path = tmp_path / "file.txt"
    file_path.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="不是目录"):
        validate_session_workspace_path(str(file_path))


def test_tool_registry_workspace_context_affects_resolve_path(tmp_path: Path):
    registry = ToolRegistry(workspace=tmp_path)
    registry.register(_PathProbeTool())

    outcome = asyncio.run(registry.execute_outcome("path_probe", {}))

    assert outcome.display_text == str((tmp_path / "nested" / "file.txt").resolve())
