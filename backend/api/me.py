"""普通用户自助接口（/api/me）：身份、模型与人设，返回值统一脱敏。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger
from pydantic import BaseModel, Field

from backend.modules.config.schema import McpServerConfig, ProviderConfig
from backend.modules.multiuser.effective import (
    ModelResolutionError,
    assert_shared_model_allowed,
    build_provider,
    list_available_models,
    resolve_persona_for_user,
    validate_model_ref,
)
from backend.modules.providers.connection_test import run_connection_test
from backend.modules.multiuser.identity import (
    AuthUser,
    allowed_chat_modes,
    normalize_chat_mode_policy,
)
from backend.modules.multiuser.permissions import require_active_user
from backend.modules.multiuser.runtime import user_runtime_manager
from backend.modules.multiuser.ssrf import SsrfError, validate_outbound_url
from backend.modules.multiuser.user_config import (
    load_user_config,
    normalize_model_ref,
    patch_user_config,
    save_user_config,
)
from backend.modules.multiuser.user_mcp import (
    MAX_USER_MCP_SERVERS,
    UserMcpError,
    load_user_mcp_servers,
    mask_server_config,
    owner_server_prefix,
    prepare_server_list,
    restore_masked_config,
    save_user_mcp_servers,
    user_mcp_manager,
)

router = APIRouter(
    prefix="/api/me",
    tags=["me"],
    dependencies=[Depends(require_active_user)],
)


def _require_regular(user: AuthUser) -> str:
    """这些接口只对普通用户开放；管理员请使用全局管理接口。"""
    if user.is_admin or not user.owner_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"detail": "管理员请使用全局配置接口", "code": "ADMIN_USE_GLOBAL"},
        )
    return user.owner_id


# ======================================================================
# 身份
# ======================================================================


@router.get("")
async def get_me(user: AuthUser = Depends(require_active_user)) -> Dict[str, Any]:
    """当前登录用户信息（不含任何敏感字段）。"""
    from backend.modules.multiuser.settings import load_settings

    settings = await load_settings()
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name or user.username,
        "role": user.role,
        "status": user.status,
        "is_admin": user.is_admin,
        "chat_mode_policy": normalize_chat_mode_policy(user.chat_mode_policy),
        "allowed_chat_modes": allowed_chat_modes(user),
        "mode": settings.mode,
        "shared_providers": settings.shared_providers,
        "shared_skills_wiki_mcp": settings.shared_skills_wiki_mcp,
    }


# ======================================================================
# 模型
# ======================================================================


class OwnModelRequest(BaseModel):
    provider: str = Field(..., min_length=1, max_length=64)
    model: str = Field(..., min_length=1, max_length=200)
    display_name: Optional[str] = Field(None, max_length=100)
    api_key: Optional[str] = Field(None, max_length=4096)
    api_base: Optional[str] = Field(None, max_length=2048)
    enabled: bool = True


class ModelSelectionRequest(BaseModel):
    source: str = Field(..., description="shared | own")
    provider: str
    model: str


class ModelTestRequest(BaseModel):
    source: str
    provider: str
    model: str


@router.get("/models")
async def list_my_models(user: AuthUser = Depends(require_active_user)) -> Dict[str, Any]:
    """可用模型：共享（别名、无 Key）+ 自有。"""
    return await list_available_models(user)


@router.get("/reasoning-levels")
async def get_my_reasoning_levels(model: str = "") -> Dict[str, Any]:
    """返回模型思考档位的内置建议，对所有登录用户开放。"""
    from backend.modules.providers.thinking_profiles import (
        KNOWN_REASONING_LEVELS,
        resolve_model_reasoning_levels,
    )

    return {
        "model": model,
        "levels": resolve_model_reasoning_levels(model),
        "known_levels": list(KNOWN_REASONING_LEVELS),
    }


@router.post("/models")
async def add_own_model(
    payload: OwnModelRequest,
    user: AuthUser = Depends(require_active_user),
) -> Dict[str, Any]:
    """添加自有模型；``api_base`` 必须通过 SSRF 校验。"""
    owner_id = _require_regular(user)
    api_base = (payload.api_base or "").strip() or None
    if api_base:
        try:
            api_base = validate_outbound_url(api_base)
        except SsrfError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    raw = await load_user_config(owner_id)
    providers = raw.get("providers")
    if not isinstance(providers, dict):
        providers = {}
        raw["providers"] = providers

    provider_data = providers.get(payload.provider)
    if not isinstance(provider_data, dict):
        provider_data = {"enabled": True, "models": [], "api_key": "", "api_keys": []}
        providers[payload.provider] = provider_data

    if api_base:
        provider_data["api_base"] = api_base
    if payload.api_key is not None and payload.api_key.strip():
        provider_data["api_key"] = payload.api_key.strip()

    models = provider_data.get("models")
    if not isinstance(models, list):
        models = []
    provider_data["models"] = models

    existing = next((m for m in models if isinstance(m, dict) and m.get("id") == payload.model), None)
    if existing is not None:
        existing["display_name"] = payload.display_name or payload.model
        existing["enabled"] = payload.enabled
    else:
        models.append(
            {
                "id": payload.model,
                "display_name": payload.display_name or payload.model,
                "enabled": payload.enabled,
                "source": "manual",
            }
        )

    # 结构校验：非法配置不写入
    try:
        ProviderConfig.model_validate(provider_data)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"模型配置无效: {exc}") from exc

    await save_user_config(owner_id, raw)
    user_runtime_manager.invalidate(owner_id)
    return await list_available_models(user)


@router.delete("/models")
async def delete_own_model(
    provider: str = Query(...),
    model: str = Query(...),
    user: AuthUser = Depends(require_active_user),
) -> Dict[str, Any]:
    """删除自有模型；共享模型不可删除。"""
    owner_id = _require_regular(user)
    raw = await load_user_config(owner_id)
    providers = raw.get("providers") or {}
    provider_data = providers.get(provider) if isinstance(providers, dict) else None

    if not isinstance(provider_data, dict):
        raise HTTPException(status_code=404, detail="模型不存在")

    models = provider_data.get("models") or []
    remaining = [m for m in models if not (isinstance(m, dict) and m.get("id") == model)]
    if len(remaining) == len(models):
        raise HTTPException(status_code=404, detail="模型不存在")
    provider_data["models"] = remaining

    current = normalize_model_ref(raw.get("model_ref"))
    if current and current["source"] == "own" and current["provider"] == provider and current["model"] == model:
        raw.pop("model_ref", None)

    await save_user_config(owner_id, raw)
    user_runtime_manager.invalidate(owner_id)
    return await list_available_models(user)


@router.put("/model-selection")
async def set_model_selection(
    payload: ModelSelectionRequest,
    user: AuthUser = Depends(require_active_user),
) -> Dict[str, Any]:
    """切换当前使用的模型（共享或自有）。"""
    owner_id = _require_regular(user)
    try:
        ref = await validate_model_ref(user, payload.source, payload.provider, payload.model)
    except ModelResolutionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await patch_user_config(owner_id, model_ref=ref)
    user_runtime_manager.invalidate(owner_id)
    return await list_available_models(user)


@router.post("/models/test")
async def test_own_model(
    payload: ModelTestRequest,
    user: AuthUser = Depends(require_active_user),
) -> Dict[str, Any]:
    """连通性测试：服务端代发一次最小流式请求，不回显密钥。

    探测必须走 run_connection_test 与实际对话同一条 chat_stream 链路，
    不能调用 provider 上不存在的非流式方法。
    """
    try:
        ref = await validate_model_ref(user, payload.source, payload.provider, payload.model)
        raw = await load_user_config(user.owner_id or "")
        if payload.source == "shared":
            from backend.modules.multiuser.effective import _from_shared  # 内部复用

            assert_shared_model_allowed(user, ref["provider"], ref["model"])
            resolved = _from_shared(ref["provider"], ref["model"])
        else:
            from backend.modules.multiuser.effective import _from_own  # 内部复用

            resolved = _from_own(raw, ref["provider"], ref["model"])

        provider = build_provider(resolved, timeout=20.0, max_retries=0)
        success, detail = await run_connection_test(
            provider,
            provider_id=ref["provider"],
            model=resolved.model_id,
            max_tokens=8,
        )
        if success:
            return {"success": True, "message": detail}
        return {"success": False, "message": detail}
    except HTTPException:
        raise
    except ModelResolutionError as exc:
        return {"success": False, "message": str(exc)}
    except Exception as exc:
        logger.warning(f"Model test failed for {user.username}: {exc}")
        return {"success": False, "message": f"连接失败: {exc}"}


# ======================================================================
# 人设
# ======================================================================


class PersonaUpdate(BaseModel):
    """人设的局部更新，字段需覆盖全部可编辑项以免丢失已有设置。"""

    ai_name: Optional[str] = Field(None, max_length=50)
    user_name: Optional[str] = Field(None, max_length=50)
    user_address: Optional[str] = Field(None, max_length=200)
    output_language: Optional[str] = Field(None, max_length=20)
    personality: Optional[str] = Field(None, max_length=50)
    custom_personality: Optional[str] = Field(None, max_length=4000)
    max_history_messages: Optional[int] = Field(None, ge=-1, le=500)
    enable_short_context_summary: Optional[bool] = None
    heartbeat: Optional[Dict[str, Any]] = None


@router.get("/persona")
async def get_my_persona(user: AuthUser = Depends(require_active_user)) -> Dict[str, Any]:
    persona = await resolve_persona_for_user(user)
    return persona.model_dump()


@router.put("/persona")
async def update_my_persona(
    payload: PersonaUpdate,
    user: AuthUser = Depends(require_active_user),
) -> Dict[str, Any]:
    owner_id = _require_regular(user)
    from backend.modules.config.schema import PersonaConfig

    # 主动问候只属于管理员，普通用户提交的 heartbeat 直接忽略
    submitted = payload.model_dump(exclude_none=True)
    submitted.pop("heartbeat", None)

    # 以当前生效值为基底合并，调用方只需传要改的字段
    base = (await resolve_persona_for_user(user)).model_dump()
    for key, value in submitted.items():
        base[key] = value
    try:
        PersonaConfig(**base)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"人设配置无效: {exc}") from exc

    # 仅落库调用方显式提交的字段，避免整键替换丢失已有覆盖层
    raw = await load_user_config(owner_id)
    existing_persona = raw.get("persona")
    merged_persona = {
        **(existing_persona if isinstance(existing_persona, dict) else {}),
        **submitted,
    }
    await patch_user_config(owner_id, persona=merged_persona)
    user_runtime_manager.invalidate(owner_id)
    return (await resolve_persona_for_user(user)).model_dump()


# ======================================================================
# 用户自建 MCP
# ======================================================================


class UserMcpUpdateRequest(BaseModel):
    servers: List[McpServerConfig] = Field(default_factory=list)


class UserMcpTestRequest(BaseModel):
    server: McpServerConfig


def _masked_mcp_view(
    owner_id: str,
    servers: List[McpServerConfig],
    status: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """把用户 MCP 配置转换为脱敏视图，并附上运行状态。"""
    if status is None:
        status = user_mcp_manager.get_status(owner_id)
    prefix = owner_server_prefix(owner_id)
    server_status = status.get("server_status", {})
    items: List[Dict[str, Any]] = []
    for server in servers:
        info = server_status.get(prefix + (server.id or server.name), {})
        item = mask_server_config(server)
        item["running"] = bool(info.get("connected"))
        item["tool_count"] = int(info.get("tool_count", 0))
        items.append(item)
    return items


@router.get("/mcp")
async def list_my_mcp(user: AuthUser = Depends(require_active_user)) -> Dict[str, Any]:
    """列出本人 MCP 服务器（凭证已脱敏）。"""
    from backend.modules.multiuser.settings import load_settings

    owner_id = _require_regular(user)
    settings = await load_settings()
    servers = await load_user_mcp_servers(owner_id)
    status = user_mcp_manager.get_status(owner_id)
    return {
        "enabled": settings.allow_user_mcp,
        "max_servers": MAX_USER_MCP_SERVERS,
        "stdio_allowlist": list(settings.user_mcp_stdio_allowlist),
        "connected": bool(status.get("connected")),
        "tool_count": int(status.get("tool_count", 0)),
        "servers": _masked_mcp_view(owner_id, servers, status),
    }


@router.put("/mcp")
async def update_my_mcp(
    payload: UserMcpUpdateRequest,
    user: AuthUser = Depends(require_active_user),
) -> Dict[str, Any]:
    """整体替换本人 MCP 配置；所有条目重新做安全校验。"""
    from backend.modules.multiuser.settings import load_settings

    owner_id = _require_regular(user)
    settings = await load_settings()
    if not settings.allow_user_mcp:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"detail": "管理员已关闭用户自建 MCP", "code": "USER_MCP_DISABLED"},
        )

    existing = {s.id: s for s in await load_user_mcp_servers(owner_id)}
    restored = [
        restore_masked_config(s, existing.get((s.id or "").strip()) or existing.get(s.name.strip()))
        for s in payload.servers
    ]

    try:
        prepared = prepare_server_list(
            restored,
            allowlist=settings.user_mcp_stdio_allowlist,
        )
    except UserMcpError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await save_user_mcp_servers(owner_id, prepared)
    # 断开旧连接并让下次请求重建运行时
    await user_mcp_manager.disconnect(owner_id)
    user_runtime_manager.invalidate(owner_id)

    return {
        "enabled": settings.allow_user_mcp,
        "max_servers": MAX_USER_MCP_SERVERS,
        "stdio_allowlist": list(settings.user_mcp_stdio_allowlist),
        "connected": False,
        "tool_count": 0,
        "servers": _masked_mcp_view(owner_id, prepared),
    }


@router.post("/mcp/test")
async def test_my_mcp(
    payload: UserMcpTestRequest,
    user: AuthUser = Depends(require_active_user),
) -> Dict[str, Any]:
    """测试单个 MCP 服务器连通性；不落库、不回显凭证。"""
    from backend.modules.multiuser.settings import load_settings

    owner_id = _require_regular(user)
    settings = await load_settings()
    if not settings.allow_user_mcp:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"detail": "管理员已关闭用户自建 MCP", "code": "USER_MCP_DISABLED"},
        )

    existing = {s.id: s for s in await load_user_mcp_servers(owner_id)}
    server = restore_masked_config(
        payload.server,
        existing.get((payload.server.id or "").strip())
        or existing.get(payload.server.name.strip()),
    )
    try:
        return await user_mcp_manager.test_server(owner_id, server)
    except UserMcpError as exc:
        # 配置未通过校验：客户端错误，用状态码而非 200 承载失败
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.warning(f"User MCP test failed for {user.username}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="连接失败，请检查配置",
        ) from exc
