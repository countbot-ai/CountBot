"""渠道扫码接入（Onboarding）：对齐 zcode 扫码绑定，支持 QQ/飞书/企业微信/钉钉；begin 返回二维码，poll 单次查询返回 pending/success/expired/error。"""

from __future__ import annotations

import base64
import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from loguru import logger

QQ_PORTAL_BASE = "https://q.qq.com"
QQ_BIND_CREATE_PATH = "/lite/create_bind_task"
QQ_BIND_POLL_PATH = "/lite/poll_bind_result"
# 必须使用 QQ 开放平台认可的 source（官方 OpenClaw connector 用 openclaw）；未注册的 source 会让手机 QQ 侧 SelectBindBot 鉴权返回 401。
QQ_QR_URL_TEMPLATE = (
    "https://q.qq.com/qqbot/openclaw/connect.html?task_id={task_id}&_wv=2&source=openclaw"
)
QQ_POLL_INTERVAL_SECONDS = 2

FEISHU_ACCOUNTS_URL = "https://accounts.feishu.cn"
LARK_ACCOUNTS_URL = "https://accounts.larksuite.com"
FEISHU_REGISTRATION_PATH = "/oauth/v1/app/registration"
FEISHU_REGISTRATION_SOURCE = "node-sdk/countbot"

WECOM_QR_GENERATE_URL = "https://work.weixin.qq.com/ai/qc/generate"
WECOM_QR_QUERY_URL = "https://work.weixin.qq.com/ai/qc/query_result"

DINGTALK_REGISTRATION_BASE = "https://oapi.dingtalk.com"
DINGTALK_REGISTRATION_SOURCE = "COUNTBOT"

ONBOARDING_CHANNELS = ("qq", "feishu", "wecom", "dingtalk")

_SESSION_TTL_SECONDS = 15 * 60
_REQUEST_TIMEOUT_SECONDS = 15.0

_SUCCESS_STATUSES = {"success"}
_TERMINAL_STATUSES = {"success", "expired", "error", "access_denied"}


@dataclass
class OnboardingSession:
    """一次扫码接入会话。"""

    session_key: str
    channel: str
    account_id: str
    started_at: float
    expires_at: float
    interval_seconds: float
    state: Dict[str, Any] = field(default_factory=dict)


_SESSIONS: Dict[str, OnboardingSession] = {}


# ----------------------------------------------------------------------
# 会话管理
# ----------------------------------------------------------------------


def _purge_expired_sessions(now: Optional[float] = None) -> None:
    """清理过期会话，避免二维码状态长期驻留内存。"""
    current = time.time() if now is None else now
    for session_key, session in list(_SESSIONS.items()):
        if session.expires_at <= current:
            _SESSIONS.pop(session_key, None)


def _drop_sessions_for_account(channel: str, account_id: str) -> None:
    """同一账号重新发起扫码时丢弃旧会话，防止旧二维码继续生效。"""
    for session_key, session in list(_SESSIONS.items()):
        if session.channel == channel and session.account_id == account_id:
            _SESSIONS.pop(session_key, None)


def drop_onboarding_session(session_key: str) -> None:
    """显式结束一个扫码会话（用户关闭二维码时调用）。"""
    _SESSIONS.pop(str(session_key or ""), None)


# ----------------------------------------------------------------------
# HTTP 辅助
# ----------------------------------------------------------------------


async def _request_json(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    **kwargs: Any,
) -> Tuple[httpx.Response, Dict[str, Any]]:
    """发起请求并尽量解析 JSON；非 JSON 响应返回空字典。"""
    timeout = kwargs.pop("timeout", _REQUEST_TIMEOUT_SECONDS)
    try:
        response = await client.request(method, url, timeout=timeout, **kwargs)
    except httpx.HTTPError as exc:
        raise RuntimeError(f"网络请求失败: {exc}") from exc

    payload: Dict[str, Any] = {}
    try:
        data = response.json()
        if isinstance(data, dict):
            payload = data
    except ValueError:
        payload = {}
    return response, payload


def _with_query(url: str, **params: Any) -> str:
    """在 URL 上合并查询参数，保留原参数。"""
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update({key: str(value) for key, value in params.items() if value is not None})
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


# ----------------------------------------------------------------------
# QQ 开放平台扫码绑定
# ----------------------------------------------------------------------


def _qq_headers() -> Dict[str, str]:
    return {
        "content-type": "application/json",
        # q.qq.com 缺少 Accept 会返回反爬挑战页。
        "accept": "application/json",
        "user-agent": "CountBot/1.0",
    }


def decrypt_qq_secret(encrypted_base64: str, key_base64: str) -> str:
    """解密 QQ 返回的 bot_encrypt_secret（AES-256-GCM，IV 12B + 密文 + TAG 16B）。"""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    raw = base64.b64decode(encrypted_base64)
    if len(raw) <= 28:
        raise ValueError("QQ 绑定密钥长度异常")
    key = base64.b64decode(key_base64)
    if len(key) != 32:
        raise ValueError("QQ 绑定密钥格式异常")
    iv, ciphertext = raw[:12], raw[12:]
    return AESGCM(key).decrypt(iv, ciphertext, None).decode("utf-8")


async def _begin_qq(client: httpx.AsyncClient) -> Dict[str, Any]:
    aes_key = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
    response, payload = await _request_json(
        client,
        "POST",
        f"{QQ_PORTAL_BASE}{QQ_BIND_CREATE_PATH}",
        headers=_qq_headers(),
        json={"key": aes_key},
    )
    data = payload.get("data") or {}
    if response.status_code >= 400 or int(payload.get("retcode") or 0) != 0:
        message = payload.get("msg") or f"HTTP {response.status_code}"
        raise RuntimeError(f"创建 QQ 绑定任务失败: {message}")

    task_id = str(data.get("task_id") or "").strip()
    if not task_id:
        raise RuntimeError("创建 QQ 绑定任务失败: 响应缺少 task_id")

    return {
        "qr_url": QQ_QR_URL_TEMPLATE.format(task_id=task_id),
        "interval": QQ_POLL_INTERVAL_SECONDS,
        "expires_in": 600,
        "state": {"task_id": task_id, "aes_key": aes_key},
    }


async def _poll_qq(client: httpx.AsyncClient, session: OnboardingSession) -> Dict[str, Any]:
    response, payload = await _request_json(
        client,
        "POST",
        f"{QQ_PORTAL_BASE}{QQ_BIND_POLL_PATH}",
        headers=_qq_headers(),
        json={"task_id": session.state.get("task_id")},
    )
    # q.qq.com poll_bind_result 频率限制返回非 0 retcode（可重试）；401/403 是鉴权失败，需直接提示用户。
    retcode = int(payload.get("retcode") or 0)
    if response.status_code >= 400 or retcode != 0:
        logger.debug(
            f"QQ poll_bind_result retcode={retcode} msg={payload.get('msg') or ''}"
        )
        if retcode in {401, 403}:
            return {
                "status": "error",
                "message": (
                    f"QQ 绑定鉴权失败 (retcode={retcode})，"
                    "请确认使用手机 QQ 扫码并保持登录状态"
                ),
            }
        return {
            "status": "pending",
            "interval": QQ_POLL_INTERVAL_SECONDS,
            "message": "等待扫码确认",
        }

    data = payload.get("data") or {}
    status = int(data.get("status") or 0)
    if status == 2:
        app_id = str(data.get("bot_appid") or "").strip()
        encrypted = str(data.get("bot_encrypt_secret") or "").strip()
        if not app_id or not encrypted:
            return {"status": "error", "message": "QQ 未返回机器人凭据"}
        try:
            app_secret = decrypt_qq_secret(encrypted, str(session.state.get("aes_key") or ""))
        except Exception as exc:  # noqa: BLE001 - 解密失败需要转成用户可读错误
            logger.warning(f"QQ 绑定密钥解密失败: {exc}")
            return {"status": "error", "message": "QQ 凭据解密失败，请重新扫码"}
        return {
            "status": "success",
            "message": "QQ 机器人绑定成功",
            "credentials": {"app_id": app_id, "secret": app_secret},
        }
    if status == 3:
        return {"status": "expired", "message": "二维码已过期，请重新发起扫码绑定"}
    return {
        "status": "pending",
        "interval": QQ_POLL_INTERVAL_SECONDS,
        "message": "等待扫码确认",
    }


# ----------------------------------------------------------------------
# 飞书应用扫码创建
# ----------------------------------------------------------------------


async def _feishu_post(
    client: httpx.AsyncClient,
    domain: str,
    body: Dict[str, str],
) -> Tuple[httpx.Response, Dict[str, Any]]:
    base_url = LARK_ACCOUNTS_URL if domain == "lark" else FEISHU_ACCOUNTS_URL
    return await _request_json(
        client,
        "POST",
        f"{base_url}{FEISHU_REGISTRATION_PATH}",
        headers={"content-type": "application/x-www-form-urlencoded"},
        data=body,
    )


async def _begin_feishu(client: httpx.AsyncClient) -> Dict[str, Any]:
    _, init_payload = await _feishu_post(client, "feishu", {"action": "init"})
    supported = init_payload.get("supported_auth_methods") or []
    if "client_secret" not in supported:
        raise RuntimeError("当前飞书环境不支持 client_secret 注册")

    response, begin_payload = await _feishu_post(
        client,
        "feishu",
        {
            "action": "begin",
            "archetype": "PersonalAgent",
            "auth_method": "client_secret",
            "request_user_info": "open_id",
        },
    )
    if response.status_code >= 400:
        raise RuntimeError(f"飞书扫码创建应用失败: HTTP {response.status_code}")

    device_code = str(begin_payload.get("device_code") or "").strip()
    verification_uri = str(begin_payload.get("verification_uri_complete") or "").strip()
    if not device_code or not verification_uri:
        raise RuntimeError("飞书扫码创建应用失败: 响应缺少 device_code")

    qr_url = _with_query(
        verification_uri,
        **{"from": "sdk", "source": FEISHU_REGISTRATION_SOURCE, "tp": "sdk"},
    )
    return {
        "qr_url": qr_url,
        "user_code": str(begin_payload.get("user_code") or "").strip(),
        "interval": int(begin_payload.get("interval") or 5),
        "expires_in": int(begin_payload.get("expire_in") or begin_payload.get("expires_in") or 600),
        "state": {"device_code": device_code, "domain": "feishu", "poll_domain": "feishu"},
    }


async def _poll_feishu(client: httpx.AsyncClient, session: OnboardingSession) -> Dict[str, Any]:
    poll_domain = str(session.state.get("poll_domain") or "feishu")
    response, payload = await _feishu_post(
        client,
        poll_domain,
        {"action": "poll", "device_code": str(session.state.get("device_code") or "")},
    )
    if response.status_code >= 400:
        return {"status": "pending", "interval": 5, "message": "等待扫码授权"}

    user_info = payload.get("user_info") or {}
    tenant_brand = str(user_info.get("tenant_brand") or "").lower()

    # Lark 租户需要切换到 accounts.larksuite.com 继续轮询。
    if tenant_brand == "lark" and poll_domain != "lark":
        session.state["poll_domain"] = "lark"
        return {"status": "pending", "interval": 2, "message": "正在切换 Lark 授权域"}

    client_id = str(payload.get("client_id") or "").strip()
    client_secret = str(payload.get("client_secret") or "").strip()
    if client_id and client_secret:
        if tenant_brand == "lark":
            # CountBot 的飞书渠道目前固定使用 open.feishu.cn，Lark 凭据无法直接复用。
            return {
                "status": "error",
                "message": "检测到 Lark 全球区租户，当前版本仅支持飞书中国区",
            }
        app_name = str(payload.get("app_name") or payload.get("client_name") or "").strip()
        return {
            "status": "success",
            "message": "飞书机器人创建成功",
            "credentials": {"app_id": client_id, "app_secret": client_secret},
            "display_name": app_name,
        }

    error = str(payload.get("error") or "").strip()
    if error in {"", "authorization_pending"}:
        return {"status": "pending", "interval": 5, "message": "等待扫码授权"}
    if error == "slow_down":
        return {"status": "pending", "interval": 10, "message": "扫码授权轮询过快，稍后重试"}
    if error == "access_denied":
        return {"status": "access_denied", "message": "用户拒绝了飞书授权"}
    if error == "expired_token":
        return {"status": "expired", "message": "二维码已过期，请重新发起扫码绑定"}
    description = str(payload.get("error_description") or "").strip()
    return {"status": "error", "message": f"飞书扫码失败: {error} {description}".strip()}


# ----------------------------------------------------------------------
# 企业微信智能机器人扫码创建
# ----------------------------------------------------------------------


async def _begin_wecom(client: httpx.AsyncClient) -> Dict[str, Any]:
    response, payload = await _request_json(
        client,
        "GET",
        f"{WECOM_QR_GENERATE_URL}?source=countbot",
        headers={"User-Agent": "CountBot/1.0"},
    )
    data = payload.get("data") or {}
    scode = str(data.get("scode") or "").strip()
    auth_url = str(data.get("auth_url") or data.get("authUrl") or "").strip()
    if response.status_code >= 400 or not scode or not auth_url:
        raise RuntimeError("企业微信扫码创建失败: 响应异常")
    return {
        "qr_url": auth_url,
        "interval": 3,
        "expires_in": 600,
        "state": {"scode": scode},
    }


async def _poll_wecom(client: httpx.AsyncClient, session: OnboardingSession) -> Dict[str, Any]:
    response, payload = await _request_json(
        client,
        "GET",
        f"{WECOM_QR_QUERY_URL}?scode={session.state.get('scode')}",
        headers={"User-Agent": "CountBot/1.0"},
    )
    # 频率限制或临时故障同样按 pending 处理，否则扫码后会停止轮询。
    if response.status_code >= 400:
        return {"status": "pending", "interval": 3, "message": "等待扫码确认"}

    data = payload.get("data") or {}
    if str(data.get("status") or "").lower() != "success":
        return {"status": "pending", "interval": 3, "message": "等待扫码确认"}

    bot_info = data.get("bot_info") or {}
    bot_id = str(bot_info.get("botid") or bot_info.get("bot_id") or "").strip()
    secret = str(bot_info.get("secret") or "").strip()
    if not bot_id or not secret:
        return {"status": "error", "message": "企业微信未返回机器人凭据"}
    return {
        "status": "success",
        "message": "企业微信机器人绑定成功",
        "credentials": {"bot_id": bot_id, "secret": secret},
    }


# ----------------------------------------------------------------------
# 钉钉扫码创建
# ----------------------------------------------------------------------


async def _begin_dingtalk(client: httpx.AsyncClient) -> Dict[str, Any]:
    response, init_payload = await _request_json(
        client,
        "POST",
        f"{DINGTALK_REGISTRATION_BASE}/app/registration/init",
        json={"source": DINGTALK_REGISTRATION_SOURCE},
    )
    if response.status_code >= 400 or int(init_payload.get("errcode") or 0) != 0:
        message = init_payload.get("errmsg") or f"HTTP {response.status_code}"
        raise RuntimeError(f"钉钉扫码初始化失败: {message}")

    nonce = str(init_payload.get("nonce") or "").strip()
    if not nonce:
        raise RuntimeError("钉钉扫码初始化失败: 响应缺少 nonce")

    response, begin_payload = await _request_json(
        client,
        "POST",
        f"{DINGTALK_REGISTRATION_BASE}/app/registration/begin",
        json={"nonce": nonce},
    )
    if response.status_code >= 400 or int(begin_payload.get("errcode") or 0) != 0:
        message = begin_payload.get("errmsg") or f"HTTP {response.status_code}"
        raise RuntimeError(f"钉钉扫码创建失败: {message}")

    device_code = str(begin_payload.get("device_code") or "").strip()
    verification_uri = str(begin_payload.get("verification_uri_complete") or "").strip()
    if not device_code or not verification_uri:
        raise RuntimeError("钉钉扫码创建失败: 响应缺少 device_code")

    return {
        "qr_url": verification_uri,
        "user_code": str(begin_payload.get("user_code") or "").strip(),
        "interval": int(begin_payload.get("interval") or 3),
        "expires_in": int(begin_payload.get("expires_in") or 600),
        "state": {"device_code": device_code},
    }


async def _poll_dingtalk(client: httpx.AsyncClient, session: OnboardingSession) -> Dict[str, Any]:
    response, payload = await _request_json(
        client,
        "POST",
        f"{DINGTALK_REGISTRATION_BASE}/app/registration/poll",
        json={"device_code": str(session.state.get("device_code") or "")},
    )
    if response.status_code >= 400 or int(payload.get("errcode") or 0) != 0:
        # 轮询接口的可重试错误不终止流程，交由会话 TTL 兜底。
        return {"status": "pending", "interval": 3, "message": "等待扫码确认"}

    status = str(payload.get("status") or "").strip().upper()
    if status == "SUCCESS":
        client_id = str(payload.get("client_id") or "").strip()
        client_secret = str(payload.get("client_secret") or "").strip()
        if not client_id or not client_secret:
            return {"status": "error", "message": "钉钉未返回机器人凭据"}
        return {
            "status": "success",
            "message": "钉钉机器人绑定成功",
            "credentials": {"client_id": client_id, "client_secret": client_secret},
        }
    if status == "FAIL":
        reason = str(payload.get("fail_reason") or "").strip()
        return {"status": "error", "message": f"钉钉扫码授权失败: {reason}".rstrip(": ")}
    if status == "EXPIRED":
        return {"status": "expired", "message": "二维码已过期，请重新发起扫码绑定"}
    return {"status": "pending", "interval": 3, "message": "等待扫码确认"}


_BEGINNERS = {
    "qq": _begin_qq,
    "feishu": _begin_feishu,
    "wecom": _begin_wecom,
    "dingtalk": _begin_dingtalk,
}

_POLLERS = {
    "qq": _poll_qq,
    "feishu": _poll_feishu,
    "wecom": _poll_wecom,
    "dingtalk": _poll_dingtalk,
}


# ----------------------------------------------------------------------
# 对外接口
# ----------------------------------------------------------------------


def supports_onboarding(channel: str) -> bool:
    return str(channel or "").strip().lower() in ONBOARDING_CHANNELS


async def begin_onboarding(
    channel: str,
    account_id: str,
    *,
    display_name: str = "",
    client: Optional[httpx.AsyncClient] = None,
) -> Dict[str, Any]:
    """发起扫码接入，返回二维码与轮询参数。"""
    normalized = str(channel or "").strip().lower()
    if normalized not in _BEGINNERS:
        raise ValueError(f"渠道 {channel} 不支持扫码接入")

    _purge_expired_sessions()
    normalized_account = str(account_id or "default").strip() or "default"
    _drop_sessions_for_account(normalized, normalized_account)

    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS, follow_redirects=True)
    try:
        result = await _BEGINNERS[normalized](http)
    finally:
        if owns_client:
            await http.aclose()

    session_key = uuid.uuid4().hex
    interval_seconds = float(result.get("interval") or 3)
    # 平台给的二维码有效期可能很长（例如钉钉 2 小时），但本地会话统一按 15 分钟兜底。
    expires_in = min(int(result.get("expires_in") or _SESSION_TTL_SECONDS), _SESSION_TTL_SECONDS)
    session_state = dict(result.get("state") or {})
    if str(display_name or "").strip():
        session_state["display_name"] = str(display_name).strip()
    _SESSIONS[session_key] = OnboardingSession(
        session_key=session_key,
        channel=normalized,
        account_id=normalized_account,
        started_at=time.time(),
        expires_at=time.time() + expires_in,
        interval_seconds=interval_seconds,
        state=session_state,
    )

    logger.info(f"Channel onboarding started: {normalized}:{normalized_account}")
    return {
        "session_key": session_key,
        "channel": normalized,
        "account_id": normalized_account,
        "qr_url": result["qr_url"],
        "user_code": str(result.get("user_code") or ""),
        "interval": int(interval_seconds),
        "expires_in": expires_in,
    }


async def poll_onboarding(
    session_key: str,
    *,
    client: Optional[httpx.AsyncClient] = None,
) -> Dict[str, Any]:
    """查询扫码结果；终态会话会被立即清理。"""
    _purge_expired_sessions()
    session = _SESSIONS.get(str(session_key or ""))
    if session is None:
        return {
            "status": "expired",
            "message": "二维码已过期，请重新发起扫码绑定",
            "interval": 0,
        }

    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS, follow_redirects=True)
    try:
        result = await _POLLERS[session.channel](http, session)
    except RuntimeError as exc:
        # 网络异常按可重试处理，UI 会继续轮询直到会话过期。
        logger.warning(f"Channel onboarding poll failed: {session.channel}:{session.account_id}: {exc}")
        result = {
            "status": "pending",
            "interval": int(session.interval_seconds or 3),
            "message": str(exc),
        }
    finally:
        if owns_client:
            await http.aclose()

    status = str(result.get("status") or "pending")
    if status in _TERMINAL_STATUSES:
        _SESSIONS.pop(session.session_key, None)
        logger.info(f"Channel onboarding finished: {session.channel}:{session.account_id}: {status}")

    if status in _SUCCESS_STATUSES:
        result.setdefault("channel", session.channel)
        result.setdefault("account_id", session.account_id)
        if session.state.get("display_name"):
            result.setdefault("display_name", session.state["display_name"])
    return result
