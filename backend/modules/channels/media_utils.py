"""渠道媒体文件公共工具。"""

from __future__ import annotations

import base64
import mimetypes
import secrets
import time
from pathlib import Path
from typing import Mapping, Optional, Sequence
from urllib.parse import unquote, urlparse

import httpx
from Crypto.Cipher import AES

from backend.modules.workspace.manager import workspace_manager

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg", ".tiff"}
_AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".m4a", ".amr", ".aac", ".opus", ".silk"}
_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".mpeg", ".m4v"}

_MIME_EXTENSION_MAP = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.ms-powerpoint": ".ppt",
    "application/msword": ".doc",
    "application/x-rar-compressed": ".rar",
    "application/x-7z-compressed": ".7z",
    "application/octet-stream": ".bin",
    "text/plain": ".txt",
    "text/markdown": ".md",
    "text/csv": ".csv",
    "application/json": ".json",
    "application/pdf": ".pdf",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "audio/ogg": ".ogg",
    "audio/mp4": ".m4a",
    "audio/aac": ".aac",
    "audio/amr": ".amr",
    "video/quicktime": ".mov",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/svg+xml": ".svg",
}


def get_channel_temp_dir(channel: str, scope: str = "inbound") -> Path:
    base_dir = workspace_manager.temp_dir / "channels" / channel / scope
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


def sanitize_filename(filename: Optional[str], fallback: str = "attachment") -> str:
    raw = str(filename or "").strip()
    if not raw:
        return fallback

    raw = raw.replace("\\", "/").split("/")[-1]
    raw = raw.replace("\x00", "")
    safe_chars = []
    for ch in raw:
        if ch.isalnum() or ch in {"-", "_", ".", " ", "(", ")", "[", "]"}:
            safe_chars.append(ch)
        else:
            safe_chars.append("_")
    safe = "".join(safe_chars).strip(" ._")
    return safe or fallback


def extract_filename_from_content_disposition(disposition: Optional[str]) -> Optional[str]:
    raw = str(disposition or "").strip()
    if not raw:
        return None

    lower = raw.lower()
    idx = lower.find("filename*=")
    if idx >= 0:
        value = raw[idx + len("filename*="):].split(";", 1)[0].strip().strip('"')
        encoded = value.split("''", 1)[1] if "''" in value else value
        try:
            decoded = unquote(encoded)
        except Exception:
            decoded = encoded
        return sanitize_filename(decoded) if decoded else None

    idx = lower.find("filename=")
    if idx >= 0:
        value = raw[idx + len("filename="):].split(";", 1)[0].strip().strip('"')
        return sanitize_filename(value) if value else None

    return None


def _normalize_content_type(content_type: Optional[str]) -> Optional[str]:
    raw = str(content_type or "").strip()
    if not raw:
        return None
    return raw.split(";", 1)[0].strip().lower() or None


def infer_extension(
    *,
    filename: Optional[str] = None,
    content_type: Optional[str] = None,
    fallback: str = ".bin",
) -> str:
    if filename:
        suffix = Path(filename).suffix.lower()
        if suffix:
            return suffix

    normalized = _normalize_content_type(content_type)
    if normalized:
        mapped = _MIME_EXTENSION_MAP.get(normalized)
        if mapped:
            return mapped
        guessed = mimetypes.guess_extension(normalized)
        if guessed:
            return guessed

    return fallback


def save_bytes_to_temp(
    channel: str,
    data: bytes,
    *,
    message_id: Optional[str] = None,
    filename: Optional[str] = None,
    content_type: Optional[str] = None,
    prefix: str = "attachment",
    scope: str = "inbound",
) -> str:
    temp_dir = get_channel_temp_dir(channel, scope)
    safe_filename = sanitize_filename(filename, fallback=prefix)
    suffix = infer_extension(filename=safe_filename, content_type=content_type)
    stem = Path(safe_filename).stem or prefix
    unique = sanitize_filename(message_id, fallback=str(int(time.time())))[:32]
    token = secrets.token_hex(4)
    final_name = f"{stem}_{unique}_{token}{suffix}"
    file_path = temp_dir / final_name
    file_path.write_bytes(data)
    return str(file_path)


async def download_to_temp(
    channel: str,
    url: str,
    *,
    client: httpx.AsyncClient,
    message_id: Optional[str] = None,
    filename: Optional[str] = None,
    content_type: Optional[str] = None,
    headers: Optional[Mapping[str, str]] = None,
    prefix: str = "attachment",
    max_bytes: int = 100 * 1024 * 1024,
) -> str:
    response = await client.get(url, headers=dict(headers or {}), follow_redirects=True)
    response.raise_for_status()
    data = await response.aread()
    if len(data) > max_bytes:
        raise ValueError(f"media too large: {len(data)} bytes")

    resolved_filename = (
        filename
        or extract_filename_from_content_disposition(response.headers.get("content-disposition"))
        or _filename_from_url(url)
    )
    resolved_content_type = content_type or response.headers.get("content-type")
    return save_bytes_to_temp(
        channel,
        data,
        message_id=message_id,
        filename=resolved_filename,
        content_type=resolved_content_type,
        prefix=prefix,
    )


def decrypt_wecom_media_bytes(encrypted_data: bytes, aes_key: str) -> bytes:
    key = _decode_wecom_aes_key(aes_key)
    iv = key[:16]
    cipher = AES.new(key, AES.MODE_CBC, iv)
    decrypted = cipher.decrypt(encrypted_data)
    return _pkcs7_unpad(decrypted, 32)


def format_inbound_media_text(media_paths: Sequence[str], original_text: str = "") -> str:
    lines = []
    text = str(original_text or "").strip()
    if text:
        lines.append(text)

    if media_paths:
        if text:
            lines.append("")
        lines.append("用户发送了以下本地附件：")
        for media_path in media_paths:
            lines.append(f"- [{infer_media_label(media_path)}] {media_path}")
        lines.append("这些文件已保存到本地临时目录，可直接读取、分析或继续处理。")

    return "\n".join(lines).strip()


def infer_media_label(path_or_name: str, content_type: Optional[str] = None) -> str:
    suffix = Path(path_or_name or "").suffix.lower()
    if suffix in _IMAGE_EXTENSIONS:
        return "图片"
    if suffix in _AUDIO_EXTENSIONS:
        return "音频"
    if suffix in _VIDEO_EXTENSIONS:
        return "视频"

    normalized = _normalize_content_type(content_type)
    if normalized:
        if normalized.startswith("image/"):
            return "图片"
        if normalized.startswith("audio/"):
            return "音频"
        if normalized.startswith("video/"):
            return "视频"

    return "文件"


def _filename_from_url(url: str) -> Optional[str]:
    try:
        path = unquote(urlparse(url).path)
    except Exception:
        return None
    name = Path(path).name
    return sanitize_filename(name) if name else None


def _decode_wecom_aes_key(aes_key: str) -> bytes:
    raw = str(aes_key or "").strip()
    if not raw:
        raise ValueError("WeCom aes key is empty")
    padded = raw + ("=" * ((4 - len(raw) % 4) % 4))
    key = base64.b64decode(padded)
    if len(key) != 32:
        raise ValueError("WeCom aes key must decode to 32 bytes")
    return key


def _pkcs7_unpad(data: bytes, block_size: int) -> bytes:
    if not data:
        raise ValueError("Invalid PKCS7 data")
    pad_len = data[-1]
    if pad_len < 1 or pad_len > block_size:
        raise ValueError("Invalid PKCS7 padding length")
    padding = data[-pad_len:]
    if any(byte != pad_len for byte in padding):
        raise ValueError("Invalid PKCS7 padding bytes")
    return data[:-pad_len]
