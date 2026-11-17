"""渠道推送目标接口单元测试。

验证定时任务等推送场景能直接复用「设置 - 渠道」里已配置好的渠道与账号，
并从历史渠道会话中反查出 chat_id，无需重复手工填写推送目标。
"""

import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.api import channels as channels_api  # noqa: E402
from backend.modules.config.loader import config_loader  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def client(monkeypatch):
    """挂载渠道路由，并屏蔽对真实会话表的访问。"""

    async def _fake_collect(channel_ids, per_channel_limit=100):
        return {
            "wecom": [
                {
                    "chat_id": "chat-1",
                    "account_id": "default",
                    "is_group": True,
                    "session_id": "s-1",
                    "session_name": "wecom:default:chat-1:20260101_000000",
                    "last_used": "2026-01-01T00:00:00Z",
                }
            ]
        }

    monkeypatch.setattr(channels_api, "_collect_channel_chats", _fake_collect)
    monkeypatch.setattr(
        channels_api, "get_channel_manager", lambda: (_ for _ in ()).throw(RuntimeError("no manager"))
    )
    app = FastAPI()
    app.include_router(channels_api.router)
    return TestClient(app)


def test_delivery_targets_only_returns_configured_channels(client):
    """未配置且未运行的渠道不应出现在推送目标里。"""
    config_loader.config.channels.wecom.enabled = True
    config_loader.config.channels.wecom.bot_id = "bot-1"
    config_loader.config.channels.feishu.enabled = False
    config_loader.config.channels.feishu.app_id = ""
    config_loader.config.channels.feishu.app_secret = ""

    response = client.get("/api/channels/delivery-targets")
    assert response.status_code == 200

    payload = response.json()
    assert payload["success"] is True
    returned = {item["channel"] for item in payload["targets"]}
    assert "wecom" in returned
    assert "feishu" not in returned


def test_delivery_targets_carries_accounts_and_chats(client):
    """已配置渠道要带上账号列表与历史会话里反查出的 chat_id。"""
    config_loader.config.channels.wecom.enabled = True
    config_loader.config.channels.wecom.bot_id = "bot-1"

    payload = client.get("/api/channels/delivery-targets").json()
    target = next(item for item in payload["targets"] if item["channel"] == "wecom")

    assert target["configured"] is True
    assert [account["account_id"] for account in target["accounts"]] == ["default"]
    assert [chat["chat_id"] for chat in target["chats"]] == ["chat-1"]


def test_parse_session_route_ignores_non_channel_sessions():
    """普通会话名（如 New Chat 2026/10/24 15:46:22）不能被误当成渠道会话。"""
    assert channels_api._parse_session_route("New Chat 2026/10/24 15:46:22") is None
    assert channels_api._parse_session_route("wecom:default") is None
    assert channels_api._parse_session_route("wecom:default:chat-1:20260101_000000") == (
        "wecom",
        "default",
        "chat-1",
    )
