"""Settings 的输入归一化与校验：布尔拒绝模糊值，正则/cron 保存前报错，心跳参数规整到合法范围。"""

import re
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from loguru import logger

from backend.modules.config.schema import AppConfig, ModelEntry


def _normalize_api_mode_value(value: Any) -> str:
    return "chat_completions"


def _normalize_api_type_value(value: Any) -> str:
    """校验供应商协议白名单，拒绝未知值而不是静默改名。"""
    from backend.modules.providers.factory import API_TYPES, API_TYPE_OPENAI_CHAT

    normalized = str(value or "").strip().lower()
    if not normalized:
        return API_TYPE_OPENAI_CHAT
    if normalized not in API_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"api_type '{value}' 无效，可用值: {', '.join(API_TYPES)}"
            ),
        )
    return normalized


def _parse_model_entry(raw: Any) -> Optional[ModelEntry]:
    """把请求里的模型条目解析成 ModelEntry，非法条目返回 None。"""
    if isinstance(raw, ModelEntry):
        return raw
    if isinstance(raw, str):
        trimmed = raw.strip()
        return ModelEntry(id=trimmed) if trimmed else None
    if not isinstance(raw, dict):
        return None

    model_id = str(raw.get("id") or raw.get("model") or "").strip()
    if not model_id:
        return None

    source = str(raw.get("source") or "manual").strip().lower()
    if source not in ("builtin", "manual", "fetched"):
        source = "manual"

    context_window = raw.get("context_window")
    if context_window is not None:
        try:
            context_window = int(context_window)
        except (TypeError, ValueError):
            context_window = None
        if context_window is not None and context_window <= 0:
            context_window = None

    supports_image = raw.get("supports_image")
    if not isinstance(supports_image, bool):
        supports_image = None

    display_name = str(raw.get("display_name") or "").strip() or None

    return ModelEntry(
        id=model_id,
        display_name=display_name,
        enabled=bool(raw.get("enabled", True)),
        context_window=context_window,
        supports_image=supports_image,
        source=source,  # type: ignore[arg-type]
    )


def _coerce_boolean_value(value: Any, *, field_name: str) -> bool:
    """将用户输入安全转换为布尔值，拒绝模糊字符串。"""
    if isinstance(value, bool):
        return value

    if isinstance(value, int) and value in {0, 1}:
        return bool(value)

    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"{field_name} must be a boolean",
    )


def _list_enabled_channel_account_ids(config: AppConfig, channel_name: str) -> List[str]:
    """列出指定渠道当前已启用的账号 ID。"""
    channel_cfg = getattr(config.channels, channel_name, None)
    if channel_cfg is None:
        return []

    ordered_account_ids: List[str] = []

    if bool(getattr(channel_cfg, "enabled", False)):
        top_level_account_id = str(getattr(channel_cfg, "account_id", "default") or "default")
        ordered_account_ids.append(top_level_account_id)

    accounts = getattr(channel_cfg, "accounts", {}) or {}
    for raw_account_id, account_cfg in accounts.items():
        if isinstance(account_cfg, dict):
            enabled = bool(account_cfg.get("enabled", False))
            account_id = str(raw_account_id or account_cfg.get("account_id") or "default")
        else:
            enabled = bool(getattr(account_cfg, "enabled", False))
            account_id = str(raw_account_id or getattr(account_cfg, "account_id", "default") or "default")
        if enabled:
            ordered_account_ids.append(account_id)

    deduped: List[str] = []
    for account_id in ordered_account_ids:
        if account_id not in deduped:
            deduped.append(account_id)
    return deduped


def _normalize_pattern_list(value: Any) -> List[str]:
    """清理正则模式列表，去掉空白项并去重，保留原顺序。"""
    if not isinstance(value, list):
        return []

    normalized: List[str] = []
    for item in value:
        text = str(item or "").strip()
        if not text or text in normalized:
            continue
        normalized.append(text)
    return normalized


def _validate_regex_patterns_or_raise(patterns: List[str], *, field_name: str) -> None:
    """保存配置前校验正则表达式，尽早返回明确错误。"""
    for index, pattern in enumerate(patterns):
        try:
            re.compile(pattern)
        except re.error as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{field_name}[{index}] 无效: {exc}",
            ) from exc


def _validate_cron_schedule_or_raise(schedule: Any, *, field_name: str) -> str:
    """校验 cron 表达式。"""
    from croniter import croniter

    normalized = str(schedule or "").strip()
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} 不能为空",
        )

    try:
        croniter(normalized)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} 无效: {e}",
        ) from e

    return normalized


def _validate_and_normalize_heartbeat_settings(config: AppConfig) -> None:
    """校验问候助手配置，并在单机器人场景下自动补全真实账号 ID。"""
    heartbeat = config.persona.heartbeat
    heartbeat.account_id = str(getattr(heartbeat, "account_id", "default") or "default").strip() or "default"
    heartbeat.schedule = _validate_cron_schedule_or_raise(
        heartbeat.schedule,
        field_name="persona.heartbeat.schedule",
    )

    if not heartbeat.enabled:
        return

    heartbeat.channel = str(heartbeat.channel or "").strip()
    heartbeat.chat_id = str(heartbeat.chat_id or "").strip()
    if not heartbeat.channel:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="启用问候助手前必须先选择推送渠道",
        )
    if not heartbeat.chat_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="启用问候助手前必须填写推送目标 ID",
        )

    enabled_account_ids = _list_enabled_channel_account_ids(config, heartbeat.channel)
    if not enabled_account_ids:
        available_channels = ", ".join(config.channels.model_dump().keys())
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"问候助手渠道 '{heartbeat.channel}' 当前没有可用机器人实例。"
                f"可用渠道: {available_channels}"
            ),
        )

    if heartbeat.account_id in enabled_account_ids:
        return

    if heartbeat.account_id == "default" and len(enabled_account_ids) == 1:
        heartbeat.account_id = enabled_account_ids[0]
        return

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            f"问候助手账号 ID '{heartbeat.account_id}' 无效，"
            f"当前渠道可用账号: {', '.join(enabled_account_ids)}"
        ),
    )


def _heartbeat_plan_settings_changed(before: Optional[Dict[str, Any]], after: Optional[Dict[str, Any]]) -> bool:
    """判断是否需要刷新当天随机问候计划。"""
    if not before or not after:
        return False

    watched_keys = ("quiet_start", "quiet_end", "max_greets_per_day")
    return any(before.get(key) != after.get(key) for key in watched_keys)
