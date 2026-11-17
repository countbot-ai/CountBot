#!/usr/bin/env python3
"""IMA knowledge-base-only CLI."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import io
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ima_client import load_skill_config, post_json, require_credentials


if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


MB = 1024 * 1024
SIZE_LIMITS = {5: 10 * MB, 7: 10 * MB, 13: 10 * MB, 14: 10 * MB, 9: 30 * MB}
DEFAULT_SIZE_LIMIT = 200 * MB

EXT_MAP: Dict[str, Dict[str, object]] = {
    "pdf": {"media_type": 1, "content_type": "application/pdf"},
    "doc": {"media_type": 3, "content_type": "application/msword"},
    "docx": {"media_type": 3, "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    "ppt": {"media_type": 4, "content_type": "application/vnd.ms-powerpoint"},
    "pptx": {"media_type": 4, "content_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation"},
    "xls": {"media_type": 5, "content_type": "application/vnd.ms-excel"},
    "xlsx": {"media_type": 5, "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    "csv": {"media_type": 5, "content_type": "text/csv"},
    "md": {"media_type": 7, "content_type": "text/markdown"},
    "markdown": {"media_type": 7, "content_type": "text/markdown"},
    "png": {"media_type": 9, "content_type": "image/png"},
    "jpg": {"media_type": 9, "content_type": "image/jpeg"},
    "jpeg": {"media_type": 9, "content_type": "image/jpeg"},
    "webp": {"media_type": 9, "content_type": "image/webp"},
    "txt": {"media_type": 13, "content_type": "text/plain"},
    "xmind": {"media_type": 14, "content_type": "application/x-xmind"},
    "mp3": {"media_type": 15, "content_type": "audio/mpeg"},
    "m4a": {"media_type": 15, "content_type": "audio/x-m4a"},
    "wav": {"media_type": 15, "content_type": "audio/wav"},
    "aac": {"media_type": 15, "content_type": "audio/aac"},
}

CONTENT_TYPE_MAP: Dict[str, int] = {str(mapping["content_type"]).lower(): int(mapping["media_type"]) for mapping in EXT_MAP.values()}
CONTENT_TYPE_MAP.update(
    {
        "text/x-markdown": 7,
        "application/md": 7,
        "application/markdown": 7,
        "application/vnd.xmind.workbook": 14,
        "application/zip": 14,
    }
)

UNSUPPORTED_VIDEO_EXT = {"mp4", "avi", "mov", "mkv", "wmv", "flv", "webm", "m4v", "rmvb", "rm", "3gp"}
UNSUPPORTED_VIDEO_CT = {"video/mp4", "video/x-msvideo", "video/quicktime", "video/x-matroska", "video/x-ms-wmv", "video/x-flv", "video/webm"}
TRAILING_QUERY_PARTICLES = ("的", "了", "呢", "吗", "呀", "啊", "吧", "嘛")
OCR_NOISE_CHARS = "|#[](){}<>"


class IMAApiError(RuntimeError):
    def __init__(self, endpoint: str, retcode: int, errmsg: str, data: Dict[str, Any]) -> None:
        self.endpoint = endpoint
        self.retcode = retcode
        self.errmsg = errmsg
        self.data = data
        super().__init__(f"{endpoint} failed: retcode={retcode} errmsg={errmsg}")


def repair_mojibake(text: str) -> str:
    if not text:
        return text
    for source_encoding in ("gbk", "gb18030"):
        try:
            candidate = text.encode(source_encoding).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        if candidate and candidate != text:
            return candidate
    return text


def is_permission_denied(retcode: int, errmsg: str) -> bool:
    normalized = repair_mojibake(errmsg)
    return retcode == 220030 or "没有权限" in normalized


def unwrap_response(result: Dict[str, Any]) -> tuple[bool, int, str, Dict[str, Any]]:
    if "retcode" in result:
        retcode = int(result.get("retcode", -1))
        errmsg = repair_mojibake(str(result.get("errmsg", "")))
        data = result.get("data", {}) or {}
        return retcode == 0, retcode, errmsg, data if isinstance(data, dict) else {"value": data}
    if "code" in result and "msg" in result:
        code = int(result.get("code", -1))
        msg = repair_mojibake(str(result.get("msg", "")))
        data = result.get("data", {}) or {}
        return code == 0, code, msg, data if isinstance(data, dict) else {"value": data}
    return True, 0, "", result or {}


def api_call(endpoint: str, payload: Dict[str, Any], *, config: Dict[str, Any]) -> Dict[str, Any]:
    result = post_json(endpoint, payload, config=config)
    ok, retcode, errmsg, data = unwrap_response(result)
    if not ok:
        raise IMAApiError(endpoint, retcode, errmsg, data)
    return data


def print_output(payload: Any, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if isinstance(payload, str):
        print(payload)
        return
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def normalize_content_type(value: str) -> str:
    if not value:
        return ""
    return value.split(";", 1)[0].strip().lower()


def format_size(num_bytes: int) -> str:
    if num_bytes < MB:
        return f"{num_bytes / 1024:.1f} KB"
    return f"{num_bytes / MB:.1f} MB"


def preflight_file(file_path: str, *, content_type: str = "") -> Dict[str, Any]:
    path = Path(file_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if not path.is_file():
        raise ValueError(f"Not a file: {path}")

    file_ext = path.suffix[1:].lower() if path.suffix else ""
    normalized_ct = normalize_content_type(content_type)

    if file_ext in UNSUPPORTED_VIDEO_EXT:
        raise ValueError(f"Video files (.{file_ext}) are not supported by IMA OpenAPI.")
    if normalized_ct in UNSUPPORTED_VIDEO_CT:
        raise ValueError(f"Video files ({normalized_ct}) are not supported by IMA OpenAPI.")

    ext_mapping = EXT_MAP.get(file_ext)
    ct_media_type = CONTENT_TYPE_MAP.get(normalized_ct)

    if ct_media_type is not None:
        media_type = ct_media_type
        resolved_content_type = normalized_ct
    elif normalized_ct:
        if ext_mapping is None:
            raise ValueError(f"Unrecognized content type {normalized_ct}{f' with extension .{file_ext}' if file_ext else ''}.")
        media_type = int(ext_mapping["media_type"])
        resolved_content_type = str(ext_mapping["content_type"])
    else:
        if ext_mapping is None:
            if file_ext:
                raise ValueError(f"Unrecognized file extension .{file_ext}.")
            raise ValueError("File has no extension and no --content-type was provided.")
        media_type = int(ext_mapping["media_type"])
        resolved_content_type = str(ext_mapping["content_type"])

    file_size = path.stat().st_size
    size_limit = SIZE_LIMITS.get(media_type, DEFAULT_SIZE_LIMIT)
    if file_size > size_limit:
        raise ValueError(f"File size {format_size(file_size)} exceeds the {format_size(size_limit)} limit for this type.")

    return {
        "file_path": str(path),
        "file_name": path.name,
        "file_ext": file_ext,
        "file_size": file_size,
        "content_type": resolved_content_type,
        "media_type": media_type,
    }


def hmac_sha1(key: str, data: str) -> str:
    return hmac.new(key.encode("utf-8"), data.encode("utf-8"), hashlib.sha1).hexdigest()


def sha1(data: str) -> str:
    return hashlib.sha1(data.encode("utf-8")).hexdigest()


def build_cos_authorization(
    *,
    secret_id: str,
    secret_key: str,
    method: str,
    pathname: str,
    headers: Dict[str, str],
    start_time: str,
    expired_time: str,
) -> str:
    key_time = f"{start_time};{expired_time}"
    sign_key = hmac_sha1(secret_key, key_time)
    header_keys = sorted(headers)
    http_headers = "&".join(f"{key.lower()}={urllib.parse.quote(str(headers[key]), safe='')}" for key in header_keys)
    http_string = f"{method.lower()}\n{pathname}\n\n{http_headers}\n"
    string_to_sign = f"sha1\n{key_time}\n{sha1(http_string)}\n"
    signature = hmac_sha1(sign_key, string_to_sign)
    header_list = ";".join(key.lower() for key in header_keys)
    return "&".join(
        [
            "q-sign-algorithm=sha1",
            f"q-ak={secret_id}",
            f"q-sign-time={key_time}",
            f"q-key-time={key_time}",
            f"q-header-list={header_list}",
            "q-url-param-list=",
            f"q-signature={signature}",
        ]
    )


def cos_upload(file_path: str, credential: Dict[str, Any], *, content_type: str) -> Dict[str, Any]:
    path = Path(file_path).expanduser().resolve()
    file_bytes = path.read_bytes()
    bucket_name = str(credential["bucket_name"])
    region = str(credential["region"])
    hostname = f"{bucket_name}.cos.{region}.myqcloud.com"
    cos_key = str(credential["cos_key"]).lstrip("/")
    pathname = f"/{cos_key}"

    sign_headers = {"content-length": str(len(file_bytes)), "host": hostname}
    authorization = build_cos_authorization(
        secret_id=str(credential["secret_id"]),
        secret_key=str(credential["secret_key"]),
        method="PUT",
        pathname=pathname,
        headers=sign_headers,
        start_time=str(credential["start_time"]),
        expired_time=str(credential["expired_time"]),
    )

    request = urllib.request.Request(
        url=f"https://{hostname}{pathname}",
        data=file_bytes,
        method="PUT",
        headers={
            "Content-Type": content_type,
            "Content-Length": str(len(file_bytes)),
            "Authorization": authorization,
            "x-cos-security-token": str(credential["token"]),
        },
    )
    with urllib.request.urlopen(request) as response:
        return {
            "status": response.status,
            "cos_key": cos_key,
            "bucket_name": bucket_name,
            "region": region,
        }


def join_keywords(query: Optional[str], keywords: Sequence[str]) -> List[str]:
    result: List[str] = []
    values: List[str] = []
    if query and query.strip():
        values.append(query.strip())
    for keyword in keywords:
        value = keyword.strip()
        if value:
            values.append(value)
    for value in values:
        result.append(value)
        parts = [item.strip() for item in re.split(r"[\s,，;；]+", value) if item.strip()]
        normalized_parts = [normalize_query_term(item) for item in parts]
        normalized_parts = [item for item in normalized_parts if item]
        if len(normalized_parts) > 1:
            result.append(" ".join(normalized_parts))
        for part in parts:
            result.append(part)
            normalized = normalize_query_term(part)
            if normalized and normalized != part:
                result.append(normalized)
    deduped: List[str] = []
    seen = set()
    for item in result:
        if item not in seen:
            deduped.append(item)
            seen.add(item)
    return deduped


def list_knowledge_bases(*, config: Dict[str, Any], query: str = "", limit: int = 20) -> List[Dict[str, Any]]:
    data = api_call("openapi/wiki/v1/search_knowledge_base", {"query": query, "cursor": "", "limit": limit}, config=config)
    return list(data.get("info_list", []) or [])


def list_addable_knowledge_bases(*, config: Dict[str, Any], limit: int = 20) -> List[Dict[str, Any]]:
    data = api_call("openapi/wiki/v1/get_addable_knowledge_base_list", {"cursor": "", "limit": limit}, config=config)
    return list(data.get("addable_knowledge_base_list", []) or [])


def resolve_knowledge_base_id(
    *,
    config: Dict[str, Any],
    kb_id: str = "",
    kb_name: str = "",
    require: bool = False,
    allow_default: bool = True,
) -> str:
    if kb_id.strip():
        return kb_id.strip()

    configured_name = str(config.get("default_knowledge_base_name", "")).strip() if allow_default else ""
    configured_id = str(config.get("default_knowledge_base_id", "")).strip() if allow_default else ""
    if configured_id and not kb_name.strip():
        return configured_id

    lookup_name = kb_name.strip() or configured_name
    if not lookup_name:
        if require:
            raise ValueError("Knowledge base is required. Use --kb-id / --kb-name or configure a default knowledge base.")
        return ""

    candidates = list_knowledge_bases(config=config, query=lookup_name, limit=50) or list_knowledge_bases(config=config, query="", limit=50)
    normalized_lookup = lookup_name.lower()
    exact_matches = [item for item in candidates if str(item.get("name", "")).strip().lower() == normalized_lookup]
    contains_matches = [item for item in candidates if normalized_lookup in str(item.get("name", "")).strip().lower()]
    if len(exact_matches) == 1:
        return str(exact_matches[0]["id"])
    if len(contains_matches) == 1:
        return str(contains_matches[0]["id"])
    if len(candidates) == 1:
        return str(candidates[0]["id"])
    if not candidates:
        raise ValueError(f"No knowledge base matched: {lookup_name}")
    matched_names = ", ".join(str(item.get("name", "")) for item in (exact_matches or contains_matches or candidates)[:10])
    raise ValueError(f"Knowledge base name is ambiguous: {lookup_name}. Candidates: {matched_names}")


def resolve_knowledge_folder_id(config: Dict[str, Any], folder_id: str) -> str:
    explicit_folder = folder_id.strip()
    if explicit_folder:
        return explicit_folder
    configured_folder = str(config.get("default_knowledge_folder_id", "")).strip()
    if configured_folder:
        return configured_folder
    return ""


def get_root_knowledge_folder_id(*, config: Dict[str, Any], knowledge_base_id: str) -> str:
    payload = api_call(
        "openapi/wiki/v1/get_knowledge_list",
        {"knowledge_base_id": knowledge_base_id, "cursor": "", "limit": 1},
        config=config,
    )
    current_path = payload.get("current_path", []) or []
    if current_path:
        return str(current_path[0].get("folder_id", "")).strip() or knowledge_base_id
    return knowledge_base_id


def render_kb_list(items: Sequence[Dict[str, Any]]) -> str:
    lines = [f"知识库数量: {len(items)}"]
    for item in items:
        lines.append(f"- {item.get('name', '')} ({item.get('id', '')})")
    return "\n".join(lines)


def clean_highlight_text(value: str) -> str:
    text = re.sub(r"</?em>", "", value or "", flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def truncate_display_text(value: str, limit: int = 320) -> str:
    text = clean_highlight_text(value)
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)].rstrip() + "…"


def normalize_query_term(value: str) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    if not text:
        return ""
    if re.search(r"[\u4e00-\u9fff]", text):
        while len(text) > 2 and text.endswith(TRAILING_QUERY_PARTICLES):
            text = text[:-1].strip()
    return text


def is_informative_query_term(value: str) -> bool:
    text = normalize_query_term(value)
    if not text:
        return False
    if re.fullmatch(r"[\u4e00-\u9fff]", text):
        return False
    if re.fullmatch(r"[A-Za-z0-9]", text):
        return False
    return True


def split_query_terms(value: str) -> List[str]:
    raw_parts = [item.strip() for item in re.split(r"[\s,，、;；/|]+", value or "") if item.strip()]
    raw_parts = raw_parts or ([value.strip()] if str(value).strip() else [])
    informative_terms: List[str] = []
    fallback_terms: List[str] = []
    for item in raw_parts:
        normalized = normalize_query_term(item) or item
        if normalized and normalized not in fallback_terms:
            fallback_terms.append(normalized)
        if is_informative_query_term(normalized) and normalized not in informative_terms:
            informative_terms.append(normalized)
    return informative_terms or fallback_terms


def count_excerpt_term_matches(excerpt: str, terms: Sequence[str]) -> int:
    searchable = clean_highlight_text(excerpt).lower()
    return sum(1 for term in terms if term and term.lower() in searchable)


def matched_terms_in_searchable(searchable: str, terms: Sequence[str]) -> List[str]:
    lowered = searchable.lower()
    matched: List[str] = []
    for term in terms:
        normalized = str(term).strip()
        if normalized and normalized.lower() in lowered and normalized not in matched:
            matched.append(normalized)
    return matched


def is_clean_summary_excerpt(value: str) -> bool:
    text = clean_highlight_text(value)
    if not text:
        return False
    noise_count = sum(text.count(ch) for ch in OCR_NOISE_CHARS)
    return noise_count <= max(4, len(text) // 40)


def is_substantially_richer_excerpt(candidate: str, baseline: str) -> bool:
    candidate_text = clean_highlight_text(candidate)
    baseline_text = clean_highlight_text(baseline)
    return len(candidate_text) >= max(30, len(baseline_text) + 12)


def choose_preferred_hit(current: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, Any]:
    current_terms = split_query_terms(str(current.get("query", "")))
    candidate_terms = split_query_terms(str(candidate.get("query", "")))
    current_excerpt = clean_highlight_text(str(current.get("highlight_content", "")))
    candidate_excerpt = clean_highlight_text(str(candidate.get("highlight_content", "")))
    current_key = (
        count_excerpt_term_matches(current_excerpt, current_terms),
        len(current_excerpt),
    )
    candidate_key = (
        count_excerpt_term_matches(candidate_excerpt, candidate_terms),
        len(candidate_excerpt),
    )
    return candidate if candidate_key > current_key else current


def is_relevant_kb_item(item: Dict[str, Any], query: str) -> bool:
    terms = split_query_terms(query)
    if not terms:
        return True
    searchable = " ".join([str(item.get("title", "")).strip(), clean_highlight_text(str(item.get("highlight_content", "")))]).lower()
    matched_terms = matched_terms_in_searchable(searchable, terms)
    if len(terms) <= 1:
        return bool(matched_terms)
    return len(matched_terms) == len(terms)


def render_kb_search_results(
    results: Sequence[Dict[str, Any]],
    *,
    query: str = "",
    keywords: Sequence[str] = (),
    kb_id: str = "",
    kb_name: str = "",
    display_limit: int = 5,
) -> str:
    del query, keywords, kb_id, kb_name
    flattened_hits = flatten_kb_content_hits(results)
    if flattened_hits:
        lines: List[str] = [f"知识库命中: {len(flattened_hits)}"]
        shown_hits = flattened_hits[: max(1, display_limit)]
        for index, hit in enumerate(shown_hits, start=1):
            line = f"{index}. {hit.get('title', '')}"
            kb_label = str(hit.get("knowledge_base_name", "")).strip()
            if kb_label:
                line += f" [{kb_label}]"
            lines.append(line)
            highlight = truncate_display_text(str(hit.get("highlight_content", "")), limit=180)
            if highlight:
                lines.append(f"   {highlight}")
        if len(flattened_hits) > len(shown_hits):
            lines.append(f"其余结果: {len(flattened_hits) - len(shown_hits)}")
        return "\n".join(lines)
    permission_errors = [group for group in results if group.get("error")]
    if permission_errors:
        return f"知识库命中: 0\n说明: 当前没有命中可访问内容，另有 {len(permission_errors)} 个知识库因权限被跳过。"
    return "知识库命中: 0"


def build_permission_result(
    *,
    knowledge_base_id: str,
    knowledge_base_name: str,
    query: str = "",
    error: str,
) -> Dict[str, Any]:
    return {
        "knowledge_base_id": knowledge_base_id,
        "knowledge_base_name": knowledge_base_name,
        "query": query,
        "items": [],
        "is_end": True,
        "next_cursor": "",
        "error": error,
        "error_type": "permission_denied",
    }


def flatten_raw_kb_content_hits(groups: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    hits: List[Dict[str, Any]] = []
    for group in groups:
        for item in group.get("items", []) or []:
            hits.append(
                {
                    "query": group.get("query", ""),
                    "knowledge_base_id": group.get("knowledge_base_id", ""),
                    "knowledge_base_name": group.get("knowledge_base_name", ""),
                    "media_id": item.get("media_id", ""),
                    "title": item.get("title", ""),
                    "parent_folder_id": item.get("parent_folder_id", ""),
                    "highlight_content": item.get("highlight_content", ""),
                }
            )
    return hits


def build_kb_hit_key(hit: Dict[str, Any]) -> tuple[str, str]:
    knowledge_base_id = str(hit.get("knowledge_base_id", "")).strip()
    media_id = str(hit.get("media_id", "")).strip()
    if media_id:
        return knowledge_base_id, media_id
    title = str(hit.get("title", "")).strip().lower()
    parent_folder_id = str(hit.get("parent_folder_id", "")).strip()
    return knowledge_base_id, f"{title}::{parent_folder_id}"


def flatten_kb_content_hits(groups: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    raw_hits = flatten_raw_kb_content_hits(groups)
    aggregated: Dict[tuple[str, str], Dict[str, Any]] = {}
    for index, hit in enumerate(raw_hits):
        hit_key = build_kb_hit_key(hit)
        terms = split_query_terms(str(hit.get("query", "")))
        searchable = " ".join(
            [
                str(hit.get("title", "")).strip(),
                clean_highlight_text(str(hit.get("highlight_content", ""))),
            ]
        )
        matched_terms = matched_terms_in_searchable(searchable, terms)
        aggregated_hit = aggregated.get(hit_key)
        if aggregated_hit is None:
            aggregated[hit_key] = {
                **hit,
                "queries": [str(hit.get("query", "")).strip()] if str(hit.get("query", "")).strip() else [],
                "matched_terms": matched_terms,
                "first_seen_index": index,
            }
            continue

        query = str(hit.get("query", "")).strip()
        if query and query not in aggregated_hit["queries"]:
            aggregated_hit["queries"].append(query)
        for term in matched_terms:
            if term and term not in aggregated_hit["matched_terms"]:
                aggregated_hit["matched_terms"].append(term)
        preferred = choose_preferred_hit(aggregated_hit, hit)
        if preferred is hit:
            aggregated_hit["query"] = hit.get("query", "")
            aggregated_hit["highlight_content"] = hit.get("highlight_content", "")
            aggregated_hit["parent_folder_id"] = hit.get("parent_folder_id", "")

    aggregated_hits = list(aggregated.values())
    for hit in aggregated_hits:
        hit["query_count"] = len(hit.get("queries", []))
        hit["matched_term_count"] = len(hit.get("matched_terms", []))
    aggregated_hits.sort(
        key=lambda item: (
            -int(item.get("matched_term_count", 0)),
            -int(item.get("query_count", 0)),
            -len(clean_highlight_text(str(item.get("highlight_content", "")))),
            int(item.get("first_seen_index", 0)),
        )
    )
    return aggregated_hits


def build_folder_context_for_hit(hit: Dict[str, Any], *, config: Dict[str, Any], limit: int = 10) -> Dict[str, Any]:
    knowledge_base_id = str(hit.get("knowledge_base_id", "")).strip()
    folder_id = str(hit.get("parent_folder_id", "")).strip()
    if not knowledge_base_id or not folder_id:
        return {"items": [], "current_path": [], "error": "当前命中缺少知识库或文件夹定位信息。"}
    try:
        payload = api_call(
            "openapi/wiki/v1/get_knowledge_list",
            {"knowledge_base_id": knowledge_base_id, "folder_id": folder_id, "cursor": "", "limit": limit},
            config=config,
        )
    except IMAApiError as exc:
        if is_permission_denied(exc.retcode, exc.errmsg):
            return {"items": [], "current_path": [], "error": "没有权限继续浏览该命中的所在文件夹。"}
        raise
    items = list(payload.get("knowledge_list", []) or [])
    current_title = str(hit.get("title", "")).strip()
    sibling_items = [item for item in items if str(item.get("title", "")).strip() != current_title]
    return {"items": sibling_items, "current_path": payload.get("current_path", []) or [], "error": ""}


def candidate_queries_for_hit(hit: Dict[str, Any]) -> List[str]:
    candidates: List[str] = []
    query = str(hit.get("query", "")).strip()
    for matched_query in hit.get("queries", []) or []:
        if str(matched_query).strip():
            candidates.append(str(matched_query).strip())
    title = str(hit.get("title", "")).strip()
    if query:
        candidates.append(query)
    if title:
        candidates.append(title)
        if "." in title:
            stem = title.rsplit(".", 1)[0].strip()
            if stem and stem != title:
                candidates.append(stem)

    deduped: List[str] = []
    seen = set()
    for item in candidates:
        normalized = item.lower()
        if item and normalized not in seen:
            deduped.append(item)
            seen.add(normalized)
    return deduped

def search_knowledge_with_paging(
    *,
    config: Dict[str, Any],
    knowledge_base_id: str,
    query: str,
    item_limit: int,
    page_limit: int,
) -> Dict[str, Any]:
    collected_items: List[Dict[str, Any]] = []
    cursor = ""
    next_cursor = ""
    is_end = True
    pages_scanned = 0

    while pages_scanned < page_limit and len(collected_items) < item_limit:
        payload = api_call(
            "openapi/wiki/v1/search_knowledge",
            {"knowledge_base_id": knowledge_base_id, "query": query, "cursor": cursor},
            config=config,
        )
        pages_scanned += 1
        next_cursor = str(payload.get("next_cursor", "") or "")
        is_end = bool(payload.get("is_end", True))

        for item in list(payload.get("info_list", []) or []):
            if is_relevant_kb_item(item, query):
                collected_items.append(item)
                if len(collected_items) >= item_limit:
                    break

        if is_end or not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor

    return {
        "items": collected_items[:item_limit],
        "is_end": is_end,
        "next_cursor": next_cursor,
        "pages_scanned": pages_scanned,
    }


def build_enriched_hit_context(hit: Dict[str, Any], *, config: Dict[str, Any], limit: int = 5) -> Dict[str, Any]:
    knowledge_base_id = str(hit.get("knowledge_base_id", "")).strip()
    media_id = str(hit.get("media_id", "")).strip()
    title = str(hit.get("title", "")).strip()
    if not knowledge_base_id:
        return {"queries": [], "matches": [], "best_match": None}

    matches: List[Dict[str, Any]] = []
    for query in candidate_queries_for_hit(hit):
        try:
            payload = api_call(
                "openapi/wiki/v1/search_knowledge",
                {"knowledge_base_id": knowledge_base_id, "query": query, "cursor": ""},
                config=config,
            )
        except IMAApiError as exc:
            if is_permission_denied(exc.retcode, exc.errmsg):
                continue
            raise
        for item in list(payload.get("info_list", []) or [])[:limit]:
            same_item = False
            if media_id and str(item.get("media_id", "")).strip() == media_id:
                same_item = True
            elif title and str(item.get("title", "")).strip().lower() == title.lower():
                same_item = True
            if not same_item:
                continue
            matches.append(
                {
                    "query": query,
                    "media_id": item.get("media_id", ""),
                    "title": item.get("title", ""),
                    "parent_folder_id": item.get("parent_folder_id", ""),
                    "highlight_content": clean_highlight_text(str(item.get("highlight_content", ""))),
                }
            )

    deduped_matches: List[Dict[str, Any]] = []
    seen_pairs = set()
    for item in matches:
        key = (str(item.get("query", "")).strip().lower(), str(item.get("highlight_content", "")).strip())
        if key in seen_pairs:
            continue
        deduped_matches.append(item)
        seen_pairs.add(key)

    original_query = str(hit.get("query", "")).strip().lower()
    baseline_excerpt = clean_highlight_text(str(hit.get("highlight_content", "")))
    aggregate_terms: List[str] = []
    for term in hit.get("matched_terms", []) or []:
        if str(term).strip() and str(term).strip() not in aggregate_terms:
            aggregate_terms.append(str(term).strip())
    for query in hit.get("queries", []) or []:
        for term in split_query_terms(str(query)):
            if term and term not in aggregate_terms:
                aggregate_terms.append(term)
    if not aggregate_terms and original_query:
        aggregate_terms = split_query_terms(original_query)

    def match_rank(item: Dict[str, Any]) -> tuple[int, int, int, int, int]:
        excerpt = clean_highlight_text(str(item.get("highlight_content", "")))
        clean_summary = 1 if is_clean_summary_excerpt(excerpt) else 0
        richer = 1 if is_substantially_richer_excerpt(excerpt, baseline_excerpt) else 0
        exact_query = 1 if str(item.get("query", "")).strip().lower() == original_query else 0
        match_count = count_excerpt_term_matches(excerpt, aggregate_terms)
        return (
            1 if clean_summary and richer else 0,
            match_count,
            exact_query,
            clean_summary,
            len(excerpt),
        )

    best_match = max(deduped_matches, key=match_rank) if deduped_matches else None
    return {"queries": candidate_queries_for_hit(hit), "matches": deduped_matches, "best_match": best_match}


def select_best_hit_excerpt(hit: Dict[str, Any], enriched_context: Optional[Dict[str, Any]] = None) -> str:
    if enriched_context:
        best_match = enriched_context.get("best_match") or {}
        enriched_highlight = clean_highlight_text(str(best_match.get("highlight_content", ""))).strip()
        if enriched_highlight:
            return enriched_highlight
    return clean_highlight_text(str(hit.get("highlight_content", ""))).strip()


def render_concise_kb_hit_detail(hit: Dict[str, Any], *, enriched_context: Optional[Dict[str, Any]] = None) -> str:
    excerpt = select_best_hit_excerpt(hit, enriched_context=enriched_context)
    lines = [f"标题: {hit.get('title', '')}"]
    kb_name = str(hit.get("knowledge_base_name", "")).strip()
    if kb_name:
        lines.append(f"知识库: {kb_name}")
    matched_terms = [str(item).strip() for item in hit.get("matched_terms", []) or [] if str(item).strip()]
    if matched_terms:
        lines.append(f"命中词: {'、'.join(matched_terms[:5])}")
    if excerpt:
        lines.append(f"结果片段: {truncate_display_text(excerpt)}")
    else:
        lines.append("结果片段: 当前只能定位到该条目，接口未返回可展示的命中片段。")
        lines.append("说明: 无法直接读取全文，只能返回稳定命中的结果片段。")
    return "\n".join(lines)


def render_kb_hit_detail(hit: Dict[str, Any], *, folder_context: Optional[Dict[str, Any]] = None) -> str:
    del folder_context
    return render_concise_kb_hit_detail(hit)


def render_inspected_kb_hit_detail(
    hit: Dict[str, Any],
    *,
    folder_context: Optional[Dict[str, Any]] = None,
    enriched_context: Optional[Dict[str, Any]] = None,
) -> str:
    del folder_context
    return render_concise_kb_hit_detail(hit, enriched_context=enriched_context)


def command_test(args: argparse.Namespace, config: Dict[str, Any]) -> Dict[str, Any]:
    require_credentials(config)
    tests: List[Dict[str, Any]] = []

    def run(name: str, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        result = post_json(endpoint, payload, config=config)
        ok, retcode, errmsg, data = unwrap_response(result)
        item = {"name": name, "endpoint": endpoint, "ok": ok, "retcode": retcode, "errmsg": errmsg, "data": data}
        tests.append(item)
        return item

    kb_listing = run("list_knowledge_bases", "openapi/wiki/v1/search_knowledge_base", {"query": "", "cursor": "", "limit": 10})
    addable = run("list_addable_knowledge_bases", "openapi/wiki/v1/get_addable_knowledge_base_list", {"cursor": "", "limit": 10})

    kb_candidates = addable["data"].get("addable_knowledge_base_list", []) if addable["ok"] else []
    read_kb_id = args.kb_id or ""
    if not read_kb_id and kb_candidates:
        read_kb_id = str(kb_candidates[0].get("id", ""))
    if not read_kb_id and kb_listing["ok"]:
        kb_items = kb_listing["data"].get("info_list", []) or []
        if kb_items:
            read_kb_id = str(kb_items[0].get("id", ""))

    if read_kb_id:
        run("get_knowledge_base", "openapi/wiki/v1/get_knowledge_base", {"ids": [read_kb_id]})
        run("list_knowledge_items", "openapi/wiki/v1/get_knowledge_list", {"knowledge_base_id": read_kb_id, "cursor": "", "limit": 5})
        run("search_knowledge", "openapi/wiki/v1/search_knowledge", {"knowledge_base_id": read_kb_id, "query": args.kb_query, "cursor": ""})

    passed = sum(1 for item in tests if item["ok"])
    return {
        "config_path": config["config_path"],
        "base_url": config["base_url"],
        "passed": passed,
        "total": len(tests),
        "all_passed": passed == len(tests),
        "tests": tests,
        "effective_knowledge_base_id": read_kb_id,
        "effective_kb_query": args.kb_query,
    }


def command_list_kb(args: argparse.Namespace, config: Dict[str, Any]) -> Any:
    items = list_knowledge_bases(config=config, query=args.query or "", limit=args.limit)
    payload = {"query": args.query or "", "count": len(items), "items": items}
    return payload if args.json else render_kb_list(items)


def command_list_addable_kb(args: argparse.Namespace, config: Dict[str, Any]) -> Any:
    items = list_addable_knowledge_bases(config=config, limit=args.limit)
    payload = {"count": len(items), "items": items}
    return payload if args.json else render_kb_list(items)


def command_list_kb_items(args: argparse.Namespace, config: Dict[str, Any]) -> Any:
    knowledge_base_id = resolve_knowledge_base_id(config=config, kb_id=args.kb_id, kb_name=args.kb_name, require=True)
    request_payload: Dict[str, Any] = {"knowledge_base_id": knowledge_base_id, "cursor": args.cursor, "limit": args.limit}
    if args.folder_id:
        request_payload["folder_id"] = args.folder_id
    try:
        payload = api_call("openapi/wiki/v1/get_knowledge_list", request_payload, config=config)
    except IMAApiError as exc:
        if is_permission_denied(exc.retcode, exc.errmsg):
            result = {
                "knowledge_base_id": knowledge_base_id,
                "folder_id": args.folder_id or "",
                "items": [],
                "current_path": [],
                "is_end": True,
                "next_cursor": "",
                "error": f"没有权限访问该知识库: {args.kb_name or knowledge_base_id}",
                "error_type": "permission_denied",
            }
            return result if args.json else result["error"]
        raise
    result = {
        "knowledge_base_id": knowledge_base_id,
        "folder_id": args.folder_id or "",
        "items": payload.get("knowledge_list", []),
        "current_path": payload.get("current_path", []),
        "is_end": payload.get("is_end", True),
        "next_cursor": payload.get("next_cursor", ""),
    }
    if args.json:
        return result
    lines = [f"知识库: {knowledge_base_id}", f"条目数量: {len(result['items'])}"]
    for item in result["items"]:
        lines.append(f"- {item.get('title', '')} ({item.get('media_id', '')})")
    return "\n".join(lines)


def command_search_kb(args: argparse.Namespace, config: Dict[str, Any]) -> Any:
    queries = join_keywords(args.query, args.keyword)
    if not queries:
        raise ValueError("Use --query or one or more --keyword values.")
    item_limit = max(1, int(getattr(args, "limit", 10)))
    kb_scan_limit = max(1, int(getattr(args, "kb_limit", 20)))
    display_limit = max(1, int(getattr(args, "show", 5)))
    search_pages = max(1, int(getattr(args, "search_pages", 1)))

    kb_id = ""
    if args.kb_id or args.kb_name:
        kb_id = resolve_knowledge_base_id(config=config, kb_id=args.kb_id, kb_name=args.kb_name, require=True)
    elif config.get("restrict_search_to_default_knowledge_base"):
        kb_id = resolve_knowledge_base_id(config=config, require=True, allow_default=True)

    if kb_id:
        details = api_call("openapi/wiki/v1/get_knowledge_base", {"ids": [kb_id]}, config=config)
        info = details.get("infos", {}).get(kb_id, {})
        kb_targets = [{"id": kb_id, "name": info.get("name", args.kb_name or kb_id)}]
    else:
        kb_targets = list_knowledge_bases(config=config, query="", limit=kb_scan_limit)

    groups: List[Dict[str, Any]] = []
    skipped_knowledge_bases: List[Dict[str, Any]] = []
    for kb in kb_targets:
        for query in queries:
            try:
                search_result = search_knowledge_with_paging(
                    config=config,
                    knowledge_base_id=str(kb["id"]),
                    query=query,
                    item_limit=item_limit,
                    page_limit=search_pages,
                )
                groups.append(
                    {
                        "knowledge_base_id": kb["id"],
                        "knowledge_base_name": kb.get("name", ""),
                        "query": query,
                        "items": search_result["items"],
                        "is_end": search_result["is_end"],
                        "next_cursor": search_result["next_cursor"],
                        "pages_scanned": search_result["pages_scanned"],
                    }
                )
            except IMAApiError as exc:
                if is_permission_denied(exc.retcode, exc.errmsg):
                    permission_result = build_permission_result(
                        knowledge_base_id=str(kb["id"]),
                        knowledge_base_name=str(kb.get("name", "")),
                        query=query,
                        error=f"没有权限访问知识库 {kb.get('name', kb['id'])}",
                    )
                    groups.append(permission_result)
                    skipped_knowledge_bases.append(
                        {
                            "knowledge_base_id": kb["id"],
                            "knowledge_base_name": kb.get("name", ""),
                            "query": query,
                            "reason": permission_result["error"],
                        }
                    )
                    continue
                raise

    raw_content_hits = flatten_raw_kb_content_hits(groups)
    content_hits = flatten_kb_content_hits(groups)
    payload = {
        "queries": queries,
        "content_hit_count": len(content_hits),
        "content_hits": content_hits,
        "raw_content_hit_count": len(raw_content_hits),
        "raw_content_hits": raw_content_hits,
        "searched_knowledge_bases": kb_targets,
        "groups": groups,
        "skipped_knowledge_bases": skipped_knowledge_bases,
        "display_limit": display_limit,
        "per_kb_limit": item_limit,
        "search_pages": search_pages,
        "kb_scan_limit": kb_scan_limit,
    }
    return payload if args.json else render_kb_search_results(groups, query=args.query, keywords=args.keyword, kb_id=args.kb_id, kb_name=args.kb_name, display_limit=display_limit)


def command_upload_file(args: argparse.Namespace, config: Dict[str, Any]) -> Any:
    knowledge_base_id = resolve_knowledge_base_id(config=config, kb_id=args.kb_id, kb_name=args.kb_name, require=True)
    folder_id = resolve_knowledge_folder_id(config, args.folder_id or "")
    file_info = preflight_file(args.file, content_type=args.content_type or "")

    repeated_request: Dict[str, Any] = {"knowledge_base_id": knowledge_base_id, "params": [{"name": file_info["file_name"], "media_type": file_info["media_type"]}]}
    if folder_id:
        repeated_request["folder_id"] = folder_id
    repeated = api_call("openapi/wiki/v1/check_repeated_names", repeated_request, config=config)
    duplicate_items = [item for item in repeated.get("results", []) or [] if item.get("is_repeated")]
    if duplicate_items and not args.allow_duplicate:
        raise ValueError(f"Duplicate file name detected in the target knowledge base: {duplicate_items[0].get('name', file_info['file_name'])}. Use --allow-duplicate to continue anyway.")

    create_media = api_call(
        "openapi/wiki/v1/create_media",
        {
            "file_name": file_info["file_name"],
            "file_size": file_info["file_size"],
            "content_type": file_info["content_type"],
            "knowledge_base_id": knowledge_base_id,
            "file_ext": file_info["file_ext"],
        },
        config=config,
    )
    upload_result = cos_upload(file_info["file_path"], create_media["cos_credential"], content_type=str(file_info["content_type"]))

    final_title = args.title or str(file_info["file_name"])
    add_payload: Dict[str, Any] = {
        "media_type": file_info["media_type"],
        "media_id": create_media["media_id"],
        "title": final_title,
        "knowledge_base_id": knowledge_base_id,
        "file_info": {
            "cos_key": create_media["cos_credential"]["cos_key"],
            "file_size": file_info["file_size"],
            "last_modify_time": int(Path(file_info["file_path"]).stat().st_mtime),
            "password": args.file_password or "",
            "file_name": file_info["file_name"],
        },
    }
    if folder_id:
        add_payload["folder_id"] = folder_id
    add_result = api_call("openapi/wiki/v1/add_knowledge", add_payload, config=config)
    payload = {
        "knowledge_base_id": knowledge_base_id,
        "folder_id": folder_id,
        "file": file_info,
        "duplicate_check": repeated.get("results", []),
        "create_media": create_media,
        "cos_upload": upload_result,
        "add_knowledge": add_result,
    }
    if args.json:
        return payload
    return "\n".join([f"上传成功: {file_info['file_name']}", f"知识库: {knowledge_base_id}", f"文件夹: {folder_id}", f"media_id: {create_media['media_id']}"])


def command_import_url(args: argparse.Namespace, config: Dict[str, Any]) -> Any:
    knowledge_base_id = resolve_knowledge_base_id(config=config, kb_id=args.kb_id, kb_name=args.kb_name, require=True)
    folder_id = resolve_knowledge_folder_id(config, args.folder_id or "") or get_root_knowledge_folder_id(config=config, knowledge_base_id=knowledge_base_id)
    urls = [url.strip() for url in args.url if url.strip()]
    if not urls:
        raise ValueError("Use one or more --url values.")
    payload = api_call("openapi/wiki/v1/import_urls", {"knowledge_base_id": knowledge_base_id, "folder_id": folder_id, "urls": urls}, config=config)
    result = {"knowledge_base_id": knowledge_base_id, "folder_id": folder_id, "urls": urls, "results": payload.get("results", {})}
    if args.json:
        return result
    lines = [f"URL 导入完成: {len(urls)} 条"]
    for url, info in (payload.get("results", {}) or {}).items():
        lines.append(f"- {url} -> ret_code={info.get('ret_code')} media_id={info.get('media_id', '')}")
    return "\n".join(lines)


def command_show_kb_hit(args: argparse.Namespace, config: Dict[str, Any]) -> Any:
    search_args = argparse.Namespace(
        kb_id=args.kb_id,
        kb_name=args.kb_name,
        query=args.query,
        keyword=args.keyword,
        limit=args.limit,
        kb_limit=args.kb_limit,
        search_pages=args.search_pages,
        json=True,
    )
    result = command_search_kb(search_args, config)
    hits = result.get("content_hits", [])
    if not hits:
        raise ValueError("没有找到可查看的知识库内容命中。请先换一个关键词，或先执行 search-kb 确认有结果。")

    selected_hit: Optional[Dict[str, Any]] = None
    if args.media_id:
        for hit in hits:
            if str(hit.get("media_id", "")) == args.media_id:
                selected_hit = hit
                break
        if selected_hit is None:
            raise ValueError(f"没有找到指定 media_id 的命中项: {args.media_id}")
    elif args.title:
        exact_matches = [hit for hit in hits if str(hit.get("title", "")).strip().lower() == args.title.strip().lower()]
        if len(exact_matches) == 1:
            selected_hit = exact_matches[0]
        elif len(exact_matches) > 1:
            raise ValueError(f"找到多条同名命中，请改用 --pick 或 --media-id: {args.title}")
        else:
            title_matches = [hit for hit in hits if args.title.strip().lower() in str(hit.get("title", "")).strip().lower()]
            if len(title_matches) == 1:
                selected_hit = title_matches[0]
            elif len(title_matches) > 1:
                raise ValueError(f"找到多条标题包含该词的命中，请改用 --pick 或 --media-id: {args.title}")
            else:
                raise ValueError(f"没有找到标题匹配的命中项: {args.title}")
    else:
        pick_index = args.pick
        if pick_index < 1 or pick_index > len(hits):
            raise ValueError(f"--pick 超出范围，当前共有 {len(hits)} 条命中。")
        selected_hit = hits[pick_index - 1]

    detail = {
        "selected_hit": selected_hit,
        "available_hit_count": len(hits),
        "queries": result.get("queries", []),
        "folder_context": build_folder_context_for_hit(selected_hit, config=config, limit=10),
    }
    return detail if args.json else render_kb_hit_detail(selected_hit, folder_context=detail["folder_context"])


def command_inspect_kb_hit(args: argparse.Namespace, config: Dict[str, Any]) -> Any:
    show_args = argparse.Namespace(
        kb_id=args.kb_id,
        kb_name=args.kb_name,
        query=args.query,
        keyword=args.keyword,
        pick=args.pick,
        media_id=args.media_id,
        title=args.title,
        limit=args.limit,
        kb_limit=args.kb_limit,
        search_pages=args.search_pages,
        json=True,
    )
    detail = command_show_kb_hit(show_args, config)
    selected_hit = detail["selected_hit"]
    enriched_context = build_enriched_hit_context(selected_hit, config=config, limit=5)
    result = {**detail, "enriched_context": enriched_context}
    if args.json:
        return result
    return render_inspected_kb_hit_detail(selected_hit, folder_context=result.get("folder_context"), enriched_context=enriched_context)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="IMA knowledge-base CLI")
    parser.add_argument("--config", help="Optional path to config.json")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def with_json(subparser: argparse.ArgumentParser) -> argparse.ArgumentParser:
        subparser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
        return subparser

    test_parser = with_json(subparsers.add_parser("test", help="Run integrated connectivity checks"))
    test_parser.add_argument("--kb-id", default="", help="Optional knowledge base ID used for read tests")
    test_parser.add_argument("--kb-query", default="a", help="Keyword used for knowledge search test")

    list_kb = with_json(subparsers.add_parser("list-kb", help="List knowledge bases"))
    list_kb.add_argument("--query", default="", help="Optional knowledge-base keyword")
    list_kb.add_argument("--limit", type=int, default=20, help="Maximum number of knowledge bases to return")

    list_addable_kb = with_json(subparsers.add_parser("list-addable-kb", help="List writable knowledge bases"))
    list_addable_kb.add_argument("--limit", type=int, default=20, help="Maximum number of knowledge bases to return")

    list_kb_items = with_json(subparsers.add_parser("list-kb-items", help="List items in a knowledge base or folder"))
    list_kb_items.add_argument("--kb-id", default="", help="Target knowledge base ID")
    list_kb_items.add_argument("--kb-name", default="", help="Target knowledge base name")
    list_kb_items.add_argument("--folder-id", default="", help="Optional target folder ID")
    list_kb_items.add_argument("--cursor", default="", help="Pagination cursor")
    list_kb_items.add_argument("--limit", type=int, default=20, help="Maximum number of items to return")

    search_kb = with_json(subparsers.add_parser("search-kb", help="Search knowledge-base content"))
    search_kb.add_argument("--kb-id", default="", help="Scope search to one knowledge base ID")
    search_kb.add_argument("--kb-name", default="", help="Scope search to one knowledge base name")
    search_kb.add_argument("--query", default="", help='Single combined query, for example "午餐 菜单"')
    search_kb.add_argument("--keyword", action="append", default=[], help='Repeatable keyword. `--keyword "午餐 美食 推荐"` 会自动拆成多个关键词分别搜索')
    search_kb.add_argument("--limit", type=int, default=10, help="Maximum number of hits kept per keyword and knowledge base")
    search_kb.add_argument("--show", type=int, default=5, help="Maximum number of hits shown in text output")
    search_kb.add_argument("--search-pages", type=int, default=1, help="Maximum number of search_knowledge pages scanned per keyword and knowledge base")
    search_kb.add_argument("--kb-limit", type=int, default=20, help="Maximum number of knowledge bases scanned when no --kb-id/--kb-name is given")

    show_kb_hit = with_json(subparsers.add_parser("show-kb-hit", help="Show one specific knowledge-base content hit in detail"))
    show_kb_hit.add_argument("--kb-id", default="", help="Optional knowledge base ID to narrow the search")
    show_kb_hit.add_argument("--kb-name", default="", help="Optional knowledge base name to narrow the search")
    show_kb_hit.add_argument("--query", default="", help='Single combined query, for example "orslow 朴期"')
    show_kb_hit.add_argument("--keyword", action="append", default=[], help='Repeatable keyword. `--keyword "orslow 朴期"` 会自动拆词')
    show_kb_hit.add_argument("--pick", type=int, default=1, help="Pick the Nth hit from the flattened content_hits result, 1-based")
    show_kb_hit.add_argument("--media-id", default="", help="Directly select a hit by media_id")
    show_kb_hit.add_argument("--title", default="", help="Directly select a hit by title")
    show_kb_hit.add_argument("--limit", type=int, default=10, help="Maximum number of hits kept per keyword and knowledge base")
    show_kb_hit.add_argument("--search-pages", type=int, default=1, help="Maximum number of search_knowledge pages scanned per keyword and knowledge base")
    show_kb_hit.add_argument("--kb-limit", type=int, default=20, help="Maximum number of knowledge bases scanned when no --kb-id/--kb-name is given")

    inspect_kb_hit = with_json(subparsers.add_parser("inspect-kb-hit", help="Deep-inspect one knowledge-base hit with richer OCR-like content and folder context"))
    inspect_kb_hit.add_argument("--kb-id", default="", help="Optional knowledge base ID to narrow the search")
    inspect_kb_hit.add_argument("--kb-name", default="", help="Optional knowledge base name to narrow the search")
    inspect_kb_hit.add_argument("--query", default="", help='Single combined query, for example "orslow 朴期"')
    inspect_kb_hit.add_argument("--keyword", action="append", default=[], help='Repeatable keyword. `--keyword "orslow 朴期"` 会自动拆词')
    inspect_kb_hit.add_argument("--pick", type=int, default=1, help="Pick the Nth hit from the flattened content_hits result, 1-based")
    inspect_kb_hit.add_argument("--media-id", default="", help="Directly select a hit by media_id")
    inspect_kb_hit.add_argument("--title", default="", help="Directly select a hit by title")
    inspect_kb_hit.add_argument("--limit", type=int, default=10, help="Maximum number of hits kept per keyword and knowledge base")
    inspect_kb_hit.add_argument("--search-pages", type=int, default=1, help="Maximum number of search_knowledge pages scanned per keyword and knowledge base")
    inspect_kb_hit.add_argument("--kb-limit", type=int, default=20, help="Maximum number of knowledge bases scanned when no --kb-id/--kb-name is given")

    upload_file = with_json(subparsers.add_parser("upload-file", help="Upload a local file into a knowledge base"))
    upload_file.add_argument("--kb-id", default="", help="Target knowledge base ID")
    upload_file.add_argument("--kb-name", default="", help="Target knowledge base name")
    upload_file.add_argument("--folder-id", default="", help="Optional target folder ID")
    upload_file.add_argument("--file", required=True, help="Local file path")
    upload_file.add_argument("--title", default="", help="Final title shown in the knowledge base")
    upload_file.add_argument("--content-type", default="", help="Optional MIME type override")
    upload_file.add_argument("--file-password", default="", help="Optional file password for protected documents")
    upload_file.add_argument("--allow-duplicate", action="store_true", help="Continue even when a duplicate file name is detected")

    import_url = with_json(subparsers.add_parser("import-url", help="Import one or more web pages into a knowledge base"))
    import_url.add_argument("--kb-id", default="", help="Target knowledge base ID")
    import_url.add_argument("--kb-name", default="", help="Target knowledge base name")
    import_url.add_argument("--folder-id", default="", help="Optional target folder ID")
    import_url.add_argument("--url", action="append", required=True, help="Repeatable URL value. Use multiple --url options for batch import")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    config = load_skill_config(args.config)

    handlers = {
        "test": command_test,
        "list-kb": command_list_kb,
        "list-addable-kb": command_list_addable_kb,
        "list-kb-items": command_list_kb_items,
        "search-kb": command_search_kb,
        "show-kb-hit": command_show_kb_hit,
        "inspect-kb-hit": command_inspect_kb_hit,
        "upload-file": command_upload_file,
        "import-url": command_import_url,
    }

    try:
        result = handlers[args.command](args, config)
        print_output(result, as_json=bool(getattr(args, "json", False)))
    except Exception as exc:
        if bool(getattr(args, "json", False)):
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
