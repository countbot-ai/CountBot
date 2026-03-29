#!/usr/bin/env python
"""Shared helpers for IMA skill configuration and API calls."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional


DEFAULT_BASE_URL = "https://ima.qq.com"


def get_default_config_path() -> Path:
    return Path(__file__).resolve().parent / "config.json"


def parse_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def load_skill_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    path = Path(config_path).expanduser().resolve() if config_path else get_default_config_path()
    data: Dict[str, Any] = {}

    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))

    default_knowledge_base = data.get("default_knowledge_base", {}) or {}
    if not isinstance(default_knowledge_base, dict):
        default_knowledge_base = {}

    client_id = os.environ.get("IMA_OPENAPI_CLIENTID", "").strip() or data.get("client_id") or data.get("id") or ""
    api_key = os.environ.get("IMA_OPENAPI_APIKEY", "").strip() or data.get("api_key") or data.get("key") or ""
    base_url = os.environ.get("IMA_OPENAPI_BASE_URL", "").strip() or data.get("base_url") or DEFAULT_BASE_URL
    timeout = data.get("request_timeout_seconds", 30)
    default_knowledge_base_id = (
        os.environ.get("IMA_OPENAPI_DEFAULT_KB_ID", "").strip()
        or default_knowledge_base.get("id")
        or data.get("default_knowledge_base_id")
        or ""
    )
    default_knowledge_base_name = (
        os.environ.get("IMA_OPENAPI_DEFAULT_KB_NAME", "").strip()
        or default_knowledge_base.get("name")
        or data.get("default_knowledge_base_name")
        or ""
    )
    default_knowledge_folder_id = (
        os.environ.get("IMA_OPENAPI_DEFAULT_KB_FOLDER_ID", "").strip()
        or default_knowledge_base.get("folder_id")
        or data.get("default_knowledge_folder_id")
        or ""
    )
    restrict_search = os.environ.get("IMA_OPENAPI_SCOPE_DEFAULT_KB")
    if restrict_search is None:
        restrict_search_to_default_knowledge_base = parse_bool(data.get("restrict_search_to_default_knowledge_base"), False)
    else:
        restrict_search_to_default_knowledge_base = parse_bool(restrict_search, False)

    return {
        "client_id": str(client_id).strip(),
        "api_key": str(api_key).strip(),
        "base_url": str(base_url).rstrip("/"),
        "request_timeout_seconds": int(timeout),
        "default_knowledge_base_id": str(default_knowledge_base_id).strip(),
        "default_knowledge_base_name": str(default_knowledge_base_name).strip(),
        "default_knowledge_folder_id": str(default_knowledge_folder_id).strip(),
        "default_knowledge_base": {
            "id": str(default_knowledge_base_id).strip(),
            "name": str(default_knowledge_base_name).strip(),
            "folder_id": str(default_knowledge_folder_id).strip(),
        },
        "restrict_search_to_default_knowledge_base": restrict_search_to_default_knowledge_base,
        "config_path": str(path),
    }


def require_credentials(config: Dict[str, Any]) -> tuple[str, str]:
    client_id = config.get("client_id", "").strip()
    api_key = config.get("api_key", "").strip()
    missing = []
    if not client_id:
        missing.append("IMA_OPENAPI_CLIENTID/client_id")
    if not api_key:
        missing.append("IMA_OPENAPI_APIKEY/api_key")
    if missing:
        raise ValueError("Missing credential(s): " + ", ".join(missing))
    return client_id, api_key


def post_json(
    endpoint_path: str,
    payload: Dict[str, Any],
    *,
    config: Optional[Dict[str, Any]] = None,
    config_path: Optional[str] = None,
) -> Dict[str, Any]:
    cfg = config or load_skill_config(config_path)
    client_id, api_key = require_credentials(cfg)
    base_url = cfg.get("base_url", DEFAULT_BASE_URL).rstrip("/")
    timeout = int(cfg.get("request_timeout_seconds", 30))
    url = f"{base_url}/{endpoint_path.lstrip('/')}"

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url=url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "ima-openapi-clientid": client_id,
            "ima-openapi-apikey": api_key,
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"IMA HTTP error {exc.code}: {response_body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"IMA request failed: {exc.reason}") from exc
