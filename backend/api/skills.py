"""Skills API 端点"""

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, status
from loguru import logger
from pydantic import BaseModel, Field

from backend.modules.agent.skills import SkillsLoader
from backend.modules.agent.skills_config import SkillConfigManager
from backend.modules.agent.skills_schema import SkillConfigSchema
from backend.modules.config.loader import config_loader
from backend.utils.paths import APPLICATION_ROOT

router = APIRouter(prefix="/api/skills", tags=["skills"])

# 内置技能目录
BUILTIN_SKILLS_DIR = APPLICATION_ROOT / "skills"


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


class ConfigFieldSchema(BaseModel):
    """配置字段Schema"""
    
    key: str = Field(..., description="字段键名")
    type: str = Field(..., description="字段类型")
    label: str = Field(..., description="显示标签")
    description: str | None = Field(None, description="字段说明")
    required: bool = Field(False, description="是否必填")
    sensitive: bool = Field(False, description="是否敏感信息")
    readonly: bool = Field(False, description="是否只读")
    default: Any = Field(None, description="默认值")
    placeholder: str | None = Field(None, description="占位符")
    validation: str | None = Field(None, description="正则验证")
    min: int | None = Field(None, description="最小值")
    max: int | None = Field(None, description="最大值")
    options: list[dict] | None = Field(None, description="选项列表")
    help_url: str | None = Field(None, description="帮助链接")
    fields: list['ConfigFieldSchema'] | None = Field(None, description="子字段")
    collapsible: bool = Field(False, description="是否可折叠")


class SkillConfigSchemaResponse(BaseModel):
    """技能配置Schema响应"""
    
    has_schema: bool = Field(..., description="是否有Schema")
    schema: dict | None = Field(None, description="Schema定义")


class SkillConfigResponse(BaseModel):
    """技能配置响应"""
    
    has_config: bool = Field(..., description="是否有配置文件")
    config: dict | None = Field(None, description="配置内容")
    status: str = Field(..., description="配置状态")
    errors: list[str] = Field(default_factory=list, description="错误列表")


class UpdateSkillConfigRequest(BaseModel):
    """更新技能配置请求"""
    
    config: dict = Field(..., description="配置内容")


class SkillConfigStatusResponse(BaseModel):
    """技能配置状态响应"""
    
    status: str = Field(..., description="配置状态")
    message: str = Field(..., description="状态消息")
    errors: list[str] = Field(default_factory=list, description="错误列表")


class SkillConfigHelpResponse(BaseModel):
    """技能配置帮助响应"""
    
    has_help: bool = Field(..., description="是否有帮助文档")
    content: str | None = Field(None, description="帮助内容")


class FixSkillConfigResponse(BaseModel):
    """修复技能配置响应"""
    
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


# ============================================================================
# Skills Config Endpoints
# ============================================================================


@router.get("/{name}/config/schema", response_model=SkillConfigSchemaResponse)
async def get_skill_config_schema(name: str) -> SkillConfigSchemaResponse:
    """
    获取技能配置Schema
    
    Args:
        name: 技能名称
        
    Returns:
        SkillConfigSchemaResponse: Schema信息
    """
    try:
        schema_loader = SkillConfigSchema(BUILTIN_SKILLS_DIR)
        schema = schema_loader.load_schema(name)
        
        if not schema:
            return SkillConfigSchemaResponse(
                has_schema=False,
                schema=None
            )
        
        return SkillConfigSchemaResponse(
            has_schema=True,
            schema=schema
        )
        
    except Exception as e:
        logger.exception(f"Failed to get config schema: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get config schema: {str(e)}"
        )


@router.get("/{name}/config", response_model=SkillConfigResponse)
async def get_skill_config(name: str) -> SkillConfigResponse:
    """
    获取技能配置
    
    Args:
        name: 技能名称
        
    Returns:
        SkillConfigResponse: 配置信息
    """
    try:
        config_manager = SkillConfigManager(BUILTIN_SKILLS_DIR)
        
        # 检查是否有配置文件
        if not config_manager.has_config(name):
            return SkillConfigResponse(
                has_config=False,
                config=None,
                status="not_configured",
                errors=[]
            )
        
        # 加载配置
        config = config_manager.load_config(name)
        if config is None:
            return SkillConfigResponse(
                has_config=True,
                config=None,
                status="invalid_format",
                errors=["配置文件格式错误"]
            )
        
        # 检查配置状态
        status_code, errors = config_manager.get_config_status(name)
        
        return SkillConfigResponse(
            has_config=True,
            config=config,
            status=status_code,
            errors=errors
        )
        
    except Exception as e:
        logger.exception(f"Failed to get skill config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get skill config: {str(e)}"
        )


@router.put("/{name}/config", response_model=SkillConfigResponse)
async def update_skill_config(
    name: str, 
    request: UpdateSkillConfigRequest
) -> SkillConfigResponse:
    """
    更新技能配置
    
    Args:
        name: 技能名称
        request: 更新配置请求
        
    Returns:
        SkillConfigResponse: 更新后的配置信息
    """
    try:
        config_manager = SkillConfigManager(BUILTIN_SKILLS_DIR)
        schema_loader = SkillConfigSchema(BUILTIN_SKILLS_DIR)
        
        # 检查配置文件是否存在
        if not config_manager.has_config(name):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Config file not found for skill '{name}'"
            )
        
        # 验证配置
        is_valid, errors = schema_loader.validate_config(name, request.config)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid config: {', '.join(errors)}"
            )
        
        # 保存配置
        success = config_manager.save_config(name, request.config)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to save config for skill '{name}'"
            )
        
        logger.info(f"Updated config for skill: {name}")
        
        # 返回更新后的配置
        return await get_skill_config(name)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to update skill config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update skill config: {str(e)}"
        )


@router.get("/{name}/config/status", response_model=SkillConfigStatusResponse)
async def get_skill_config_status(name: str) -> SkillConfigStatusResponse:
    """
    获取技能配置状态
    
    Args:
        name: 技能名称
        
    Returns:
        SkillConfigStatusResponse: 配置状态
    """
    try:
        config_manager = SkillConfigManager(BUILTIN_SKILLS_DIR)
        schema_loader = SkillConfigSchema(BUILTIN_SKILLS_DIR)
        
        # 检查Schema
        if not schema_loader.has_schema(name):
            return SkillConfigStatusResponse(
                status="no_schema",
                message="该技能不支持可视化配置编辑",
                errors=[]
            )
        
        # 检查配置文件
        if not config_manager.has_config(name):
            return SkillConfigStatusResponse(
                status="not_configured",
                message="配置文件不存在",
                errors=[]
            )
        
        # 获取配置状态
        status_code, errors = config_manager.get_config_status(name)
        
        status_messages = {
            "valid": "配置正常",
            "invalid_format": "配置文件格式错误",
            "missing_fields": "配置不完整",
        }
        
        return SkillConfigStatusResponse(
            status=status_code,
            message=status_messages.get(status_code, "未知状态"),
            errors=errors
        )
        
    except Exception as e:
        logger.exception(f"Failed to check config status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check config status: {str(e)}"
        )


@router.post("/{name}/config/fix", response_model=FixSkillConfigResponse)
async def fix_skill_config(name: str) -> FixSkillConfigResponse:
    """
    自动修复技能配置
    
    Args:
        name: 技能名称
        
    Returns:
        FixSkillConfigResponse: 修复结果
    """
    try:
        config_manager = SkillConfigManager(BUILTIN_SKILLS_DIR)
        schema_loader = SkillConfigSchema(BUILTIN_SKILLS_DIR)
        
        # 检查Schema
        if not schema_loader.has_schema(name):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Schema not found"
            )
        
        # 检查配置文件
        if not config_manager.has_config(name):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Config file not found"
            )
        
        # 执行修复
        success = config_manager.auto_fix_config(name)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fix config"
            )
        
        logger.info(f"Fixed config for skill: {name}")
        
        return FixSkillConfigResponse(
            success=True,
            message="配置已自动修复"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to fix config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fix config: {str(e)}"
        )


@router.get("/{name}/config/help", response_model=SkillConfigHelpResponse)
async def get_skill_config_help(name: str) -> SkillConfigHelpResponse:
    """
    获取技能配置帮助文档
    
    Args:
        name: 技能名称
        
    Returns:
        SkillConfigHelpResponse: 帮助文档
    """
    try:
        config_manager = SkillConfigManager(BUILTIN_SKILLS_DIR)
        
        content = config_manager.get_help_content(name)
        
        if not content:
            return SkillConfigHelpResponse(
                has_help=False,
                content=None
            )
        
        return SkillConfigHelpResponse(
            has_help=True,
            content=content
        )
        
    except Exception as e:
        logger.exception(f"Failed to get config help: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get config help: {str(e)}"
        )
