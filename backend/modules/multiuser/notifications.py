"""用户通知渠道：仅出站 HTTP 推送，统一做 SSRF 校验、凭证脱敏与限流。"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from typing import Any, Dict, Optional, Tuple

import httpx
from loguru import logger

from backend.models.user import (
    NOTIFY_DINGTALK_WEBHOOK,
    NOTIFY_FEISHU_WEBHOOK,
    NOTIFY_GENERIC_WEBHOOK,
    NOTIFY_SERVERCHAN,
    NOTIFY_SHARED_TARGET,
    NOTIFY_TELEGRAM,
    NOTIFY_TYPES,
    NOTIFY_WECOM_WEBHOOK,
)
from backend.modules.multiuser.ssrf import (
    SsrfError,
    assert_outbound_url_allowed,
    validate_outbound_url,
)


ALLOWED_HOSTS: Dict[str, Tuple[str, ...]] = {
    NOTIFY_SERVERCHAN: ("sctapi.ftqq.com",),
    NOTIFY_TELEGRAM: ("api.telegram.org",),
    NOTIFY_FEISHU_WEBHOOK: ("open.feishu.cn", "open.larksuite.com"),
    NOTIFY_DINGTALK_WEBHOOK: ("oapi.dingtalk.com",),
    NOTIFY_WECOM_WEBHOOK: ("qyapi.weixin.qq.com",),
    # 通用 webhook 由管理员显式开启域名白名单，这里不做额外限制
    NOTIFY_GENERIC_WEBHOOK: (),
}

DEFAULT_DAILY_LIMIT = 50
MIN_SEND_INTERVAL_SECONDS = 1.0
REQUEST_TIMEOUT = 10.0
MAX_RESPONSE_BYTES = 64 * 1024


class NotificationError(ValueError):
    """通知渠道配置或发送失败。"""


# ----------------------------------------------------------------------
# 校验与脱敏
# ----------------------------------------------------------------------

def _require_str(config: Dict[str, Any], key: str, *, max_len: int = 512) -> str:
    value = str(config.get(key) or "").strip()
    if not value:
        raise NotificationError(f"缺少字段: {key}")
    if len(value) > max_len:
        raise NotificationError(f"字段过长: {key}")
    return value


def validate_channel_config(channel_type: str, config: Dict[str, Any]) -> Dict[str, str]:
    """校验并归一化渠道配置，返回只含允许字段的新字典。"""
    if channel_type not in NOTIFY_TYPES:
        raise NotificationError("不支持的通知渠道类型")
    if not isinstance(config, dict):
        raise NotificationError("渠道配置必须是对象")

    if channel_type == NOTIFY_SERVERCHAN:
        sendkey = _require_str(config, "sendkey", max_len=128)
        if not (sendkey.startswith("SCT") or sendkey.startswith("sctp")):
            raise NotificationError("SendKey 格式不正确")
        return {"sendkey": sendkey}

    if channel_type == NOTIFY_TELEGRAM:
        token = _require_str(config, "bot_token", max_len=256)
        chat_id = _require_str(config, "chat_id", max_len=64)
        # token 必须符合 bot API 形态，避免被当作任意路径拼接
        if ":" not in token or not token.split(":", 1)[0].isdigit():
            raise NotificationError("Bot Token 格式不正确")
        return {"bot_token": token, "chat_id": chat_id}

    if channel_type == NOTIFY_GENERIC_WEBHOOK:
        url = _require_str(config, "url", max_len=2048)
        try:
            url = validate_outbound_url(url)
        except SsrfError as exc:
            raise NotificationError(str(exc)) from exc
        return {"url": url}

    # 飞书 / 钉钉 / 企微：只接受官方域名下的 webhook
    url = _require_str(config, "webhook_url", max_len=2048)
    try:
        url = validate_outbound_url(url, allowed_hosts=ALLOWED_HOSTS.get(channel_type) or None)
    except SsrfError as exc:
        raise NotificationError(str(exc)) from exc
    return {"webhook_url": url}


def mask_channel_config(channel_type: str, config: Dict[str, Any]) -> Dict[str, str]:
    """面向接口返回的脱敏视图。"""
    def mask(value: str, keep: int = 4) -> str:
        text = str(value or "")
        if len(text) <= keep * 2:
            return "*" * len(text)
        return f"{text[:keep]}****{text[-keep:]}"

    if channel_type == NOTIFY_SERVERCHAN:
        return {"sendkey": mask(config.get("sendkey"))}
    if channel_type == NOTIFY_TELEGRAM:
        return {
            "bot_token": mask(config.get("bot_token")),
            "chat_id": str(config.get("chat_id") or ""),
        }
    if channel_type == NOTIFY_GENERIC_WEBHOOK:
        return {"url": mask(config.get("url"), keep=12)}
    if channel_type == NOTIFY_SHARED_TARGET:
        # 复用管理员渠道：配置里只有引用，没有凭据，原样回显便于界面回填
        return {
            "channel": str(config.get("channel") or ""),
            "account_id": str(config.get("account_id") or ""),
            "chat_id": str(config.get("chat_id") or ""),
        }
    return {"webhook_url": mask(config.get("webhook_url"), keep=12)}


def credential_signature(channel_type: str, config: Dict[str, Any]) -> Optional[str]:
    """用于全局唯一性校验的凭证签名（不落库、不返回）。"""
    if channel_type == NOTIFY_SERVERCHAN:
        return f"{channel_type}:{config.get('sendkey')}"
    if channel_type == NOTIFY_TELEGRAM:
        return f"{channel_type}:{config.get('bot_token')}:{config.get('chat_id')}"
    return None


# ----------------------------------------------------------------------
# 限流
# ----------------------------------------------------------------------

_daily_counts: Dict[str, Tuple[str, int]] = {}
_last_sent: Dict[str, float] = defaultdict(float)


def _today() -> str:
    return time.strftime("%Y-%m-%d")


def check_rate_limit(owner_id: str, channel_id: str, daily_limit: int = DEFAULT_DAILY_LIMIT) -> None:
    day = _today()
    key, count = _daily_counts.get(owner_id, (day, 0))
    if key != day:
        count = 0
    if count >= daily_limit:
        raise NotificationError("今日推送次数已达上限")
    _daily_counts[owner_id] = (day, count + 1)

    now = time.monotonic()
    if now - _last_sent.get(channel_id, 0.0) < MIN_SEND_INTERVAL_SECONDS:
        raise NotificationError("发送过于频繁，请稍后再试")
    _last_sent[channel_id] = now


# ----------------------------------------------------------------------
# 发送
# ----------------------------------------------------------------------

def _payload(channel_type: str, config: Dict[str, Any], title: str, content: str) -> Tuple[str, Dict[str, Any]]:
    if channel_type == NOTIFY_SERVERCHAN:
        key = config["sendkey"]
        url = f"https://sctapi.ftqq.com/{key}.send"
        return url, {"title": title[:32], "desp": content}

    if channel_type == NOTIFY_TELEGRAM:
        url = f"https://api.telegram.org/bot{config['bot_token']}/sendMessage"
        return url, {
            "chat_id": config["chat_id"],
            "text": f"{title}\n\n{content}",
            "disable_web_page_preview": True,
        }

    if channel_type == NOTIFY_FEISHU_WEBHOOK:
        return config["webhook_url"], {
            "msg_type": "text",
            "content": {"text": f"{title}\n{content}"},
        }

    if channel_type == NOTIFY_DINGTALK_WEBHOOK:
        return config["webhook_url"], {
            "msgtype": "text",
            "text": {"content": f"{title}\n{content}"},
        }

    if channel_type == NOTIFY_WECOM_WEBHOOK:
        return config["webhook_url"], {
            "msgtype": "text",
            "text": {"content": f"{title}\n{content}"},
        }

    return config["url"], {"title": title, "content": content}


async def send_notification(
    channel_type: str,
    config: Dict[str, Any],
    title: str,
    content: str,
) -> None:
    """发送一条通知；失败抛 :class:`NotificationError`。"""
    if channel_type not in NOTIFY_TYPES:
        raise NotificationError("不支持的通知渠道类型")

    url, payload = _payload(channel_type, config, title, content or "")

    # 发送前重新校验目标地址，防止 DNS rebinding
    try:
        assert_outbound_url_allowed(url)
    except SsrfError as exc:
        raise NotificationError(f"目标地址未通过安全校验: {exc}") from exc

    try:
        async with httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            response = await client.post(url, json=payload)
    except Exception as exc:
        raise NotificationError(f"发送失败: {exc}") from exc

    if response.status_code >= 400:
        raise NotificationError(f"上游返回 {response.status_code}")

    if len(response.content or b"") > MAX_RESPONSE_BYTES:
        logger.warning("Notification response exceeded size limit; ignored")


async def send_to_channel_row(row, title: str, content: str, daily_limit: int = DEFAULT_DAILY_LIMIT) -> None:
    """按数据库行发送，内部完成限流与配置解析。"""
    try:
        config = json.loads(row.config_json or "{}")
    except json.JSONDecodeError as exc:
        raise NotificationError("渠道配置损坏") from exc

    check_rate_limit(row.owner_id, row.id, daily_limit=daily_limit)

    if row.type == NOTIFY_SHARED_TARGET:
        await _send_via_shared_target(config, title, content)
        return

    await send_notification(row.type, config, title, content)


async def _send_via_shared_target(config: Dict[str, Any], title: str, content: str) -> None:
    """复用管理员已配置的渠道发送，凭据只保留在管理员配置中。"""
    channel_id = str(config.get("channel") or "").strip()
    account_id = str(config.get("account_id") or "default").strip() or "default"
    chat_id = str(config.get("chat_id") or "").strip()
    if not channel_id or not chat_id:
        raise NotificationError("推送目标配置不完整")

    from backend.modules.multiuser.settings import load_settings

    if channel_id not in (await load_settings()).notify_shared_channels:
        raise NotificationError("该渠道已停止共享")

    from backend.api.channels import get_channel_manager
    from backend.modules.channels.base import OutboundMessage

    try:
        manager = get_channel_manager()
    except Exception as exc:
        raise NotificationError(f"渠道管理器不可用: {exc}") from exc

    instance = manager.get_channel(channel_id, account_id=account_id)
    if instance is None:
        raise NotificationError(f"渠道 {channel_id}:{account_id} 未运行")

    text = f"{title}\n{content}".strip() if title else content
    try:
        await instance.send(
            OutboundMessage(
                channel=channel_id,
                chat_id=chat_id,
                content=text,
                metadata={"account_id": account_id},
            )
        )
    except Exception as exc:
        raise NotificationError(f"发送失败: {exc}") from exc
