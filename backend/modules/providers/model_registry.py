"""供应商模型清单的读写规则。

只描述「给定一份 ProviderConfig 应如何增删改排序模型」，不绑定配置存放在全局
还是用户私有空间。管理员全局配置与普通用户私有配置共用本模块，避免各自维护
一套判重、归一化与序列化口径。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, Tuple

from fastapi import HTTPException, status

from backend.modules.config.schema import ModelEntry, ProviderConfig
from backend.modules.native_caps.types import normalize_native_capabilities

MODEL_SOURCES = ("builtin", "manual", "fetched")
MAX_SHARED_ALIAS_LENGTH = 40
MAX_SHARED_NOTE_LENGTH = 120


class ModelPayloadLike(Protocol):
    id: str
    display_name: Optional[str]
    enabled: bool
    context_window: Optional[int]
    supports_image: Optional[bool]
    stream_enabled: Optional[bool]
    reasoning_levels: Optional[List[str]]
    reasoning_level: Optional[str]
    source: Optional[str]
    native_capabilities: Optional[Dict[str, Any]]
    shared: bool
    shared_alias: Optional[str]
    shared_note: Optional[str]
    user_daily_limit: Optional[int]


class AddModelsLike(Protocol):
    models: List[ModelPayloadLike]
    source: str


class UpdateModelLike(Protocol):
    display_name: Optional[str]
    enabled: Optional[bool]
    context_window: Optional[int]
    supports_image: Optional[bool]
    stream_enabled: Optional[bool]
    reasoning_levels: Optional[List[str]]
    reasoning_level: Optional[str]
    native_capabilities: Optional[Dict[str, Any]]
    shared: Optional[bool]
    shared_alias: Optional[str]
    shared_note: Optional[str]
    user_daily_limit: Optional[int]
    clear_display_name: bool
    clear_context_window: bool
    clear_supports_image: bool
    clear_stream_enabled: bool
    clear_reasoning_level: bool
    clear_shared_alias: bool
    clear_shared_note: bool
    clear_user_daily_limit: bool


def normalize_reasoning_levels(levels: Optional[List[str]]) -> List[str]:
    """档位列表归一化：小写去空白、去重、保序，非法值丢弃。"""
    normalized: List[str] = []
    for raw in levels or []:
        level = str(raw or "").strip().lower()
        if not level or level in normalized:
            continue
        normalized.append(level)
    return normalized


def normalize_single_level(level: Optional[str]) -> Optional[str]:
    normalized = str(level or "").strip().lower()
    return normalized or None


def normalize_alias(alias: Optional[str]) -> Optional[str]:
    """别名归一化：去空白、限长；空串视为未填。"""
    value = str(alias or "").strip()
    if not value:
        return None
    if len(value) > MAX_SHARED_ALIAS_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"共享别名最长 {MAX_SHARED_ALIAS_LENGTH} 个字符",
        )
    return value


def normalize_shared_note(note: Optional[str]) -> Optional[str]:
    value = str(note or "").strip()
    if not value:
        return None
    if len(value) > MAX_SHARED_NOTE_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"共享说明最长 {MAX_SHARED_NOTE_LENGTH} 个字符",
        )
    return value


def normalize_daily_limit(limit: Optional[int]) -> Optional[int]:
    """每日限额：None/<=0 视为不限。"""
    if limit is None:
        return None
    try:
        value = int(limit)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="每日限额必须是正整数",
        ) from None
    return value if value > 0 else None


def to_model_entry(
    payload: ModelPayloadLike,
    default_source: str,
    *,
    allow_shared: bool,
) -> ModelEntry:
    """条目自身显式给了来源就以它为准，否则跟随本次批量提交的来源。"""
    explicit_source = str(payload.source or "").strip().lower()
    source = explicit_source if explicit_source in MODEL_SOURCES else default_source
    if source not in MODEL_SOURCES:
        source = "manual"
    return ModelEntry(
        id=payload.id.strip(),
        display_name=(payload.display_name or "").strip() or None,
        enabled=bool(payload.enabled),
        context_window=payload.context_window if (payload.context_window or 0) > 0 else None,
        supports_image=payload.supports_image,
        stream_enabled=payload.stream_enabled,
        reasoning_levels=normalize_reasoning_levels(payload.reasoning_levels or []),
        reasoning_level=normalize_single_level(payload.reasoning_level),
        source=source,  # type: ignore[arg-type]
        native_capabilities=normalize_native_capabilities(payload.native_capabilities),
        shared=bool(payload.shared) if allow_shared else False,
        shared_alias=normalize_alias(payload.shared_alias) if allow_shared else None,
        shared_note=normalize_shared_note(payload.shared_note) if allow_shared else None,
        user_daily_limit=(
            normalize_daily_limit(payload.user_daily_limit) if allow_shared else None
        ),
    )


def ensure_alias_unique(
    providers: Dict[str, ProviderConfig],
    *,
    provider_id: str,
    model_id: str,
    alias: Optional[str],
    pending: Optional[List[Tuple[str, str, str]]] = None,
) -> None:
    """校验共享别名在共享集合内唯一，含本次未落库的 pending 条目。"""
    if not alias:
        return
    for other_provider_id, provider in providers.items():
        for entry in provider.models:
            if not entry.shared:
                continue
            if other_provider_id == provider_id and entry.id == model_id:
                continue
            if entry.resolved_alias() == alias:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"共享别名「{alias}」已被 {other_provider_id}/{entry.id} 占用",
                )
    for other_provider_id, other_model_id, other_alias in pending or []:
        if other_provider_id == provider_id and other_model_id == model_id:
            continue
        if other_alias == alias:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"共享别名「{alias}」在本批次中重复",
            )


def serialize_models(provider: ProviderConfig) -> List[Dict[str, Any]]:
    return [entry.model_dump() for entry in provider.models]


def add_models(
    provider: ProviderConfig,
    request: AddModelsLike,
    *,
    provider_id: str,
    providers: Dict[str, ProviderConfig],
    allow_shared: bool,
) -> Tuple[int, List[Dict[str, Any]]]:
    """批量添加；已存在的 ID 只补空字段，不覆盖用户改过的展示名与开关。"""
    pending_aliases: List[Tuple[str, str, str]] = []
    if allow_shared:
        for payload in request.models:
            model_id = (payload.id or "").strip()
            if not model_id or not payload.shared:
                continue
            effective = normalize_alias(payload.shared_alias) or (
                (payload.display_name or "").strip() or model_id
            )
            pending_aliases.append((provider_id, model_id, effective))
        for other_provider_id, other_model_id, other_alias in pending_aliases:
            ensure_alias_unique(
                providers,
                provider_id=other_provider_id,
                model_id=other_model_id,
                alias=other_alias,
                pending=pending_aliases,
            )

    added = 0
    for payload in request.models:
        model_id = (payload.id or "").strip()
        if not model_id:
            continue

        existing = provider.find_model(model_id)
        if existing is None:
            provider.models.append(to_model_entry(payload, request.source, allow_shared=allow_shared))
            added += 1
            continue

        if payload.display_name and not existing.display_name:
            existing.display_name = payload.display_name.strip()
        if payload.context_window and not existing.context_window:
            existing.context_window = payload.context_window
        if payload.supports_image is not None and existing.supports_image is None:
            existing.supports_image = payload.supports_image
        if payload.stream_enabled is not None and existing.stream_enabled is None:
            existing.stream_enabled = payload.stream_enabled
        if payload.reasoning_levels and not existing.reasoning_levels:
            existing.reasoning_levels = normalize_reasoning_levels(payload.reasoning_levels)
        if payload.reasoning_level and not existing.reasoning_level:
            existing.reasoning_level = normalize_single_level(payload.reasoning_level)
        if (
            payload.native_capabilities is not None
            and not existing.native_capabilities.any_enabled()
        ):
            existing.native_capabilities = normalize_native_capabilities(
                payload.native_capabilities
            )

    return added, serialize_models(provider)


def reorder_models(
    provider: ProviderConfig,
    model_ids: List[str],
) -> List[Dict[str, Any]]:
    """按传入顺序重排；未出现在列表里的模型保持相对顺序附在末尾。"""
    order = [model_id for model_id in model_ids if model_id]
    by_id = {entry.id: entry for entry in provider.models}

    reordered: List[ModelEntry] = []
    used: set[str] = set()
    for model_id in order:
        entry = by_id.get(model_id)
        if entry is not None and model_id not in used:
            reordered.append(entry)
            used.add(model_id)
    for entry in provider.models:
        if entry.id not in used:
            reordered.append(entry)

    provider.models = reordered
    return serialize_models(provider)


def update_model(
    provider: ProviderConfig,
    model_id: str,
    request: UpdateModelLike,
    *,
    provider_id: str,
    providers: Dict[str, ProviderConfig],
    allow_shared: bool,
) -> List[Dict[str, Any]]:
    """更新单个模型（部分更新）；共享字段先算成目标状态再校验，校验不过整体放弃。"""
    entry = provider.find_model(model_id)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"供应商 {provider_id} 下没有模型 {model_id}",
        )

    if allow_shared:
        next_shared = entry.shared if request.shared is None else bool(request.shared)
        if request.clear_shared_alias:
            next_alias = None
        elif request.shared_alias is not None:
            next_alias = normalize_alias(request.shared_alias)
        else:
            next_alias = entry.shared_alias
        if request.clear_shared_note:
            next_note = None
        elif request.shared_note is not None:
            next_note = normalize_shared_note(request.shared_note)
        else:
            next_note = entry.shared_note
        if request.clear_user_daily_limit:
            next_limit = None
        elif request.user_daily_limit is not None:
            next_limit = normalize_daily_limit(request.user_daily_limit)
        else:
            next_limit = entry.user_daily_limit

        if next_shared:
            effective_alias = next_alias or request.display_name or entry.display_name or entry.id
            ensure_alias_unique(
                providers,
                provider_id=provider_id,
                model_id=model_id,
                alias=str(effective_alias).strip() or None,
            )

    if request.clear_display_name:
        entry.display_name = None
    elif request.display_name is not None:
        entry.display_name = request.display_name.strip() or None

    if request.enabled is not None:
        entry.enabled = bool(request.enabled)

    if request.clear_context_window:
        entry.context_window = None
    elif request.context_window is not None:
        entry.context_window = request.context_window if request.context_window > 0 else None

    if request.clear_supports_image:
        entry.supports_image = None
    elif request.supports_image is not None:
        entry.supports_image = request.supports_image

    if request.clear_stream_enabled:
        entry.stream_enabled = None
    elif request.stream_enabled is not None:
        entry.stream_enabled = request.stream_enabled

    if request.reasoning_levels is not None:
        entry.reasoning_levels = normalize_reasoning_levels(request.reasoning_levels)

    if request.clear_reasoning_level:
        entry.reasoning_level = None
    elif request.reasoning_level is not None:
        entry.reasoning_level = normalize_single_level(request.reasoning_level)

    if request.native_capabilities is not None:
        entry.native_capabilities = normalize_native_capabilities(
            request.native_capabilities
        )

    if allow_shared:
        entry.shared = next_shared
        entry.shared_alias = next_alias
        entry.shared_note = next_note
        entry.user_daily_limit = next_limit

    return serialize_models(provider)


def delete_model(
    provider: ProviderConfig,
    model_id: str,
    *,
    provider_id: str,
) -> List[Dict[str, Any]]:
    before = len(provider.models)
    provider.models = [entry for entry in provider.models if entry.id != model_id]
    if len(provider.models) == before:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"供应商 {provider_id} 下没有模型 {model_id}",
        )
    return serialize_models(provider)
