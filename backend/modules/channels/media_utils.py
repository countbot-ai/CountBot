"""渠道媒体文件公共工具。"""

from __future__ import annotations

import asyncio
import base64
import mimetypes
import secrets
import shutil
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence
from urllib.parse import unquote, urlparse

import httpx
from Crypto.Cipher import AES

from backend.modules.workspace.manager import workspace_manager

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg", ".tiff"}
_AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".m4a", ".amr", ".aac", ".opus", ".silk"}
_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".mpeg", ".m4v"}

# 入站附件约束与 zcode 保持一致：单条消息最多 4 个附件，单个附件最大 5MB。
MAX_INBOUND_ATTACHMENTS = 4
MAX_INBOUND_ATTACHMENT_BYTES = 5 * 1024 * 1024
DEFAULT_INBOUND_ATTACHMENT_PROMPT = "请查看附件并根据内容协助我。"

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
    max_bytes: int = MAX_INBOUND_ATTACHMENT_BYTES,
) -> str:
    if len(data) > max_bytes:
        raise ValueError(
            f"media too large: {len(data)} bytes (limit {max_bytes} bytes)"
        )
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


@dataclass
class PromotedMediaEntry:
    """单条渠道媒体的转存结果。"""

    original_path: str
    stored_path: str
    attachment_item: Optional[dict[str, Any]] = None


@dataclass
class PromotedMediaResult:
    """渠道入站媒体转存后的路径与附件元信息。"""

    media_paths: list[str] = field(default_factory=list)
    attachment_items: list[dict[str, Any]] = field(default_factory=list)
    entries: list[PromotedMediaEntry] = field(default_factory=list)


async def promote_inbound_media(
    channel: str,
    media_paths: Optional[Sequence[str]],
    *,
    account_id: str = "default",
    workspace: Optional[Path] = None,
) -> PromotedMediaResult:
    """把渠道临时媒体复制到工作空间的持久目录。

    频道下载的媒体默认落在 ``workspace/temp/channels``，语义上是临时文件。
    这里在消息进入 Agent 前统一转存到 ``workspace/uploads/channels``，同时
    产出附件元信息，供当前轮图片输入与后续历史消息复用。

    已在 ``uploads/`` 下的文件不会重复复制；工作空间外的路径保持原样，
    不改变现有渠道行为。
    """
    paths = [
        str(path or "").strip()
        for path in (media_paths or ())
        if str(path or "").strip()
    ]
    if not paths:
        return PromotedMediaResult()

    return await asyncio.to_thread(
        _promote_inbound_media_sync,
        channel,
        paths,
        account_id,
        workspace,
    )


def _promote_inbound_media_sync(
    channel: str,
    media_paths: list[str],
    account_id: str,
    workspace: Optional[Path],
) -> PromotedMediaResult:
    from backend.modules.session.message_context import build_attachment_item

    result = PromotedMediaResult()
    workspace_root = Path(workspace or workspace_manager.workspace_path).expanduser().resolve()
    uploads_root = workspace_root / "uploads"
    safe_channel = sanitize_filename(channel, fallback="channel")
    safe_account = sanitize_filename(account_id, fallback="default")
    now = datetime.now(timezone.utc)
    destination_dir = (
        uploads_root / "channels" / safe_channel / safe_account
        / now.strftime("%Y") / now.strftime("%m") / now.strftime("%d")
    )
    stored_by_source: dict[Path, str] = {}

    for raw_path in media_paths:
        candidate = _resolve_inbound_media_path(raw_path, workspace_root)
        if candidate is None:
            result.media_paths.append(raw_path)
            result.entries.append(PromotedMediaEntry(raw_path, raw_path))
            continue

        if candidate in stored_by_source:
            stored_path = stored_by_source[candidate]
            result.media_paths.append(stored_path)
            result.entries.append(PromotedMediaEntry(raw_path, stored_path))
            continue

        relative_path = candidate.relative_to(workspace_root).as_posix()
        if relative_path.startswith("uploads/"):
            stored_path = relative_path
        else:
            try:
                destination_dir.mkdir(parents=True, exist_ok=True)
                filename = sanitize_filename(candidate.name, fallback="attachment")
                destination = destination_dir / f"{uuid.uuid4().hex[:12]}-{filename}"
                shutil.copy2(candidate, destination)
            except OSError as exc:
                logger.warning(f"转存渠道媒体失败 {raw_path}: {exc}")
                result.media_paths.append(raw_path)
                result.entries.append(PromotedMediaEntry(raw_path, raw_path))
                continue
            stored_path = destination.relative_to(workspace_root).as_posix()

        item = build_attachment_item(
            relative_path=stored_path,
            absolute_path=(workspace_root / stored_path),
        )
        result.media_paths.append(stored_path)
        result.attachment_items.append(item)
        result.entries.append(
            PromotedMediaEntry(raw_path, stored_path, attachment_item=item)
        )
        stored_by_source[candidate] = stored_path

    return result


def _resolve_inbound_media_path(raw_path: str, workspace_root: Path) -> Optional[Path]:
    """解析渠道媒体路径，只处理工作空间内的现存文件。"""
    try:
        candidate = Path(raw_path).expanduser()
        candidate = (
            candidate.resolve()
            if candidate.is_absolute()
            else (workspace_root / candidate).resolve()
        )
    except (OSError, RuntimeError) as exc:
        logger.debug(f"渠道媒体路径解析失败 {raw_path}: {exc}")
        return None

    if not candidate.is_relative_to(workspace_root):
        return None
    if not candidate.exists() or not candidate.is_file():
        return None
    return candidate


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
    max_bytes: int = MAX_INBOUND_ATTACHMENT_BYTES,
) -> str:
    # 流式读取并在超限时立即中止，避免先把超大文件完整读进内存。
    async with client.stream(
        "GET", url, headers=dict(headers or {}), follow_redirects=True
    ) as response:
        response.raise_for_status()

        declared_length = str(response.headers.get("content-length") or "").strip()
        if declared_length.isdigit() and int(declared_length) > max_bytes:
            raise ValueError(
                f"media too large: {declared_length} bytes (limit {max_bytes} bytes)"
            )

        chunks: list[bytes] = []
        total = 0
        async for chunk in response.aiter_bytes():
            total += len(chunk)
            if total > max_bytes:
                raise ValueError(f"media too large: {total}+ bytes (limit {max_bytes} bytes)")
            chunks.append(chunk)
        data = b"".join(chunks)

        resolved_filename = (
            filename
            or extract_filename_from_content_disposition(
                response.headers.get("content-disposition")
            )
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
        max_bytes=max_bytes,
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
        lines.append("这些文件已保存到工作区附件目录，可直接读取、分析或继续处理。")

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
