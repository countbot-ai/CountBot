"""请求预览：展示即将发往模型的完整请求内容。

输出三部分：system_prompt 按区块拆分并标注控制它的注入开关；tools 列出
工具定义与各自体积；messages 为完整消息列表，首条用户消息里追加的动态
上下文单独标出。

只构建数据，不发请求、不落库。
"""

import json
from typing import Any, Dict, List, Optional

from backend.modules.agent.context import ContextBuilder


def _content_text(message: Dict[str, Any]) -> str:
    """取消息的纯文本内容（多模态只取文本块），用于统计体积。"""
    content = message.get("content")
    if isinstance(content, list):
        return " ".join(
            str(item.get("text") or "")
            for item in content
            if isinstance(item, dict)
        )
    return str(content or "")


# system prompt 区块与注入开关的对应关系，用于说明「这块为什么在/不在」。
# 值可以是单个开关名，也可以是一组开关名；后者表示该区块内部有多个段落，
# 分别受不同开关控制（如 identity 的名称恒注入、环境信息随 core_rules）。
_SECTION_SWITCH_MAP = {
    "identity": ("always", "core_rules"),
    "rules": "core_rules",
    "channel_rules": "always",
    "skills_always": "skills_always",
    "skills_summary": "skills_summary",
    "agent_teams": "agent_teams",
}

# 混合区块中各开关负责的部分，用于在预览里给出可理解的说明
_MIXED_SECTION_NOTES = {
    "identity": "名称与性格始终注入；环境信息（运行时/工作目录/路径）随 core_rules 开关",
}


def _section_switch_note(name: str, injection_config: Any) -> Dict[str, Any]:
    """给出某个区块的开关归属说明。

    单个开关直接返回其取值；多个开关时分别列出各自状态，并标注该区块为部分受控，
    避免把混合区块误报成「始终注入」。
    """
    switches = _SECTION_SWITCH_MAP.get(name, "always")
    if isinstance(switches, str):
        switches = (switches,)

    resolved = {}
    for switch in switches:
        if switch == "always":
            resolved["always"] = True
            continue
        enabled = True
        if injection_config is not None:
            enabled = bool(getattr(injection_config, switch, True))
        resolved[switch] = enabled

    if set(resolved) == {"always"}:
        return {
            "controlled_by": None,
            "enabled": True,
            "partial": False,
            "note": "始终注入",
        }

    if "always" in resolved:
        # 混合：部分恒定、部分受控，不能简单回答「是否启用」
        return {
            "controlled_by": [k for k in resolved if k != "always"],
            "enabled": True,
            "partial": True,
            "switch_states": resolved,
            "note": _MIXED_SECTION_NOTES.get(name, "部分内容始终注入，其余受开关控制"),
        }

    return {
        "controlled_by": list(resolved),
        "enabled": all(resolved.values()),
        "partial": False,
        "switch_states": resolved,
        "note": "",
    }


def build_request_preview(
    context_builder: ContextBuilder,
    *,
    message: str,
    history: Optional[List[Dict[str, Any]]] = None,
    session_summary: Optional[str] = None,
    media: Optional[List[str]] = None,
    channel: Optional[str] = None,
    chat_id: Optional[str] = None,
    account_id: Optional[str] = None,
    persona_config=None,
    tool_registry=None,
) -> Dict[str, Any]:
    """构建一次请求的预览数据。

    Args:
        context_builder: 上下文构建器（与真实请求使用同一实例）
        message: 用户本次输入
        history: 历史消息
        session_summary: 会话摘要
        media: 附件路径
        channel: 渠道标识
        chat_id: 会话在渠道侧的 ID
        account_id: 渠道账号
        persona_config: 人设配置
        tool_registry: 工具注册表，用于列出工具定义

    Returns:
        可直接返回给前端的预览字典
    """
    history = history or []

    # 1) system prompt 分块
    try:
        sections = context_builder.build_system_prompt_sections(
            persona_config=persona_config,
            channel=channel,
        )
    except Exception as exc:  # 区块构建失败时要能看到原因，而不是整个预览 500
        sections = []
        sections_error = str(exc)
    else:
        sections_error = None

    injection_config = getattr(context_builder, "injection_config", None)
    section_items = []
    for section in sections:
        content = section["content"]
        note = _section_switch_note(section["name"], injection_config)
        section_items.append(
            {
                "name": section["name"],
                "chars": len(content),
                "content": content,
                **note,
            }
        )

    system_prompt = "\n\n---\n\n".join(section["content"].rstrip() for section in sections)

    # 2) 完整消息列表
    # 归一化为字符串：下游 build_messages 内部有 ``in message`` 之类的字符串运算，
    # 传入 None 会抛 TypeError 使整个预览接口 500。预览是排查工具，不应因调用方
    # 少传一个参数就整体失败。
    message = str(message) if message is not None else ""

    messages = context_builder.build_messages(
        history=history,
        current_message=message,
        session_summary=session_summary,
        media=media,
        channel=channel,
        chat_id=chat_id,
        account_id=account_id,
        persona_config=persona_config,
    )

    first_user_message = ""
    for item in messages:
        if item.get("role") == "user":
            first_user_message = str(item.get("content") or "")
            break

    # 首条用户消息里除用户原文之外的部分，即为动态上下文注入
    dynamic_context = ""
    if first_user_message and first_user_message != (message or ""):
        dynamic_context = first_user_message[len(message or ""):].strip()

    # 3) 工具定义
    tools: List[Dict[str, Any]] = []
    tool_chars_total = 0
    if tool_registry is not None:
        try:
            definitions = tool_registry.get_definitions() or []
        except Exception:
            definitions = []
        for definition in definitions:
            function = (definition or {}).get("function") or {}
            name = function.get("name") or ""
            chars = len(str(function))
            tool_chars_total += chars
            tools.append(
                {
                    "name": name,
                    "chars": chars,
                    "description": str(function.get("description") or "")[:200],
                }
            )

    # 上下文占用按来源分桶：只告诉使用者「占了多少字符」不够，
    # 真正的问题是「压哪里最划算」，这需要把 token 归到具体来源上。
    from backend.modules.agent.history_compactor import (
        estimate_messages_tokens,
        estimate_tokens,
    )

    message_tokens = estimate_messages_tokens(messages)
    system_tokens = estimate_tokens(system_prompt)
    tool_tokens = estimate_tokens(json.dumps(tools, ensure_ascii=False)) if tools else 0
    total_tokens = message_tokens + system_tokens + tool_tokens

    breakdown = [
        {
            "source": "system_prompt",
            "chars": len(system_prompt),
            "est_tokens": system_tokens,
        },
        {
            "source": "system_tool_schemas",
            "chars": tool_chars_total,
            "est_tokens": tool_tokens,
        },
        {
            "source": "messages",
            "chars": sum(len(str(_content_text(m))) for m in messages),
            "est_tokens": message_tokens,
        },
    ]
    for item in breakdown:
        item["share"] = (
            round(item["est_tokens"] / total_tokens, 4) if total_tokens else 0.0
        )

    return {
        "system_prompt": system_prompt,
        "system_prompt_chars": len(system_prompt),
        "sections": section_items,
        "sections_error": sections_error,
        "messages": messages,
        "message_count": len(messages),
        "first_user_message": first_user_message,
        "dynamic_context": dynamic_context,
        "tools": tools,
        "tool_count": len(tools),
        "tool_chars": tool_chars_total,
        "usage": {
            "est_total_tokens": total_tokens,
            "breakdown": breakdown,
        },
        "injection": {
            "core_rules": _flag(injection_config, "core_rules"),
            "external_coding_guidance": _flag(injection_config, "external_coding_guidance"),
            "skills_always": _flag(injection_config, "skills_always"),
            "skills_summary": _flag(injection_config, "skills_summary"),
            "agent_teams": _flag(injection_config, "agent_teams"),
            "dynamic_context": _flag(injection_config, "dynamic_context"),
            "team_reminder": _flag(injection_config, "team_reminder"),
            "auto_memory_summary": _flag(injection_config, "auto_memory_summary"),
            "disabled_tools": list(getattr(injection_config, "disabled_tools", []) or []),
        },
    }


def _flag(injection_config: Any, name: str) -> bool:
    """读取注入开关；未配置时按默认开启处理。"""
    if injection_config is None:
        return True
    return bool(getattr(injection_config, name, True))
