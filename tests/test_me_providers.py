"""普通用户自有供应商端点回归：/api/me/providers 的 CRUD、SSRF 约束与共享字段剥离。"""

import sys
import uuid
from pathlib import Path

import pytest
import pytest_asyncio

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

TEST_PASSWORD = "test-placeholder"
PREFIX = "__me_prov_test_"

VALID_PROVIDER = {
    "enabled": True,
    "api_key": "test-placeholder",
    "api_keys": ["test-placeholder"],
    # 公网 IP 字面量：SSRF 校验含真实 DNS 解析，测试不依赖域名可解析
    "api_base": "https://93.184.216.34/v1",
    "name": "我的供应商",
    "api_type": "openai-chat-completions",
    "models": [],
}


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def _create_user(role: str = "user", status: str = "active"):
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
                status=status,
            )
        )
        await session.commit()
    return user_id, username


async def _token(user_id: str, username: str) -> str:
    from backend.modules.auth.utils import create_session

    return create_session(username, user_id=user_id)


async def _cleanup_user(user_id: str, username: str) -> None:
    from backend.database import AsyncSessionLocal
    from backend.models.user import User
    from backend.modules.auth.utils import revoke_sessions_for_user_id
    from backend.modules.multiuser.user_config import delete_user_config

    async with AsyncSessionLocal() as session:
        user = await session.get(User, user_id)
        if user is not None:
            await session.delete(user)
            await session.commit()
    revoke_sessions_for_user_id(user_id)
    try:
        await delete_user_config(user_id)
    except Exception:
        pass


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture(autouse=True)
async def _ensure_auth_configured():
    """补齐管理员凭据并开启多用户，测试后还原；全新数据库下也能通过。"""
    from backend.database import init_db
    from backend.modules.auth.router import get_stored_credentials, save_credentials
    from backend.modules.auth.utils import hash_password
    from backend.modules.multiuser import settings as mu_settings

    await init_db()
    original_username, original_hash = await get_stored_credentials()
    if not original_hash:
        await save_credentials("__me_prov_admin__", hash_password(TEST_PASSWORD))
    original_enabled = (await mu_settings.load_settings(use_cache=False)).enabled
    await mu_settings.save_settings(enabled=True)
    try:
        yield
    finally:
        await mu_settings.save_settings(enabled=original_enabled)
        if not original_hash:
            await save_credentials(original_username, original_hash)


@pytest.mark.asyncio
async def test_provider_crud_roundtrip():
    """增改查删全链路：写入 -> 读回一致 -> 模型增删改排序走同一份配置。"""
    from backend.app import app

    user_id, username = await _create_user()
    try:
        token = await _token(user_id, username)
        client = __import__("fastapi.testclient", fromlist=["TestClient"]).TestClient(app)
        headers = _headers(token)

        # 初始为空
        view = client.get("/api/me/providers", headers=headers).json()
        assert view["providers"] == {}

        # 写入供应商
        response = client.put(
            "/api/me/providers",
            json={"providers": {"myprov": dict(VALID_PROVIDER)}},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["providers"]["myprov"]["api_key"] == "test-placeholder"

        # 追加模型
        added = client.post(
            "/api/me/providers/myprov/models",
            json={"models": [{"id": "model-a"}, {"id": "model-b"}], "source": "manual"},
            headers=headers,
        )
        assert added.status_code == 200, added.text
        assert [item["id"] for item in added.json()] == ["model-a", "model-b"]

        # 排序
        reordered = client.put(
            "/api/me/providers/myprov/models/order",
            json={"model_ids": ["model-b", "model-a"]},
            headers=headers,
        )
        assert [item["id"] for item in reordered.json()] == ["model-b", "model-a"]

        # 编辑
        updated = client.put(
            "/api/me/providers/myprov/models/model-a",
            json={"display_name": "模型 A", "clear_display_name": False},
            headers=headers,
        )
        target = next(item for item in updated.json() if item["id"] == "model-a")
        assert target["display_name"] == "模型 A"

        # 输出模式：模型级覆盖，以及清空后回落跟随全局
        streamed = client.put(
            "/api/me/providers/myprov/models/model-a",
            json={"stream_enabled": False},
            headers=headers,
        )
        target = next(item for item in streamed.json() if item["id"] == "model-a")
        assert target["stream_enabled"] is False

        restored = client.put(
            "/api/me/providers/myprov/models/model-a",
            json={"clear_stream_enabled": True},
            headers=headers,
        )
        target = next(item for item in restored.json() if item["id"] == "model-a")
        assert target["stream_enabled"] is None

        # 删除模型与供应商
        deleted = client.delete(
            "/api/me/providers/myprov/models/model-b", headers=headers
        )
        assert [item["id"] for item in deleted.json()] == ["model-a"]

        removed = client.delete("/api/me/providers/myprov", headers=headers)
        assert removed.status_code == 200
        assert client.get("/api/me/providers", headers=headers).json()["providers"] == {}
    finally:
        await _cleanup_user(user_id, username)


@pytest.mark.asyncio
async def test_provider_sharing_fields_are_stripped():
    """用户提交的共享字段一律剥离：共享动作只由管理员发起。"""
    from backend.app import app

    user_id, username = await _create_user()
    try:
        token = await _token(user_id, username)
        client = __import__("fastapi.testclient", fromlist=["TestClient"]).TestClient(app)
        headers = _headers(token)

        payload = dict(VALID_PROVIDER)
        payload["models"] = [
            {
                "id": "model-a",
                "enabled": True,
                "source": "manual",
                "shared": True,
                "shared_alias": "别名",
                "shared_note": "备注",
                "user_daily_limit": 10,
            }
        ]
        response = client.put(
            "/api/me/providers",
            json={"providers": {"myprov": payload}},
            headers=headers,
        )
        assert response.status_code == 200
        model = response.json()["providers"]["myprov"]["models"][0]
        assert not model["shared"]
        assert not model["shared_alias"]
        assert not model["shared_note"]
        assert model["user_daily_limit"] is None
    finally:
        await _cleanup_user(user_id, username)


@pytest.mark.asyncio
async def test_provider_api_base_rejects_internal_target():
    """SSRF 约束：内网地址与非法 scheme 落库前直接拒绝。"""
    from backend.app import app

    user_id, username = await _create_user()
    try:
        token = await _token(user_id, username)
        client = __import__("fastapi.testclient", fromlist=["TestClient"]).TestClient(app)
        headers = _headers(token)

        for bad_base in ("http://127.0.0.1:8080/v1", "http://169.254.169.254/latest", "ftp://x"):
            payload = dict(VALID_PROVIDER)
            payload["api_base"] = bad_base
            response = client.put(
                "/api/me/providers",
                json={"providers": {"myprov": payload}},
                headers=headers,
            )
            assert response.status_code == 400, f"{bad_base} -> {response.status_code}"
    finally:
        await _cleanup_user(user_id, username)


@pytest.mark.asyncio
async def test_provider_configs_are_isolated_between_users():
    """A 的自有供应商对 B 不可见，B 无法按同名 id 读到 A 的配置。"""
    from backend.app import app

    a_id, a_name = await _create_user()
    b_id, b_name = await _create_user()
    try:
        client = __import__("fastapi.testclient", fromlist=["TestClient"]).TestClient(app)

        a_headers = _headers(await _token(a_id, a_name))
        b_headers = _headers(await _token(b_id, b_name))

        saved = client.put(
            "/api/me/providers",
            json={"providers": {"myprov": dict(VALID_PROVIDER)}},
            headers=a_headers,
        )
        assert saved.status_code == 200

        b_view = client.get("/api/me/providers", headers=b_headers).json()
        assert "myprov" not in b_view["providers"]

        # B 按 id 操作 A 的配置：读不到即 404
        assert (
            client.delete("/api/me/providers/myprov/models/model-a", headers=b_headers).status_code
            == 404
        )
        assert (
            client.post("/api/me/providers/myprov/test", headers=b_headers).status_code == 404
        )

        # A 的配置未被 B 的操作影响
        a_view = client.get("/api/me/providers", headers=a_headers).json()
        assert a_view["providers"]["myprov"]["api_key"] == "test-placeholder"
    finally:
        await _cleanup_user(a_id, a_name)
        await _cleanup_user(b_id, b_name)


@pytest.mark.asyncio
async def test_provider_test_connection_uses_shared_probe(monkeypatch):
    """连通性测试复用共享探测：走 chat_stream 链路，返回统一成功/失败结构。"""
    from backend.app import app
    from backend.api import me_providers

    async def _fake_probe(provider, **kwargs):
        assert kwargs["model"] == "model-a"
        return True, "Successfully connected to myprov"

    monkeypatch.setattr(me_providers, "run_connection_test", _fake_probe)

    user_id, username = await _create_user()
    try:
        token = await _token(user_id, username)
        client = __import__("fastapi.testclient", fromlist=["TestClient"]).TestClient(app)
        headers = _headers(token)

        client.put(
            "/api/me/providers",
            json={"providers": {"myprov": dict(VALID_PROVIDER)}},
            headers=headers,
        )
        response = client.post(
            "/api/me/providers/test-connection",
            json={
                "provider": "myprov",
                "model": "model-a",
                "api_key": "test-placeholder",
                "api_base": "https://93.184.216.34/v1",
                "api_type": "openai-chat-completions",
            },
            headers=headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["success"] is True
    finally:
        await _cleanup_user(user_id, username)
