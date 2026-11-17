"""用户级配置存储：仅保存用户可自主决定的配置子集，写入前统一校验。"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from loguru import logger


async def load_user_config(user_id: str) -> Dict[str, Any]:
    """读取用户配置；不存在或损坏时返回空结构。"""
    if not user_id:
        return {}
    from backend.database import AsyncSessionLocal
    from backend.models.user import UserConfig

    try:
        async with AsyncSessionLocal() as session:
            row = await session.get(UserConfig, user_id)
            if row is None or not row.config_json:
                return {}
            data = json.loads(row.config_json)
            return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning(f"Failed to load user config for {user_id}: {exc}")
        return {}


async def save_user_config(user_id: str, config: Dict[str, Any]) -> None:
    """整体覆盖写入用户配置（调用方必须已完成校验）。"""
    if not user_id:
        return
    from backend.database import AsyncSessionLocal
    from backend.models.user import UserConfig

    payload = json.dumps(config or {}, ensure_ascii=False)
    async with AsyncSessionLocal() as session:
        await session.merge(UserConfig(user_id=user_id, config_json=payload))
        await session.commit()


async def patch_user_config(user_id: str, **changes: Any) -> Dict[str, Any]:
    """局部更新用户配置并返回最新值。"""
    config = await load_user_config(user_id)
    config.update(changes)
    await save_user_config(user_id, config)
    return config


async def delete_user_config(user_id: str) -> None:
    if not user_id:
        return
    from backend.database import AsyncSessionLocal
    from backend.models.user import UserConfig

    async with AsyncSessionLocal() as session:
        row = await session.get(UserConfig, user_id)
        if row is not None:
            await session.delete(row)
            await session.commit()


def normalize_model_ref(raw: Optional[Dict[str, Any]]) -> Optional[Dict[str, str]]:
    """把模型引用收敛为固定字段，拒绝缺字段的结构。"""
    if not isinstance(raw, dict):
        return None
    source = str(raw.get("source") or "").strip().lower()
    provider = str(raw.get("provider") or "").strip()
    model = str(raw.get("model") or "").strip()
    if source not in ("shared", "own") or not provider or not model:
        return None
    alias = str(raw.get("alias") or "").strip()
    return {
        "source": source,
        "provider": provider,
        "model": model,
        "alias": alias,
    }
