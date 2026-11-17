"""共享模型元数据与管理员总览测试。"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException

from backend.modules.providers import model_registry
from backend.modules.config.schema import AppConfig, ModelEntry, ProviderConfig

_normalize_alias = model_registry.normalize_alias
_normalize_daily_limit = model_registry.normalize_daily_limit


def _ensure_alias_unique(config, **kwargs):
    return model_registry.ensure_alias_unique(config.providers, **kwargs)
from backend.modules.multiuser.effective import (
    SHARED_MODEL_DISPLAY_NAME,
    list_shared_models,
)


def _config_with(*entries: tuple[str, ModelEntry]) -> AppConfig:
    """按 (provider_id, entry) 组装一份最小配置。"""
    providers: dict[str, ProviderConfig] = {}
    for provider_id, entry in entries:
        provider = providers.get(provider_id)
        if provider is None:
            provider = ProviderConfig(name=provider_id)
            providers[provider_id] = provider
        provider.models.append(entry)
    return AppConfig(providers=providers)


# ---------------------------------------------------------------------------
# 归一化
# ---------------------------------------------------------------------------


def test_normalize_alias_strips_and_limits():
    assert _normalize_alias("  GLM-4 Plus  ") == "GLM-4 Plus"
    assert _normalize_alias("   ") is None
    assert _normalize_alias(None) is None

    with pytest.raises(HTTPException) as exc:
        _normalize_alias("x" * 41)
    assert exc.value.status_code == 400


def test_normalize_daily_limit_treats_zero_as_unlimited():
    assert _normalize_daily_limit(None) is None
    assert _normalize_daily_limit(0) is None
    assert _normalize_daily_limit(-5) is None
    assert _normalize_daily_limit(200) == 200


# ---------------------------------------------------------------------------
# 别名唯一性
# ---------------------------------------------------------------------------


def test_alias_conflict_across_providers_is_rejected():
    config = _config_with(
        ("zhipu", ModelEntry(id="glm-4", shared=True, shared_alias="共享 GLM")),
    )
    with pytest.raises(HTTPException) as exc:
        _ensure_alias_unique(
            config,
            provider_id="openai",
            model_id="gpt-4o",
            alias="共享 GLM",
        )
    assert exc.value.status_code == 409


def test_alias_of_self_is_allowed():
    """更新自身别名时不应与自己冲突。"""
    config = _config_with(
        ("zhipu", ModelEntry(id="glm-4", shared=True, shared_alias="共享 GLM")),
    )
    _ensure_alias_unique(
        config,
        provider_id="zhipu",
        model_id="glm-4",
        alias="共享 GLM",
    )


def test_alias_conflict_inside_same_batch_is_rejected():
    """同一次批量提交里两个条目用了同一个别名，也要拒绝。"""
    config = AppConfig(providers={})
    pending = [("zhipu", "glm-4", "同名"), ("zhipu", "glm-4-air", "同名")]
    with pytest.raises(HTTPException) as exc:
        _ensure_alias_unique(
            config,
            provider_id="zhipu",
            model_id="glm-4",
            alias="同名",
            pending=pending,
        )
    assert exc.value.status_code == 409


def test_unshared_entries_do_not_block_alias():
    """未共享的条目不占用别名，不参与冲突判定。"""
    config = _config_with(
        ("zhipu", ModelEntry(id="glm-4", shared=False, shared_alias="共享 GLM")),
    )
    _ensure_alias_unique(
        config,
        provider_id="openai",
        model_id="gpt-4o",
        alias="共享 GLM",
    )


# ---------------------------------------------------------------------------
# list_shared_models
# ---------------------------------------------------------------------------


def test_list_shared_models_filters_and_hides_keys(monkeypatch):
    config = _config_with(
        (
            "zhipu",
            ModelEntry(id="glm-4", shared=True, shared_alias="共享 GLM", user_daily_limit=100),
        ),
        ("zhipu", ModelEntry(id="glm-3", shared=False)),
        ("zhipu", ModelEntry(id="glm-4v", shared=True, enabled=False, shared_alias="停用的")),
    )
    config.providers["zhipu"].api_key = "test-placeholder"

    from backend.modules.config import loader as loader_module

    monkeypatch.setattr(loader_module.config_loader, "config", config, raising=False)

    items = list_shared_models()

    assert [item["model"] for item in items] == ["glm-4"]
    assert items[0]["alias"] == "共享 GLM"
    assert items[0]["daily_limit"] == 100
    assert "test-placeholder" not in str(items)


def test_list_shared_models_alias_falls_back_to_id(monkeypatch):
    config = _config_with(("zhipu", ModelEntry(id="glm-4", shared=True)))

    from backend.modules.config import loader as loader_module

    monkeypatch.setattr(loader_module.config_loader, "config", config, raising=False)

    items = list_shared_models()
    assert items[0]["alias"] == "glm-4"


def test_list_shared_models_anonymize_hides_upstream(monkeypatch):
    """普通用户视图脱敏：真实供应商名与共享备注不下发，统一展示为「内置模型」。"""
    config = _config_with(
        ("newbi", ModelEntry(id="grok-4.6", shared=True, shared_note="好友只读模型")),
    )
    config.providers["newbi"].name = "newbi"

    from backend.modules.config import loader as loader_module

    monkeypatch.setattr(loader_module.config_loader, "config", config, raising=False)

    anonymized = list_shared_models(anonymize=True)
    assert anonymized[0]["provider_name"] == SHARED_MODEL_DISPLAY_NAME
    assert anonymized[0]["note"] == ""

    # 管理员总览不脱敏：保留真实供应商名与共享备注
    admin_view = list_shared_models()
    assert admin_view[0]["provider_name"] == "newbi"
    assert admin_view[0]["note"] == "好友只读模型"


# ---------------------------------------------------------------------------
# 供应商级保存不能丢模型级字段
# ---------------------------------------------------------------------------


def test_parse_model_entry_keeps_shared_metadata():
    """回归：PUT /api/settings 重写 models 时必须保留共享与模型级设置。"""
    from backend.api.settings.validators import _parse_model_entry

    entry = _parse_model_entry(
        {
            "id": "grok-4.6",
            "enabled": True,
            "shared": True,
            "shared_alias": "grok马斯克",
            "shared_note": "管理员提供",
            "user_daily_limit": 100,
            "stream_enabled": False,
            "reasoning_levels": ["low", "High"],
            "reasoning_level": "High",
        }
    )

    assert entry is not None
    assert entry.shared is True
    assert entry.shared_alias == "grok马斯克"
    assert entry.shared_note == "管理员提供"
    assert entry.user_daily_limit == 100
    assert entry.stream_enabled is False
    assert entry.reasoning_levels == ["low", "high"]
    assert entry.reasoning_level == "high"


# ---------------------------------------------------------------------------
# 新增模型回归
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_provider_models_counts_added(monkeypatch):
    """回归：批量新增模型时计数器必须初始化，否则接口会 500。"""
    from backend.api.settings import provider_models as pm
    from backend.api.settings.models import AddProviderModelsRequest, ProviderModelPayload

    config = _config_with()
    config.providers["zhipu"] = ProviderConfig(name="zhipu")

    from backend.modules.config import loader as loader_module

    monkeypatch.setattr(loader_module.config_loader, "config", config, raising=False)

    async def _noop_save(_config):
        return None

    monkeypatch.setattr(pm, "_save_and_reload", _noop_save)

    result = await pm.add_provider_models(
        "zhipu",
        AddProviderModelsRequest(
            models=[ProviderModelPayload(id="glm-4"), ProviderModelPayload(id="glm-4v")],
            source="manual",
        ),
    )
    # AppConfig 会为已知供应商补内置默认模型，因此只断言新增项存在
    ids = [item["id"] for item in result]
    assert "glm-4" in ids and "glm-4v" in ids

    # 重复添加同一 ID 走「补空字段」分支，不应重复插入
    again = await pm.add_provider_models(
        "zhipu",
        AddProviderModelsRequest(models=[ProviderModelPayload(id="glm-4")], source="manual"),
    )
    assert len(again) == len(ids)


# ---------------------------------------------------------------------------
# API 层
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shared_models_endpoint_requires_admin():
    """普通用户访问共享模型总览必须 403。"""
    import uuid

    from fastapi.testclient import TestClient

    from backend.app import app
    from backend.database import AsyncSessionLocal, init_db
    from backend.models.user import User
    from backend.modules.auth.router import get_stored_credentials, save_credentials
    from backend.modules.auth.utils import (
        create_session,
        hash_password,
        revoke_all_sessions,
        revoke_sessions_for_user_id,
    )
    from backend.modules.multiuser.settings import invalidate_cache

    await init_db()
    invalidate_cache()

    from backend.modules.multiuser import settings as mu_settings

    original_enabled = (await mu_settings.load_settings(use_cache=False)).enabled
    await mu_settings.save_settings(enabled=True)

    original_username, original_hash = await get_stored_credentials()
    if not original_hash:
        await save_credentials("__shared_admin__", hash_password("test-placeholder"))

    user_id = str(uuid.uuid4())
    username = f"__shared_test_{user_id[:8]}"
    try:
        async with AsyncSessionLocal() as session:
            session.add(
                User(
                    id=user_id,
                    username=username,
                    password_hash=hash_password("test-placeholder"),
                    role="user",
                    status="active",
                )
            )
            await session.commit()

        token = create_session(username, user_id=user_id)
        client = TestClient(app)
        response = client.get(
            "/api/admin/shared-models",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403
        assert "api_key" not in response.text
    finally:
        async with AsyncSessionLocal() as session:
            user = await session.get(User, user_id)
            if user is not None:
                await session.delete(user)
                await session.commit()
        revoke_sessions_for_user_id(user_id)
        revoke_all_sessions(username)
        await mu_settings.save_settings(enabled=original_enabled)
        if not original_hash:
            await save_credentials(original_username, original_hash)
