"""性格复制接口：基于内置性格生成自定义副本。"""

import uuid

import pytest
import pytest_asyncio

TEST_PASSWORD = "test-placeholder"
PREFIX = "__dup_test_"


@pytest_asyncio.fixture(autouse=True)
async def _ensure_auth_configured():
    """临时写入管理员密码哈希并开启多用户，测试后还原。"""
    from backend.modules.auth.router import get_stored_credentials, save_credentials
    from backend.modules.auth.utils import hash_password
    from backend.modules.multiuser import settings as mu_settings

    original_username, original_hash = await get_stored_credentials()
    if not original_hash:
        await save_credentials("__dup_admin__", hash_password(TEST_PASSWORD))
    original_enabled = (await mu_settings.load_settings(use_cache=False)).enabled
    await mu_settings.save_settings(enabled=True)
    try:
        yield
    finally:
        await mu_settings.save_settings(enabled=original_enabled)
        if not original_hash:
            await save_credentials(original_username, original_hash)


def _client():
    from fastapi.testclient import TestClient

    from backend.app import app

    return TestClient(app)


async def _create_user(role: str = "user"):
    from backend.database import AsyncSessionLocal
    from backend.models.user import User
    from backend.modules.auth.utils import hash_password

    user_id = str(uuid.uuid4())
    username = f"{PREFIX}{user_id[:8]}"
    async with AsyncSessionLocal() as session:
        session.add(
            User(
                id=user_id,
                username=username,
                password_hash=hash_password(TEST_PASSWORD),
                role=role,
                status="active",
            )
        )
        await session.commit()
    return user_id, username


def _token(user_id: str, username: str) -> str:
    from backend.modules.auth.utils import create_session

    return create_session(username, user_id=user_id)


async def _cleanup(user_id: str, username: str, personality_ids) -> None:
    from backend.database import AsyncSessionLocal
    from backend.models.personality import Personality
    from backend.models.user import User
    from backend.modules.auth.utils import revoke_all_sessions, revoke_sessions_for_user_id

    async with AsyncSessionLocal() as session:
        for pid in personality_ids:
            row = await session.get(Personality, pid)
            if row is not None:
                await session.delete(row)
        user = await session.get(User, user_id)
        if user is not None:
            await session.delete(user)
        await session.commit()
    revoke_sessions_for_user_id(user_id)
    revoke_all_sessions(username)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.asyncio
async def test_duplicate_builtin_personality():
    """复制内置性格得到一份自定义副本，内容一致且归属当前用户。"""
    from backend.database import AsyncSessionLocal, init_db
    from backend.models.personality import Personality
    from backend.modules.multiuser.settings import invalidate_cache

    await init_db()
    invalidate_cache()

    builtin_id = f"__builtin_{uuid.uuid4().hex[:8]}"
    copy_id = f"persona-{uuid.uuid4().hex[:8]}"
    user_id, username = await _create_user()
    try:
        async with AsyncSessionLocal() as session:
            session.add(
                Personality(
                    id=builtin_id,
                    name="暴躁",
                    description="嘴上不饶人",
                    traits=["暴躁", "嘴硬心软"],
                    speaking_style="短句",
                    icon="CloudLightning",
                    is_builtin=True,
                )
            )
            await session.commit()

        client = _client()
        headers = {"Authorization": f"Bearer {_token(user_id, username)}"}
        response = client.post(
            f"/api/personalities/{builtin_id}/duplicate",
            json={"id": copy_id},
            headers=headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == copy_id
        assert body["is_builtin"] is False
        assert body["traits"] == ["暴躁", "嘴硬心软"]
        assert body["speaking_style"] == "短句"
        assert body["name"].startswith("暴躁")

        # 副本对当前用户可见
        listing = client.get("/api/personalities", headers=headers)
        ids = [item["id"] for item in listing.json()["personalities"]]
        assert copy_id in ids
    finally:
        await _cleanup(user_id, username, [builtin_id, copy_id])


@pytest.mark.asyncio
async def test_duplicate_missing_source_returns_404():
    """源性格不存在时返回 404。"""
    from backend.database import init_db
    from backend.modules.multiuser.settings import invalidate_cache

    await init_db()
    invalidate_cache()

    user_id, username = await _create_user()
    try:
        client = _client()
        headers = {"Authorization": f"Bearer {_token(user_id, username)}"}
        response = client.post(
            "/api/personalities/__missing_persona__/duplicate",
            json={"id": f"persona-{uuid.uuid4().hex[:8]}"},
            headers=headers,
        )
        assert response.status_code == 404
    finally:
        await _cleanup(user_id, username, [])


@pytest.mark.asyncio
async def test_duplicate_rejects_existing_id():
    """副本 ID 在同一作用域内已存在时返回 400。"""
    from backend.database import AsyncSessionLocal, init_db
    from backend.models.personality import Personality
    from backend.modules.multiuser.settings import invalidate_cache

    await init_db()
    invalidate_cache()

    builtin_id = f"__builtin_{uuid.uuid4().hex[:8]}"
    taken_id = f"persona-{uuid.uuid4().hex[:8]}"
    user_id, username = await _create_user()
    try:
        async with AsyncSessionLocal() as session:
            session.add(
                Personality(
                    id=builtin_id,
                    name="温柔",
                    description="轻声细语",
                    traits=["温柔"],
                    speaking_style="长句",
                    icon="Heart",
                    is_builtin=True,
                )
            )
            session.add(
                Personality(
                    id=taken_id,
                    name="已有副本",
                    description="占位",
                    traits=["温柔"],
                    speaking_style="长句",
                    icon="Heart",
                    is_builtin=False,
                    owner_id=user_id,
                )
            )
            await session.commit()

        client = _client()
        headers = {"Authorization": f"Bearer {_token(user_id, username)}"}
        response = client.post(
            f"/api/personalities/{builtin_id}/duplicate",
            json={"id": taken_id},
            headers=headers,
        )
        assert response.status_code == 400
    finally:
        await _cleanup(user_id, username, [builtin_id, taken_id])
