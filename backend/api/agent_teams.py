"""Agent Teams API — CRUD for user-defined multi-agent workflow templates."""

import uuid
from typing import Any, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.agent_team import AgentTeam

router = APIRouter(prefix="/api/agent-teams", tags=["agent-teams"])


def _normalize_api_mode(value: Any) -> str:
    return "chat_completions"


# ============================================================================
# Pydantic schemas
# ============================================================================


class AgentDefinition(BaseModel):
    """One agent slot inside a workflow."""
    id: str = Field(..., description="Unique identifier within the team")
    role: str = Field(default="", description="Role / persona label")
    system_prompt: Optional[str] = Field(
        None,
        description=(
            "Persistent system-level instructions for this agent. "
            "Injected as the system message so the LLM fully adopts this persona "
            "before seeing the workflow goal or task."
        ),
    )
    task: str = Field(default="", description="What this agent should do (pipeline/graph only)")
    perspective: Optional[str] = Field(None, description="Viewpoint label (council mode only)")
    depends_on: List[str] = Field(default_factory=list, description="IDs this agent waits for (graph mode)")
    condition: Optional[dict] = Field(
        None,
        description=(
            "Optional execution condition (graph mode only). "
            "Example: {'type': 'output_contains', 'node': 'test', 'text': '通过'}"
        ),
    )


class AgentTeamCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    mode: str = Field("pipeline", pattern="^(pipeline|graph|council)$")
    agents: List[AgentDefinition] = Field(default_factory=list)
    is_active: bool = Field(True)
    cross_review: bool = Field(True, description="Council mode only: enable cross-review between members")
    enable_skills: bool = Field(False, description="Enable skills system for sub-agents")


class AgentTeamUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    mode: Optional[str] = Field(None, pattern="^(pipeline|graph|council)$")
    agents: Optional[List[AgentDefinition]] = None
    is_active: Optional[bool] = None
    cross_review: Optional[bool] = Field(None, description="Council mode only: enable cross-review between members")
    enable_skills: Optional[bool] = Field(None, description="Enable skills system for sub-agents")


class AgentTeamResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    mode: str
    agents: List[Any]
    is_active: bool
    cross_review: bool
    enable_skills: bool
    use_custom_model: bool
    created_at: str
    updated_at: str


class TeamModelConfigRequest(BaseModel):
    """团队模型配置请求"""
    provider: Optional[str] = None
    model: Optional[str] = None
    api_mode: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    max_iterations: Optional[int] = None
    thinking_enabled: Optional[bool] = None
    api_key: Optional[str] = None
    api_base: Optional[str] = None


class TeamModelConfigResponse(BaseModel):
    """团队模型配置响应"""
    team_id: str
    use_custom_model: bool
    model_settings: dict
    global_defaults: dict


# ============================================================================
# Helpers
# ============================================================================


def _to_response(team: AgentTeam) -> AgentTeamResponse:
    return AgentTeamResponse(**team.to_dict())


async def _get_or_404(team_id: str, db: AsyncSession) -> AgentTeam:
    result = await db.execute(select(AgentTeam).where(AgentTeam.id == team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Agent team '{team_id}' not found")
    return team


# ============================================================================
# Endpoints
# ============================================================================


@router.get("/", response_model=List[AgentTeamResponse])
async def list_teams(db: AsyncSession = Depends(get_db)) -> List[AgentTeamResponse]:
    """Return all agent teams ordered by creation time (newest first)."""
    try:
        result = await db.execute(
            select(AgentTeam).order_by(AgentTeam.created_at.desc())
        )
        teams = result.scalars().all()
        return [_to_response(t) for t in teams]
    except Exception as exc:
        logger.exception(f"Failed to list agent teams: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{team_id}", response_model=AgentTeamResponse)
async def get_team(team_id: str, db: AsyncSession = Depends(get_db)) -> AgentTeamResponse:
    team = await _get_or_404(team_id, db)
    return _to_response(team)


@router.post("/", response_model=AgentTeamResponse, status_code=status.HTTP_201_CREATED)
async def create_team(
    payload: AgentTeamCreate,
    db: AsyncSession = Depends(get_db),
) -> AgentTeamResponse:
    """Create a new agent team template."""
    try:
        # 检查是否存在同名团队
        existing = await db.execute(
            select(AgentTeam).where(AgentTeam.name == payload.name)
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"团队名称 '{payload.name}' 已存在，请使用其他名称"
            )
        
        team = AgentTeam(
            id=str(uuid.uuid4()),
            name=payload.name,
            description=payload.description,
            mode=payload.mode,
            agents=[a.model_dump() for a in payload.agents],
            is_active=payload.is_active,
            cross_review=payload.cross_review,
            enable_skills=payload.enable_skills,
        )
        db.add(team)
        await db.commit()
        await db.refresh(team)
        return _to_response(team)
    except HTTPException:
        raise
    except Exception as exc:
        await db.rollback()
        logger.exception(f"Failed to create agent team: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.put("/{team_id}", response_model=AgentTeamResponse)
async def update_team(
    team_id: str,
    payload: AgentTeamUpdate,
    db: AsyncSession = Depends(get_db),
) -> AgentTeamResponse:
    """Update an existing agent team."""
    team = await _get_or_404(team_id, db)
    try:
        # 如果要修改名称，检查新名称是否与其他团队重复
        if payload.name is not None and payload.name != team.name:
            existing = await db.execute(
                select(AgentTeam).where(
                    AgentTeam.name == payload.name,
                    AgentTeam.id != team_id
                )
            )
            if existing.scalar_one_or_none() is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"团队名称 '{payload.name}' 已存在，请使用其他名称"
                )
            team.name = payload.name
        
        if payload.description is not None:
            team.description = payload.description
        if payload.mode is not None:
            team.mode = payload.mode
        if payload.agents is not None:
            team.agents = [a.model_dump() for a in payload.agents]
        if payload.is_active is not None:
            team.is_active = payload.is_active
        if payload.cross_review is not None:
            team.cross_review = payload.cross_review
        if payload.enable_skills is not None:
            team.enable_skills = payload.enable_skills
        await db.commit()
        await db.refresh(team)
        return _to_response(team)
    except HTTPException:
        raise
    except Exception as exc:
        await db.rollback()
        logger.exception(f"Failed to update agent team {team_id}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team(team_id: str, db: AsyncSession = Depends(get_db)) -> None:
    """Delete an agent team."""
    team = await _get_or_404(team_id, db)
    try:
        await db.delete(team)
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.exception(f"Failed to delete agent team {team_id}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


# ============================================================================
# Team Model Configuration Endpoints
# ============================================================================


@router.get("/{team_id}/config", response_model=TeamModelConfigResponse)
async def get_team_config(
    team_id: str,
    db: AsyncSession = Depends(get_db),
) -> TeamModelConfigResponse:
    """获取团队模型配置
    
    返回团队的有效配置（如果有自定义配置则返回，否则返回全局默认）
    """
    import json
    from backend.modules.config.loader import config_loader
    
    team = await _get_or_404(team_id, db)
    
    try:
        config = config_loader.config
        global_model = config.model.model_dump()
        
        # 解析团队自定义配置
        team_model_config = {}
        if team.use_custom_model and team.team_model_config:
            try:
                team_model_config = json.loads(team.team_model_config)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse team model config for {team_id}")
        
        # 合并配置（团队配置覆盖全局配置）
        effective_config = global_model.copy()
        for key, value in team_model_config.items():
            if value is not None and value != "":
                effective_config[key] = (
                    _normalize_api_mode(value) if key == "api_mode" else value
                )
        
        # 确保 api_key 和 api_base 字段存在
        if "api_key" not in effective_config:
            effective_config["api_key"] = ""
        if "api_base" not in effective_config:
            effective_config["api_base"] = ""
        
        return TeamModelConfigResponse(
            team_id=team_id,
            use_custom_model=team.use_custom_model,
            model_settings=effective_config,
            global_defaults=global_model,
        )
        
    except Exception as e:
        logger.exception(f"Failed to get team config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get team config: {str(e)}"
        )


@router.put("/{team_id}/config")
async def update_team_config(
    team_id: str,
    request: TeamModelConfigRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """更新团队模型配置"""
    import json
    from datetime import datetime, timezone
    
    team = await _get_or_404(team_id, db)
    
    try:
        # 构建配置字典（只保存非空值）
        config_dict = {}
        if request.provider is not None and request.provider != "":
            config_dict["provider"] = request.provider
        if request.model is not None and request.model != "":
            config_dict["model"] = request.model
        if request.api_mode is not None and request.api_mode != "":
            config_dict["api_mode"] = _normalize_api_mode(request.api_mode)
        if request.temperature is not None:
            config_dict["temperature"] = request.temperature
        if request.max_tokens is not None:
            config_dict["max_tokens"] = request.max_tokens
        if request.max_iterations is not None:
            config_dict["max_iterations"] = request.max_iterations
        if request.thinking_enabled is not None:
            config_dict["thinking_enabled"] = request.thinking_enabled
        if request.api_key is not None and request.api_key != "":
            config_dict["api_key"] = request.api_key
        if request.api_base is not None and request.api_base != "":
            config_dict["api_base"] = request.api_base
        
        # 保存配置
        team.team_model_config = json.dumps(config_dict)
        team.use_custom_model = True
        team.updated_at = datetime.now(timezone.utc)
        
        await db.commit()
        await db.refresh(team)
        
        logger.info(f"Updated model config for team {team_id}: {config_dict}")
        
        return {
            "success": True,
            "team_id": team_id,
            "message": "Team model configuration updated"
        }
        
    except Exception as e:
        await db.rollback()
        logger.exception(f"Failed to update team config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update team config: {str(e)}"
        )


@router.delete("/{team_id}/config")
async def reset_team_config(
    team_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """重置团队模型配置为全局默认"""
    from datetime import datetime, timezone
    
    team = await _get_or_404(team_id, db)
    
    try:
        team.team_model_config = None
        team.use_custom_model = False
        team.updated_at = datetime.now(timezone.utc)
        
        await db.commit()
        
        logger.info(f"Reset model config for team {team_id}")
        
        return {
            "success": True,
            "team_id": team_id,
            "message": "Team model configuration reset to global defaults"
        }
        
    except Exception as e:
        await db.rollback()
        logger.exception(f"Failed to reset team config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset team config: {str(e)}"
        )
