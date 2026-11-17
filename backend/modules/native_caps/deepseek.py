"""DeepSeek 原生能力的请求注入规则。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .registry import (
    PROTOCOL_ANTHROPIC,
    PROTOCOL_CHAT,
    PROTOCOL_RESPONSES,
    supports_native_capabilities,
)
from .types import NativeCapabilities, normalize_native_capabilities

WEB_SEARCH_TOOL = "deepseek_web_search"
READ_URL_TOOL = "deepseek_read_url"


def _tool_declaration(name: str, protocol: str) -> Dict[str, Any]:
    if protocol == PROTOCOL_ANTHROPIC:
        return {"type": name, "name": name}
    return {"type": name}


def build_tools(
    capabilities: Any,
    *,
    protocol: str,
    provider_id: Optional[str],
    model: Optional[str],
) -> List[Dict[str, Any]]:
    """按协议生成服务端工具声明；不支持时返回空列表。"""
    if not supports_native_capabilities(provider_id, model):
        return []
    caps = normalize_native_capabilities(capabilities)
    if protocol not in (PROTOCOL_CHAT, PROTOCOL_RESPONSES, PROTOCOL_ANTHROPIC):
        return []

    tools: List[Dict[str, Any]] = []
    if caps.web_search:
        tools.append(_tool_declaration(WEB_SEARCH_TOOL, protocol))
    if caps.read_url:
        tools.append(_tool_declaration(READ_URL_TOOL, protocol))
    return tools


def build_request_overrides(
    capabilities: Any,
    *,
    protocol: str,
    provider_id: Optional[str],
    model: Optional[str],
    thinking_enabled: Optional[bool] = None,
) -> Dict[str, Any]:
    """生成要合并进 request_params 的字段。

    只返回扩展字段，不覆盖原有 model / messages / tools；
    调用方负责把 tools 合并进已有函数工具列表。
    """
    caps: NativeCapabilities = normalize_native_capabilities(capabilities)
    overrides: Dict[str, Any] = {}

    tools = build_tools(
        caps,
        protocol=protocol,
        provider_id=provider_id,
        model=model,
    )
    if tools:
        overrides["tools"] = tools

    if caps.safety_check and supports_native_capabilities(provider_id, model):
        # 安全校验可与联网工具叠加；单独使用时也不会联网。
        overrides["safety_check"] = {"level": "high"}

    # thinking_enabled 目前不影响注入，保留参数便于后续按思考模式切换行为。
    _ = thinking_enabled
    return overrides


def merge_tools(
    existing: Optional[List[Dict[str, Any]]],
    extra: Optional[List[Dict[str, Any]]],
) -> Optional[List[Dict[str, Any]]]:
    """合并函数工具与服务端工具，按 type/name 去重。"""
    if not extra:
        return existing
    merged: List[Dict[str, Any]] = list(existing or [])
    seen = {
        str(item.get("type") or "") + ":" + str(item.get("name") or "")
        for item in merged
        if isinstance(item, dict)
    }
    for item in extra:
        key = str(item.get("type") or "") + ":" + str(item.get("name") or "")
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged
