"""归一化各供应商返回的用量字段后落库；记录失败只告警，不影响主流程。"""

from typing import Any, Dict, Optional

from loguru import logger

from backend.models.model_usage import (
    USAGE_KIND_CHAT,
    USAGE_KIND_COMPACTION,
    USAGE_KIND_OTHER,
    USAGE_KIND_SUBAGENT,
    USAGE_KIND_SUMMARY,
    ModelUsage,
)

__all__ = [
    "USAGE_KIND_CHAT",
    "USAGE_KIND_SUMMARY",
    "USAGE_KIND_COMPACTION",
    "USAGE_KIND_SUBAGENT",
    "USAGE_KIND_OTHER",
    "normalize_usage",
    "has_usage",
    "record_usage",
    "summarize_usage",
]

# 各供应商字段别名，统一归一化到同一语义
_PROMPT_KEYS = ("prompt_tokens", "input_tokens", "promptTokens", "inputTokens")
_COMPLETION_KEYS = ("completion_tokens", "output_tokens", "completionTokens", "outputTokens")
_TOTAL_KEYS = ("total_tokens", "totalTokens")
_CACHE_READ_KEYS = (
    "cache_read_input_tokens",
    "cacheReadInputTokens",
    "cache_read_tokens",
    "prompt_cache_hit_tokens",
    "cached_tokens",
)
_CACHE_WRITE_KEYS = (
    "cache_creation_input_tokens",
    "cacheWriteInputTokens",
    "cache_write_tokens",
    "prompt_cache_miss_tokens",
)
_REASONING_KEYS = ("reasoning_tokens", "reasoningTokens", "completion_tokens_details")


# OpenAI 系把缓存/推理 token 放在这些 *_details 子对象里（如 prompt_tokens_details.cached_tokens）。
_DETAIL_CONTAINER_KEYS = (
    "prompt_tokens_details",
    "completion_tokens_details",
    "promptTokensDetails",
    "completionTokensDetails",
)


def _first_int(raw: Dict[str, Any], keys: tuple) -> int:
    """按别名顺序取第一个可转换为整数的值。

    顶层未命中时再下钻 *_details 容器，否则 OpenAI 系原生上报的缓存命中会被算成 0。
    """
    for key in keys:
        if key in raw:
            value = raw[key]
            if isinstance(value, dict):
                # 该 key 本身即明细容器（如 completion_tokens_details 作别名）
                value = value.get(key) or value.get("reasoning_tokens", 0)
            try:
                return int(value or 0)
            except (TypeError, ValueError):
                pass

    for container_key in _DETAIL_CONTAINER_KEYS:
        container = raw.get(container_key)
        if not isinstance(container, dict):
            continue
        for key in keys:
            if key in container:
                try:
                    return int(container[key] or 0)
                except (TypeError, ValueError):
                    continue
    return 0


def normalize_usage(raw: Optional[Dict[str, Any]]) -> Dict[str, int]:
    """把供应商的原始用量字典归一化为统一字段。

    Args:
        raw: 供应商返回的 usage 字典，可能为 None 或字段缺失

    Returns:
        含 prompt/completion/total/cache_read/cache_write/reasoning 六个整数字段
    """
    result = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "reasoning_tokens": 0,
    }
    if not isinstance(raw, dict) or not raw:
        return result

    result["prompt_tokens"] = _first_int(raw, _PROMPT_KEYS)
    result["completion_tokens"] = _first_int(raw, _COMPLETION_KEYS)
    result["cache_read_tokens"] = _first_int(raw, _CACHE_READ_KEYS)
    result["cache_write_tokens"] = _first_int(raw, _CACHE_WRITE_KEYS)
    result["reasoning_tokens"] = _first_int(raw, _REASONING_KEYS)

    total = _first_int(raw, _TOTAL_KEYS)
    if total <= 0:
        total = result["prompt_tokens"] + result["completion_tokens"]
    result["total_tokens"] = total
    return result


def has_usage(normalized: Dict[str, int]) -> bool:
    """归一化结果里是否有实际数值（全 0 视为供应商未上报）。"""
    return any(value > 0 for value in normalized.values())


async def record_usage(
    *,
    session_id: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    kind: str = USAGE_KIND_CHAT,
    turn_index: Optional[int] = None,
    raw_usage: Optional[Dict[str, Any]] = None,
) -> Optional[ModelUsage]:
    """记录一次模型请求的用量。

    Args:
        session_id: 关联会话
        provider: 供应商标识
        model: 模型名
        kind: 用途分类（对话/摘要/压缩/子代理）
        turn_index: 本轮对话内的第几次模型调用
        raw_usage: 供应商原始 usage 字典

    Returns:
        写入的记录；未上报用量或写入失败时返回 None
    """
    normalized = normalize_usage(raw_usage)
    if not has_usage(normalized):
        return None

    try:
        from backend.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            record = ModelUsage(
                session_id=session_id,
                provider=provider,
                model=model,
                kind=kind or USAGE_KIND_OTHER,
                turn_index=turn_index,
                **normalized,
            )
            db.add(record)
            await db.commit()
            await db.refresh(record)
            return record
    except Exception as exc:
        logger.warning(f"Failed to record model usage: {exc}")
        return None


async def summarize_usage(
    *,
    session_id: Optional[str] = None,
    days: int = 7,
) -> Dict[str, Any]:
    """汇总用量：总量、按用途拆分、按模型拆分。

    Args:
        session_id: 只统计指定会话；为 None 时统计全库
        days: 统计最近多少天

    Returns:
        汇总字典，可直接返回给前端
    """
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import func, select

    from backend.database import AsyncSessionLocal

    since = datetime.now(timezone.utc) - timedelta(days=max(1, days))

    try:
        async with AsyncSessionLocal() as db:
            base = select(
                func.count(ModelUsage.id),
                func.coalesce(func.sum(ModelUsage.prompt_tokens), 0),
                func.coalesce(func.sum(ModelUsage.completion_tokens), 0),
                func.coalesce(func.sum(ModelUsage.total_tokens), 0),
                func.coalesce(func.sum(ModelUsage.cache_read_tokens), 0),
                func.coalesce(func.sum(ModelUsage.cache_write_tokens), 0),
            ).where(ModelUsage.created_at >= since)
            if session_id:
                base = base.where(ModelUsage.session_id == session_id)
            row = (await db.execute(base)).one()

            total_requests = int(row[0] or 0)
            prompt_tokens = int(row[1] or 0)
            completion_tokens = int(row[2] or 0)
            total_tokens = int(row[3] or 0)
            cache_read = int(row[4] or 0)
            cache_write = int(row[5] or 0)

            kind_stmt = select(
                ModelUsage.kind,
                func.count(ModelUsage.id),
                func.coalesce(func.sum(ModelUsage.total_tokens), 0),
            ).where(ModelUsage.created_at >= since)
            if session_id:
                kind_stmt = kind_stmt.where(ModelUsage.session_id == session_id)
            kind_rows = (await db.execute(kind_stmt.group_by(ModelUsage.kind))).all()

            model_stmt = select(
                ModelUsage.provider,
                ModelUsage.model,
                func.count(ModelUsage.id),
                func.coalesce(func.sum(ModelUsage.total_tokens), 0),
            ).where(ModelUsage.created_at >= since)
            if session_id:
                model_stmt = model_stmt.where(ModelUsage.session_id == session_id)
            model_rows = (
                await db.execute(
                    model_stmt.group_by(ModelUsage.provider, ModelUsage.model)
                )
            ).all()

            # 缓存命中率：复用 token 占全部输入的比例
            hit_rate = round(cache_read / prompt_tokens, 4) if prompt_tokens else 0.0

            return {
                "window_days": days,
                "session_id": session_id,
                "total_requests": total_requests,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "cache_read_tokens": cache_read,
                "cache_write_tokens": cache_write,
                "cache_hit_rate": hit_rate,
                "by_kind": [
                    {"kind": kind, "requests": int(count or 0), "tokens": int(tokens or 0)}
                    for kind, count, tokens in kind_rows
                ],
                "by_model": [
                    {
                        "provider": provider,
                        "model": model,
                        "requests": int(count or 0),
                        "tokens": int(tokens or 0),
                    }
                    for provider, model, count, tokens in model_rows
                ],
            }
    except Exception as exc:
        logger.warning(f"Failed to summarize usage: {exc}")
        return {
            "window_days": days,
            "session_id": session_id,
            "total_requests": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "cache_hit_rate": 0.0,
            "by_kind": [],
            "by_model": [],
            "error": str(exc),
        }
