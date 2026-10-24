"""渠道扫码接入单元测试。

覆盖 QQ / 飞书 / 企业微信 / 钉钉四个扫码流程的 begin -> poll 协议解析，
以及 QQ 密钥解密、飞书 Lark 域切换、会话一次性消费等关键边界。
所有请求都走 httpx.MockTransport，不会访问真实平台。
"""

import asyncio
import base64
import json
import sys
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.modules.channels import onboarding


def _run(coro):
    return asyncio.run(coro)


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# ---------------------------------------------------------------------------
# QQ
# ---------------------------------------------------------------------------


def test_decrypt_qq_secret_roundtrip():
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = b"k" * 32
    iv = b"i" * 12
    encrypted = AESGCM(key).encrypt(iv, b"qq-app-secret", None)
    payload = base64.b64encode(iv + encrypted).decode("ascii")
    key_base64 = base64.b64encode(key).decode("ascii")

    assert onboarding.decrypt_qq_secret(payload, key_base64) == "qq-app-secret"


def test_qq_onboarding_begin_poll_success():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/lite/create_bind_task":
            body = json.loads(request.content)
            captured["aes_key"] = body["key"]
            return httpx.Response(200, json={"retcode": 0, "data": {"task_id": "task-1"}})
        if request.url.path == "/lite/poll_bind_result":
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            key = base64.b64decode(captured["aes_key"])
            iv = b"i" * 12
            encrypted = AESGCM(key).encrypt(iv, b"secret-value", None)
            return httpx.Response(
                200,
                json={
                    "retcode": 0,
                    "data": {
                        "status": 2,
                        "bot_appid": "10240001",
                        "bot_encrypt_secret": base64.b64encode(iv + encrypted).decode("ascii"),
                    },
                },
            )
        raise AssertionError(f"unexpected request: {request.url}")

    async def scenario():
        async with _client(handler) as client:
            begin = await onboarding.begin_onboarding("qq", "qq-account", client=client)
            assert begin["qr_url"].startswith("https://q.qq.com/qqbot/openclaw/connect.html")
            assert "source=openclaw" in begin["qr_url"]
            assert begin["session_key"]
            result = await onboarding.poll_onboarding(begin["session_key"], client=client)
            assert result["status"] == "success"
            assert result["credentials"] == {"app_id": "10240001", "secret": "secret-value"}

            # 成功后会话被消费，再次轮询返回过期。
            again = await onboarding.poll_onboarding(begin["session_key"], client=client)
            assert again["status"] == "expired"

    _run(scenario())


def test_qq_rate_limit_is_treated_as_pending():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/lite/create_bind_task":
            return httpx.Response(200, json={"retcode": 0, "data": {"task_id": "task-2"}})
        return httpx.Response(200, json={"retcode": 1001, "msg": "轮询频率过高"})

    async def scenario():
        async with _client(handler) as client:
            begin = await onboarding.begin_onboarding("qq", "qq-account-2", client=client)
            result = await onboarding.poll_onboarding(begin["session_key"], client=client)
            assert result["status"] == "pending"

    _run(scenario())


def test_qq_poll_auth_failure_is_terminal():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/lite/create_bind_task":
            return httpx.Response(200, json={"retcode": 0, "data": {"task_id": "task-3"}})
        return httpx.Response(200, json={"retcode": 401, "msg": "unauthorized"})

    async def scenario():
        async with _client(handler) as client:
            begin = await onboarding.begin_onboarding("qq", "qq-account-3", client=client)
            result = await onboarding.poll_onboarding(begin["session_key"], client=client)
            assert result["status"] == "error"
            assert "401" in result["message"]

    _run(scenario())


# ---------------------------------------------------------------------------
# 飞书
# ---------------------------------------------------------------------------


def _feishu_handler(poll_payload):
    def handler(request: httpx.Request) -> httpx.Response:
        form = parse_qs(request.content.decode())
        action = form.get("action", [""])[0]
        if action == "init":
            return httpx.Response(200, json={"supported_auth_methods": ["client_secret"]})
        if action == "begin":
            return httpx.Response(
                200,
                json={
                    "device_code": "device-1",
                    "verification_uri_complete": "https://open.feishu.cn/page/launcher?user_code=ABCD",
                    "user_code": "ABCD",
                    "interval": 5,
                    "expire_in": 600,
                },
            )
        if action == "poll":
            if isinstance(poll_payload, list):
                return httpx.Response(200, json=poll_payload.pop(0))
            return httpx.Response(200, json=poll_payload)
        raise AssertionError(f"unexpected action: {action}")

    return handler


def test_feishu_onboarding_success():
    handler = _feishu_handler({"client_id": "cli_123", "client_secret": "feishu-secret"})

    async def scenario():
        async with _client(handler) as client:
            begin = await onboarding.begin_onboarding("feishu", "feishu-account", client=client)
            assert "from=sdk" in begin["qr_url"]
            result = await onboarding.poll_onboarding(begin["session_key"], client=client)
            assert result["status"] == "success"
            assert result["credentials"] == {"app_id": "cli_123", "app_secret": "feishu-secret"}

    _run(scenario())


def test_feishu_lark_tenant_switches_domain_then_reports_unsupported():
    handler = _feishu_handler(
        [
            {"error": "authorization_pending", "user_info": {"tenant_brand": "lark"}},
            {"client_id": "cli_lark", "client_secret": "lark-secret", "user_info": {"tenant_brand": "lark"}},
        ]
    )
    hosts = []

    def tracking_handler(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host)
        return handler(request)

    async def scenario():
        async with _client(tracking_handler) as client:
            begin = await onboarding.begin_onboarding("feishu", "feishu-lark", client=client)
            first = await onboarding.poll_onboarding(begin["session_key"], client=client)
            assert first["status"] == "pending"
            second = await onboarding.poll_onboarding(begin["session_key"], client=client)
            assert second["status"] == "error"
            assert "Lark" in second["message"]

    _run(scenario())
    assert "accounts.larksuite.com" in hosts


def test_feishu_access_denied_is_terminal():
    handler = _feishu_handler({"error": "access_denied"})

    async def scenario():
        async with _client(handler) as client:
            begin = await onboarding.begin_onboarding("feishu", "feishu-denied", client=client)
            result = await onboarding.poll_onboarding(begin["session_key"], client=client)
            assert result["status"] == "access_denied"

            again = await onboarding.poll_onboarding(begin["session_key"], client=client)
            assert again["status"] == "expired"

    _run(scenario())


# ---------------------------------------------------------------------------
# 企业微信
# ---------------------------------------------------------------------------


def test_wecom_onboarding_success():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/ai/qc/generate":
            return httpx.Response(
                200,
                json={"data": {"scode": "scode-1", "auth_url": "https://work.weixin.qq.com/ai/qc/c?s=1"}},
            )
        if request.url.path == "/ai/qc/query_result":
            assert request.url.params["scode"] == "scode-1"
            return httpx.Response(
                200,
                json={"data": {"status": "success", "bot_info": {"botid": "bot-1", "secret": "wecom-secret"}}},
            )
        raise AssertionError(f"unexpected request: {request.url}")

    async def scenario():
        async with _client(handler) as client:
            begin = await onboarding.begin_onboarding("wecom", "wecom-account", client=client)
            assert begin["qr_url"].startswith("https://work.weixin.qq.com/")
            result = await onboarding.poll_onboarding(begin["session_key"], client=client)
            assert result["status"] == "success"
            assert result["credentials"] == {"bot_id": "bot-1", "secret": "wecom-secret"}

    _run(scenario())


def test_wecom_http_error_is_retryable():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/ai/qc/generate":
            return httpx.Response(200, json={"data": {"scode": "scode-2", "auth_url": "https://x"}})
        return httpx.Response(503, text="busy")

    async def scenario():
        async with _client(handler) as client:
            begin = await onboarding.begin_onboarding("wecom", "wecom-account-2", client=client)
            result = await onboarding.poll_onboarding(begin["session_key"], client=client)
            assert result["status"] == "pending"

    _run(scenario())


# ---------------------------------------------------------------------------
# 钉钉
# ---------------------------------------------------------------------------


def test_dingtalk_onboarding_success():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/app/registration/init":
            assert json.loads(request.content)["source"] == onboarding.DINGTALK_REGISTRATION_SOURCE
            return httpx.Response(200, json={"errcode": 0, "nonce": "nonce-1"})
        if request.url.path == "/app/registration/begin":
            assert json.loads(request.content)["nonce"] == "nonce-1"
            return httpx.Response(
                200,
                json={
                    "errcode": 0,
                    "device_code": "device-1",
                    "verification_uri_complete": "https://open.dingtalk.com/scan?code=1",
                    "user_code": "CODE-1",
                    "interval": 3,
                    "expires_in": 600,
                },
            )
        if request.url.path == "/app/registration/poll":
            return httpx.Response(
                200,
                json={"errcode": 0, "status": "SUCCESS", "client_id": "ding-id", "client_secret": "ding-secret"},
            )
        raise AssertionError(f"unexpected request: {request.url}")

    async def scenario():
        async with _client(handler) as client:
            begin = await onboarding.begin_onboarding("dingtalk", "ding-account", client=client)
            assert begin["user_code"] == "CODE-1"
            result = await onboarding.poll_onboarding(begin["session_key"], client=client)
            assert result["status"] == "success"
            assert result["credentials"] == {"client_id": "ding-id", "client_secret": "ding-secret"}

    _run(scenario())


def test_dingtalk_fail_status_reports_reason():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/app/registration/init":
            return httpx.Response(200, json={"errcode": 0, "nonce": "nonce-2"})
        if request.url.path == "/app/registration/begin":
            return httpx.Response(
                200,
                json={
                    "errcode": 0,
                    "device_code": "device-2",
                    "verification_uri_complete": "https://open.dingtalk.com/scan?code=2",
                },
            )
        return httpx.Response(200, json={"errcode": 0, "status": "FAIL", "fail_reason": "已取消"})

    async def scenario():
        async with _client(handler) as client:
            begin = await onboarding.begin_onboarding("dingtalk", "ding-account-2", client=client)
            result = await onboarding.poll_onboarding(begin["session_key"], client=client)
            assert result["status"] == "error"
            assert "已取消" in result["message"]

    _run(scenario())


# ---------------------------------------------------------------------------
# 通用
# ---------------------------------------------------------------------------


def test_unknown_channel_is_rejected():
    async def scenario():
        with pytest.raises(ValueError):
            await onboarding.begin_onboarding("telegram", "telegram-account")

    _run(scenario())


def test_missing_session_returns_expired():
    async def scenario():
        result = await onboarding.poll_onboarding("missing-session")
        assert result["status"] == "expired"

    _run(scenario())


def test_apply_onboarding_credentials_enables_primary(monkeypatch, tmp_path):
    from backend.api import channels as api_channels
    from backend.modules.config.schema import AppConfig

    config = AppConfig()
    config.workspace.path = str(tmp_path)
    monkeypatch.setattr(api_channels.config_loader, "config", config)
    monkeypatch.setattr(api_channels, "_validate_external_coding_route_config", lambda *args, **kwargs: None)

    updated = api_channels._apply_onboarding_credentials(
        "qq", "default", {"app_id": "1024", "secret": "qq-secret"}
    )

    assert updated.enabled is True
    assert updated.app_id == "1024"
    assert updated.secret == "qq-secret"


def test_apply_onboarding_credentials_creates_secondary_account(monkeypatch, tmp_path):
    from backend.api import channels as api_channels
    from backend.modules.config.schema import AppConfig

    config = AppConfig()
    config.workspace.path = str(tmp_path)
    monkeypatch.setattr(api_channels.config_loader, "config", config)
    monkeypatch.setattr(api_channels, "_validate_external_coding_route_config", lambda *args, **kwargs: None)

    updated = api_channels._apply_onboarding_credentials(
        "feishu",
        "bot-2",
        {"app_id": "cli_2", "app_secret": "feishu-secret"},
        display_name="Feishu Bot 2",
    )

    account = updated.accounts["bot-2"]
    assert account.enabled is True
    assert account.app_id == "cli_2"
    assert account.display_name == "Feishu Bot 2"
    # 主账号不应被扫码结果覆盖。
    assert updated.app_id == ""


def test_apply_onboarding_credentials_rejects_duplicate_bot(monkeypatch, tmp_path):
    from backend.api import channels as api_channels
    from backend.modules.config.schema import AppConfig, QQAccountConfig

    config = AppConfig()
    config.workspace.path = str(tmp_path)
    config.channels.qq = api_channels.config_loader.config.channels.qq.__class__(
        app_id="1024",
        secret="existing",
        accounts={"bot-2": QQAccountConfig(app_id="2048", secret="existing-2", enabled=True)},
    )
    monkeypatch.setattr(api_channels.config_loader, "config", config)
    monkeypatch.setattr(api_channels, "_validate_external_coding_route_config", lambda *args, **kwargs: None)

    with pytest.raises(ValueError):
        api_channels._apply_onboarding_credentials(
            "qq", "bot-3", {"app_id": "1024", "secret": "dup-secret"}
        )

    # 校验失败时不应写入任何新账号。
    assert "bot-3" not in api_channels.config_loader.config.channels.qq.accounts


def test_poll_endpoint_applies_credentials_and_returns_config(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from backend.api import channels as api_channels
    from backend.modules.config.schema import AppConfig

    config = AppConfig()
    config.workspace.path = str(tmp_path)
    monkeypatch.setattr(api_channels.config_loader, "config", config)
    monkeypatch.setattr(api_channels, "_validate_external_coding_route_config", lambda *args, **kwargs: None)

    async def fake_poll(session_key):
        return {
            "status": "success",
            "message": "QQ 机器人绑定成功",
            "account_id": "default",
            "credentials": {"app_id": "1024", "secret": "qq-secret"},
        }

    async def fake_save():
        return None

    monkeypatch.setattr(api_channels, "poll_onboarding", fake_poll)
    monkeypatch.setattr(api_channels.config_loader, "save", fake_save)

    fake_request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                message_handler=None,
                channel_manager=None,
                channel_manager_task=None,
                message_queue=None,
            )
        )
    )

    result = _run(
        api_channels.poll_channel_onboarding(
            "qq",
            api_channels.ChannelOnboardPollRequest(session_key="session-1"),
            fake_request,
        )
    )

    assert result["success"] is True
    assert result["status"] == "success"
    assert result["config"]["app_id"] == "1024"
    assert result["config"]["enabled"] is True


def test_dingtalk_inbound_dedupe_is_bounded():
    from types import SimpleNamespace

    from backend.modules.channels.dingtalk import DingTalkChannel

    channel = DingTalkChannel(SimpleNamespace(account_id="default"))

    assert channel.claim_inbound_message("msg-1") is True
    assert channel.claim_inbound_message("msg-1") is False
    # 空 ID 无法去重，按新消息处理，避免误吞消息。
    assert channel.claim_inbound_message("") is True

    for index in range(1200):
        channel.claim_inbound_message(f"bulk-{index}")
    assert len(channel._processed_ids) == 1000
