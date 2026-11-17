"""管理员共享模型视图：普通用户能看到什么共享模型，由管理员在「设置 → 模型」里逐条勾选决定。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import case, func, select

from backend.api.admin._router import router
from backend.database import AsyncSessionLocal
from backend.models.model_usage import ModelUsage
from backend.modules.multiuser.effective import list_shared_models
from backend.modules.multiuser.identity import AuthUser
from backend.modules.multiuser.permissions import require_admin
from backend.modules.multiuser.settings import load_settings


class SharedModelItem(BaseModel):
    """单个共享模型（不含任何密钥）。"""

    ref: str
    provider: str
    model: str
    alias: str
    note: str = ""
    daily_limit: Optional[int] = None
    context_window: Optional[int] = None
    supports_image: Optional[bool] = None
    provider_name: str


class SharedModelUsageItem(BaseModel):
    """某用户对某个共享模型的用量。"""

    owner_id: str
    username: str
    provider: str
    model: str
    today_calls: int
    total_calls: int
    today_tokens: int


class SharedModelsResponse(BaseModel):
    """共享模型总览。"""

    enabled: bool = Field(..., description="共享模式且已开启共享供应商")
    mode: str
    shared_providers: bool
    items: List[SharedModelItem] = Field(default_factory=list)
    usage: List[SharedModelUsageItem] = Field(default_factory=list)


def _start_of_today() -> datetime:
    return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


async def _collect_usage(model_ids: List[str]) -> List[SharedModelUsageItem]:
    """按 owner、供应商、模型聚合 shared 用量，避免同名模型跨供应商混算。"""
    if not model_ids:
        return []

    from backend.models.user import User

    start_of_day = _start_of_today()
    is_today = ModelUsage.created_at >= start_of_day
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(
                    ModelUsage.owner_id,
                    ModelUsage.provider,
                    ModelUsage.model,
                    func.count().label("total_calls"),
                    func.sum(case((is_today, 1), else_=0)).label("today_calls"),
                    func.sum(
                        case((is_today, ModelUsage.total_tokens), else_=0)
                    ).label("today_tokens"),
                )
                .where(
                    ModelUsage.model_ref_source == "shared",
                    ModelUsage.owner_id.is_not(None),
                    ModelUsage.model.in_(model_ids),
                )
                .group_by(ModelUsage.owner_id, ModelUsage.provider, ModelUsage.model)
            )
        ).all()

        owner_ids = {row.owner_id for row in rows if row.owner_id}
        names: Dict[str, str] = {}
        if owner_ids:
            users = (
                await session.execute(
                    select(User.id, User.username).where(User.id.in_(owner_ids))
                )
            ).all()
            names = {user_id: username for user_id, username in users}

    return [
        SharedModelUsageItem(
            owner_id=row.owner_id or "",
            username=names.get(row.owner_id or "", row.owner_id or ""),
            provider=row.provider or "",
            model=row.model or "",
            today_calls=int(row.today_calls or 0),
            total_calls=int(row.total_calls or 0),
            today_tokens=int(row.today_tokens or 0),
        )
        for row in rows
    ]


@router.get("/shared-models", response_model=SharedModelsResponse)
async def get_shared_models(
    include_usage: bool = Query(True, description="是否附带各用户用量"),
    _admin: AuthUser = Depends(require_admin),
) -> SharedModelsResponse:
    """共享模型清单与用量总览。"""
    settings = await load_settings(use_cache=False)
    items = list_shared_models()

    usage: List[SharedModelUsageItem] = []
    if include_usage and items:
        usage = await _collect_usage([item["model"] for item in items])
        usage.sort(key=lambda row: (row.provider, row.model, -row.today_calls))

    return SharedModelsResponse(
        enabled=settings.mode == "shared" and settings.shared_providers,
        mode=settings.mode,
        shared_providers=settings.shared_providers,
        items=[
            SharedModelItem(
                ref=item["ref"],
                provider=item["provider"],
                model=item["model"],
                alias=item["alias"],
                note=item["note"],
                daily_limit=item["daily_limit"],
                context_window=item.get("context_window"),
                supports_image=item.get("supports_image"),
                provider_name=item["provider_name"],
            )
            for item in items
        ],
        usage=usage,
    )
