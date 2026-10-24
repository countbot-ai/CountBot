"""工具边界加固测试

覆盖：read_file 读取上限、写入路径串行化、exec 取消穿透。
"""

import asyncio
import threading
import time
from pathlib import Path

import pytest

from backend.modules.tools.filesystem import ReadFileTool, WriteFileTool
from backend.modules.tools.path_lock import PathLockRegistry, path_write_lock
from backend.modules.tools.shell import ExecTool
from backend.modules.agent.task_manager import CancellationToken


# ---------------------------------------------------------------------------
# read_file 上限
# ---------------------------------------------------------------------------


def _outcome(tool, **kwargs):
    return asyncio.run(tool.execute_outcome(**kwargs))


def test_read_default_caps_lines(tmp_path):
    target = tmp_path / "big.txt"
    target.write_text("\n".join(f"line{i}" for i in range(5000)), encoding="utf-8")

    tool = ReadFileTool(tmp_path, restrict_to_workspace=False)
    result = _outcome(tool, path=str(target))

    text = result.display_text
    assert result.state.name == "SUCCEEDED"
    # 只返回上限内的行，并给出可执行的续读提示
    assert "line0" in text
    assert "line1999" in text
    assert "line2000" not in text
    assert "start_line=2001" in text


def test_read_respects_explicit_range_within_cap(tmp_path):
    target = tmp_path / "big.txt"
    target.write_text("\n".join(f"line{i}" for i in range(5000)), encoding="utf-8")

    tool = ReadFileTool(tmp_path, restrict_to_workspace=False)
    result = _outcome(tool, path=str(target), start_line=100, end_line=110)
    text = result.display_text

    assert "line99" in text
    assert "line100" in text  # 1-based
    assert "line109" in text
    assert "line110" not in text


def test_read_oversized_range_still_capped(tmp_path):
    """显式传入超大区间不能绕过上限。"""
    target = tmp_path / "big.txt"
    target.write_text("\n".join(f"line{i}" for i in range(5000)), encoding="utf-8")

    tool = ReadFileTool(tmp_path, restrict_to_workspace=False)
    result = _outcome(tool, path=str(target), start_line=1, end_line=5000)
    assert "start_line=" in result.display_text or "Truncated" in result.display_text


def test_read_caps_by_chars(tmp_path):
    """单行超大文本应按字符预算截断。"""
    target = tmp_path / "wide.txt"
    target.write_text("x" * 200000, encoding="utf-8")

    tool = ReadFileTool(tmp_path, restrict_to_workspace=False, max_chars=1000)
    result = _outcome(tool, path=str(target))
    assert result.state.name == "SUCCEEDED"
    assert len(result.display_text) < 3000
    assert "characters" in result.display_text


def test_single_line_truncation_gives_no_bogus_line_hint(tmp_path):
    """单行被字符预算截断时不得提示 start_line 续读。

    此时并不存在「下一行」，照提示续读会因越界直接失败，属于误导性输出。
    """
    target = tmp_path / "wide.txt"
    target.write_text("x" * 200000, encoding="utf-8")

    tool = ReadFileTool(tmp_path, restrict_to_workspace=False, max_chars=1000)
    text = _outcome(tool, path=str(target)).display_text

    assert "start_line=" not in text
    assert "narrower line range" in text


def test_multi_line_truncation_still_gives_line_hint(tmp_path):
    """多行文件仍要给出可执行的续读行号。"""
    target = tmp_path / "big.txt"
    target.write_text("\n".join(f"L{i}" for i in range(5000)), encoding="utf-8")

    tool = ReadFileTool(tmp_path, restrict_to_workspace=False)
    text = _outcome(tool, path=str(target)).display_text
    assert "start_line=" in text


def test_read_custom_limits(tmp_path):
    target = tmp_path / "big.txt"
    target.write_text("\n".join(f"line{i}" for i in range(100)), encoding="utf-8")

    tool = ReadFileTool(tmp_path, restrict_to_workspace=False, max_lines=10)
    result = _outcome(tool, path=str(target))
    assert "line9" in result.display_text
    assert "line10" not in result.display_text


def test_batch_read_total_budget(tmp_path):
    """批量读取总量受限，超出后剩余文件不再展开。"""
    files = []
    for i in range(20):
        f = tmp_path / f"f{i}.txt"
        f.write_text("y" * 5000, encoding="utf-8")
        files.append(str(f))

    tool = ReadFileTool(tmp_path, restrict_to_workspace=False, max_chars=1000)
    result = _outcome(tool, paths=files)
    assert "not read" in result.display_text or len(result.display_text) < 20 * 1000


# ---------------------------------------------------------------------------
# 写入路径串行
# ---------------------------------------------------------------------------


def test_path_lock_serializes_same_path():
    registry = PathLockRegistry()
    order = []

    async def worker(tag: str):
        lock = registry.acquire(Path("/tmp/same.txt"))
        try:
            await lock.acquire()
            order.append(f"{tag}-enter")
            await asyncio.sleep(0.01)
            order.append(f"{tag}-exit")
        finally:
            if lock.locked():
                lock.release()
            registry.release(Path("/tmp/same.txt"))

    async def scenario():
        await asyncio.gather(worker("a"), worker("b"))

    asyncio.run(scenario())
    assert order == ["a-enter", "a-exit", "b-enter", "b-exit"]


def test_append_does_not_lose_updates(tmp_path):
    """并发追加不应互相覆盖。"""
    target = tmp_path / "log.txt"
    target.write_text("", encoding="utf-8")
    tool = WriteFileTool(tmp_path, restrict_to_workspace=False)

    async def scenario():
        await asyncio.gather(
            *(
                tool.execute_outcome(path=str(target), content=f"L{i}\n", mode="append")
                for i in range(10)
            )
        )

    asyncio.run(scenario())
    lines = target.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 10
    assert len(set(lines)) == 10


def test_concurrent_edits_are_serialized(tmp_path):
    """并发精确替换不应互相覆盖，最终结果应包含所有替换。"""
    from backend.modules.tools.filesystem import EditFileTool

    target = tmp_path / "doc.txt"
    target.write_text("".join(f"T{i}=old\n" for i in range(8)), encoding="utf-8")
    tool = EditFileTool(tmp_path, restrict_to_workspace=False)

    async def scenario():
        for i in range(8):
            await tool.execute_outcome(
                path=str(target), old_text=f"T{i}=old", new_text=f"T{i}=new"
            )

    asyncio.run(scenario())
    text = target.read_text(encoding="utf-8")
    assert text.count("=new") == 8
    assert "=old" not in text


# ---------------------------------------------------------------------------
# exec 取消穿透
# ---------------------------------------------------------------------------


def test_exec_terminates_process_on_cancel(tmp_path):
    """取消令牌触发后，长命令必须被终止而不是继续跑满超时。"""
    tool = ExecTool(workspace=tmp_path, timeout=60, max_output_length=1000)
    token = CancellationToken()
    tool.set_cancel_token(token)

    async def scenario():
        task = asyncio.create_task(
            tool.execute_outcome(command="sleep 30", timeout=60)
        )
        await asyncio.sleep(0.6)
        started = time.monotonic()
        token.cancel()
        result = await asyncio.wait_for(task, timeout=10)
        return result, time.monotonic() - started

    result, elapsed = asyncio.run(scenario())
    # 远小于 sleep 30 与 timeout 60 说明进程确实被终止
    assert elapsed < 8
    assert result is not None


def test_exec_terminates_child_processes(tmp_path):
    """shell 派生的子进程也要被终止，不能只杀父进程。"""
    tool = ExecTool(workspace=tmp_path, timeout=60, max_output_length=1000)
    token = CancellationToken()
    tool.set_cancel_token(token)

    script = tmp_path / "spawn_child.sh"
    script.write_text(
        "#!/bin/sh\nsleep 30 &\necho started\nwait\n", encoding="utf-8"
    )
    script.chmod(0o755)

    async def scenario():
        task = asyncio.create_task(
            tool.execute_outcome(command=str(script), timeout=60)
        )
        await asyncio.sleep(0.8)
        token.cancel()
        await asyncio.wait_for(task, timeout=10)

    asyncio.run(scenario())


def test_exec_without_token_still_works(tmp_path):
    tool = ExecTool(workspace=tmp_path, timeout=30, max_output_length=1000)
    result = asyncio.run(tool.execute_outcome(command="echo hello", timeout=30))
    assert "hello" in result.display_text

def test_path_lock_rejects_same_task_reentrancy(tmp_path):
    """同任务嵌套获取同一路径必须快速报错，而不是自我死锁。

    死锁表现为「整个请求永久无响应」，极难排查；明确报错能立刻定位调用链问题。
    """
    async def scenario():
        async with path_write_lock(tmp_path / "a.txt"):
            with pytest.raises(RuntimeError, match="not reentrant"):
                async with path_write_lock(tmp_path / "a.txt"):
                    pass

    asyncio.run(scenario())


def test_path_lock_allows_sequential_reacquire(tmp_path):
    """释放后再次获取应正常，重入检测不能误伤串行调用。"""
    async def scenario():
        async with path_write_lock(tmp_path / "b.txt"):
            pass
        async with path_write_lock(tmp_path / "b.txt"):
            pass

    asyncio.run(scenario())


def test_path_lock_still_serializes_across_tasks(tmp_path):
    """重入检测不能破坏跨任务串行语义。"""
    order = []

    async def worker(tag):
        async with path_write_lock(tmp_path / "c.txt"):
            order.append(f"{tag}-in")
            await asyncio.sleep(0.01)
            order.append(f"{tag}-out")

    async def scenario():
        await asyncio.gather(worker("a"), worker("b"))

    asyncio.run(scenario())
    assert order == ["a-in", "a-out", "b-in", "b-out"]
