"""用户级共享模型可见范围：范围存储、引用解析与 fail-closed 判定。"""

from __future__ import annotations

import json
from typing import Any, Optional, Sequence, Tuple

SHARED_MODEL_SCOPE_ALL = "all"
SHARED_MODEL_SCOPE_SELECTED = "selected"
SHARED_MODEL_SCOPES = frozenset({SHARED_MODEL_SCOPE_ALL, SHARED_MODEL_SCOPE_SELECTED})
SHARED_MODEL_REF_PREFIX = "shared:"
MAX_SHARED_MODEL_REFS = 200


def shared_model_ref(provider_id: str, model_id: str) -> str:
    """稳定的共享模型引用，避免依赖展示别名。"""
    return f"{SHARED_MODEL_REF_PREFIX}{provider_id}:{model_id}"


def normalize_shared_model_scope(value: Any) -> str:
    """未知值按 all 处理，保持旧用户全量可见。"""
    text = str(value or "").strip().lower()
    return text if text in SHARED_MODEL_SCOPES else SHARED_MODEL_SCOPE_ALL


def normalize_shared_model_refs(value: Any) -> Tuple[str, ...]:
    """把数据库 JSON、请求列表或单个字符串收敛为去重引用元组。"""
    payload = value
    if isinstance(payload, str):
        try:
            payload = json.loads(payload) if payload.strip() else []
        except (TypeError, ValueError):
            payload = []
    if isinstance(payload, dict) or not isinstance(payload, (list, tuple, set)):
        return ()

    refs: list[str] = []
    for item in payload:
        if not isinstance(item, str):
            continue
        ref = item.strip()
        if not ref.startswith(SHARED_MODEL_REF_PREFIX):
            continue
        if ref not in refs:
            refs.append(ref)
        if len(refs) >= MAX_SHARED_MODEL_REFS:
            break
    return tuple(refs)


def serialize_shared_model_refs(value: Any) -> str:
    """以 JSON 文本落库，兼容 SQLite 旧表迁移。"""
    return json.dumps(list(normalize_shared_model_refs(value)), ensure_ascii=False)


def allowed_shared_model_refs(user: Any) -> Optional[frozenset[str]]:
    """返回用户的共享模型白名单；None 表示不限制（管理员或 all）。"""
    if user is None or getattr(user, "is_admin", False):
        return None
    if normalize_shared_model_scope(getattr(user, "shared_model_scope", None)) != SHARED_MODEL_SCOPE_SELECTED:
        return None
    return frozenset(normalize_shared_model_refs(getattr(user, "shared_model_refs", ())))


def is_shared_model_allowed(user: Any, provider_id: str, model_id: str) -> bool:
    """共享模型是否对当前用户可见/可用；未知范围按 all。"""
    allowed = allowed_shared_model_refs(user)
    if allowed is None:
        return True
    return shared_model_ref(provider_id, model_id) in allowed


def filter_shared_models_for_user(items: Sequence[dict], user: Any) -> list[dict]:
    """按用户白名单过滤共享模型目录。"""
    allowed = allowed_shared_model_refs(user)
    if allowed is None:
        return list(items)
    return [item for item in items if item.get("ref") in allowed]
