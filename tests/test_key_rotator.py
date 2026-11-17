"""KeyRotator 单元测试。

重点回归 mark_key_failed 在 failed_key 不在列表时的死锁 bug：
修复前实现在持有非重入锁的情况下调用 self.next_key()（其内部再次获取同一把锁），
同线程重入 threading.Lock 会永久阻塞。本测试用带超时的子线程守护，
若死锁复发会以清晰的失败报出，而不是把测试进程挂死。
"""

import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.modules.providers.runtime import KeyRotator, get_key_rotator


def _run_with_timeout(func, timeout=5.0):
    """在子线程里跑 func，超时视为死锁。返回 func 的结果。"""
    box = {}

    def _target():
        box["result"] = func()

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        pytest.fail(
            f"mark_key_failed 在 {timeout}s 内未返回，疑似锁重入死锁复发"
        )
    return box.get("result")


# --------------------------------------------------------------------------
# 死锁回归：failed_key 不在 keys 中，会走 except ValueError 分支
# --------------------------------------------------------------------------

def test_mark_key_failed_unknown_key_does_not_deadlock():
    rotator = KeyRotator(["k1", "k2", "k3"])
    # "unknown" 不在列表 -> 触发 index() 的 ValueError 分支
    result = _run_with_timeout(lambda: rotator.mark_key_failed("unknown"))
    assert result in {"k1", "k2", "k3"}


def test_mark_key_failed_empty_string_key_does_not_deadlock():
    # loop.py 中 current_key 可能是 "" (getattr(..., "") or "")
    rotator = KeyRotator(["k1", "k2"])
    result = _run_with_timeout(lambda: rotator.mark_key_failed(""))
    assert result in {"k1", "k2"}


def test_mark_key_failed_unknown_key_advances_pointer():
    """未知 key 走内联轮询，应真正推进指针（返回连续不同的 key）。"""
    rotator = KeyRotator(["k1", "k2", "k3"])
    first = _run_with_timeout(lambda: rotator.mark_key_failed("unknown"))
    second = _run_with_timeout(lambda: rotator.mark_key_failed("unknown"))
    assert first == "k1"
    assert second == "k2"
    assert first != second


# --------------------------------------------------------------------------
# 正常轮换行为
# --------------------------------------------------------------------------

def test_mark_key_failed_returns_next_key():
    rotator = KeyRotator(["k1", "k2", "k3"])
    assert rotator.mark_key_failed("k1") == "k2"
    # 指针已落在 k2，标记 k2 失败 -> k3
    assert rotator.mark_key_failed("k2") == "k3"


def test_mark_key_failed_wraps_around():
    rotator = KeyRotator(["k1", "k2", "k3"])
    assert rotator.mark_key_failed("k3") == "k1"


def test_mark_key_failed_single_key_returns_none():
    rotator = KeyRotator(["only"])
    assert rotator.mark_key_failed("only") is None


def test_mark_key_failed_empty_rotator_returns_none():
    rotator = KeyRotator([])
    assert rotator.mark_key_failed("anything") is None


def test_mark_key_failed_two_keys_alternate():
    rotator = KeyRotator(["a", "b"])
    assert rotator.mark_key_failed("a") == "b"
    assert rotator.mark_key_failed("b") == "a"


# --------------------------------------------------------------------------
# 基础属性与轮询
# --------------------------------------------------------------------------

def test_constructor_filters_blank_keys():
    rotator = KeyRotator(["k1", "", "  ", "k2", None])  # type: ignore[list-item]
    assert rotator.keys == ["k1", "k2"]
    assert rotator.count == 2


def test_next_key_round_robin():
    rotator = KeyRotator(["k1", "k2"])
    assert rotator.next_key() == "k1"
    assert rotator.next_key() == "k2"
    assert rotator.next_key() == "k1"


def test_current_key_does_not_advance():
    rotator = KeyRotator(["k1", "k2"])
    assert rotator.current_key() == "k1"
    assert rotator.current_key() == "k1"


def test_next_key_empty_returns_none():
    assert KeyRotator([]).next_key() is None
    assert KeyRotator([]).current_key() is None


# --------------------------------------------------------------------------
# 并发压测：多线程同时 mark_key_failed，不得死锁 / 不得越界
# --------------------------------------------------------------------------

def test_concurrent_mark_key_failed_no_deadlock():
    rotator = KeyRotator([f"k{i}" for i in range(5)])
    errors = []

    def _worker():
        try:
            for _ in range(200):
                # 混合已知与未知 key，覆盖两条分支
                rotator.mark_key_failed("k1")
                rotator.mark_key_failed("ghost")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=_worker, daemon=True) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10.0)

    alive = [t for t in threads if t.is_alive()]
    assert not alive, "并发 mark_key_failed 出现挂起线程，疑似死锁"
    assert not errors, f"并发执行抛出异常: {errors}"


# --------------------------------------------------------------------------
# get_key_rotator 缓存复用
# --------------------------------------------------------------------------

def test_get_key_rotator_reuses_instance_for_same_keys():
    keys = ["k1", "k2"]
    r1 = get_key_rotator("prov-test-reuse", keys)
    r2 = get_key_rotator("prov-test-reuse", keys)
    assert r1 is r2


def test_get_key_rotator_rebuilds_when_keys_change():
    r1 = get_key_rotator("prov-test-change", ["k1", "k2"])
    r2 = get_key_rotator("prov-test-change", ["k1", "k2", "k3"])
    assert r1 is not r2
    assert r2.count == 3


# --------------------------------------------------------------------------
# 失败冷却：刚失败的 Key 不应在下一轮立刻被再次选中
# --------------------------------------------------------------------------

def test_failed_key_is_skipped_during_cooldown(monkeypatch):
    import backend.modules.providers.runtime as runtime

    fake_now = [1000.0]
    monkeypatch.setattr(runtime.time, "monotonic", lambda: fake_now[0])

    rotator = KeyRotator(["k1", "k2"])
    assert rotator.mark_key_failed("k1", cooldown_seconds=60) == "k2"
    # k1 仍在冷却：下一次轮询应继续选中 k2
    assert rotator.next_key() == "k2"

    # 冷却结束后 k1 重新可用
    fake_now[0] += 61
    assert rotator.next_key() == "k1"


def test_all_keys_cooled_falls_back_to_rotation(monkeypatch):
    import backend.modules.providers.runtime as runtime

    fake_now = [2000.0]
    monkeypatch.setattr(runtime.time, "monotonic", lambda: fake_now[0])

    rotator = KeyRotator(["k1", "k2"])
    rotator.mark_key_failed("k1", cooldown_seconds=60)
    rotator.mark_key_failed("k2", cooldown_seconds=60)
    # 全部冷却时不能返回 None，仍需给调用方一个 Key 兜底
    assert rotator.next_key() in {"k1", "k2"}


# --------------------------------------------------------------------------
# 工厂：Key 列表随实例携带，故障转移可指定 Key，探测不推进共享轮换器
# --------------------------------------------------------------------------

def _create_provider(provider_id: str, **kwargs):
    from backend.modules.providers.factory import create_provider

    return create_provider(
        provider_id=provider_id,
        timeout=5.0,
        max_retries=0,
        **kwargs,
    )


def test_factory_attaches_effective_keys_to_provider():
    provider_id = "prov-factory-keys"
    get_key_rotator(provider_id, ["k1", "k2"])
    provider = _create_provider(provider_id, api_keys=["k1", "k2"])
    assert provider.api_keys == ["k1", "k2"]
    assert provider.api_type == "openai-chat-completions"
    assert provider.api_key in {"k1", "k2"}


def test_factory_key_override_wins_without_advancing_poll():
    provider_id = "prov-factory-override"
    get_key_rotator(provider_id, ["k1", "k2"])
    provider = _create_provider(
        provider_id, api_keys=["k1", "k2"], key_override="k2"
    )
    assert provider.api_key == "k2"
    # key_override 不应推进轮询指针：下一次仍从 k1 开始
    rotator = get_key_rotator(provider_id, ["k1", "k2"])
    assert rotator.next_key() == "k1"


def test_factory_probe_mode_does_not_touch_shared_rotator():
    provider_id = "prov-factory-probe"
    rotator = get_key_rotator(provider_id, ["k1", "k2"])
    assert rotator.next_key() == "k1"

    provider = _create_provider(
        provider_id,
        api_key="k2",
        api_keys=["k1", "k2"],
        enable_key_rotation=False,
    )
    assert provider.api_key == "k2"
    # 探测没有推进共享轮换器：下一次仍是 k2
    assert get_key_rotator(provider_id, ["k1", "k2"]).next_key() == "k2"


# --------------------------------------------------------------------------
# 模型清单拉取：鉴权失败时自动换 Key，非鉴权错误不盲目重试
# --------------------------------------------------------------------------

def test_catalog_failover_switches_to_next_key(monkeypatch):
    import asyncio

    import backend.api.settings.model_catalog as catalog

    calls = []

    async def fake_fetch(*, api_base, api_key, api_type):
        calls.append(api_key)
        if api_key == "k1":
            raise catalog.ModelCatalogError("bad key", status_code=401)
        return [("m1", None, None, None)]

    monkeypatch.setattr(catalog, "fetch_provider_models", fake_fetch)
    models, used_index = asyncio.run(
        catalog.fetch_provider_models_with_key_failover(
            api_base="http://example.com",
            api_keys=["k1", "k2"],
            api_type="openai-chat-completions",
        )
    )

    assert calls == ["k1", "k2"]
    assert used_index == 1
    assert models[0][0] == "m1"


def test_catalog_failover_stops_on_non_auth_error(monkeypatch):
    import asyncio

    import pytest as pytest_mod

    import backend.api.settings.model_catalog as catalog

    calls = []

    async def fake_fetch(*, api_base, api_key, api_type):
        calls.append(api_key)
        raise catalog.ModelCatalogError("bad base url", status_code=404)

    monkeypatch.setattr(catalog, "fetch_provider_models", fake_fetch)
    with pytest_mod.raises(catalog.ModelCatalogError):
        asyncio.run(
            catalog.fetch_provider_models_with_key_failover(
                api_base="http://example.com",
                api_keys=["k1", "k2"],
                api_type="openai-chat-completions",
            )
        )
    assert calls == ["k1"]
