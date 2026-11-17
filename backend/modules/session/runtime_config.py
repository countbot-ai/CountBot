"""解析会话级运行时配置。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional, Union

from loguru import logger

from backend.modules.config.schema import AppConfig, ModelConfig, PersonaConfig
from backend.modules.providers.registry import get_provider_metadata

# 会话级模型绑定仅认可带来源标记的写入，无标记的历史绑定视为失效并回落全局默认
SESSION_MODEL_SOURCE_CHANNEL_COMMAND = "channel_command"
SESSION_MODEL_SOURCE_SESSION_PANEL = "session_panel"
SESSION_MODEL_SOURCES = frozenset(
    {SESSION_MODEL_SOURCE_CHANNEL_COMMAND, SESSION_MODEL_SOURCE_SESSION_PANEL}
)

# 会话对话模式：agent 提供完整能力，chat 不向模型提供任何工具与执行约束
CHAT_MODE_AGENT = "agent"
CHAT_MODE_CHAT = "chat"


def normalize_chat_mode(value: Any) -> str:
    """归一化对话模式，未知值一律回落到 agent。"""
    return CHAT_MODE_CHAT if _normalized_text(value) == CHAT_MODE_CHAT else CHAT_MODE_AGENT


def is_explicit_session_model_config(raw_model_overrides: Dict[str, Any]) -> bool:
    """会话级模型绑定是否来自用户显式设置（带合法来源标记）。"""
    return _normalized_text(raw_model_overrides.get("source")) in SESSION_MODEL_SOURCES


def _normalize_api_mode(value: Any) -> str:
    return "chat_completions"


@dataclass
class SessionRuntimeConfig:
    """单个会话的最终运行时配置。"""

    use_custom_config: bool
    has_custom_model_config: bool
    has_custom_persona_config: bool
    provider_name: str
    model_name: str
    api_mode: str
    temperature: float
    max_tokens: int
    max_iterations: int
    thinking_enabled: bool
    stream_enabled: bool
    reasoning_level: Optional[str]
    chat_mode: str
    api_key: str
    api_base: Optional[str]
    model_config: ModelConfig
    persona_config: PersonaConfig
    model_response: Dict[str, Any]
    persona_response: Dict[str, Any]
    # 会话里显式写入的人设字段（未与全局合并）：普通用户需要它按「自身人设 +
    # 会话改动」叠加，而不是继承管理员全局人设。
    persona_overrides: Optional[Dict[str, Any]] = None
    # 需要固化进执行器覆盖参数的输出模式：None 表示不固化（交给运行时基座解析），
    # 避免普通用户会话保存其他参数时把管理员全局值误写成自己的输出模式。
    stream_override: Optional[bool] = None


def build_session_model_override(
    runtime_config: "SessionRuntimeConfig",
    *,
    force: bool = False,
) -> Optional[Dict[str, Any]]:
    """将会话运行时配置转换为执行器可消费的模型覆盖参数。"""

    if not force and not runtime_config.has_custom_model_config:
        return None

    overrides = {
        "provider": runtime_config.provider_name,
        "model": runtime_config.model_name,
        "api_mode": runtime_config.api_mode,
        "temperature": runtime_config.temperature,
        "max_tokens": runtime_config.max_tokens,
        "max_iterations": runtime_config.max_iterations,
        "thinking_enabled": runtime_config.thinking_enabled,
        "reasoning_level": runtime_config.reasoning_level,
        "supports_image": runtime_config.model_config.supports_image,
        "api_key": runtime_config.api_key,
        "api_base": runtime_config.api_base or "",
    }
    # 只有会话显式设置过、或当前模型条目明确限定输出模式时才下发；
    # 其余情况交给运行时基座，避免覆盖用户自己的模型级设置。
    if runtime_config.stream_override is not None:
        overrides["stream_enabled"] = runtime_config.stream_override
    return overrides


def _parse_session_json(raw: Optional[str], *, session_id: Optional[str], field_name: str) -> Dict[str, Any]:
    if not raw:
        return {}

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(f"会话配置解析失败：{session_id or '<unknown>'} / {field_name}")
        return {}

    if isinstance(data, dict):
        return data

    logger.warning(f"会话配置格式无效：{session_id or '<unknown>'} / {field_name}")
    return {}


def _normalized_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    return value or None


def _merge_persona_overrides(
    base_persona_data: Dict[str, Any],
    raw_persona_overrides: Dict[str, Any],
) -> Dict[str, Any]:
    """对 persona 配置做浅层覆盖，但对 heartbeat 做深合并。"""
    merged = dict(base_persona_data)

    heartbeat_override = raw_persona_overrides.get("heartbeat")
    if isinstance(heartbeat_override, dict):
        heartbeat_base = merged.get("heartbeat") or {}
        if hasattr(heartbeat_base, "model_dump"):
            heartbeat_base = heartbeat_base.model_dump()
        merged["heartbeat"] = {
            **heartbeat_base,
            **{key: value for key, value in heartbeat_override.items() if value is not None},
        }
    elif heartbeat_override is not None:
        merged["heartbeat"] = heartbeat_override

    for key, value in raw_persona_overrides.items():
        if key == "heartbeat":
            continue
        if value is not None:
            merged[key] = value

    return merged


def resolve_session_runtime_config(app_config: AppConfig, session: Optional[Any]) -> SessionRuntimeConfig:
    """解析会话最终配置，优先级为会话配置 > 全局 provider 配置 > provider 默认值。"""

    session_id = getattr(session, "id", None)
    use_custom_config = bool(session and getattr(session, "use_custom_config", False))

    raw_model_overrides = (
        _parse_session_json(
            getattr(session, "session_model_config", None),
            session_id=session_id,
            field_name="session_model_config",
        )
        if use_custom_config
        else {}
    )
    if raw_model_overrides and not is_explicit_session_model_config(raw_model_overrides):
        raw_model_overrides = {}
    raw_persona_overrides = (
        _parse_session_json(
            getattr(session, "session_persona_config", None),
            session_id=session_id,
            field_name="session_persona_config",
        )
        if use_custom_config
        else {}
    )

    effective_model_data = app_config.model.model_dump()
    for key in ("provider", "model"):
        normalized = _normalized_text(raw_model_overrides.get(key))
        if normalized is not None:
            effective_model_data[key] = normalized
    for key in ("temperature", "max_tokens", "max_iterations", "thinking_enabled",
                "stream_enabled", "reasoning_level", "api_mode", "supports_image"):
        if raw_model_overrides.get(key) is not None:
            effective_model_data[key] = (
                _normalize_api_mode(raw_model_overrides[key])
                if key == "api_mode"
                else raw_model_overrides[key]
            )

    # 输出模式优先级：会话显式设置 > 当前模型条目 > 全局默认。
    # 只有前两者需要固化进执行器覆盖参数；仅全局默认时交给运行时基座解析，
    # 否则普通用户的自有模型设置会被会话里保存的其他参数间接覆盖。
    raw_stream_override = raw_model_overrides.get("stream_enabled")
    selected_provider = app_config.providers.get(
        str(effective_model_data.get("provider") or "").strip()
    )
    selected_entry = (
        selected_provider.find_model(str(effective_model_data.get("model") or "").strip())
        if selected_provider is not None
        else None
    )
    entry_stream_override = (
        selected_entry.stream_enabled if selected_entry is not None else None
    )
    if raw_stream_override is None:
        effective_model_data["stream_enabled"] = (
            bool(entry_stream_override)
            if entry_stream_override is not None
            else bool(app_config.model.stream_enabled)
        )
    stream_override = (
        bool(raw_stream_override)
        if raw_stream_override is not None
        else (
            bool(entry_stream_override)
            if entry_stream_override is not None
            else None
        )
    )

    effective_persona_data = _merge_persona_overrides(
        app_config.persona.model_dump(),
        raw_persona_overrides,
    )
    effective_model_config = ModelConfig(**effective_model_data)
    effective_persona_config = PersonaConfig(**effective_persona_data)

    provider_name = effective_model_config.provider
    provider_config = app_config.providers.get(provider_name)
    provider_meta = get_provider_metadata(provider_name)

    # 思考档位优先级：会话覆盖（已在 effective_model_config 里）> 模型条目默认 > 全局设置
    reasoning_level = _normalized_text(effective_model_config.reasoning_level)
    if reasoning_level is None and provider_config is not None:
        model_entry = provider_config.find_model(effective_model_config.model)
        if model_entry is not None:
            reasoning_level = _normalized_text(model_entry.reasoning_level)

    # 对话模式是纯会话级开关：未显式设置时保持完整 Agent 能力
    chat_mode = normalize_chat_mode(raw_model_overrides.get("chat_mode"))

    session_api_key = _normalized_text(raw_model_overrides.get("api_key"))
    session_api_base = _normalized_text(raw_model_overrides.get("api_base"))

    api_key = session_api_key
    if api_key is None:
        api_key = provider_config.api_key if provider_config else ""

    api_base = session_api_base
    if api_base is None:
        api_base = (
            (provider_config.api_base if provider_config else None)
            or (provider_meta.default_api_base if provider_meta else None)
        )

    model_response = app_config.model.model_dump()
    for key, value in raw_model_overrides.items():
        # source 是绑定来源元数据，不属于模型配置，不能投影进响应
        if key in {"api_key", "api_base", "source"}:
            continue
        if isinstance(value, str):
            normalized = _normalized_text(value)
            if normalized is not None:
                model_response[key] = (
                    _normalize_api_mode(normalized)
                    if key == "api_mode"
                    else normalized
                )
        elif value is not None:
            model_response[key] = (
                _normalize_api_mode(value)
                if key == "api_mode"
                else value
            )
    model_response["api_key"] = raw_model_overrides.get("api_key", "") or ""
    model_response["api_base"] = raw_model_overrides.get("api_base", "") or ""
    # 模型条目可能改写了输出模式；响应回显最终生效值，避免面板显示与实际请求不一致
    model_response["stream_enabled"] = effective_model_config.stream_enabled

    persona_response = _merge_persona_overrides(
        app_config.persona.model_dump(),
        raw_persona_overrides,
    )

    return SessionRuntimeConfig(
        use_custom_config=use_custom_config,
        has_custom_model_config=bool(raw_model_overrides),
        has_custom_persona_config=bool(raw_persona_overrides),
        provider_name=provider_name,
        model_name=effective_model_config.model,
        api_mode=effective_model_config.api_mode,
        temperature=effective_model_config.temperature,
        max_tokens=effective_model_config.max_tokens,
        max_iterations=effective_model_config.max_iterations,
        thinking_enabled=effective_model_config.thinking_enabled,
        stream_enabled=effective_model_config.stream_enabled,
        reasoning_level=reasoning_level,
        chat_mode=chat_mode,
        api_key=api_key,
        api_base=api_base,
        model_config=effective_model_config,
        persona_config=effective_persona_config,
        model_response=model_response,
        persona_response=persona_response,
        persona_overrides=raw_persona_overrides,
        stream_override=stream_override,
    )
