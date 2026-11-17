"""存量配置迁移测试：旧默认工具调用上限 25 迁移为不限制（0）。"""

import json

import pytest


class _FakeSession:
    """够用的最小 session 替身：只实现 get / merge / commit。"""

    def __init__(self, rows: dict):
        self.rows = dict(rows)
        self.merged = []
        self.commits = 0

    async def get(self, model, key):
        value = self.rows.get(key)
        if value is None:
            return None
        return type("Row", (), {"key": key, "value": value})()

    async def merge(self, obj):
        self.merged.append((obj.key, obj.value))
        self.rows[obj.key] = obj.value
        return obj

    async def commit(self):
        self.commits += 1


def _loader():
    from backend.modules.config.loader import ConfigLoader

    return ConfigLoader.__new__(ConfigLoader)  # 不跑 __init__（会碰配置/数据库）


@pytest.mark.asyncio
async def test_legacy_default_is_migrated_once():
    from backend.modules.config.loader import (
        LEGACY_DEFAULT_MAX_ITERATIONS,
        MIGRATION_KEY_MAX_ITERATIONS,
    )

    loader = _loader()
    config_dict = {"model": {"max_iterations": LEGACY_DEFAULT_MAX_ITERATIONS}}
    session = _FakeSession({"config.model.max_iterations": "25"})

    await loader._migrate_legacy_max_iterations(session, config_dict)

    assert config_dict["model"]["max_iterations"] == 0
    assert "config.model.max_iterations" in dict(session.merged)
    assert MIGRATION_KEY_MAX_ITERATIONS in dict(session.merged)
    assert session.commits == 1

    # 第二次加载（marker 已存在）不再迁移
    config_dict2 = {"model": {"max_iterations": LEGACY_DEFAULT_MAX_ITERATIONS}}
    await loader._migrate_legacy_max_iterations(session, config_dict2)
    assert config_dict2["model"]["max_iterations"] == LEGACY_DEFAULT_MAX_ITERATIONS


@pytest.mark.asyncio
async def test_other_values_are_not_migrated():
    loader = _loader()
    session = _FakeSession({})

    for value in (0, 30, 150, None):
        config_dict = {"model": {"max_iterations": value}}
        await loader._migrate_legacy_max_iterations(session, config_dict)
        assert config_dict["model"]["max_iterations"] == value

    # 没有 model 段也不应报错
    await loader._migrate_legacy_max_iterations(session, {})
    assert session.commits == 0
    assert json.dumps({}) == "{}"
