"""用户级共享模型白名单：目录过滤、解析门闩与管理员编辑校验。"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.modules.multiuser import effective
from backend.modules.multiuser.shared_access import (
    SHARED_MODEL_SCOPE_ALL,
    SHARED_MODEL_SCOPE_SELECTED,
    filter_shared_models_for_user,
    is_shared_model_allowed,
    normalize_shared_model_refs,
    normalize_shared_model_scope,
    serialize_shared_model_refs,
)


def _user(
    scope: str = SHARED_MODEL_SCOPE_ALL,
    refs=("shared:admin:m1",),
    *,
    admin: bool = False,
):
    return SimpleNamespace(
        id="u1",
        owner_id="u1",
        username="alice",
        display_name="Alice",
        role="admin" if admin else "user",
        status="active",
        is_admin=admin,
        shared_model_scope=scope,
        shared_model_refs=refs,
    )


def _shared_items(*model_ids: str) -> list[dict]:
    return [
        {"ref": f"shared:admin:{model_id}", "provider": "admin", "model": model_id}
        for model_id in model_ids
    ]


def test_scope_and_refs_are_normalized_for_legacy_and_bad_values():
    assert normalize_shared_model_scope(None) == SHARED_MODEL_SCOPE_ALL
    assert normalize_shared_model_scope("SELECTED") == SHARED_MODEL_SCOPE_SELECTED
    assert normalize_shared_model_scope("bogus") == SHARED_MODEL_SCOPE_ALL
    assert normalize_shared_model_refs('["shared:p:m1", "shared:p:m1", "bad"]') == (
        "shared:p:m1",
    )
    assert normalize_shared_model_refs("not-json") == ()
    assert serialize_shared_model_refs(["shared:p:m1"]) == '["shared:p:m1"]'


def test_catalog_filter_respects_selected_scope_and_admin_bypass():
    items = _shared_items("m1", "m2", "m3")
    selected = _user(
        SHARED_MODEL_SCOPE_SELECTED,
        ("shared:admin:m1", "shared:admin:m3"),
    )
    assert [item["model"] for item in filter_shared_models_for_user(items, selected)] == [
        "m1",
        "m3",
    ]
    assert filter_shared_models_for_user(items, _user()) == items
    assert filter_shared_models_for_user(items, _user(admin=True)) == items
    assert filter_shared_models_for_user(
        items, _user(SHARED_MODEL_SCOPE_SELECTED, ())
    ) == []


def test_shared_model_gate_denies_unlisted_and_allows_admin():
    user = _user(
        SHARED_MODEL_SCOPE_SELECTED,
        ("shared:admin:m1",),
    )
    assert is_shared_model_allowed(user, "admin", "m1")
    assert not is_shared_model_allowed(user, "admin", "m2")
    assert is_shared_model_allowed(_user(), "admin", "m2")
    assert is_shared_model_allowed(_user(admin=True), "admin", "m2")
    assert not is_shared_model_allowed(
        _user(SHARED_MODEL_SCOPE_SELECTED, ()), "admin", "m1"
    )


def test_auth_user_mapping_parses_json_refs():
    from backend.modules.multiuser.identity import user_to_auth_user

    user = _user(
        SHARED_MODEL_SCOPE_SELECTED,
        '["shared:admin:m1", "shared:admin:m2"]',
    )
    auth = user_to_auth_user(user)
    assert auth.shared_model_scope == SHARED_MODEL_SCOPE_SELECTED
    assert auth.shared_model_refs == ("shared:admin:m1", "shared:admin:m2")


@pytest.mark.asyncio
async def test_list_available_models_filters_and_clears_disallowed_selected(monkeypatch):
    from backend.modules.multiuser import settings as mu_settings

    async def _fake_settings(use_cache=True):
        return SimpleNamespace(mode="shared", shared_providers=True)

    async def _fake_load(_user_id):
        return {
            "model_ref": {
                "source": "shared",
                "provider": "admin",
                "model": "m2",
                "alias": "m2",
            }
        }

    monkeypatch.setattr(mu_settings, "load_settings", _fake_settings)
    monkeypatch.setattr(
        effective, "list_shared_models", lambda anonymize=False: _shared_items("m1", "m2")
    )
    monkeypatch.setattr(effective, "load_user_config", _fake_load)

    data = await effective.list_available_models(
        _user(SHARED_MODEL_SCOPE_SELECTED, ("shared:admin:m1",))
    )

    assert [item["model"] for item in data["shared"]] == ["m1"]
    assert data["selected"] is None


@pytest.mark.asyncio
async def test_validate_model_ref_rejects_forged_shared_model(monkeypatch):
    from backend.modules.multiuser import settings as mu_settings

    async def _fake_settings(use_cache=True):
        return SimpleNamespace(mode="shared", shared_providers=True)

    async def _fake_load(_user_id):
        return {}

    monkeypatch.setattr(mu_settings, "load_settings", _fake_settings)
    monkeypatch.setattr(effective, "load_user_config", _fake_load)

    user = _user(SHARED_MODEL_SCOPE_SELECTED, ("shared:admin:m1",))
    with pytest.raises(effective.ModelResolutionError, match="未授权"):
        await effective.validate_model_ref(user, "shared", "admin", "m2")


@pytest.mark.asyncio
async def test_validate_model_ref_allows_listed_shared_model(monkeypatch):
    from backend.modules.multiuser import settings as mu_settings

    async def _fake_settings(use_cache=True):
        return SimpleNamespace(mode="shared", shared_providers=True)

    async def _fake_load(_user_id):
        return {}

    monkeypatch.setattr(mu_settings, "load_settings", _fake_settings)
    monkeypatch.setattr(effective, "load_user_config", _fake_load)
    monkeypatch.setattr(
        effective,
        "_from_shared",
        lambda provider, model: SimpleNamespace(alias=f"{provider}/{model}"),
    )

    ref = await effective.validate_model_ref(
        _user(SHARED_MODEL_SCOPE_SELECTED, ("shared:admin:m1",)),
        "shared",
        "admin",
        "m1",
    )
    assert ref["model"] == "m1"


def test_admin_selection_forces_all_and_rejects_unshared_ref(monkeypatch):
    from backend.api.admin import users as admin_users

    monkeypatch.setattr(
        admin_users,
        "list_shared_models",
        lambda: [{"ref": "shared:admin:m1"}],
    )
    assert admin_users._shared_selection("admin", "selected", ["shared:admin:m1"]) == (
        SHARED_MODEL_SCOPE_ALL,
        [],
    )
    assert admin_users._shared_selection("user", "all", ["shared:admin:m1"]) == (
        SHARED_MODEL_SCOPE_ALL,
        [],
    )
    with pytest.raises(Exception) as exc:
        admin_users._shared_selection("user", "selected", ["shared:admin:gone"])
    assert getattr(exc.value, "status_code", None) == 400


@pytest.mark.asyncio
async def test_resolve_model_for_user_rejects_revoked_shared(monkeypatch):
    from backend.modules.multiuser import settings as mu_settings

    async def _fake_settings(use_cache=True):
        return SimpleNamespace(mode="shared", shared_providers=True)

    async def _fake_load(_user_id):
        return {
            "model_ref": {
                "source": "shared",
                "provider": "admin",
                "model": "m2",
                "alias": "m2",
            }
        }

    monkeypatch.setattr(mu_settings, "load_settings", _fake_settings)
    monkeypatch.setattr(effective, "load_user_config", _fake_load)
    monkeypatch.setattr(
        effective,
        "_from_shared",
        lambda provider, model: pytest.fail("不应解析未授权的共享模型"),
    )

    with pytest.raises(effective.ModelResolutionError, match="未授权"):
        await effective.resolve_model_for_user(
            _user(SHARED_MODEL_SCOPE_SELECTED, ("shared:admin:m1",))
        )


@pytest.mark.asyncio
async def test_resolve_model_ref_for_user_denies_unlisted(monkeypatch):
    from backend.modules.multiuser import settings as mu_settings

    async def _fake_settings(use_cache=True):
        return SimpleNamespace(mode="shared", shared_providers=True)

    async def _fake_load(_user_id):
        return {}

    monkeypatch.setattr(mu_settings, "load_settings", _fake_settings)
    monkeypatch.setattr(effective, "load_user_config", _fake_load)
    monkeypatch.setattr(
        effective,
        "_from_shared",
        lambda provider, model: pytest.fail("不应解析未授权的共享模型"),
    )

    with pytest.raises(effective.ModelResolutionError, match="不可用或未共享"):
        await effective.resolve_model_ref_for_user(
            _user(SHARED_MODEL_SCOPE_SELECTED, ("shared:admin:m1",)),
            "admin",
            "m2",
        )
