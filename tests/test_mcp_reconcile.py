"""reconcile_registry_sync 回归测试。

场景：MCP 配置中途变化后，长生命周期的会话级注册表能否被“全量对齐”
（增/删/换），从而修复“老对话不加载新工具”。
"""

import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.modules.mcp.client import McpClientManager
from backend.modules.tools.registry import ToolRegistry
from backend.modules.tools.base import Tool


class DummyTool(Tool):
    def __init__(self, name):
        self._name = name

    @property
    def name(self):
        return self._name

    @property
    def description(self):
        return self._name

    @property
    def parameters(self):
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs):
        return self._name


def _mgr_with(wrappers):
    mgr = McpClientManager()
    mgr._connected = True
    mgr._tool_wrappers = dict(wrappers)
    return mgr


def test_reconcile_adds_new_tools():
    """老对话注册表里没有的新 MCP 工具，应被补齐。"""
    reg = ToolRegistry()
    reg.register(DummyTool("shell"))  # 非 MCP 本地工具
    a, b = DummyTool("mcp_demo_add"), DummyTool("mcp_demo_echo")
    mgr = _mgr_with({"mcp_demo_add": a, "mcp_demo_echo": b})

    changed = mgr.reconcile_registry_sync(reg)

    assert changed == 2
    assert reg.has_tool("mcp_demo_add") and reg.has_tool("mcp_demo_echo")
    assert reg.has_tool("shell"), "本地工具不受影响"


def test_reconcile_removes_deleted_tools():
    """配置里删掉的 MCP 工具，应从注册表移除；本地工具保留。"""
    reg = ToolRegistry()
    reg.register(DummyTool("shell"))
    reg.register(DummyTool("mcp_demo_add"))
    reg.register(DummyTool("mcp_old_gone"))  # manager 已无
    keep = DummyTool("mcp_demo_add")
    mgr = _mgr_with({"mcp_demo_add": keep})

    changed = mgr.reconcile_registry_sync(reg)

    # mcp_old_gone 被移除(1)，mcp_demo_add 对象不同被替换(移除+新增=2)
    assert not reg.has_tool("mcp_old_gone")
    assert reg.has_tool("mcp_demo_add")
    assert reg.get_tool("mcp_demo_add") is keep, "应替换为 manager 当前的 wrapper"
    assert reg.has_tool("shell")
    assert changed == 3


def test_reconcile_replaces_reconnected_wrapper():
    """重连后 wrapper 对象更换：注册表里的旧对象应被替换为新对象。"""
    reg = ToolRegistry()
    old = DummyTool("mcp_demo_add")
    reg.register(old)
    new = DummyTool("mcp_demo_add")
    mgr = _mgr_with({"mcp_demo_add": new})

    mgr.reconcile_registry_sync(reg)

    assert reg.get_tool("mcp_demo_add") is new
    assert reg.get_tool("mcp_demo_add") is not old


def test_reconcile_when_disconnected_removes_all_mcp():
    """MCP 未连接：注册表里的 MCP 工具应全部移除，本地工具保留。"""
    reg = ToolRegistry()
    reg.register(DummyTool("shell"))
    reg.register(DummyTool("mcp_demo_add"))
    mgr = McpClientManager()
    mgr._connected = False
    mgr._tool_wrappers = {}

    changed = mgr.reconcile_registry_sync(reg)

    assert not reg.has_tool("mcp_demo_add")
    assert reg.has_tool("shell")
    assert changed == 1


def test_reconcile_idempotent():
    """已对齐时再次调用不产生变更。"""
    reg = ToolRegistry()
    a = DummyTool("mcp_demo_add")
    mgr = _mgr_with({"mcp_demo_add": a})

    assert mgr.reconcile_registry_sync(reg) == 1
    assert mgr.reconcile_registry_sync(reg) == 0
    assert mgr.reconcile_registry_sync(reg) == 0


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
