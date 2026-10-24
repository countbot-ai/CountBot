"""把本地图片附件解析成 provider-neutral 的图片内容块。

多模态 Provider 只接受内容块，不接受本地路径。这里负责路径校验、类型/体积
过滤与 base64 编码；无法安全转成内容块的附件会留在路径链路里，由图片技能兜底。
"""

from __future__ import annotations

import base64
import mimetypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from loguru import logger

SUPPORTED_IMAGE_MEDIA_TYPES = frozenset(
    {"image/png", "image/jpeg", "image/gif", "image/webp"}
)
# 单图 5MB 覆盖 Anthropic 的图片上限；超过后继续走路径 + 图片技能。
MAX_IMAGE_BYTES = 5 * 1024 * 1024
# 单请求所有原生图片的原始字节总量，避免一次消息把上下文撑爆。
MAX_TOTAL_IMAGE_BYTES = 30 * 1024 * 1024
MAX_NATIVE_IMAGE_COUNT = 10

_EXTENSION_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


@dataclass
class ImageBlockResult:
    """图片内容块解析结果。"""

    blocks: list[dict] = field(default_factory=list)
    attached_paths: set[str] = field(default_factory=set)
    skipped_paths: list[str] = field(default_factory=list)


def build_image_blocks(
    media_paths: Optional[Iterable[str]],
    *,
    workspace: Path,
) -> ImageBlockResult:
    """把可读图片附件转成模型可接收的 image 内容块。"""
    result = ImageBlockResult()
    workspace_root = Path(workspace).expanduser().resolve()
    total_bytes = 0

    for raw_path in media_paths or ():
        normalized = str(raw_path or "").strip().replace("\\", "/")
        if not normalized or normalized in result.skipped_paths:
            continue

        candidate = _resolve_media_path(normalized, workspace_root)
        if candidate is None:
            result.skipped_paths.append(normalized)
            continue

        media_type = _infer_image_media_type(candidate)
        if media_type is None:
            result.skipped_paths.append(normalized)
            continue

        try:
            size = candidate.stat().st_size
        except OSError as exc:
            logger.debug(f"读取图片附件大小失败 {normalized}: {exc}")
            result.skipped_paths.append(normalized)
            continue

        if size <= 0 or size > MAX_IMAGE_BYTES or total_bytes + size > MAX_TOTAL_IMAGE_BYTES:
            logger.debug(
                f"图片附件跳过原生发送（size={size}, total={total_bytes}）: {normalized}"
            )
            result.skipped_paths.append(normalized)
            continue

        if len(result.blocks) >= MAX_NATIVE_IMAGE_COUNT:
            result.skipped_paths.append(normalized)
            continue

        try:
            encoded = base64.b64encode(candidate.read_bytes()).decode("ascii")
        except OSError as exc:
            logger.warning(f"读取图片附件失败 {normalized}: {exc}")
            result.skipped_paths.append(normalized)
            continue

        result.blocks.append(
            {
                "type": "image",
                "media_type": media_type,
                "data": encoded,
                "source_path": normalized,
            }
        )
        result.attached_paths.add(normalized)
        total_bytes += size

    return result


def _resolve_media_path(raw_path: str, workspace_root: Path) -> Optional[Path]:
    """只允许读取工作空间内的现存文件。"""
    try:
        candidate = Path(raw_path).expanduser()
        candidate = (
            candidate.resolve()
            if candidate.is_absolute()
            else (workspace_root / candidate).resolve()
        )
    except (OSError, RuntimeError) as exc:
        logger.debug(f"图片附件路径解析失败 {raw_path}: {exc}")
        return None

    if not candidate.is_relative_to(workspace_root):
        logger.debug(f"图片附件不在工作空间内，跳过原生发送: {raw_path}")
        return None
    if not candidate.exists() or not candidate.is_file():
        return None
    return candidate


def _infer_image_media_type(path: Path) -> Optional[str]:
    media_type = _EXTENSION_MEDIA_TYPES.get(path.suffix.lower())
    if media_type:
        return media_type

    guessed = str(mimetypes.guess_type(path.name)[0] or "").lower()
    if guessed in SUPPORTED_IMAGE_MEDIA_TYPES:
        return guessed
    return None
