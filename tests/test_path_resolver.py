"""统一路径解析（_path_resolver.resolve_path）与跨工具链路回归测试。

背景：screenshot 等工具产出的路径相对于 workspace（工作空间），而 send_media
此前用裸 ``Path(path)`` 按进程 CWD 解析相对路径——进程 CWD 与 workspace 不是
同一目录，导致「截图后把返回路径交给发送工具」这类多步任务在文件查找一步
直接失败。resolve_path 统一了基准：

1. 绝对路径：原样返回；
2. 相对路径：按当前生效的工作空间（WorkspaceManager 单例）解析；
3. 运行期热切换工作空间后，所有工具的解析立即跟随，无需重建实例；
4. 工作空间不可用时兜底进程 CWD，不抛异常。

运行无需数据库与外部环境变量。
"""
from pathlib import Path

import pytest

from backend.modules.tools._path_resolver import resolve_path
from backend.modules.tools.send_media import SendMediaTool
from backend.modules.workspace import manager as workspace_manager_module


@pytest.fixture
def workspace(tmp_path):
    """把全局工作空间指向临时目录，测试结束后恢复原值。"""
    manager = workspace_manager_module.workspace_manager
    original = manager._workspace_path
    ws = tmp_path / "ws"
    ws.mkdir()
    manager._workspace_path = ws
    try:
        yield ws
    finally:
        manager._workspace_path = original


def test_absolute_path_returned_as_is(workspace):
    """绝对路径原样返回（不拼接工作空间）。"""
    target = workspace / "sub" / "file.txt"
    assert resolve_path(str(target)) == target.resolve()


def test_relative_path_resolved_against_workspace(workspace):
    """相对路径按当前工作空间解析，而不是进程 CWD。"""
    resolved = resolve_path("screenshots/desktop_20260917_120000.png")
    assert resolved == (workspace / "screenshots" / "desktop_20260917_120000.png").resolve()


def test_workspace_hot_switch_is_followed(workspace, tmp_path):
    """工作空间热切换后，解析立即跟随新路径，无需重建工具实例。"""
    assert resolve_path("a.txt") == (workspace / "a.txt").resolve()

    new_ws = tmp_path / "ws2"
    new_ws.mkdir()
    workspace_manager_module.workspace_manager._workspace_path = new_ws

    assert resolve_path("a.txt") == (new_ws / "a.txt").resolve()


def test_fallback_to_cwd_when_workspace_unavailable(workspace, monkeypatch):
    """工作空间单例不可用时兜底进程 CWD，不抛异常。"""

    class _BrokenWorkspaceManager:
        @property
        def workspace_path(self):
            raise RuntimeError("workspace not ready")

    # resolve_path 从包级导入 workspace_manager，需补丁包属性
    import backend.modules.workspace as workspace_package

    monkeypatch.setattr(workspace_package, "workspace_manager", _BrokenWorkspaceManager())
    assert resolve_path("a.txt") == (Path.cwd() / "a.txt").resolve()


# ---------------------------------------------------------------------------
# 跨工具链路回归：截图（产出相对路径）→ send_media（按 workspace 解析）
# ---------------------------------------------------------------------------

def test_send_media_resolves_screenshot_relative_path(workspace):
    """截图返回的相对路径应能被 send_media 解析到真实文件。

    这是修复的核心场景：文件实际保存在 workspace 下，而进程 CWD 下并不存在
    该文件——旧实现（裸 ``Path(path)`` 按 CWD 解析）会判定「不存在」并中断任务。
    """
    shot = workspace / "screenshots" / "desktop_20260917_235959.png"
    shot.parent.mkdir(parents=True, exist_ok=True)
    shot.write_bytes(b"\x89PNG fake")

    # 模拟进程 CWD 与 workspace 不同目录（workspace 在 pytest 的 tmp_path 下）
    assert not (Path.cwd() / "screenshots" / "desktop_20260917_235959.png").exists()

    # 旧实现按 CWD 解析时找不到文件；新实现按工作空间解析成功
    tool = SendMediaTool()  # 不传任何参数，验证构造函数向后兼容
    resolved = tool._resolve_file_path("screenshots/desktop_20260917_235959.png")
    assert resolved.exists()
    assert resolved == shot


def test_send_media_absolute_path_untouched(workspace):
    """绝对路径调用方式保持既有行为：原样使用，不拼接工作空间。"""
    target = workspace / "data.txt"
    target.write_text("hello", encoding="utf-8")

    tool = SendMediaTool(workspace=workspace)
    assert tool._resolve_file_path(str(target)) == target
