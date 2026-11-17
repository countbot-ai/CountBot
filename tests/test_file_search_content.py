"""file_search 内容检索测试：返回 file:line:snippet 且 type=file 仍递归目录。"""

import asyncio

import pytest

from backend.modules.tools.file_search import FileSearchTool


@pytest.fixture()
def workspace(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "report.py").write_text(
        "def build():\n    total = 100\n    return total\n", encoding="utf-8"
    )
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "note.md").write_text(
        "今日充值 100 笔，这个根本不对\n另一行\n", encoding="utf-8"
    )
    (tmp_path / "blob.bin").write_bytes(b"\x00\x01binary 100\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "skip.js").write_text("const total = 100\n", encoding="utf-8")
    return tmp_path


def _search(workspace, **kwargs):
    tool = FileSearchTool(workspace)
    return asyncio.run(tool.execute(**kwargs))


def test_content_search_returns_path_line_snippet(workspace):
    out = _search(workspace, path=".", content="100")

    assert "pkg/report.py:2: total = 100" in out
    assert "docs/note.md:1:" in out
    # 二进制与 node_modules 必须被跳过
    assert "blob.bin" not in out
    assert "node_modules" not in out


def test_content_search_regex(workspace):
    out = _search(workspace, path=".", content=r"今日充值\s+\d+", regex=True)
    assert "docs/note.md:1:" in out


def test_content_search_case_insensitive_by_default(workspace):
    (workspace / "Case.txt").write_text("TOTAL VALUE\n", encoding="utf-8")
    assert "Case.txt:1:" in _search(workspace, path=".", content="total")
    assert "Case.txt" not in _search(workspace, path=".", content="total", case_sensitive=True)


def test_content_search_limit_is_reported(workspace):
    out = _search(workspace, path=".", content="100", limit=1)
    assert "more exist" in out


def test_name_search_still_recurses_with_type_file(workspace):
    """type=file 时也必须进入子目录，否则递归搜索是假的。"""
    out = _search(workspace, path=".", pattern="*.md", type="file")
    assert "note.md" in out


def test_content_search_outcome_path(workspace):
    """execute_outcome 与 execute 行为一致（工具主链路走 outcome）。"""
    tool = FileSearchTool(workspace)
    result = asyncio.run(tool.execute_outcome(path=".", content="100"))
    assert result.state.value == "SUCCEEDED"
    assert "pkg/report.py:2:" in result.display_text


def test_skip_dirs_only_apply_inside_workspace(tmp_path):
    """工作区自身放在 dist/build 之类目录下时，不能被整片跳过。"""
    root = tmp_path / "build" / "ws"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "a.py").write_text("value = 100\n", encoding="utf-8")

    out = _search(root, path=".", content="100")
    assert "pkg/a.py:1:" in out


def test_skip_dirs_still_apply_inside_workspace(workspace):
    """工作区内部的 node_modules 依然要跳过。"""
    out = _search(workspace, path=".", content="total")
    assert "node_modules" not in out
