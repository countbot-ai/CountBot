"""SSRF 用前复校验测试：建连前重新解析并校验域名指向。"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.modules.config.schema import McpServerConfig
from backend.modules.multiuser.ssrf import (
    SsrfError,
    assert_outbound_url_allowed,
    validate_outbound_url,
)

PUBLIC_IP = "93.184.216.34"
INTERNAL_IP = "10.0.0.7"


def _stub_resolver(monkeypatch, ip: str):
    monkeypatch.setattr(
        "backend.modules.multiuser.ssrf._resolve_host_ips",
        lambda host: {ip},
    )


def test_config_time_passes_then_use_time_blocks(monkeypatch):
    """配置期解析到公网 IP 通过；用前重新解析到内网 IP 必须拦下。"""
    url = "https://rebind.example.com/mcp"

    _stub_resolver(monkeypatch, PUBLIC_IP)
    assert validate_outbound_url(url) == url

    _stub_resolver(monkeypatch, INTERNAL_IP)
    with pytest.raises(SsrfError) as exc:
        assert_outbound_url_allowed(url)
    assert "内网" in str(exc.value)


def test_use_time_blocks_loopback_and_metadata(monkeypatch):
    _stub_resolver(monkeypatch, "127.0.0.1")
    with pytest.raises(SsrfError):
        assert_outbound_url_allowed("https://rebind.example.com/hook")

    _stub_resolver(monkeypatch, "169.254.169.254")
    with pytest.raises(SsrfError):
        assert_outbound_url_allowed("https://rebind.example.com/hook")


def test_use_time_allows_public_host(monkeypatch):
    _stub_resolver(monkeypatch, PUBLIC_IP)
    assert assert_outbound_url_allowed("https://ok.example.com/hook")


@pytest.mark.asyncio
async def test_notification_send_revalidates(monkeypatch):
    """通知发送前复校验：DNS 翻到内网后不再发出请求。"""
    from backend.modules.multiuser import notifications as notify_module
    from backend.modules.multiuser.notifications import (
        NOTIFY_GENERIC_WEBHOOK,
        NotificationError,
        send_notification,
    )

    config = {"url": "https://rebind.example.com/hook"}
    _stub_resolver(monkeypatch, INTERNAL_IP)

    called = {"n": 0}

    class _BoomClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            called["n"] += 1
            raise AssertionError("不应发起请求")

        async def __aexit__(self, *_exc):
            return False

    monkeypatch.setattr(notify_module.httpx, "AsyncClient", _BoomClient)

    with pytest.raises(NotificationError) as exc:
        await send_notification(NOTIFY_GENERIC_WEBHOOK, config, "标题", "内容")
    assert "安全校验" in str(exc.value)
    assert called["n"] == 0


def test_user_mcp_skips_rebound_host(monkeypatch):
    """用户自建 MCP：建连前复校验失败时跳过该服务器。"""
    from backend.modules.multiuser.user_mcp import UserMcpManager

    server = McpServerConfig(
        id="demo",
        name="demo",
        transport="streamable_http",
        url="https://rebind.example.com/mcp",
    )

    monkeypatch.setattr(
        "backend.modules.multiuser.ssrf._resolve_host_ips",
        lambda host: {PUBLIC_IP},
    )
    assert UserMcpManager._url_safe_now(server, "owner") is True

    monkeypatch.setattr(
        "backend.modules.multiuser.ssrf._resolve_host_ips",
        lambda host: {INTERNAL_IP},
    )
    assert UserMcpManager._url_safe_now(server, "owner") is False


def test_user_own_model_api_base_revalidated(monkeypatch):
    """用户自建模型的 api_base 在解析时复校验。"""
    from backend.modules.multiuser.effective import ModelResolutionError, _from_own

    raw = {
        "providers": {
            "custom_openai": {
                "api_base": "https://rebind.example.com/v1",
                "api_key": "test-placeholder",
                "models": [{"id": "my-model", "enabled": True}],
            }
        }
    }

    monkeypatch.setattr(
        "backend.modules.multiuser.ssrf._resolve_host_ips",
        lambda host: {PUBLIC_IP},
    )
    resolved = _from_own(raw, "custom_openai", "my-model")
    assert resolved.model_id == "my-model"

    monkeypatch.setattr(
        "backend.modules.multiuser.ssrf._resolve_host_ips",
        lambda host: {INTERNAL_IP},
    )
    with pytest.raises(ModelResolutionError) as exc:
        _from_own(raw, "custom_openai", "my-model")
    assert "安全校验" in str(exc.value)
