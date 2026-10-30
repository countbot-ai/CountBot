"""exec 输出截断落盘测试

验证超长输出被截断时，完整内容会写入当前工作区的 temp 目录并在结果中给出路径，
保证模型不会因为截断而彻底看不到尾部内容。

注意：ExecTool.workspace 是跟随运行配置热切换的只读属性，不是构造参数快照，
因此测试里需要读取 tool.workspace 来定位产出文件，而不是使用传入的临时目录。
"""

import sys
from pathlib import Path

import pytest

from backend.modules.tools.shell import ExecTool


def _make_tool(tmp_path: Path, max_output_length: int = 100) -> ExecTool:
    # 真正执行命令的用例要用工作区外的解释器，因此关掉路径限制；
    # 路径守卫本身有独立用例覆盖。
    return ExecTool(
        workspace=tmp_path,
        max_output_length=max_output_length,
        restrict_to_workspace=False,
    )


def _artifacts(tool: ExecTool):
    return sorted(tool.workspace.glob("temp/exec-output-*.log"))


def _clear_artifacts(tool: ExecTool) -> None:
    for path in _artifacts(tool):
        path.unlink(missing_ok=True)


def test_short_output_not_truncated(tmp_path):
    tool = _make_tool(tmp_path)
    before = set(_artifacts(tool))
    result = tool._truncate_with_artifact("short output")
    assert result == "short output"
    # 未截断时不应产生新的落盘文件
    assert set(_artifacts(tool)) == before


def test_long_output_truncated_and_persisted(tmp_path):
    tool = _make_tool(tmp_path, max_output_length=50)
    _clear_artifacts(tool)
    content = "x" * 200

    result = tool._truncate_with_artifact(content, command="echo hi")

    # 返回文本包含截断提示与文件路径
    assert "中间省略" in result
    assert "完整输出已保存到:" in result
    assert "read_file" in result

    saved = _artifacts(tool)
    assert len(saved) == 1
    written = saved[0].read_text(encoding="utf-8")
    # 完整内容必须落盘，包含命令头信息
    assert content in written
    assert "# command: echo hi" in written


def test_truncated_text_keeps_head_and_tail(tmp_path):
    """截断后同时保留开头与结尾：失败原因通常在末尾，开头提示也有价值。"""
    tool = _make_tool(tmp_path, max_output_length=100)
    content = "HEAD_MARK" + ("y" * 5000) + "TAIL_ERROR_MARK"
    result = tool._truncate_with_artifact(content)

    assert "HEAD_MARK" in result
    # 尾部必须保留，否则模型看不到真正的报错行
    assert "TAIL_ERROR_MARK" in result
    assert "中间省略" in result


def test_artifact_write_failure_degrades_gracefully(tmp_path, monkeypatch):
    """写盘失败时应退化为普通截断，而不是抛错。"""
    tool = _make_tool(tmp_path, max_output_length=10)

    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(tool, "_write_output_artifact", _boom)
    result = tool._truncate_with_artifact("z" * 100)
    assert "中间省略" in result
    assert "完整输出已保存到" not in result


@pytest.mark.asyncio
async def test_exec_records_artifact_for_long_output(tmp_path):
    """真实执行一次产生大量输出的命令，确认落盘链路生效。"""
    tool = _make_tool(tmp_path, max_output_length=200)
    _clear_artifacts(tool)

    # 安全策略禁止内联解释器代码，改为写入脚本文件后执行；
    # 解释器路径用 sys.executable，Windows 上没有 python3 命令
    script = tool.workspace / "emit_long_output.py"
    script.write_text("print('line' * 500)\n", encoding="utf-8")

    try:
        outcome = await tool.execute_outcome(
            command=f'"{sys.executable}" "{script}"',
            timeout=30,
        )
        display = getattr(outcome, "display_text", str(outcome))
        assert "中间省略" in display

        saved = _artifacts(tool)
        assert saved, "expected full output artifact"
        assert len(saved[0].read_text(encoding="utf-8")) > 200
    finally:
        script.unlink(missing_ok=True)
        _clear_artifacts(tool)
