"""性格管理 API"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.personality import Personality
from backend.modules.multiuser.identity import AuthUser
from backend.modules.multiuser.permissions import owner_scope, require_active_user



def _visible_filter(user: AuthUser):
    """可见范围：内置 + 自己的自定义；管理员看内置与管理员的。"""
    scope = owner_scope(user)
    if scope:
        return or_(Personality.is_builtin == True, Personality.owner_id == scope)  # noqa: E712
    return Personality.owner_id.is_(None)


def _load_editable(db, personality_id: str, user: AuthUser):
    """加载可编辑的性格：普通用户只能改自己的，管理员可改内置与管理员条目。"""
    query = select(Personality).where(Personality.id == personality_id)
    scope = owner_scope(user)
    if scope:
        query = query.where(Personality.owner_id == scope)
    else:
        query = query.where(Personality.owner_id.is_(None))
    return query


router = APIRouter(
    prefix="/api/personalities",
    tags=["personalities"],
    dependencies=[Depends(require_active_user)],
)


class PersonalityCreate(BaseModel):
    """创建性格请求"""
    id: str = Field(..., min_length=1, max_length=50, pattern="^[a-z0-9_-]+$")
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1)
    traits: List[str] = Field(..., min_items=1)
    speaking_style: str = Field(..., min_length=1)
    icon: str = Field(default="Smile", max_length=50)

    # 克隆人格的扩展字段；普通语气预设不传即可
    mental_models: Optional[List[Dict[str, Any]]] = None
    heuristics: Optional[List[Dict[str, Any]]] = None
    expression_dna: Optional[Dict[str, Any]] = None
    values: Optional[List[str]] = None
    anti_patterns: Optional[List[str]] = None
    tensions: Optional[List[str]] = None
    honesty_boundaries: Optional[List[str]] = None
    memory_anchors: Optional[List[Dict[str, Any]]] = None
    response_profile: Optional[Dict[str, Any]] = None
    source_type: Optional[str] = Field(None, description="personal / public / self")
    source_stats: Optional[Dict[str, Any]] = None
    research_dimensions: Optional[List[Dict[str, Any]]] = None
    memory_doc: Optional[str] = None
    persona_doc: Optional[str] = None
    combined_doc: Optional[str] = None


class PersonalityUpdate(BaseModel):
    """更新性格请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, min_length=1)
    traits: Optional[List[str]] = Field(None, min_items=1)
    speaking_style: Optional[str] = Field(None, min_length=1)
    icon: Optional[str] = Field(None, max_length=50)
    is_active: Optional[bool] = None
    mental_models: Optional[List[Dict[str, Any]]] = None
    heuristics: Optional[List[Dict[str, Any]]] = None
    expression_dna: Optional[Dict[str, Any]] = None
    values: Optional[List[str]] = None
    anti_patterns: Optional[List[str]] = None
    tensions: Optional[List[str]] = None
    honesty_boundaries: Optional[List[str]] = None
    memory_anchors: Optional[List[Dict[str, Any]]] = None
    response_profile: Optional[Dict[str, Any]] = None
    source_type: Optional[str] = None
    source_stats: Optional[Dict[str, Any]] = None
    research_dimensions: Optional[List[Dict[str, Any]]] = None
    memory_doc: Optional[str] = None
    persona_doc: Optional[str] = None
    combined_doc: Optional[str] = None


# 克隆人格的可写字段；创建与更新共用同一张映射表，避免两处漏字段
_CLONE_FIELDS = (
    "mental_models",
    "heuristics",
    "expression_dna",
    "values",
    "anti_patterns",
    "tensions",
    "honesty_boundaries",
    "memory_anchors",
    "research_dimensions",
    "response_profile",
    "source_type",
    "source_stats",
    "memory_doc",
    "persona_doc",
    "combined_doc",
)


def _apply_clone_fields(personality: Personality, data: Any) -> None:
    """把请求里显式提供的扩展字段写入模型；未提供则保持原值。"""
    for field in _CLONE_FIELDS:
        value = getattr(data, field, None)
        if value is not None:
            setattr(personality, field, value)


@router.get("")
async def list_personalities(
    active_only: bool = False,
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(require_active_user),
):
    """获取所有性格列表（内置 + 自己的）"""
    query = select(Personality).where(_visible_filter(user))
    if active_only:
        query = query.where(Personality.is_active == True)  # noqa: E712
    
    query = query.order_by(Personality.is_builtin.desc(), Personality.created_at)
    
    result = await db.execute(query)
    personalities = result.scalars().all()
    
    return {
        "personalities": [p.to_dict() for p in personalities],
        "total": len(personalities)
    }


@router.get("/{personality_id}")
async def get_personality(
    personality_id: str,
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(require_active_user),
):
    """获取单个性格详情"""
    result = await db.execute(
        select(Personality).where(Personality.id == personality_id, _visible_filter(user))
    )
    personality = result.scalar_one_or_none()
    
    if not personality:
        raise HTTPException(status_code=404, detail="性格不存在")
    
    return personality.to_dict()


@router.post("")
async def create_personality(
    data: PersonalityCreate,
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(require_active_user),
):
    """创建自定义性格"""
    # 普通用户的 ID 只在自己作用域内唯一，避免占用管理员的 ID
    scope = owner_scope(user)
    existing_query = select(Personality).where(Personality.id == data.id)
    if scope:
        existing_query = existing_query.where(Personality.owner_id == scope)
    result = await db.execute(existing_query)
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="性格 ID 已存在")
    
    # 创建新性格
    personality = Personality(
        id=data.id,
        name=data.name,
        description=data.description,
        traits=data.traits,
        speaking_style=data.speaking_style,
        icon=data.icon,
        is_builtin=False,
        is_active=True,
        owner_id=scope,
    )
    _apply_clone_fields(personality, data)

    db.add(personality)
    await db.commit()
    await db.refresh(personality)
    
    return personality.to_dict()


@router.put("/{personality_id}")
async def update_personality(
    personality_id: str,
    data: PersonalityUpdate,
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(require_active_user),
):
    """更新性格（管理员可改内置，普通用户只能改自己的）"""
    result = await db.execute(_load_editable(db, personality_id, user))
    personality = result.scalar_one_or_none()
    
    if not personality:
        raise HTTPException(status_code=404, detail="性格不存在")
    
    # 内置性格和自定义性格都可以修改所有字段
    if data.name is not None:
        personality.name = data.name
    if data.description is not None:
        personality.description = data.description
    if data.traits is not None:
        personality.traits = data.traits
    if data.speaking_style is not None:
        personality.speaking_style = data.speaking_style
    if data.icon is not None:
        personality.icon = data.icon
    if data.is_active is not None:
        personality.is_active = data.is_active
    _apply_clone_fields(personality, data)

    await db.commit()
    await db.refresh(personality)
    
    return personality.to_dict()


@router.delete("/{personality_id}")
async def delete_personality(
    personality_id: str,
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(require_active_user),
):
    """删除性格（仅限自定义性格）"""
    result = await db.execute(_load_editable(db, personality_id, user))
    personality = result.scalar_one_or_none()
    
    if not personality:
        raise HTTPException(status_code=404, detail="性格不存在")
    
    if personality.is_builtin:
        raise HTTPException(status_code=403, detail="内置性格不能删除，只能禁用")
    
    await db.delete(personality)
    await db.commit()
    
    return {"message": "删除成功"}


class DuplicateRequest(BaseModel):
    """复制性格请求"""
    new_id: str = Field(..., min_length=1, max_length=50, pattern="^[a-z0-9_-]+$")
    new_name: Optional[str] = None


@router.post("/{personality_id}/duplicate")
async def duplicate_personality(
    personality_id: str,
    request: DuplicateRequest,
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(require_active_user),
):
    """复制性格（用于基于内置性格创建自定义版本）"""
    new_id = request.new_id
    new_name = request.new_name
    scope = owner_scope(user)
    # 获取源性格（只能复制自己可见的）
    result = await db.execute(
        select(Personality).where(Personality.id == personality_id, _visible_filter(user))
    )
    source = result.scalar_one_or_none()
    
    if not source:
        raise HTTPException(status_code=404, detail="源性格不存在")
    
    
    # 检查新 ID 是否已存在于自己的作用域
    existing = select(Personality).where(Personality.id == new_id)
    if scope:
        existing = existing.where(Personality.owner_id == scope)
    result = await db.execute(existing)
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="新性格 ID 已存在")
    
    # 创建副本
    personality = Personality(
        id=new_id,
        name=new_name or f"{source.name} (副本)",
        description=source.description,
        traits=source.traits.copy(),
        speaking_style=source.speaking_style,
        icon=source.icon,
        is_builtin=False,
        is_active=True,
        owner_id=scope,
    )
    
    db.add(personality)
    await db.commit()
    await db.refresh(personality)
    
    return personality.to_dict()
