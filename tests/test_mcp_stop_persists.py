"""回归：手动“停止”某个 MCP server 后，不应被惰性自动连接立刻拉起。

现象：单 server 时，点“停止”→ _connected 变 False，但全局 MCP 开关仍开着，
下一次 /overview 轮询里的 ensure_connected() 把它又连回来 → 按钮停不下来。
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
    def __init__(self):
        self._tools = {}

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
    async def aclose(self):
        pass


def _cfg(sid):
    return types.SimpleNamespace(
        id=sid, name=sid, enabled=True, connect_timeout=10, timeout=30, transport="stdio",
    )


def _patch_connect(monkeypatch, tools=("t",)):
    calls = {"count": 0, "servers": []}

    async def fake_connect(server_id, cfg, registry, out_wrappers=None):
        calls["count"] += 1
        calls["servers"].append(server_id)
        for suffix in tools:
            registry.register_name(f"mcp_{server_id}_{suffix}")
        return FakeStack()

    monkeypatch.setattr(mcp_client, "connect_mcp_server", fake_connect)
    return calls


def _mgr(sid="srv"):
    m = McpClientManager()
    m.set_registry(FakeRegistry())
    m._server_configs[sid] = _cfg(sid)
    return m


def test_disconnect_marks_manually_stopped(monkeypatch):
    async def scenario():
        m = _mgr()
        _patch_connect(monkeypatch)
        assert await m.start_server("srv") is True
        assert m._connected is True

        assert await m.disconnect_server("srv") is True
        assert "srv" in m._manually_stopped
        assert "srv" not in m._conn_tasks
        assert m._connected is False

    asyncio.run(scenario())


def test_reconnect_all_skips_manually_stopped(monkeypatch):
    async def scenario():
        m = _mgr()
        calls = _patch_connect(monkeypatch)
        await m.start_server("srv")
        await m.disconnect_server("srv")
        before = calls["count"]

        await m.reconnect_all()  # 惰性重连不应把手动停止的 server 拉起

        assert calls["count"] == before, "手动停止的 server 不应被 reconnect_all 重连"
        assert "srv" not in m._conn_tasks

    asyncio.run(scenario())


def test_ensure_connected_does_not_revive_manually_stopped(monkeypatch):
    """核心回归：ensure_connected（/overview 轮询触发）不得复活手动停止的 server。"""
    async def scenario():
        m = _mgr()
        _patch_connect(monkeypatch)
        await m.start_server("srv")
        await m.disconnect_server("srv")

        # 模拟全局 MCP 开关仍打开
        from backend.modules.config.loader import config_loader
        monkeypatch.setattr(config_loader.config.mcp, "enabled", True, raising=False)

        revived = await m.ensure_connected()

        assert revived is False
        assert "srv" not in m._conn_tasks, "停止的 server 不应被 ensure_connected 复活"
        assert m._connected is False

    asyncio.run(scenario())


def test_start_clears_manually_stopped(monkeypatch):
    async def scenario():
        m = _mgr()
        _patch_connect(monkeypatch)
        await m.start_server("srv")
        await m.disconnect_server("srv")
        assert "srv" in m._manually_stopped

        assert await m.start_server("srv") is True
        assert "srv" not in m._manually_stopped, "显式启动应撤销手动停止标记"
        assert "srv" in m._conn_tasks
        assert m._connected is True

    asyncio.run(scenario())


def test_disconnect_all_clears_manually_stopped(monkeypatch):
    async def scenario():
        m = _mgr()
        _patch_connect(monkeypatch)
        await m.start_server("srv")
        await m.disconnect_server("srv")
        assert m._manually_stopped

        await m.disconnect()  # 全局断开=整体重置
        assert m._manually_stopped == set()

    asyncio.run(scenario())


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
