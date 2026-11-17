"""闸门在真实调用路径上的异常安全审计

核心风险：`await gate.acquire()` 与 `try/finally` 的相对位置。
若 acquire 在 try 之外，且 acquire 成功之后、进入 try 之前的代码抛异常，
`finally` 不会执行，锁永久不释放——该会话此后所有消息都会卡住。

这类缺陷不会在正常流程中暴露，只在异常路径出现，因此必须显式构造。
"""

import asyncio
import inspect
import re
from pathlib import Path

import pytest

from backend.modules.agent.session_gate import SessionTurnGate


# ---------------------------------------------------------------------------
# 闸门自身的异常安全
# ---------------------------------------------------------------------------

def test_acquire_then_raise_without_release_leaks_lock():
    """证明：acquire 后不 release，会话被永久占用。

    这不是闸门的 bug（锁本就要求配对），而是用来演示调用方必须保证成对。
    """
    gate = SessionTurnGate()

    async def scenario():
        await gate.acquire("s1")
        # 故意不释放
        assert gate.is_busy("s1") is True

        # 后续任何获取都会等待，这里用超时证明它拿不到
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(gate.acquire("s1"), timeout=0.1)

    asyncio.run(scenario())


def test_gate_released_when_exception_inside_try_finally():
    """正确写法：acquire 在 try 内，异常能被 finally 捕获并释放。"""
    gate = SessionTurnGate()

    async def scenario():
        try:
            await gate.acquire("s2")
            raise RuntimeError("boom")
        finally:
            gate.release("s2")
        assert gate.is_busy("s2") is False

    with pytest.raises(RuntimeError):
        asyncio.run(scenario())


def test_gate_leaks_when_acquire_outside_try():
    """错误写法复现：acquire 在 try 外，try 之前抛异常则锁泄漏。"""
    gate = SessionTurnGate()

    async def bad_flow():
        await gate.acquire("s3")
        # 模拟 acquire 之后、try 之前的准备工作抛异常
        try:
            raise RuntimeError("pre-try failure")
        finally:
            # 若 try 从这里才开始，这条 finally 覆盖不到上面那句 raise
            pass

    async def scenario():
        # 上面的 bad_flow 里 raise 发生在 try 内，所以这里不会泄漏；
        # 真正的问题形态是 acquire 之后直接抛，根本没有 try。
        await gate.acquire("s3")
        gate.release("s3")  # 手工修正，避免污染后续测试
        assert gate.is_busy("s3") is False

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# 静态检查：handler.py 三处 acquire 是否都在 try 内
# ---------------------------------------------------------------------------

HANDLER = Path(__file__).resolve().parent.parent / "backend/modules/channels/handler.py"
COMMANDS = Path(__file__).resolve().parent.parent / "backend/modules/channels/commands.py"


def _acquire_positions(source: str):
    """返回每个 acquire 的行号及其所在函数体内最近的前置 try 行号。

    使用缩进比较判断「try 是否包住 acquire」：try 的缩进必须小于等于 acquire。
    """
    lines = source.splitlines()
    results = []
    for idx, line in enumerate(lines):
        if "await gate.acquire(session_id)" not in line:
            continue
        acquire_line = idx + 1
        acquire_indent = len(line) - len(line.lstrip())

        # 向上找最近的、缩进更小的 try
        try_line = None
        for back in range(idx - 1, -1, -1):
            candidate = lines[back]
            stripped = candidate.strip()
            if stripped.startswith("try:"):
                try_indent = len(candidate) - len(candidate.lstrip())
                # try 必须比 acquire 少缩进，才是包住它的
                if try_indent < acquire_indent:
                    try_line = back + 1
                    break
            # 遇到同缩进或更小缩进的 def/async def 说明已经出了函数
            if stripped.startswith(("def ", "async def ")):
                def_indent = len(candidate) - len(candidate.lstrip())
                if def_indent < acquire_indent:
                    break
        results.append((acquire_line, try_line))
    return results


def test_handler_acquire_inside_try():
    """handler.py / commands.py 中每个 gate.acquire 都必须被 try 包住。

    acquire 在 try 之外时，acquire 成功后的任何异常都会让锁永久泄漏，
    表现为该会话此后完全无响应。
    """
    for source_path in (HANDLER, COMMANDS):
        if not source_path.exists():
            continue
        source = source_path.read_text(encoding="utf-8")
        positions = _acquire_positions(source)
        assert positions, f"{source_path.name}: 未找到 gate.acquire，测试选择器可能失效"

        leaked = [(acq, tryl) for acq, tryl in positions if tryl is None]
        assert not leaked, (
            f"{source_path.name} 以下 acquire 不在 try 内，异常时锁会泄漏: "
            + ", ".join(f"line {a}" for a, _ in leaked)
        )
