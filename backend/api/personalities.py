"""性格管理 API"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.personality import Personality
from backend.modules.multiuser.identity import AuthUser
from backend.modules.multiuser.permissions import owner_scope, require_active_user



def _visible_filter(user: AuthUser):
    """可见范围：内置与自己的性格；管理员看内置与管理员的。"""
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
    traits: List[str] = Field(..., min_length=1)
    speaking_style: str = Field(..., min_length=1)
    icon: str = Field(default="Smile", max_length=50)


class PersonalityDuplicate(BaseModel):
    """复制性格请求"""
    id: str = Field(..., min_length=1, max_length=50, pattern="^[a-z0-9_-]+$")
    name: Optional[str] = Field(None, min_length=1, max_length=100)


class PersonalityUpdate(BaseModel):
    """更新性格请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, min_length=1)
    traits: Optional[List[str]] = Field(None, min_length=1)
    speaking_style: Optional[str] = Field(None, min_length=1)
    icon: Optional[str] = Field(None, max_length=50)
    is_active: Optional[bool] = None
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
    """创建性格"""
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

    db.add(personality)
    await db.commit()
    await db.refresh(personality)
    
    return personality.to_dict()


@router.post("/{personality_id}/duplicate")
async def duplicate_personality(
    personality_id: str,
    data: PersonalityDuplicate,
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(require_active_user),
):
    """复制性格，常用于基于内置性格创建自定义版本"""
    result = await db.execute(
        select(Personality).where(Personality.id == personality_id, _visible_filter(user))
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="性格不存在")

    # 副本 ID 只在自己作用域内校验唯一性
    scope = owner_scope(user)
    existing_query = select(Personality).where(Personality.id == data.id)
    if scope:
        existing_query = existing_query.where(Personality.owner_id == scope)
    if (await db.execute(existing_query)).scalar_one_or_none():
        raise HTTPException(status_code=400, detail="性格 ID 已存在")

    duplicate = Personality(
        id=data.id,
        name=data.name or f"{source.name} (副本)",
        description=source.description,
        traits=list(source.traits or []),
        speaking_style=source.speaking_style,
        icon=source.icon,
        is_builtin=False,
        is_active=True,
        owner_id=scope,
    )

    db.add(duplicate)
    await db.commit()
    await db.refresh(duplicate)

    return duplicate.to_dict()


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

    await db.commit()
    await db.refresh(personality)
    
    return personality.to_dict()


@router.delete("/{personality_id}")
async def delete_personality(
    personality_id: str,
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(require_active_user),
):
    """删除性格，内置与新增使用同一规则"""
    result = await db.execute(_load_editable(db, personality_id, user))
    personality = result.scalar_one_or_none()
    
    if not personality:
        raise HTTPException(status_code=404, detail="性格不存在")
    
    await db.delete(personality)
    await db.commit()
    
    return {"message": "删除成功"}
