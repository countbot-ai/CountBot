"""微信渠道模块

基于腾讯微信 iLink Bot HTTP JSON API 实现：
- 扫码登录获取 bot token
- `getupdates` 长轮询接收入站消息
- `sendmessage` 发送文本 / 图片 / 视频 / 文件
- 微信 CDN AES-128-ECB 上传下载

当前仅支持微信私聊场景，不支持群聊。
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import html
import json
import random
import re
import secrets
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx
from Crypto.Cipher import AES
from loguru import logger

from backend.modules.channels.base import BaseChannel, OutboundMessage
from backend.modules.channels.media_utils import (
    download_to_temp,
    format_inbound_media_text,
    get_channel_temp_dir,
    save_bytes_to_temp,
)

DEFAULT_BASE_URL = "https://ilinkai.weixin.qq.com"
DEFAULT_CDN_BASE_URL = "https://novac2c.cdn.weixin.qq.com/c2c"

DEFAULT_LONG_POLL_TIMEOUT_MS = 35_000
DEFAULT_API_TIMEOUT_MS = 15_000
DEFAULT_LIGHT_API_TIMEOUT_MS = 10_000
LOGIN_TTL_MS = 5 * 60_000
SESSION_PAUSE_DURATION_MS = 60 * 60_000
CONFIG_CACHE_TTL_MS = 24 * 60 * 60_000
CONFIG_CACHE_INITIAL_RETRY_MS = 2_000
CONFIG_CACHE_MAX_RETRY_MS = 60 * 60_000
TYPING_KEEPALIVE_INTERVAL_MS = 5_000

MESSAGE_TYPE_USER = 1
MESSAGE_TYPE_BOT = 2

MESSAGE_ITEM_TEXT = 1
MESSAGE_ITEM_IMAGE = 2
MESSAGE_ITEM_VOICE = 3
MESSAGE_ITEM_FILE = 4
MESSAGE_ITEM_VIDEO = 5

UPLOAD_MEDIA_IMAGE = 1
UPLOAD_MEDIA_VIDEO = 2
UPLOAD_MEDIA_FILE = 3

SESSION_EXPIRED_ERRCODE = -14
TYPING_STATUS_TYPING = 1
TYPING_STATUS_CANCEL = 2

_IMAGE_SIGNATURES = {
    b"\x89PNG\r\n\x1a\n": ("image/png", "png"),
    b"\xff\xd8\xff": ("image/jpeg", "jpg"),
    b"GIF87a": ("image/gif", "gif"),
    b"GIF89a": ("image/gif", "gif"),
    b"RIFF": ("image/webp", "webp"),
}

_MIME_BY_EXT = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".json": "application/json",
    ".md": "text/markdown",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".zip": "application/zip",
    ".rar": "application/vnd.rar",
    ".7z": "application/x-7z-compressed",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".mkv": "video/x-matroska",
    ".webm": "video/webm",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".amr": "audio/amr",
    ".silk": "audio/silk",
}

_MARKDOWN_FENCE_RE = re.compile(r"```[^\n]*\n?([\s\S]*?)```")
_MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_MARKDOWN_TABLE_SEPARATOR_RE = re.compile(r"^\|[\s:|-]+\|$", re.MULTILINE)
_MARKDOWN_TABLE_ROW_RE = re.compile(r"^\|(.+)\|$", re.MULTILINE)
_MARKDOWN_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s*", re.MULTILINE)
_MARKDOWN_BLOCKQUOTE_RE = re.compile(r"^\s{0,3}>\s?", re.MULTILINE)
_MARKDOWN_UNORDERED_LIST_RE = re.compile(r"^\s*[-+*]\s+", re.MULTILINE)
_MARKDOWN_ORDERED_LIST_RE = re.compile(r"^\s*\d+\.\s+", re.MULTILINE)
_MARKDOWN_INLINE_CODE_RE = re.compile(r"`([^`]*)`")
_MARKDOWN_STRONG_RE = re.compile(r"(\*\*|__)(.*?)\1", re.DOTALL)
_MARKDOWN_EM_RE = re.compile(r"(\*|_)(.*?)\1", re.DOTALL)
_MARKDOWN_STRIKE_RE = re.compile(r"~~(.*?)~~", re.DOTALL)
_MARKDOWN_HR_RE = re.compile(r"^\s{0,3}([-*_]\s*){3,}$", re.MULTILINE)
_MARKDOWN_HTML_TAG_RE = re.compile(r"<[^>]+>")
_MARKDOWN_MULTI_NEWLINES_RE = re.compile(r"\n{3,}")


class WeChatApiError(RuntimeError):
    """微信 API 请求失败。"""


@dataclass
class WeChatLoginSession:
    """扫码登录会话。"""

    session_key: str
    account_id: str
    base_url: str
    qrcode: str
    qrcode_url: str
    started_at: float
    config_snapshot: Dict[str, Any] = field(default_factory=dict)


_ACTIVE_LOGIN_SESSIONS: Dict[str, WeChatLoginSession] = {}
_PAUSED_SESSIONS_UNTIL_MS: Dict[str, float] = {}


@dataclass
class WeChatConfigCacheEntry:
    """微信 getconfig 缓存项。"""

    typing_ticket: str = ""
    ever_succeeded: bool = False
    next_fetch_at_ms: float = 0.0
    retry_delay_ms: int = CONFIG_CACHE_INITIAL_RETRY_MS


def _ensure_trailing_slash(url: str) -> str:
    normalized = str(url or "").strip() or DEFAULT_BASE_URL
    return normalized if normalized.endswith("/") else f"{normalized}/"


def pause_wechat_session(account_id: str) -> None:
    """将微信账号标记为登录态暂停。"""
    _PAUSED_SESSIONS_UNTIL_MS[account_id] = (time.time() * 1000) + SESSION_PAUSE_DURATION_MS


def clear_wechat_session_pause(account_id: str) -> None:
    """清除微信账号暂停状态。"""
    _PAUSED_SESSIONS_UNTIL_MS.pop(account_id, None)


def get_wechat_session_pause_remaining_ms(account_id: str) -> int:
    """返回微信账号暂停剩余时长。"""
    until_ms = _PAUSED_SESSIONS_UNTIL_MS.get(account_id)
    if until_ms is None:
        return 0
    remaining = int(until_ms - (time.time() * 1000))
    if remaining <= 0:
        _PAUSED_SESSIONS_UNTIL_MS.pop(account_id, None)
        return 0
    return remaining


def is_wechat_session_paused(account_id: str) -> bool:
    """判断微信账号是否处于暂停状态。"""
    return get_wechat_session_pause_remaining_ms(account_id) > 0


def _assert_wechat_session_active(account_id: str) -> None:
    """当微信账号处于暂停状态时抛出异常。"""
    remaining_ms = get_wechat_session_pause_remaining_ms(account_id)
    if remaining_ms <= 0:
        return
    remaining_min = max(1, int((remaining_ms + 59_999) / 60_000))
    raise WeChatApiError(
        f"微信登录态已暂停，约 {remaining_min} 分钟后重试或重新扫码登录"
    )


def _is_session_expired_payload(data: Dict[str, Any]) -> bool:
    """判断微信业务响应是否表示登录态过期。"""
    errcode = int(data.get("errcode") or 0)
    ret = int(data.get("ret") or 0)
    return errcode == SESSION_EXPIRED_ERRCODE or ret == SESSION_EXPIRED_ERRCODE


def _raise_if_api_error(endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """校验微信业务响应。"""
    errcode = int(data.get("errcode") or 0)
    ret = int(data.get("ret") or 0)
    if errcode or ret:
        errmsg = str(data.get("errmsg") or "").strip()
        raise WeChatApiError(
            f"{endpoint} failed: ret={ret} errcode={errcode} {errmsg}".strip()
        )
    return data


def _random_wechat_uin() -> str:
    value = int.from_bytes(secrets.token_bytes(4), "big")
    return base64.b64encode(str(value).encode("utf-8")).decode("utf-8")


def _build_headers(body: str, token: Optional[str] = None) -> Dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "Content-Length": str(len(body.encode("utf-8"))),
        "X-WECHAT-UIN": _random_wechat_uin(),
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def _api_post_json(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    endpoint: str,
    payload: Dict[str, Any],
    token: Optional[str] = None,
    timeout_ms: int = DEFAULT_API_TIMEOUT_MS,
) -> Dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False)
    url = f"{_ensure_trailing_slash(base_url)}{endpoint}"
    response = await client.post(
        url,
        content=body.encode("utf-8"),
        headers=_build_headers(body, token=token),
        timeout=timeout_ms / 1000,
    )
    response.raise_for_status()
    if not response.text:
        return {}
    data = response.json()
    if not isinstance(data, dict):
        raise WeChatApiError(f"Invalid JSON response from {endpoint}")
    return data


async def _api_get_json(
    client: httpx.AsyncClient,
    *,
    url: str,
    timeout_ms: int = DEFAULT_LIGHT_API_TIMEOUT_MS,
    headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    response = await client.get(url, headers=headers or {}, timeout=timeout_ms / 1000)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise WeChatApiError("Invalid JSON response")
    return data


def _build_base_info() -> Dict[str, str]:
    return {"channel_version": "countbot-wechat"}


async def get_wechat_updates(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    token: str,
    get_updates_buf: str,
    timeout_ms: int = DEFAULT_LONG_POLL_TIMEOUT_MS,
) -> Dict[str, Any]:
    try:
        return await _api_post_json(
            client,
            base_url=base_url,
            endpoint="ilink/bot/getupdates",
            payload={
                "get_updates_buf": get_updates_buf or "",
                "base_info": _build_base_info(),
            },
            token=token,
            timeout_ms=timeout_ms,
        )
    except httpx.ReadTimeout:
        return {"ret": 0, "msgs": [], "get_updates_buf": get_updates_buf}


async def send_wechat_message_api(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    token: str,
    payload: Dict[str, Any],
    timeout_ms: int = DEFAULT_API_TIMEOUT_MS,
) -> None:
    response = await _api_post_json(
        client,
        base_url=base_url,
        endpoint="ilink/bot/sendmessage",
        payload={**payload, "base_info": _build_base_info()},
        token=token,
        timeout_ms=timeout_ms,
    )
    _raise_if_api_error("ilink/bot/sendmessage", response)


async def get_wechat_upload_url(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    token: str,
    payload: Dict[str, Any],
    timeout_ms: int = DEFAULT_API_TIMEOUT_MS,
) -> Dict[str, Any]:
    response = await _api_post_json(
        client,
        base_url=base_url,
        endpoint="ilink/bot/getuploadurl",
        payload={**payload, "base_info": _build_base_info()},
        token=token,
        timeout_ms=timeout_ms,
    )
    return _raise_if_api_error("ilink/bot/getuploadurl", response)


async def get_wechat_config_api(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    token: str,
    ilink_user_id: str,
    context_token: Optional[str] = None,
    timeout_ms: int = DEFAULT_LIGHT_API_TIMEOUT_MS,
) -> Dict[str, Any]:
    response = await _api_post_json(
        client,
        base_url=base_url,
        endpoint="ilink/bot/getconfig",
        payload={
            "ilink_user_id": ilink_user_id,
            "context_token": context_token or "",
            "base_info": _build_base_info(),
        },
        token=token,
        timeout_ms=timeout_ms,
    )
    return _raise_if_api_error("ilink/bot/getconfig", response)


async def send_wechat_typing_api(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    token: str,
    ilink_user_id: str,
    typing_ticket: str,
    status: int,
    timeout_ms: int = DEFAULT_LIGHT_API_TIMEOUT_MS,
) -> Dict[str, Any]:
    response = await _api_post_json(
        client,
        base_url=base_url,
        endpoint="ilink/bot/sendtyping",
        payload={
            "ilink_user_id": ilink_user_id,
            "typing_ticket": typing_ticket,
            "status": status,
            "base_info": _build_base_info(),
        },
        token=token,
        timeout_ms=timeout_ms,
    )
    return _raise_if_api_error("ilink/bot/sendtyping", response)


def _build_cdn_download_url(cdn_base_url: str, encrypted_query_param: str) -> str:
    return (
        f"{cdn_base_url.rstrip('/')}/download"
        f"?encrypted_query_param={quote(str(encrypted_query_param or ''))}"
    )


def _build_cdn_upload_url(cdn_base_url: str, upload_param: str, filekey: str) -> str:
    return (
        f"{cdn_base_url.rstrip('/')}/upload"
        f"?encrypted_query_param={quote(str(upload_param or ''))}"
        f"&filekey={quote(str(filekey or ''))}"
    )


def _aes_ecb_encrypt(plaintext: bytes, key: bytes) -> bytes:
    cipher = AES.new(key, AES.MODE_ECB)
    pad_len = 16 - (len(plaintext) % 16)
    return cipher.encrypt(plaintext + bytes([pad_len]) * pad_len)


def _aes_ecb_decrypt(ciphertext: bytes, key: bytes) -> bytes:
    cipher = AES.new(key, AES.MODE_ECB)
    padded = cipher.decrypt(ciphertext)
    pad_len = padded[-1] if padded else 0
    if pad_len < 1 or pad_len > 16:
        return padded
    return padded[:-pad_len]


def _aes_padded_size(size: int) -> int:
    return ((size // 16) + 1) * 16


def _encode_outbound_aes_key(aes_key: bytes) -> str:
    return base64.b64encode(aes_key.hex().encode("ascii")).decode("utf-8")


def _parse_inbound_aes_key(aes_key_base64: str) -> bytes:
    decoded = base64.b64decode(aes_key_base64)
    if len(decoded) == 16:
        return decoded
    if len(decoded) == 32:
        text = decoded.decode("ascii", errors="ignore")
        if len(text) == 32 and all(ch in "0123456789abcdefABCDEF" for ch in text):
            return bytes.fromhex(text)
    raise WeChatApiError("Invalid CDN aes_key")


async def _upload_buffer_to_cdn(
    client: httpx.AsyncClient,
    *,
    plaintext: bytes,
    upload_param: str,
    filekey: str,
    cdn_base_url: str,
    aes_key: bytes,
) -> str:
    ciphertext = _aes_ecb_encrypt(plaintext, aes_key)
    url = _build_cdn_upload_url(cdn_base_url, upload_param, filekey)
    last_error: Optional[Exception] = None
    for _ in range(3):
        try:
            response = await client.post(
                url,
                content=ciphertext,
                headers={"Content-Type": "application/octet-stream"},
                timeout=DEFAULT_API_TIMEOUT_MS / 1000,
            )
            if response.status_code >= 400 and response.status_code < 500:
                text = response.headers.get("x-error-message") or response.text
                raise WeChatApiError(f"CDN upload rejected: {text}")
            response.raise_for_status()
            download_param = response.headers.get("x-encrypted-param")
            if not download_param:
                raise WeChatApiError("CDN response missing x-encrypted-param")
            return download_param
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    raise last_error or WeChatApiError("CDN upload failed")


async def _download_plain_cdn_buffer(
    client: httpx.AsyncClient,
    *,
    cdn_base_url: str,
    encrypted_query_param: str,
) -> bytes:
    url = _build_cdn_download_url(cdn_base_url, encrypted_query_param)
    response = await client.get(url, timeout=DEFAULT_API_TIMEOUT_MS / 1000)
    response.raise_for_status()
    return response.content


async def _download_and_decrypt_cdn_buffer(
    client: httpx.AsyncClient,
    *,
    cdn_base_url: str,
    encrypted_query_param: str,
    aes_key_base64: str,
) -> bytes:
    encrypted = await _download_plain_cdn_buffer(
        client,
        cdn_base_url=cdn_base_url,
        encrypted_query_param=encrypted_query_param,
    )
    return _aes_ecb_decrypt(encrypted, _parse_inbound_aes_key(aes_key_base64))


def _guess_image_type(data: bytes) -> tuple[str, str]:
    for signature, result in _IMAGE_SIGNATURES.items():
        if data.startswith(signature):
            if signature == b"RIFF" and b"WEBP" not in data[:16]:
                continue
            return result
    return ("image/jpeg", "jpg")


def _markdown_to_plain_text(text: str) -> str:
    """Convert markdown-formatted replies to plain text for WeChat delivery."""
    result = str(text or "")
    if not result.strip():
        return ""

    result = _MARKDOWN_FENCE_RE.sub(lambda match: match.group(1).strip(), result)
    result = _MARKDOWN_IMAGE_RE.sub("", result)
    result = _MARKDOWN_LINK_RE.sub(r"\1", result)
    result = _MARKDOWN_TABLE_SEPARATOR_RE.sub("", result)
    result = _MARKDOWN_TABLE_ROW_RE.sub(
        lambda match: "  ".join(
            cell.strip() for cell in match.group(1).split("|")
        ).strip(),
        result,
    )
    result = _MARKDOWN_INLINE_CODE_RE.sub(r"\1", result)
    result = _MARKDOWN_HEADING_RE.sub("", result)
    result = _MARKDOWN_BLOCKQUOTE_RE.sub("", result)
    result = _MARKDOWN_UNORDERED_LIST_RE.sub("", result)
    result = _MARKDOWN_ORDERED_LIST_RE.sub("", result)
    result = _MARKDOWN_HR_RE.sub("", result)
    result = _MARKDOWN_STRONG_RE.sub(r"\2", result)
    result = _MARKDOWN_EM_RE.sub(r"\2", result)
    result = _MARKDOWN_STRIKE_RE.sub(r"\1", result)
    result = _MARKDOWN_HTML_TAG_RE.sub("", result)
    result = result.replace("\\*", "*").replace("\\_", "_").replace("\\`", "`")
    result = result.replace("\\[", "[").replace("\\]", "]").replace("\\(", "(").replace("\\)", ")")
    result = result.replace("\\#", "#").replace("\\>", ">").replace("\\-", "-")
    result = html.unescape(result)
    result = _MARKDOWN_MULTI_NEWLINES_RE.sub("\n\n", result)
    return result.strip()


def _mime_from_path(file_path: str) -> str:
    suffix = Path(file_path).suffix.lower()
    return _MIME_BY_EXT.get(suffix, "application/octet-stream")


async def _download_remote_media_to_temp(
    client: httpx.AsyncClient,
    url: str,
) -> str:
    return await download_to_temp(
        "wechat",
        url,
        client=client,
        prefix="wechat_remote",
    )


def _load_sync_buffer(account_id: str) -> str:
    state_dir = get_channel_temp_dir("wechat", "state")
    path = state_dir / f"sync_{account_id}.txt"
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[wechat] failed to load sync buffer for {account_id}: {exc}")
        return ""


def _save_sync_buffer(account_id: str, value: str) -> None:
    state_dir = get_channel_temp_dir("wechat", "state")
    path = state_dir / f"sync_{account_id}.txt"
    try:
        path.write_text(value, encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[wechat] failed to save sync buffer for {account_id}: {exc}")


def _purge_expired_login_sessions() -> None:
    now = time.time()
    expired_keys = [
        key for key, session in _ACTIVE_LOGIN_SESSIONS.items()
        if now - session.started_at > LOGIN_TTL_MS / 1000
    ]
    for key in expired_keys:
        _ACTIVE_LOGIN_SESSIONS.pop(key, None)


async def start_wechat_qr_login(
    *,
    account_id: str,
    base_url: str,
    config_snapshot: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    _purge_expired_login_sessions()
    session_key = str(uuid.uuid4())
    base = _ensure_trailing_slash(base_url)
    url = f"{base}ilink/bot/get_bot_qrcode?bot_type=3"

    async with httpx.AsyncClient(follow_redirects=True) as client:
        data = await _api_get_json(client, url=url)

    qrcode = str(data.get("qrcode") or "").strip()
    qrcode_url = str(data.get("qrcode_img_content") or "").strip()
    if not qrcode or not qrcode_url:
        raise WeChatApiError("微信登录二维码获取失败")

    _ACTIVE_LOGIN_SESSIONS[session_key] = WeChatLoginSession(
        session_key=session_key,
        account_id=account_id,
        base_url=base_url,
        qrcode=qrcode,
        qrcode_url=qrcode_url,
        started_at=time.time(),
        config_snapshot=dict(config_snapshot or {}),
    )

    return {
        "session_key": session_key,
        "qrcode_url": qrcode_url,
        "account_id": account_id,
    }


async def poll_wechat_qr_login(session_key: str) -> Dict[str, Any]:
    _purge_expired_login_sessions()
    session = _ACTIVE_LOGIN_SESSIONS.get(session_key)
    if not session:
        return {"success": False, "status": "expired", "message": "二维码已过期，请重新扫码登录"}

    base = _ensure_trailing_slash(session.base_url)
    url = f"{base}ilink/bot/get_qrcode_status?qrcode={quote(session.qrcode)}"
    headers = {"iLink-App-ClientVersion": "1"}

    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            data = await _api_get_json(
                client,
                url=url,
                timeout_ms=DEFAULT_LONG_POLL_TIMEOUT_MS,
                headers=headers,
            )
        except httpx.ReadTimeout:
            return {
                "success": True,
                "status": "wait",
                "message": "等待扫码确认",
                "session_key": session_key,
            }

    status = str(data.get("status") or "wait").strip().lower()
    if status == "confirmed":
        _ACTIVE_LOGIN_SESSIONS.pop(session_key, None)
        return {
            "success": True,
            "status": "confirmed",
            "message": "微信连接成功",
            "session_key": session_key,
            "account_id": session.account_id,
            "config_snapshot": session.config_snapshot,
            "result": {
                "token": str(data.get("bot_token") or "").strip(),
                "base_url": str(data.get("baseurl") or session.base_url or DEFAULT_BASE_URL).strip(),
                "login_bot_id": str(data.get("ilink_bot_id") or "").strip(),
                "login_user_id": str(data.get("ilink_user_id") or "").strip(),
            },
        }

    if status == "expired":
        _ACTIVE_LOGIN_SESSIONS.pop(session_key, None)
        return {
            "success": False,
            "status": "expired",
            "message": "二维码已过期，请重新扫码登录",
        }

    message = "等待扫码确认" if status == "wait" else "已扫码，请在微信里确认授权"
    return {
        "success": True,
        "status": status,
        "message": message,
        "session_key": session_key,
    }


def _extract_text_from_item_list(item_list: List[Dict[str, Any]]) -> str:
    for item in item_list:
        item_type = int(item.get("type") or 0)
        if item_type == MESSAGE_ITEM_TEXT:
            text = str(((item.get("text_item") or {}).get("text")) or "").strip()
            if not text:
                continue
            ref_msg = item.get("ref_msg") or {}
            if not ref_msg:
                return text
            title = str(ref_msg.get("title") or "").strip()
            ref_item = ref_msg.get("message_item")
            ref_text = ""
            if isinstance(ref_item, dict):
                ref_text = _extract_text_from_item_list([ref_item])
            prefix_parts = [part for part in [title, ref_text] if part]
            if not prefix_parts:
                return text
            return f"[引用: {' | '.join(prefix_parts)}]\n{text}"
        if item_type == MESSAGE_ITEM_VOICE:
            voice_text = str(((item.get("voice_item") or {}).get("text")) or "").strip()
            if voice_text:
                return voice_text
    return ""


class WeChatChannel(BaseChannel):
    """微信渠道。"""

    name = "wechat"

    def __init__(self, config: Any):
        super().__init__(config)
        self.base_url = str(getattr(config, "base_url", "") or DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL
        self.cdn_base_url = str(getattr(config, "cdn_base_url", "") or DEFAULT_CDN_BASE_URL).strip() or DEFAULT_CDN_BASE_URL
        self.token = str(getattr(config, "token", "") or "").strip()
        self._http: Optional[httpx.AsyncClient] = None
        self._poll_task: Optional[asyncio.Task] = None
        self._context_tokens: OrderedDict[str, str] = OrderedDict()
        self._processed_ids: OrderedDict[str, None] = OrderedDict()
        self._config_cache: Dict[str, WeChatConfigCacheEntry] = {}
        self._typing_tasks: Dict[str, asyncio.Task] = {}
        self._last_runtime_note: str = ""

    def _mark_session_paused(self, reason: str) -> None:
        """写入当前实例的暂停状态说明。"""
        pause_wechat_session(self.account_id)
        pause_remaining_ms = get_wechat_session_pause_remaining_ms(self.account_id)
        self._last_runtime_note = (
            f"{reason}，暂停中，约 {max(1, int((pause_remaining_ms + 59_999) / 60_000))} 分钟后重试"
        )

    def _handle_possible_session_expiry(self, exc: Exception, *, reason: str) -> bool:
        """遇到登录态过期时写回暂停状态。"""
        if str(SESSION_EXPIRED_ERRCODE) not in str(exc):
            return False
        self._mark_session_paused(reason)
        return True

    async def start(self) -> None:
        if not self.token:
            logger.warning(f"[wechat:{self.account_id}] token 未配置，跳过启动")
            return

        if self._running:
            return

        self._http = httpx.AsyncClient(follow_redirects=True)
        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        if is_wechat_session_paused(self.account_id):
            remaining_ms = get_wechat_session_pause_remaining_ms(self.account_id)
            self._last_runtime_note = (
                f"登录态暂停中，约 {max(1, int((remaining_ms + 59_999) / 60_000))} 分钟后重试"
            )
        else:
            self._last_runtime_note = "微信渠道已连接"
        logger.info(f"[wechat:{self.account_id}] 微信渠道已启动")

    async def stop(self) -> None:
        self._running = False
        typing_tasks = list(self._typing_tasks.values())
        self._typing_tasks.clear()
        for task in typing_tasks:
            task.cancel()
        if typing_tasks:
            await asyncio.gather(*typing_tasks, return_exceptions=True)
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None
        if self._http:
            await self._http.aclose()
            self._http = None
        logger.info(f"[wechat:{self.account_id}] 微信渠道已停止")

    async def send(self, msg: OutboundMessage) -> None:
        if not self._http:
            raise WeChatApiError("微信渠道未启动")
        if not self.token:
            raise WeChatApiError("微信 token 未配置")
        _assert_wechat_session_active(self.account_id)

        try:
            context_token = str((msg.metadata or {}).get("context_token") or "").strip()
            if not context_token:
                context_token = self._context_tokens.get(str(msg.chat_id), "")
            if not context_token:
                raise WeChatApiError("当前用户没有可用的微信会话上下文，请先由该用户发起一条消息")

            text_content = _markdown_to_plain_text(msg.content)
            media_items = list(msg.media or [])
            if media_items:
                sent_text = False
                for index, media_path in enumerate(media_items):
                    caption = text_content if text_content and not sent_text else ""
                    await self._send_media_file(
                        to_user_id=str(msg.chat_id),
                        file_path=media_path,
                        text=caption,
                        context_token=context_token,
                    )
                    sent_text = sent_text or bool(caption)
                if text_content and not sent_text:
                    await self._send_text(
                        to_user_id=str(msg.chat_id),
                        text=text_content,
                        context_token=context_token,
                    )
                return

            await self._send_text(
                to_user_id=str(msg.chat_id),
                text=text_content,
                context_token=context_token,
            )
        except Exception as exc:
            self._handle_possible_session_expiry(exc, reason="发送消息时登录态过期")
            raise

    async def test_connection(self) -> Dict[str, Any]:
        if not self.token:
            return {"success": False, "message": "微信 token 未配置，请先扫码登录"}

        pause_remaining_ms = get_wechat_session_pause_remaining_ms(self.account_id)
        if pause_remaining_ms > 0:
            pause_minutes = max(1, int((pause_remaining_ms + 59_999) / 60_000))
            return {
                "success": False,
                "message": f"微信登录态已暂停，请重新扫码登录或等待约 {pause_minutes} 分钟",
                "bot_info": {
                    "status": "session_paused",
                    "base_url": self.base_url,
                    "login_bot_id": str(getattr(self.config, "login_bot_id", "") or ""),
                    "login_user_id": str(getattr(self.config, "login_user_id", "") or ""),
                    "pause_remaining_ms": pause_remaining_ms,
                },
            }

        async with httpx.AsyncClient(follow_redirects=True) as client:
            try:
                resp = await get_wechat_updates(
                    client,
                    base_url=self.base_url,
                    token=self.token,
                    get_updates_buf="",
                    timeout_ms=2_000,
                )
            except httpx.HTTPStatusError as exc:
                return {
                    "success": False,
                    "message": f"微信接口返回异常: HTTP {exc.response.status_code}",
                }
            except Exception as exc:  # noqa: BLE001
                return {"success": False, "message": f"微信连接失败: {exc}"}

        errcode = int(resp.get("errcode") or 0)
        ret = int(resp.get("ret") or 0)
        if errcode == SESSION_EXPIRED_ERRCODE or ret == SESSION_EXPIRED_ERRCODE:
            return {"success": False, "message": "微信登录态已过期，请重新扫码登录"}
        if errcode or ret:
            return {
                "success": False,
                "message": f"微信接口返回错误: ret={ret} errcode={errcode} {resp.get('errmsg') or ''}".strip(),
            }

        return {
            "success": True,
            "message": "微信连接正常",
            "bot_info": {
                "status": "connected",
                "base_url": self.base_url,
                "login_bot_id": str(getattr(self.config, "login_bot_id", "") or ""),
                "login_user_id": str(getattr(self.config, "login_user_id", "") or ""),
            },
        }

    async def _poll_loop(self) -> None:
        assert self._http is not None
        get_updates_buf = _load_sync_buffer(self.account_id)
        timeout_ms = DEFAULT_LONG_POLL_TIMEOUT_MS

        try:
            while self._running:
                pause_remaining_ms = get_wechat_session_pause_remaining_ms(self.account_id)
                if pause_remaining_ms > 0:
                    self._last_runtime_note = (
                        f"登录态暂停中，约 {max(1, int((pause_remaining_ms + 59_999) / 60_000))} 分钟后重试"
                    )
                    await asyncio.sleep(min(max(pause_remaining_ms / 1000, 1), 30))
                    continue

                response = await get_wechat_updates(
                    self._http,
                    base_url=self.base_url,
                    token=self.token,
                    get_updates_buf=get_updates_buf,
                    timeout_ms=timeout_ms,
                )

                errcode = int(response.get("errcode") or 0)
                ret = int(response.get("ret") or 0)
                if errcode == SESSION_EXPIRED_ERRCODE or ret == SESSION_EXPIRED_ERRCODE:
                    self._mark_session_paused("登录态过期")
                    pause_remaining_ms = get_wechat_session_pause_remaining_ms(self.account_id)
                    logger.warning(
                        f"[wechat:{self.account_id}] 登录态过期，暂停出站与轮询约 "
                        f"{max(1, int((pause_remaining_ms + 59_999) / 60_000))} 分钟"
                    )
                    continue
                if errcode or ret:
                    logger.warning(
                        f"[wechat:{self.account_id}] getupdates failed: ret={ret}, "
                        f"errcode={errcode}, errmsg={response.get('errmsg')}"
                    )
                    await asyncio.sleep(2)
                    continue

                suggested_timeout = int(response.get("longpolling_timeout_ms") or 0)
                if suggested_timeout > 0:
                    timeout_ms = suggested_timeout
                self._last_runtime_note = "微信渠道已连接"

                next_buf = str(response.get("get_updates_buf") or "").strip()
                if next_buf:
                    get_updates_buf = next_buf
                    _save_sync_buffer(self.account_id, next_buf)

                for raw_msg in response.get("msgs") or []:
                    if not isinstance(raw_msg, dict):
                        continue
                    await self._handle_inbound_wechat_message(raw_msg)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            self._last_runtime_note = f"长轮询异常: {exc}"
            logger.exception(f"[wechat:{self.account_id}] 长轮询异常: {exc}")
        finally:
            self._running = False

    def get_runtime_status(self) -> Dict[str, Any]:
        """返回微信渠道运行时状态。"""
        pause_remaining_ms = get_wechat_session_pause_remaining_ms(self.account_id)
        paused = pause_remaining_ms > 0
        return {
            "paused": paused,
            "pause_remaining_ms": pause_remaining_ms,
            "note": self._last_runtime_note,
            "healthy_running": bool(self._running and not paused),
        }

    async def _get_cached_user_config(
        self,
        *,
        user_id: str,
        context_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """获取微信用户侧配置，包含 typing_ticket 缓存。"""
        if not self._http or not user_id:
            return {"typing_ticket": ""}
        _assert_wechat_session_active(self.account_id)

        now_ms = time.time() * 1000
        entry = self._config_cache.get(user_id)
        should_fetch = entry is None or now_ms >= entry.next_fetch_at_ms

        if should_fetch:
            fetch_ok = False
            try:
                resp = await get_wechat_config_api(
                    self._http,
                    base_url=self.base_url,
                    token=self.token,
                    ilink_user_id=user_id,
                    context_token=context_token,
                )
                ticket = str(resp.get("typing_ticket") or "").strip()
                self._config_cache[user_id] = WeChatConfigCacheEntry(
                    typing_ticket=ticket,
                    ever_succeeded=True,
                    next_fetch_at_ms=now_ms + (random.random() * CONFIG_CACHE_TTL_MS),
                    retry_delay_ms=CONFIG_CACHE_INITIAL_RETRY_MS,
                )
                fetch_ok = True
            except Exception as exc:  # noqa: BLE001
                self._handle_possible_session_expiry(exc, reason="getconfig 返回登录态过期")
                logger.debug(f"[wechat:{self.account_id}] getconfig failed for {user_id}: {exc}")

            if not fetch_ok:
                previous = entry.retry_delay_ms if entry else CONFIG_CACHE_INITIAL_RETRY_MS
                next_delay = min(previous * 2, CONFIG_CACHE_MAX_RETRY_MS)
                self._config_cache[user_id] = WeChatConfigCacheEntry(
                    typing_ticket=entry.typing_ticket if entry else "",
                    ever_succeeded=bool(entry and entry.ever_succeeded),
                    next_fetch_at_ms=now_ms + (next_delay if entry else CONFIG_CACHE_INITIAL_RETRY_MS),
                    retry_delay_ms=next_delay,
                )

        cached = self._config_cache.get(user_id)
        return {"typing_ticket": cached.typing_ticket if cached else ""}

    async def open_typing_session(
        self,
        *,
        chat_id: str,
        context_token: Optional[str] = None,
    ) -> Optional[str]:
        """开启微信 typing keepalive，会返回一个内部 session key。"""
        if not self._http or not chat_id or not self.token:
            return None
        if is_wechat_session_paused(self.account_id):
            return None

        config = await self._get_cached_user_config(user_id=chat_id, context_token=context_token)
        typing_ticket = str(config.get("typing_ticket") or "").strip()
        if not typing_ticket:
            return None

        session_key = f"{chat_id}:{uuid.uuid4().hex}"
        task = asyncio.create_task(
            self._typing_keepalive_loop(
                session_key=session_key,
                chat_id=chat_id,
                typing_ticket=typing_ticket,
            )
        )
        self._typing_tasks[session_key] = task
        return session_key

    async def close_typing_session(self, session_key: Optional[str]) -> None:
        """关闭微信 typing keepalive。"""
        if not session_key:
            return
        task = self._typing_tasks.pop(session_key, None)
        if task is None:
            return
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    async def _typing_keepalive_loop(
        self,
        *,
        session_key: str,
        chat_id: str,
        typing_ticket: str,
    ) -> None:
        """周期性发送 typing 状态，并在退出时尝试 cancel。"""
        try:
            while self._running and self._http and not is_wechat_session_paused(self.account_id):
                try:
                    await send_wechat_typing_api(
                        self._http,
                        base_url=self.base_url,
                        token=self.token,
                        ilink_user_id=chat_id,
                        typing_ticket=typing_ticket,
                        status=TYPING_STATUS_TYPING,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.debug(f"[wechat:{self.account_id}] sendtyping failed for {chat_id}: {exc}")
                    if self._handle_possible_session_expiry(
                        exc,
                        reason="sendtyping 返回登录态过期",
                    ):
                        break
                await asyncio.sleep(TYPING_KEEPALIVE_INTERVAL_MS / 1000)
        except asyncio.CancelledError:
            raise
        finally:
            try:
                if self._http and not is_wechat_session_paused(self.account_id):
                    await send_wechat_typing_api(
                        self._http,
                        base_url=self.base_url,
                        token=self.token,
                        ilink_user_id=chat_id,
                        typing_ticket=typing_ticket,
                        status=TYPING_STATUS_CANCEL,
                    )
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"[wechat:{self.account_id}] cancel typing failed for {chat_id}: {exc}")
            self._typing_tasks.pop(session_key, None)

    def _remember_context_token(self, chat_id: str, context_token: str) -> None:
        if not context_token:
            return
        self._context_tokens[chat_id] = context_token
        self._context_tokens.move_to_end(chat_id)
        while len(self._context_tokens) > 500:
            self._context_tokens.popitem(last=False)

    def _remember_message_id(self, message_id: str) -> bool:
        if not message_id:
            return True
        if message_id in self._processed_ids:
            return False
        self._processed_ids[message_id] = None
        while len(self._processed_ids) > 1000:
            self._processed_ids.popitem(last=False)
        return True

    async def _handle_inbound_wechat_message(self, raw_msg: Dict[str, Any]) -> None:
        if int(raw_msg.get("message_type") or 0) == MESSAGE_TYPE_BOT:
            return

        sender_id = str(raw_msg.get("from_user_id") or "").strip()
        if not sender_id:
            return

        message_id = str(raw_msg.get("message_id") or raw_msg.get("client_id") or "")
        if not self._remember_message_id(message_id):
            return

        context_token = str(raw_msg.get("context_token") or "").strip()
        self._remember_context_token(sender_id, context_token)

        item_list = raw_msg.get("item_list") or []
        if not isinstance(item_list, list):
            item_list = []

        content = _extract_text_from_item_list(item_list)
        media_paths = await self._download_inbound_media(item_list, message_id=message_id)
        if media_paths:
            content = format_inbound_media_text(media_paths, content)
        if not content:
            content = "[空消息]"

        metadata = {
            "message_id": message_id,
            "context_token": context_token,
            "sender_name": sender_id,
            "login_bot_id": str(getattr(self.config, "login_bot_id", "") or ""),
            "login_user_id": str(getattr(self.config, "login_user_id", "") or ""),
        }
        upstream_session_id = str(raw_msg.get("session_id") or "").strip()
        if upstream_session_id:
            metadata["session_id"] = upstream_session_id

        logger.info(f"[wechat:{self.account_id}] inbound from {sender_id}: {content[:80]}")
        await self._handle_message(
            sender_id=sender_id,
            chat_id=sender_id,
            content=content,
            media=media_paths or None,
            metadata=metadata,
        )

    async def _download_inbound_media(
        self,
        item_list: List[Dict[str, Any]],
        *,
        message_id: str,
    ) -> List[str]:
        if not self._http:
            return []

        media_paths: List[str] = []
        for item in item_list:
            if not isinstance(item, dict):
                continue
            item_type = int(item.get("type") or 0)
            try:
                if item_type == MESSAGE_ITEM_IMAGE:
                    media_path = await self._download_image_item(item, message_id=message_id)
                elif item_type == MESSAGE_ITEM_FILE:
                    media_path = await self._download_file_item(item, message_id=message_id)
                elif item_type == MESSAGE_ITEM_VIDEO:
                    media_path = await self._download_video_item(item, message_id=message_id)
                elif item_type == MESSAGE_ITEM_VOICE:
                    media_path = await self._download_voice_item(item, message_id=message_id)
                else:
                    media_path = None
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[wechat:{self.account_id}] failed to download media: {exc}")
                media_path = None

            if media_path:
                media_paths.append(media_path)
        return media_paths

    async def _download_image_item(
        self,
        item: Dict[str, Any],
        *,
        message_id: str,
    ) -> Optional[str]:
        image_item = item.get("image_item") or {}
        media = image_item.get("media") or {}
        encrypted_query_param = str(media.get("encrypt_query_param") or "").strip()
        if not encrypted_query_param:
            return None

        aes_key = str(image_item.get("aeskey") or "").strip()
        aes_key_base64 = (
            base64.b64encode(bytes.fromhex(aes_key)).decode("utf-8")
            if aes_key
            else str(media.get("aes_key") or "").strip()
        )
        if aes_key_base64:
            data = await _download_and_decrypt_cdn_buffer(
                self._http,
                cdn_base_url=self.cdn_base_url,
                encrypted_query_param=encrypted_query_param,
                aes_key_base64=aes_key_base64,
            )
        else:
            data = await _download_plain_cdn_buffer(
                self._http,
                cdn_base_url=self.cdn_base_url,
                encrypted_query_param=encrypted_query_param,
            )

        content_type, ext = _guess_image_type(data)
        return save_bytes_to_temp(
            "wechat",
            data,
            message_id=message_id,
            filename=f"image.{ext}",
            content_type=content_type,
            prefix="wechat_image",
        )

    async def _download_file_item(
        self,
        item: Dict[str, Any],
        *,
        message_id: str,
    ) -> Optional[str]:
        file_item = item.get("file_item") or {}
        media = file_item.get("media") or {}
        encrypted_query_param = str(media.get("encrypt_query_param") or "").strip()
        aes_key_base64 = str(media.get("aes_key") or "").strip()
        if not encrypted_query_param or not aes_key_base64:
            return None

        data = await _download_and_decrypt_cdn_buffer(
            self._http,
            cdn_base_url=self.cdn_base_url,
            encrypted_query_param=encrypted_query_param,
            aes_key_base64=aes_key_base64,
        )
        filename = str(file_item.get("file_name") or "file.bin").strip() or "file.bin"
        return save_bytes_to_temp(
            "wechat",
            data,
            message_id=message_id,
            filename=filename,
            content_type=_mime_from_path(filename),
            prefix="wechat_file",
        )

    async def _download_video_item(
        self,
        item: Dict[str, Any],
        *,
        message_id: str,
    ) -> Optional[str]:
        video_item = item.get("video_item") or {}
        media = video_item.get("media") or {}
        encrypted_query_param = str(media.get("encrypt_query_param") or "").strip()
        aes_key_base64 = str(media.get("aes_key") or "").strip()
        if not encrypted_query_param or not aes_key_base64:
            return None

        data = await _download_and_decrypt_cdn_buffer(
            self._http,
            cdn_base_url=self.cdn_base_url,
            encrypted_query_param=encrypted_query_param,
            aes_key_base64=aes_key_base64,
        )
        return save_bytes_to_temp(
            "wechat",
            data,
            message_id=message_id,
            filename="video.mp4",
            content_type="video/mp4",
            prefix="wechat_video",
        )

    async def _download_voice_item(
        self,
        item: Dict[str, Any],
        *,
        message_id: str,
    ) -> Optional[str]:
        voice_item = item.get("voice_item") or {}
        voice_text = str(voice_item.get("text") or "").strip()
        if voice_text:
            return None

        media = voice_item.get("media") or {}
        encrypted_query_param = str(media.get("encrypt_query_param") or "").strip()
        aes_key_base64 = str(media.get("aes_key") or "").strip()
        if not encrypted_query_param or not aes_key_base64:
            return None

        data = await _download_and_decrypt_cdn_buffer(
            self._http,
            cdn_base_url=self.cdn_base_url,
            encrypted_query_param=encrypted_query_param,
            aes_key_base64=aes_key_base64,
        )
        return save_bytes_to_temp(
            "wechat",
            data,
            message_id=message_id,
            filename="voice.silk",
            content_type="audio/silk",
            prefix="wechat_voice",
        )

    async def _send_text(
        self,
        *,
        to_user_id: str,
        text: str,
        context_token: str,
    ) -> None:
        assert self._http is not None
        _assert_wechat_session_active(self.account_id)
        plain_text = _markdown_to_plain_text(text)
        if not plain_text:
            return
        await send_wechat_message_api(
            self._http,
            base_url=self.base_url,
            token=self.token,
            payload={
                "msg": {
                    "from_user_id": "",
                    "to_user_id": to_user_id,
                    "client_id": f"countbot-{uuid.uuid4().hex[:16]}",
                    "message_type": MESSAGE_TYPE_BOT,
                    "message_state": 2,
                    "context_token": context_token,
                    "item_list": [
                        {
                            "type": MESSAGE_ITEM_TEXT,
                            "text_item": {"text": plain_text},
                        }
                    ],
                }
            },
        )

    async def _send_media_file(
        self,
        *,
        to_user_id: str,
        file_path: str,
        text: str,
        context_token: str,
    ) -> None:
        assert self._http is not None
        _assert_wechat_session_active(self.account_id)
        local_path = file_path
        if file_path.startswith("http://") or file_path.startswith("https://"):
            local_path = await _download_remote_media_to_temp(self._http, file_path)
        if not Path(local_path).exists():
            raise WeChatApiError(f"待发送文件不存在: {local_path}")

        mime_type = _mime_from_path(local_path)
        uploaded = await self._upload_local_file(to_user_id=to_user_id, file_path=local_path)
        aes_key_b64 = _encode_outbound_aes_key(uploaded["aes_key"])

        items: List[Dict[str, Any]] = []
        plain_text = _markdown_to_plain_text(text)
        if plain_text:
            items.append({"type": MESSAGE_ITEM_TEXT, "text_item": {"text": plain_text}})

        if mime_type.startswith("image/"):
            items.append(
                {
                    "type": MESSAGE_ITEM_IMAGE,
                    "image_item": {
                        "media": {
                            "encrypt_query_param": uploaded["download_param"],
                            "aes_key": aes_key_b64,
                            "encrypt_type": 1,
                        },
                        "mid_size": uploaded["cipher_size"],
                    },
                }
            )
        elif mime_type.startswith("video/"):
            items.append(
                {
                    "type": MESSAGE_ITEM_VIDEO,
                    "video_item": {
                        "media": {
                            "encrypt_query_param": uploaded["download_param"],
                            "aes_key": aes_key_b64,
                            "encrypt_type": 1,
                        },
                        "video_size": uploaded["cipher_size"],
                    },
                }
            )
        else:
            items.append(
                {
                    "type": MESSAGE_ITEM_FILE,
                    "file_item": {
                        "media": {
                            "encrypt_query_param": uploaded["download_param"],
                            "aes_key": aes_key_b64,
                            "encrypt_type": 1,
                        },
                        "file_name": Path(local_path).name,
                        "len": str(uploaded["plain_size"]),
                    },
                }
            )

        for item in items:
            await send_wechat_message_api(
                self._http,
                base_url=self.base_url,
                token=self.token,
                payload={
                    "msg": {
                        "from_user_id": "",
                        "to_user_id": to_user_id,
                        "client_id": f"countbot-{uuid.uuid4().hex[:16]}",
                        "message_type": MESSAGE_TYPE_BOT,
                        "message_state": 2,
                        "context_token": context_token,
                        "item_list": [item],
                    }
                },
            )

    async def _upload_local_file(self, *, to_user_id: str, file_path: str) -> Dict[str, Any]:
        assert self._http is not None
        _assert_wechat_session_active(self.account_id)
        plaintext = Path(file_path).read_bytes()
        aes_key = secrets.token_bytes(16)
        filekey = secrets.token_hex(16)
        plain_size = len(plaintext)
        cipher_size = _aes_padded_size(plain_size)
        raw_md5 = hashlib.md5(plaintext).hexdigest()
        mime_type = _mime_from_path(file_path)
        if mime_type.startswith("image/"):
            media_type = UPLOAD_MEDIA_IMAGE
        elif mime_type.startswith("video/"):
            media_type = UPLOAD_MEDIA_VIDEO
        else:
            media_type = UPLOAD_MEDIA_FILE

        upload_resp = await get_wechat_upload_url(
            self._http,
            base_url=self.base_url,
            token=self.token,
            payload={
                "filekey": filekey,
                "media_type": media_type,
                "to_user_id": to_user_id,
                "rawsize": plain_size,
                "rawfilemd5": raw_md5,
                "filesize": cipher_size,
                "no_need_thumb": True,
                "aeskey": aes_key.hex(),
            },
        )
        upload_param = str(upload_resp.get("upload_param") or "").strip()
        if not upload_param:
            raise WeChatApiError("微信上传参数获取失败")

        download_param = await _upload_buffer_to_cdn(
            self._http,
            plaintext=plaintext,
            upload_param=upload_param,
            filekey=filekey,
            cdn_base_url=self.cdn_base_url,
            aes_key=aes_key,
        )
        return {
            "download_param": download_param,
            "aes_key": aes_key,
            "plain_size": plain_size,
            "cipher_size": cipher_size,
        }
