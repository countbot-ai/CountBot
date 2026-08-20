"""McpClientManager 连接生命周期回归测试（持有者任务模型）。

背景：MCP 的 stdio/sse/http 传输由 anyio 实现，其 cancel scope 必须在
“进入它的那个任务”里退出。历史实现把连接的 open 放在临时任务（connect 的
gather 子任务）里、close 却在别的任务里做，触发
    RuntimeError: Attempted to exit cancel scope in a different task
导致“测试连接成功、但持久连接 0 tools / 启动失败 / 子进程泄漏”。

修复后：每个 server 由一个“持有者任务”独占——open/hold/close 全在同一任务内，
外部只通过 stop 信号或取消来停止。本文件用替身验证该模型的逻辑正确性；
真正的“跨任务不再抛 RuntimeError”由 mcp_demo_server/run_e2e.py 端到端验证。

无第三方 async 插件：用 asyncio.run 驱动。
"""

import asyncio
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import backend.modules.mcp.client as mcp_client
from backend.modules.mcp.client import McpClientManager


class FakeRegistry:
    """实现持有者任务用到的 registry 接口。"""

    def __init__(self):
        self._tools = {}  # 健康检查会读 _tools

    def register_name(self, name):
        self._tools[name] = types.SimpleNamespace(name=name)

    def unregister(self, name):
        if name in self._tools:
            del self._tools[name]
            return True
        raise KeyError(name)

    def list_tools(self):
        return sorted(self._tools)


class FakeStack:
    def __init__(self):
        self.closed = False

    async def aclose(self):
        self.closed = True


def _cfg(server_id):
    return types.SimpleNamespace(
        id=server_id, name=server_id, enabled=True,
        connect_timeout=10, timeout=30, transport="stdio",
    )


def _make_manager(server_id):
    mgr = McpClientManager()
    mgr.set_registry(FakeRegistry())
    mgr._server_configs[server_id] = _cfg(server_id)
    mgr._reconnect_backoff_base = 0.0  # 失败重试不真正 sleep
    return mgr


def _patch_connect(monkeypatch, tools, stacks=None):
    """把 connect_mcp_server 换成受控替身：注册工具、返回可关闭的 FakeStack。

    tools=None 表示模拟连接失败（返回 None）。
    """
    calls = {"count": 0}

    async def fake_connect(server_id, cfg, registry, out_wrappers=None):
        calls["count"] += 1
        if tools is None:
            return None
        for suffix in tools:
            name = f"mcp_{server_id}_{suffix}"
            registry.register_name(name)
            if out_wrappers is not None:
                out_wrappers[name] = object()
        st = FakeStack()
        if stacks is not None:
            stacks.append(st)
        return st

    monkeypatch.setattr(mcp_client, "connect_mcp_server", fake_connect)
    return calls


# --------------------------------------------------------------------------
# reconnect_server
# --------------------------------------------------------------------------
def test_reconnect_new_server_connects(monkeypatch):
    """0 连接的新 server：reconnect 应起持有者任务、注册工具、返回 True。"""
    async def scenario():
        mgr = _make_manager("srv")
        calls = _patch_connect(monkeypatch, tools=["a", "b", "c"])

        ok = await mgr.reconnect_server("srv")

        assert ok is True
        assert calls["count"] == 1
        assert "srv" in mgr._conn_tasks, "应有持有者任务在持有连接"
        assert set(mgr._mcp_tool_names) == {"mcp_srv_a", "mcp_srv_b", "mcp_srv_c"}
        # 持有者任务应仍在运行（挂在 stop.wait 上）
        assert not mgr._conn_tasks["srv"].done()

        await mgr.disconnect_server("srv")  # 清理

    asyncio.run(scenario())


def test_reconnect_replaces_old_connection_no_leak(monkeypatch):
    """再次 reconnect：旧持有者任务被停止、旧 stack 被关闭，工具数保持一致、无泄漏。"""
    async def scenario():
        mgr = _make_manager("srv")
        stacks = []
        _patch_connect(monkeypatch, tools=["a", "b"], stacks=stacks)

        assert await mgr.reconnect_server("srv") is True
        first_task = mgr._conn_tasks["srv"]
        assert len(stacks) == 1

        assert await mgr.reconnect_server("srv") is True
        # 旧任务已结束、旧 stack 已在“它自己任务里”关闭
        assert first_task.done()
        assert stacks[0].closed is True, "旧连接的 stack 应被关闭（无子进程泄漏）"
        assert len(stacks) == 2
        assert set(mgr._mcp_tool_names) == {"mcp_srv_a", "mcp_srv_b"}, "重连后工具集合一致、无重复/残留"

        await mgr.disconnect_server("srv")

    asyncio.run(scenario())


def test_reconnect_returns_false_when_connect_fails(monkeypatch):
    """连接持续失败：应耗尽重试并返回 False。"""
    async def scenario():
        mgr = _make_manager("srv")
        mgr._max_reconnect_attempts = 3
        calls = _patch_connect(monkeypatch, tools=None)

        ok = await mgr.reconnect_server("srv")

        assert ok is False
        assert calls["count"] == 3
        assert "srv" not in mgr._conn_tasks

    asyncio.run(scenario())


def test_reconnect_unknown_server_returns_false(monkeypatch):
    async def scenario():
        mgr = _make_manager("known")
        calls = _patch_connect(monkeypatch, tools=["x"])
        ok = await mgr.reconnect_server("nope")
        assert ok is False
        assert calls["count"] == 0

    asyncio.run(scenario())


# --------------------------------------------------------------------------
# disconnect_server
# --------------------------------------------------------------------------
def test_disconnect_stops_task_and_clears_tools(monkeypatch):
    """断开：停止持有者任务、关闭 stack、清空工具、_connected 归零、返回 True。"""
    async def scenario():
        mgr = _make_manager("srv")
        stacks = []
        _patch_connect(monkeypatch, tools=["a", "b"], stacks=stacks)

        assert await mgr.start_server("srv") is True
        assert mgr._connected is True
        task = mgr._conn_tasks["srv"]

        ok = await mgr.disconnect_server("srv")

        assert ok is True
        assert task.done(), "持有者任务应已停止"
        assert stacks[0].closed is True, "stack 应被关闭"
        assert "srv" not in mgr._conn_tasks
        assert [n for n in mgr._mcp_tool_names] == []
        assert mgr._connected is False

    asyncio.run(scenario())


def test_disconnect_one_of_many_keeps_connected(monkeypatch):
    """还有其它 server 时，断开其中一个不应清零 _connected。"""
    async def scenario():
        mgr = McpClientManager()
        mgr.set_registry(FakeRegistry())
        mgr._server_configs["A"] = _cfg("A")
        mgr._server_configs["B"] = _cfg("B")
        _patch_connect(monkeypatch, tools=["t"])

        assert await mgr.start_server("A") is True
        assert await mgr.start_server("B") is True

        assert await mgr.disconnect_server("A") is True
        assert "A" not in mgr._conn_tasks
        assert "B" in mgr._conn_tasks
        assert mgr._connected is True

        await mgr.disconnect_server("B")

    asyncio.run(scenario())


def test_disconnect_all_stops_everything(monkeypatch):
    async def scenario():
        mgr = McpClientManager()
        mgr.set_registry(FakeRegistry())
        mgr._server_configs["A"] = _cfg("A")
        mgr._server_configs["B"] = _cfg("B")
        stacks = []
        _patch_connect(monkeypatch, tools=["t"], stacks=stacks)

        await mgr.start_server("A")
        await mgr.start_server("B")
        assert len(mgr._conn_tasks) == 2

        await mgr.disconnect()

        assert mgr._conn_tasks == {}
        assert mgr._connected is False
        assert all(s.closed for s in stacks), "所有连接的 stack 都应关闭"
        assert mgr._mcp_tool_names == []

    asyncio.run(scenario())


# --------------------------------------------------------------------------
# connect / start_server / _safe_aclose
# --------------------------------------------------------------------------
def test_connect_sets_connected_and_starts_health_check(monkeypatch):
    """connect() 多 server：置 _connected、登记全部工具、起健康检查任务。"""
    async def scenario():
        mgr = McpClientManager()
        mgr.set_registry(FakeRegistry())
        _patch_connect(monkeypatch, tools=["t"])

        await mgr.connect([_cfg("A"), _cfg("B")])

        assert mgr._connected is True
        assert set(mgr._conn_tasks) == {"A", "B"}
        assert set(mgr._mcp_tool_names) == {"mcp_A_t", "mcp_B_t"}
        assert mgr._reconnect_task is not None and not mgr._reconnect_task.done(), "应启动健康检查任务"

        await mgr.disconnect()
        assert mgr._conn_tasks == {}
        assert mgr._connected is False

    asyncio.run(scenario())


def test_start_server_already_running_returns_true(monkeypatch):
    """已在运行的 server 再次 start：直接返回 True，不重复发起连接。"""
    async def scenario():
        mgr = _make_manager("srv")
        calls = _patch_connect(monkeypatch, tools=["t"])

        assert await mgr.start_server("srv") is True
        assert calls["count"] == 1
        assert await mgr.start_server("srv") is True
        assert calls["count"] == 1, "已运行时不应重复连接"

        await mgr.disconnect_server("srv")

    asyncio.run(scenario())


def test_safe_aclose_swallows_errors_and_timeout():
    """_safe_aclose：aclose 抛错或卡死都不得外泄、不得卡死持有者任务（B 兜底鲁棒性）。"""
    async def scenario():
        mgr = McpClientManager()

        class RaisingStack:
            async def aclose(self):
                raise RuntimeError("Attempted to exit cancel scope in a different task")

        # 抛错被吞（若外泄则本行会抛，测试失败）
        await mgr._safe_aclose(RaisingStack(), "x")

        class HangingStack:
            async def aclose(self):
                await asyncio.Event().wait()  # 永不返回

        mgr._close_timeout = 0.05
        # 超时被吞、不卡死
        await mgr._safe_aclose(HangingStack(), "y")

    asyncio.run(scenario())


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
