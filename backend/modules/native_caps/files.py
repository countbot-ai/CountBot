"""DeepSeek Files API：把本地附件上传为 file_id。"""

from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import httpx
from loguru import logger

from .registry import normalize_deepseek_api_base, supports_native_capabilities
from .types import normalize_native_capabilities

# 需要服务端解析的文档：purpose 由 document_parsing 模式决定。
PARSE_DOC_EXTENSIONS = {".pdf", ".doc", ".docx", ".ppt", ".pptx"}
PARSE_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff"}
# 无需解析、官方要求以 user_data 上传：表格会转 Markdown，纯文本直接读取。
USER_DATA_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".yaml", ".yml",
    ".xml", ".html", ".htm", ".xlsx", ".xls", ".epub", ".mobi", ".log",
    ".py", ".js", ".ts", ".java", ".go", ".rs", ".sql", ".sh",
}
SUPPORTED_EXTENSIONS = PARSE_DOC_EXTENSIONS | PARSE_IMAGE_EXTENSIONS | USER_DATA_EXTENSIONS

# file_id 由账号共享，进程内按内容哈希复用，避免同一附件每轮重复上传计费。
_FILE_ID_CACHE: Dict[str, str] = {}
_MAX_CACHE_ENTRIES = 2048
# 官方上传在 /files；部分中转只暴露 /v1/files，成功后记住可用路径。
_UPLOAD_PATH: Dict[str, str] = {}


def upload_paths(root: str) -> List[str]:
    urls = [f"{root}/files", f"{root}/v1/files"]
    preferred = _UPLOAD_PATH.get(root)
    if preferred in urls:
        urls.remove(preferred)
        urls.insert(0, preferred)
    return urls


def _cache_key(api_base: str, api_key: str, digest: str, purpose: str) -> str:
    # file_id 属于账号，缓存键包含 Key 指纹。
    key_fingerprint = hashlib.sha256(str(api_key or "").encode()).hexdigest()[:16]
    return f"{api_base}|{key_fingerprint}|{purpose}|{digest}"


def _remember(cache_key: str, file_id: str) -> None:
    if len(_FILE_ID_CACHE) >= _MAX_CACHE_ENTRIES:
        _FILE_ID_CACHE.clear()
    _FILE_ID_CACHE[cache_key] = file_id


def _digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def resolve_attachment_path(raw_path: str, workspace: Optional[Path]) -> Optional[Path]:
    candidate = Path(str(raw_path or "").strip()).expanduser()
    if not candidate.is_absolute() and workspace is not None:
        candidate = Path(workspace).expanduser() / candidate
    try:
        resolved = candidate.resolve()
    except OSError:
        return None
    if not resolved.is_file():
        return None
    return resolved


def resolve_purpose(path: Path, mode: str) -> str:
    """按官方文档选择上传 purpose。"""
    suffix = path.suffix.lower()
    if suffix in PARSE_DOC_EXTENSIONS:
        return "rich_layout_recognition" if mode == "rich" else "text_recognition"
    return "user_data"


def file_block_for(path: Path, file_id: str, purpose: str) -> Dict[str, Any]:
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    # 解析型 file_id（text/rich）只能作为 document 引用；即使原文件是图片，
    # 用 image 块回传会被上游以「uploaded for OCR」为由拒绝。
    block_type = (
        "image"
        if purpose == "user_data" and media_type.startswith("image/")
        else "document"
    )
    return {
        "type": "file",
        "file_id": file_id,
        "media_type": media_type,
        "filename": path.name,
        "source_path": str(path),
        "block_type": block_type,
    }


async def upload_file(
    *,
    api_base: str,
    api_key: str,
    path: Path,
    purpose: str,
) -> Optional[str]:
    root = normalize_deepseek_api_base(api_base)
    digest = _digest(path)
    cache_key = _cache_key(root, api_key, digest, purpose)
    cached = _FILE_ID_CACHE.get(cache_key)
    if cached:
        return cached

    headers = {"Authorization": f"Bearer {api_key}"}
    # 官方限制：上传 120s + 解析 120s，读超时需覆盖两者。
    timeout = httpx.Timeout(300.0, connect=30.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = None
            for url in upload_paths(root):
                with path.open("rb") as handle:
                    response = await client.post(
                        url,
                        headers=headers,
                        data={"purpose": purpose},
                        files={
                            "file": (
                                path.name,
                                handle,
                                mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                            )
                        },
                    )
                # 只有路径不存在才换下一种；其余状态码代表端点已接受请求。
                if response.status_code not in (404, 405):
                    if response.status_code < 400:
                        _UPLOAD_PATH[root] = url
                    break
        if response is None:
            return None
        if response.status_code >= 400:
            logger.warning(
                f"DeepSeek 文件上传失败 status={response.status_code} "
                f"file={path.name} body={response.text[:300]}"
            )
            return None
        payload = response.json()
        file_id = str(payload.get("id") or "").strip()
        if not file_id:
            logger.warning(f"DeepSeek 文件上传响应缺少 file_id: {path.name}")
            return None
        _remember(cache_key, file_id)
        logger.info(
            f"DeepSeek 文件已上传: file={path.name}, purpose={purpose}, file_id={file_id}"
        )
        return file_id
    except Exception as exc:
        logger.warning(f"DeepSeek 文件上传异常 file={path.name}: {exc}")
        return None


async def build_document_blocks(
    paths: Iterable[str],
    *,
    workspace: Optional[Path],
    api_base: Optional[str],
    api_key: Optional[str],
    provider_id: Optional[str],
    model: Optional[str],
    capabilities: Any,
    include_images: bool = False,
) -> Tuple[List[Dict[str, Any]], set[str]]:
    """上传可解析附件，返回 file 内容块与已处理路径。"""
    caps = normalize_native_capabilities(capabilities)
    if (
        caps.document_parsing == "off"
        or not supports_native_capabilities(provider_id, model)
        or not str(api_key or "").strip()
    ):
        return [], set()

    blocks: List[Dict[str, Any]] = []
    handled: set[str] = set()
    seen_digests: set[str] = set()

    for raw_path in paths:
        normalized = str(raw_path or "").strip().replace("\\", "/")
        if not normalized:
            continue
        path = resolve_attachment_path(normalized, workspace)
        if path is None or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        if path.suffix.lower() in PARSE_IMAGE_EXTENSIONS and not include_images:
            continue
        try:
            digest = _digest(path)
        except OSError:
            continue
        if digest in seen_digests:
            handled.add(normalized)
            continue
        seen_digests.add(digest)

        purpose = resolve_purpose(path, caps.document_parsing)
        file_id = await upload_file(
            api_base=str(api_base or ""),
            api_key=str(api_key or ""),
            path=path,
            purpose=purpose,
        )
        if not file_id:
            continue
        blocks.append(file_block_for(path, file_id, purpose))
        handled.add(normalized)

    return blocks, handled


def clear_file_id_cache() -> None:
    _FILE_ID_CACHE.clear()
    _UPLOAD_PATH.clear()
