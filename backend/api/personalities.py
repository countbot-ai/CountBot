"""性格管理 API"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.personality import Personality

router = APIRouter(prefix="/api/personalities", tags=["personalities"])


class PersonalityCreate(BaseModel):
    """创建性格请求"""
    id: str = Field(..., min_length=1, max_length=50, pattern="^[a-z0-9_-]+$")
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1)
    traits: list[str] = Field(..., min_items=1)
    speaking_style: str = Field(..., min_length=1)
    icon: str = Field(default="Smile", max_length=50)


class PersonalityUpdate(BaseModel):
    """更新性格请求"""
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, min_length=1)
    traits: list[str] | None = Field(None, min_items=1)
    speaking_style: str | None = Field(None, min_length=1)
    icon: str | None = Field(None, max_length=50)
    is_active: bool | None = None


@router.get("")
async def list_personalities(
    active_only: bool = False,
    db: AsyncSession = Depends(get_db)
):
    """获取所有性格列表"""
    query = select(Personality)
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
    db: AsyncSession = Depends(get_db)
):
    """获取单个性格详情"""
    result = await db.execute(
        select(Personality).where(Personality.id == personality_id)
    )
    personality = result.scalar_one_or_none()
    
    if not personality:
        raise HTTPException(status_code=404, detail="性格不存在")
    
    return personality.to_dict()


@router.post("")
async def create_personality(
    data: PersonalityCreate,
    db: AsyncSession = Depends(get_db)
):
    """创建自定义性格"""
    # 检查 ID 是否已存在
    result = await db.execute(
        select(Personality).where(Personality.id == data.id)
    )
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
    )
    
    db.add(personality)
    await db.commit()
    await db.refresh(personality)
    
    return personality.to_dict()


@router.put("/{personality_id}")
async def update_personality(
    personality_id: str,
    data: PersonalityUpdate,
    db: AsyncSession = Depends(get_db)
):
    """更新性格（内置和自定义性格都可以修改）"""
    result = await db.execute(
        select(Personality).where(Personality.id == personality_id)
    )
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
    db: AsyncSession = Depends(get_db)
):
    """删除性格（仅限自定义性格）"""
    result = await db.execute(
        select(Personality).where(Personality.id == personality_id)
    )
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
    new_name: str | None = None


@router.post("/{personality_id}/duplicate")
async def duplicate_personality(
    personality_id: str,
    request: DuplicateRequest,
    db: AsyncSession = Depends(get_db)
):
    """复制性格（用于基于内置性格创建自定义版本）"""
    new_id = request.new_id
    new_name = request.new_name
    # 获取源性格
    result = await db.execute(
        select(Personality).where(Personality.id == personality_id)
    )
    source = result.scalar_one_or_none()
    
    if not source:
        raise HTTPException(status_code=404, detail="源性格不存在")
    
    
    # 检查新 ID 是否已存在
    result = await db.execute(
        select(Personality).where(Personality.id == new_id)
    )
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
    )
    
    db.add(personality)
    await db.commit()
    await db.refresh(personality)
    
    return personality.to_dict()
