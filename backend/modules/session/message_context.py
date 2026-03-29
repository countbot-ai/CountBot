"""会话消息上下文与附件辅助函数。"""

from __future__ import annotations

import json
import mimetypes
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

from backend.modules.channels.media_utils import infer_extension, sanitize_filename
from backend.modules.workspace.manager import workspace_manager

MAX_CHAT_ATTACHMENTS = 10


def parse_message_context(raw: Optional[str]) -> dict[str, Any]:
    if not raw:
        return {}

    try:
        payload = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}

    return payload if isinstance(payload, dict) else {}


def build_message_context(
    *,
    reasoning_content: Optional[str] = None,
    attachment_items: Optional[Sequence[dict[str, Any]]] = None,
) -> Optional[str]:
    payload: dict[str, Any] = {}

    reasoning_text = str(reasoning_content or "").strip()
    if reasoning_text:
        payload["reasoning_content"] = reasoning_text

    items = [item for item in (attachment_items or []) if isinstance(item, dict) and item.get("path")]
    if items:
        payload["attachment_items"] = items
        payload["attachments"] = [str(item["path"]).strip() for item in items if str(item.get("path") or "").strip()]

    if not payload:
        return None

    return json.dumps(payload, ensure_ascii=False)


def extract_reasoning_content_from_message_context(raw: Optional[str]) -> Optional[str]:
    payload = parse_message_context(raw)
    reasoning_content = payload.get("reasoning_content")
    if reasoning_content is None:
        return None

    reasoning_text = str(reasoning_content).strip()
    return reasoning_text or None


def infer_attachment_kind(path_or_name: str, content_type: Optional[str] = None) -> str:
    suffix = Path(path_or_name or "").suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg", ".tiff"}:
        return "image"
    if suffix in {".mp3", ".wav", ".ogg", ".m4a", ".amr", ".aac", ".opus", ".silk"}:
        return "audio"
    if suffix in {".mp4", ".mov", ".avi", ".mkv", ".webm", ".mpeg", ".m4v"}:
        return "video"

    normalized = str(content_type or "").split(";", 1)[0].strip().lower()
    if normalized.startswith("image/"):
        return "image"
    if normalized.startswith("audio/"):
        return "audio"
    if normalized.startswith("video/"):
        return "video"
    return "file"


def build_attachment_item(
    *,
    relative_path: str,
    absolute_path: Path,
    content_type: Optional[str] = None,
) -> dict[str, Any]:
    normalized_path = str(relative_path).strip().replace("\\", "/")
    resolved = absolute_path.resolve()
    mime_type = str(content_type or mimetypes.guess_type(resolved.name)[0] or "").strip() or None
    try:
        size = resolved.stat().st_size
    except OSError:
        size = 0

    return {
        "path": normalized_path,
        "name": resolved.name,
        "size": size,
        "content_type": mime_type,
        "kind": infer_attachment_kind(resolved.name, mime_type),
    }


def extract_attachment_items_from_message_context(raw: Optional[str]) -> list[dict[str, Any]]:
    payload = parse_message_context(raw)
    raw_items = payload.get("attachment_items")

    if isinstance(raw_items, list):
        items = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or "").strip()
            if not path:
                continue
            items.append(
                {
                    "path": path.replace("\\", "/"),
                    "name": str(item.get("name") or Path(path).name or "attachment").strip() or "attachment",
                    "size": int(item.get("size") or 0),
                    "content_type": str(item.get("content_type") or "").strip() or None,
                    "kind": str(item.get("kind") or infer_attachment_kind(path, str(item.get("content_type") or ""))).strip() or "file",
                }
            )
        if items:
            return items

    raw_paths = payload.get("attachments")
    if not isinstance(raw_paths, list):
        return []

    return [
        {
            "path": str(path).strip().replace("\\", "/"),
            "name": Path(str(path)).name or "attachment",
            "size": 0,
            "content_type": None,
            "kind": infer_attachment_kind(str(path)),
        }
        for path in raw_paths
        if str(path).strip()
    ]


def resolve_workspace_attachments(
    attachment_paths: Optional[Sequence[str]],
    *,
    workspace: Optional[Path] = None,
    max_attachments: int = MAX_CHAT_ATTACHMENTS,
) -> list[tuple[str, Path]]:
    raw_paths = [str(path or "").strip() for path in (attachment_paths or []) if str(path or "").strip()]
    if not raw_paths:
        return []
    if len(raw_paths) > max_attachments:
        raise ValueError(f"Too many attachments: {len(raw_paths)} > {max_attachments}")

    workspace_root = Path(workspace or workspace_manager.workspace_path).expanduser().resolve()
    resolved_items: list[tuple[str, Path]] = []
    seen: set[str] = set()

    for raw in raw_paths:
        candidate = Path(raw).expanduser()
        candidate = candidate.resolve() if candidate.is_absolute() else (workspace_root / raw).resolve()

        try:
            relative = candidate.relative_to(workspace_root)
        except ValueError as exc:
            raise ValueError(f"Attachment path is outside workspace: {raw}") from exc

        if not candidate.exists() or not candidate.is_file():
            raise ValueError(f"Attachment file not found: {raw}")

        normalized_relative = relative.as_posix()
        if normalized_relative in seen:
            continue

        seen.add(normalized_relative)
        resolved_items.append((normalized_relative, candidate))

    return resolved_items


def build_attachment_items_from_workspace(
    resolved_attachments: Iterable[tuple[str, Path]]
) -> list[dict[str, Any]]:
    return [
        build_attachment_item(relative_path=relative_path, absolute_path=absolute_path)
        for relative_path, absolute_path in resolved_attachments
    ]


def build_workspace_attachment_destination(
    *,
    session_id: str,
    filename: Optional[str],
    content_type: Optional[str],
    workspace: Optional[Path] = None,
) -> tuple[str, Path]:
    workspace_root = Path(workspace or workspace_manager.workspace_path).expanduser().resolve()
    now = datetime.now(timezone.utc)
    base_dir = workspace_root / "uploads" / "chat" / session_id / now.strftime("%Y/%m/%d")
    base_dir.mkdir(parents=True, exist_ok=True)

    safe_name = sanitize_filename(filename, fallback="attachment")
    suffix = Path(safe_name).suffix.lower()
    if not suffix:
        suffix = infer_extension(filename=safe_name, content_type=content_type)
    stem = sanitize_filename(Path(safe_name).stem, fallback="attachment")[:80]
    final_name = f"{uuid.uuid4().hex[:12]}-{stem}{suffix}"

    destination = (base_dir / final_name).resolve()
    relative_path = destination.relative_to(workspace_root).as_posix()
    return relative_path, destination
