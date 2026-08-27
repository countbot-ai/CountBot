"""get_shared_provider 回归测试。

背景：Wiki 的三个 LLM 调用点（Agent 工具 ask、REST /wiki/ask、REST /wiki/compile）
都通过 `from backend.app import get_shared_provider` 获取共享 provider，但
backend.app 中从未定义过该函数——provider 实际存放在 `app.state.shared["provider"]`。
ImportError 被调用方的 `except Exception` 静默吞掉，导致：

- ask 永远走「检索结果拼接」回退，不产生自然语言回答；
- compile 永远原样返回未编译内容；
- 日志中没有任何报错，问题难以察觉。

本文件验证 backend.app 暴露 get_shared_provider，语义与 get_tool_registry 一致：
lifespan 启动前返回 None（调用方可安全降级），shared 组件就绪后返回共享 provider。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app import app, get_shared_provider  # noqa: E402


def test_returns_none_before_lifespan_startup():
    # lifespan 尚未运行时 app.state.shared 不存在，应返回 None 而非抛错
    app.state._state.pop("shared", None)
    assert get_shared_provider() is None


def test_returns_provider_once_shared_components_exist():
    sentinel = object()
    app.state.shared = {"provider": sentinel}
    try:
        assert get_shared_provider() is sentinel
    finally:
        app.state._state.pop("shared", None)


def test_returns_none_when_shared_has_no_provider():
    app.state.shared = {"provider": None}
    try:
        assert get_shared_provider() is None
    finally:
        app.state._state.pop("shared", None)
