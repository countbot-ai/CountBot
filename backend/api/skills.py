"""Skills API 端点"""

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from loguru import logger
from pydantic import BaseModel, Field

from backend.modules.agent.skills import SkillsLoader
from backend.modules.config.loader import config_loader

router = APIRouter(prefix="/api/skills", tags=["skills"])


# ============================================================================
# Request/Response Models
# ============================================================================


class SkillInfo(BaseModel):
    """技能信息"""
    
    name: str = Field(..., description="技能名称")
    description: str = Field(..., description="技能描述")
    enabled: bool = Field(..., description="是否启用")
    auto_load: bool = Field(..., description="是否自动加载", alias="autoLoad")
    requirements: list[str] = Field(default_factory=list, description="依赖要求")
    source: str = Field(..., description="技能来源: workspace 或 builtin")
    
    class Config:
        populate_by_name = True


class SkillDetail(BaseModel):
    """技能详情"""
    
    name: str = Field(..., description="技能名称")
    description: str = Field(..., description="技能描述")
    content: str = Field(..., description="技能内容")
    enabled: bool = Field(..., description="是否启用")
    auto_load: bool = Field(..., description="是否自动加载", alias="autoLoad")
    requirements: list[str] = Field(default_factory=list, description="依赖要求")
    source: str = Field(..., description="技能来源: workspace 或 builtin")
    
    class Config:
        populate_by_name = True


class ListSkillsResponse(BaseModel):
    """技能列表响应"""
    
    skills: list[SkillInfo] = Field(..., description="技能列表")


class ToggleSkillRequest(BaseModel):
    """切换技能请求"""
    
    enabled: bool = Field(..., description="是否启用")


class ToggleSkillResponse(BaseModel):
    """切换技能响应"""
    
    success: bool = Field(..., description="是否成功")
    message: str | None = Field(None, description="消息")


class CreateSkillRequest(BaseModel):
    """创建技能请求"""
    
    name: str = Field(..., description="技能名称", min_length=1, max_length=50)
    description: str = Field("", description="技能描述")
    content: str = Field(..., description="技能内容", min_length=1)
    auto_load: bool = Field(False, description="是否自动加载", alias="autoLoad")
    requirements: list[str] = Field(default_factory=list, description="依赖要求")
    
    class Config:
        populate_by_name = True


class UpdateSkillRequest(BaseModel):
    """更新技能请求"""
    
    description: str = Field("", description="技能描述")
    content: str = Field(..., description="技能内容", min_length=1)
    auto_load: bool = Field(False, description="是否自动加载", alias="autoLoad")
    requirements: list[str] = Field(default_factory=list, description="依赖要求")
    
    class Config:
        populate_by_name = True


class DeleteSkillResponse(BaseModel):
    """删除技能响应"""
    
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="消息")


# ============================================================================
# Helper Functions
# ============================================================================


from backend.modules.config.loader import config_loader
from backend.utils.paths import WORKSPACE_DIR


def get_skills_loader() -> SkillsLoader:
    """获取技能加载器实例"""
    config = config_loader.config
    workspace = Path(config.workspace.path) if config.workspace.path else WORKSPACE_DIR
    workspace = workspace.resolve()  # 确保是绝对路径
    skills_dir = workspace / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    return SkillsLoader(skills_dir)


# ============================================================================
# Skills Endpoints
# ============================================================================


@router.get("", response_model=ListSkillsResponse)
async def list_skills() -> ListSkillsResponse:
    """
    获取所有技能列表
    
    Returns:
        ListSkillsResponse: 技能列表
    """
    try:
        skills_loader = get_skills_loader()
        skills_list = skills_loader.list_skills()
        
        # 转换为响应格式
        skills_info = []
        for skill in skills_list:
            # 获取技能摘要
            summary = skills_loader.get_skill_summary(skill["name"])
            
            skills_info.append(
                SkillInfo(
                    name=skill["name"],
                    description=summary.get("description", ""),
                    enabled=skill.get("enabled", True),
                    auto_load=summary.get("auto_load", False),
                    requirements=summary.get("requirements", []),
                    source=skill.get("source", "workspace"),
                )
            )
        
        return ListSkillsResponse(skills=skills_info)
        
    except Exception as e:
        logger.exception(f"Failed to list skills: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list skills: {str(e)}"
        )


@router.get("/{name}", response_model=SkillDetail)
async def get_skill(name: str) -> SkillDetail:
    """
    获取技能详情
    
    Args:
        name: 技能名称
        
    Returns:
        SkillDetail: 技能详情
    """
    try:
        skills_loader = get_skills_loader()
        
        # 检查技能是否存在
        skills_list = skills_loader.list_skills()
        skill_exists = any(s["name"] == name for s in skills_list)
        
        if not skill_exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Skill '{name}' not found"
            )
        
        # 获取技能内容和摘要
        content = skills_loader.load_skill(name)
        summary = skills_loader.get_skill_summary(name)
        
        # 获取启用状态
        enabled = True
        for skill in skills_list:
            if skill["name"] == name:
                enabled = skill.get("enabled", True)
                break
        
        # 获取技能来源
        source = "workspace"
        for skill in skills_list:
            if skill["name"] == name:
                source = skill.get("source", "workspace")
                break
        
        return SkillDetail(
            name=name,
            description=summary.get("description", ""),
            content=content,
            enabled=enabled,
            auto_load=summary.get("auto_load", False),
            requirements=summary.get("requirements", []),
            source=source,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get skill: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get skill: {str(e)}"
        )


@router.post("/{name}/toggle", response_model=ToggleSkillResponse)
async def toggle_skill(name: str, request: ToggleSkillRequest) -> ToggleSkillResponse:
    """
    切换技能启用状态（持久化到配置）
    
    Args:
        name: 技能名称
        request: 切换技能请求
        
    Returns:
        ToggleSkillResponse: 切换结果
    """
    try:
        skills_loader = get_skills_loader()
        
        # 检查技能是否存在
        skills_list = skills_loader.list_skills()
        skill_exists = any(s["name"] == name for s in skills_list)
        
        if not skill_exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Skill '{name}' not found"
            )
        
        # 切换技能状态
        success = skills_loader.toggle_skill(name, request.enabled)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to toggle skill '{name}'"
            )
        
        # 持久化到配置文件
        config = config_loader.config
        workspace = Path(config.workspace.path) if config.workspace.path else WORKSPACE_DIR
        workspace = workspace.resolve()  # 确保是绝对路径
        config_file = workspace / ".skills_config.json"
        
        logger.info(f"Saving skills config to: {config_file}")
        
        # 读取现有配置
        skills_config = {}
        if config_file.exists():
            try:
                skills_config = json.loads(config_file.read_text(encoding="utf-8"))
                logger.debug(f"Loaded existing config: {skills_config}")
            except Exception as e:
                logger.warning(f"Failed to load existing config: {e}")
        
        # 更新配置
        if "disabled_skills" not in skills_config:
            skills_config["disabled_skills"] = []
        
        if request.enabled:
            # 启用：从禁用列表中移除
            if name in skills_config["disabled_skills"]:
                skills_config["disabled_skills"].remove(name)
                logger.info(f"Removed '{name}' from disabled list")
        else:
            # 禁用：添加到禁用列表
            if name not in skills_config["disabled_skills"]:
                skills_config["disabled_skills"].append(name)
                logger.info(f"Added '{name}' to disabled list")
        
        # 保存配置
        config_file.write_text(json.dumps(skills_config, indent=2, ensure_ascii=False), encoding="utf-8")
        
        status_text = "enabled" if request.enabled else "disabled"
        return ToggleSkillResponse(
            success=True,
            message=f"Skill '{name}' {status_text} successfully",
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to toggle skill: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to toggle skill: {str(e)}"
        )


@router.post("", response_model=SkillDetail, status_code=status.HTTP_201_CREATED)
async def create_skill(request: CreateSkillRequest) -> SkillDetail:
    """
    创建新技能
    
    Args:
        request: 创建技能请求
        
    Returns:
        SkillDetail: 创建的技能详情
    """
    try:
        skills_loader = get_skills_loader()
        
        # 检查技能是否已存在
        if skills_loader.get_skill(request.name):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Skill '{request.name}' already exists"
            )
        
        # 构建技能内容（包含 frontmatter）
        metadata = {
            "CountBot": {
                "always": request.auto_load,
                "requires": {
                    "bins": request.requirements
                }
            }
        }
        
        frontmatter = f"""---
name: {request.name}
description: {request.description}
metadata: {json.dumps(metadata)}
---

"""
        full_content = frontmatter + request.content
        
        # 创建技能
        success = skills_loader.add_skill(request.name, full_content)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create skill '{request.name}'"
            )
        
        # 返回创建的技能
        return await get_skill(request.name)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to create skill: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create skill: {str(e)}"
        )


@router.put("/{name}", response_model=SkillDetail)
async def update_skill(name: str, request: UpdateSkillRequest) -> SkillDetail:
    """
    更新技能
    
    Args:
        name: 技能名称
        request: 更新技能请求
        
    Returns:
        SkillDetail: 更新后的技能详情
    """
    try:
        skills_loader = get_skills_loader()
        
        # 检查技能是否存在
        skill = skills_loader.get_skill(name)
        if not skill:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Skill '{name}' not found"
            )
        
        # 不允许更新内置技能
        if skill.source == "builtin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot update builtin skills"
            )
        
        # 构建技能内容（包含 frontmatter）
        metadata = {
            "CountBot": {
                "always": request.auto_load,
                "requires": {
                    "bins": request.requirements
                }
            }
        }
        
        frontmatter = f"""---
name: {name}
description: {request.description}
metadata: {json.dumps(metadata)}
---

"""
        full_content = frontmatter + request.content
        
        # 更新技能
        success = skills_loader.update_skill(name, full_content)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to update skill '{name}'"
            )
        
        # 返回更新后的技能
        return await get_skill(name)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to update skill: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update skill: {str(e)}"
        )


@router.delete("/{name}", response_model=DeleteSkillResponse)
async def delete_skill(name: str) -> DeleteSkillResponse:
    """
    删除技能
    
    Args:
        name: 技能名称
        
    Returns:
        DeleteSkillResponse: 删除结果
    """
    try:
        skills_loader = get_skills_loader()
        
        # 检查技能是否存在
        skill = skills_loader.get_skill(name)
        if not skill:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Skill '{name}' not found"
            )
        
        # 不允许删除内置技能
        if skill.source == "builtin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot delete builtin skills"
            )
        
        # 删除技能
        success = skills_loader.delete_skill(name)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to delete skill '{name}'"
            )
        
        return DeleteSkillResponse(
            success=True,
            message=f"Skill '{name}' deleted successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to delete skill: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete skill: {str(e)}"
        )
