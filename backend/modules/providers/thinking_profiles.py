"""Provider-specific reasoning / thinking request helpers."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from .registry import find_provider_by_api_base

_EXTRA_BODY_REASONING_KEYS = ("thinking", "enable_thinking", "reasoning")
_TOP_LEVEL_REASONING_KEYS = (
    "thinking",
    "reasoning",
    "reasoning_effort",
    "include_reasoning",
    "reasoning_format",
)

# ======================================================================
# 思考档位（reasoning level）
#
# 档位是「模型能力」，按模型名前缀给出该模型支持的档位集合（从低到高）。
# 前端在模型编辑里勾选、在聊天窗口选择；后端负责把档位翻成各家请求字段。
# ======================================================================

# 家族级兜底：变体名（-sol / -terra / -fast 等）不在上面逐条列出时按家族给默认档位。
# 内置数据只是默认建议，用户可在模型条目里自行增删档位（见 ModelEntry.reasoning_levels）。
_MODEL_FAMILY_REASONING_LEVELS: Dict[str, Tuple[str, ...]] = {
    "gpt-6.1": ("low", "medium", "high", "xhigh", "max"),
    "gpt-6": ("low", "medium", "high", "xhigh", "max", "ultra"),
    "gpt-5.6": ("low", "medium", "high", "xhigh", "max", "ultra"),
    "gpt-5.5": ("low", "medium", "high", "xhigh"),
    "gemini-4": ("low", "medium", "high", "xhigh", "max"),
    "gemini-3": ("low", "medium", "high", "xhigh", "max"),
    "grok-4": ("low", "medium", "high", "xhigh"),
    "claude-opus": ("low", "medium", "high", "xhigh", "max"),
    "claude-sonnet": ("low", "medium", "high", "xhigh", "max"),
    "glm-5": ("low", "medium", "high", "xhigh", "max"),
    "deepseek-v4": ("low", "high", "max"),
    "qwen3": ("none", "low", "medium", "high", "xhigh", "max"),
    "minimax-m3": ("low", "medium", "high", "xhigh", "max"),
}

# 关闭档位：语义等价于「不开思考」，各协议下映射为 thinking disabled / effort none
REASONING_LEVEL_OFF = "none"

# 常用档位全集：仅用于前端「自定义档位」的填写参考，不构成任何限制
KNOWN_REASONING_LEVELS: Tuple[str, ...] = (
    "none",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
    "ultra",
)

# 自定义档位的语法约束：允许用户填内置表之外的值（如 "high2"、"5"），
# 但必须短、无空白、无特殊符号，避免把脏数据拼进请求体。
_REASONING_LEVEL_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,23}$")

_MODEL_REASONING_LEVELS: Dict[str, Tuple[str, ...]] = {
    "claude-fable-5.1": ("low", "medium", "high", "xhigh", "max"),
    "claude-fable-5": ("low", "medium", "high", "xhigh", "max"),
    "claude-mythos-5": ("low", "medium", "high", "xhigh", "max"),
    "claude-opus-4-6": ("low", "medium", "high", "max"),
    "claude-opus-4-7": ("low", "medium", "high", "xhigh", "max"),
    "claude-opus-4-8": ("low", "medium", "high", "xhigh", "max"),
    "claude-opus-5": ("low", "medium", "high", "xhigh", "max"),
    "claude-sonnet-4-6": ("low", "medium", "high", "max"),
    "claude-sonnet-5": ("low", "medium", "high", "xhigh", "max"),
    "gpt-5.5": ("low", "medium", "high", "xhigh"),
    "gpt-5.6-luna": ("low", "medium", "high", "xhigh", "max"),
    "gpt-5.6": ("low", "medium", "high", "xhigh", "max", "ultra"),
    "gpt-6-luna": ("low", "medium", "high", "xhigh", "max"),
    "gpt-6.1-sol": ("low", "medium", "high", "xhigh", "max"),
    "gpt-6": ("low", "medium", "high", "xhigh", "max", "ultra"),
    "gpt-daybreak": ("low", "medium", "high", "xhigh", "max", "ultra"),
    "codex-auto-review": ("low", "medium", "high", "xhigh", "max"),
    "gemini-3.8": ("low", "medium", "high", "xhigh", "max"),
    "gemini-3.7": ("low", "medium", "high", "xhigh", "max"),
    "gemini-3": ("low", "medium", "high", "max"),
    "grok-4.5": ("low", "medium", "high"),
    "grok-4.6": ("low", "medium", "high", "xhigh"),
    "grok-4.7": ("low", "medium", "high", "xhigh"),
    "deepseek-v4": ("low", "high", "max"),
    "glm-5.2": ("low", "medium", "high", "xhigh", "max"),
    "glm-5.3": ("low", "high", "max"),
    "kimi-k3": ("low", "high", "max"),
    "minimax-m3.1": ("low", "medium", "high", "xhigh", "max"),
    "minimax-m3": ("low", "medium", "high", "xhigh", "max"),
    "minimax-h3": ("low", "high", "max"),
    "qwen3.8": ("none", "low", "medium", "high", "xhigh", "max"),
    "qwen3.7": ("none", "low", "medium", "high", "xhigh", "max"),
    "qwen3": ("none", "low", "medium", "high", "xhigh", "max"),
}

# 用 thinking.type 开关思考的国产厂商：档位在此基础上再补 reasoning_effort
_THINKING_TYPE_PROVIDERS = {
    "deepseek",
    "zhipu",
    "moonshot",
    "minimax",
    "qwen",
    "doubao",
    "hunyuan",
    "ernie",
    "yi",
    "baichuan",
    "siliconflow",
}

_OFF_LEVEL_ALIASES = {"", "none", "off", "disabled", "false", "0", "关闭"}


def normalize_reasoning_level(level: Optional[str]) -> Optional[str]:
    """归一化档位文本（小写去空白）；空值返回 None。"""
    normalized = str(level or "").strip().lower()
    return normalized or None


def is_reasoning_off(level: Optional[str]) -> bool:
    """档位是否表示「不开思考」。"""
    normalized = normalize_reasoning_level(level)
    return normalized is None or normalized in _OFF_LEVEL_ALIASES


def resolve_model_reasoning_levels(model: Optional[str]) -> List[str]:
    """按模型名前缀返回内置建议档位（最长前缀优先），未收录返回空列表。

    这只是「默认建议」：用户可以在模型条目里自己增删档位，请求侧不依赖本表。
    """
    normalized_model = _normalized_model_name(model)
    if not normalized_model:
        return []

    for table in (_MODEL_REASONING_LEVELS, _MODEL_FAMILY_REASONING_LEVELS):
        best_prefix = ""
        for prefix in table:
            if normalized_model.startswith(prefix) and len(prefix) > len(best_prefix):
                best_prefix = prefix
        if best_prefix:
            return list(table[best_prefix])
    return []


def is_dispatchable_reasoning_level(level: Optional[str]) -> bool:
    """档位是否可直接下发到上游（含用户自定义档位，不限于内置表）。"""
    normalized = normalize_reasoning_level(level)
    if normalized is None:
        return False
    return bool(_REASONING_LEVEL_PATTERN.match(normalized))


def resolve_supported_reasoning_level(
    level: Optional[str],
    *,
    model: Optional[str],
) -> Optional[str]:
    """把请求档位收敛成可下发值；非法档位返回 None（回落 thinking_enabled 行为）。

    注意：这里**不**要求档位命中内置表——内置表只是默认建议，用户自定义的
    模型与档位必须照样能下发，否则会把自定义模型的口子堵死。
    """
    normalized = normalize_reasoning_level(level)
    if normalized is None:
        return None
    if _REASONING_LEVEL_PATTERN.match(normalized):
        return normalized
    if normalized in _OFF_LEVEL_ALIASES:
        return REASONING_LEVEL_OFF
    return None


def _apply_reasoning_level_fields(
    request_params: Dict[str, Any],
    *,
    provider_id: str,
    level: str,
) -> Tuple[str, ...]:
    """把档位翻成 OpenAI 兼容 chat.completions 的请求字段。

    - reasoning_effort：档位原样下发（none 表示关闭），主流中转/官方都认这个字段；
    - thinking.type：国产厂商（GLM/DeepSeek/Kimi 等）习惯的开关字段，额外补上。
    """
    applied: List[str] = []
    request_params["reasoning_effort"] = level
    applied.append("reasoning_effort")

    if provider_id in _THINKING_TYPE_PROVIDERS:
        fields = {"thinking": {"type": "disabled" if is_reasoning_off(level) else "enabled"}}
        applied.extend(_set_extra_body_fields(request_params, fields))

    return tuple(applied)


def _normalize_provider_id(
    provider_id: Optional[str],
    api_base: Optional[str],
) -> str:
    normalized = str(provider_id or "").strip().lower()
    if normalized and normalized not in {"custom_openai", "custom_anthropic"}:
        return normalized

    guessed = find_provider_by_api_base(api_base or "")
    if guessed:
        return guessed.id

    return normalized


def _normalized_model_name(model: Optional[str]) -> str:
    return str(model or "").strip().lower()


def _ensure_extra_body(request_params: Dict[str, Any]) -> Dict[str, Any]:
    extra_body = request_params.get("extra_body")
    if isinstance(extra_body, dict):
        return dict(extra_body)
    return {}


def clear_reasoning_request_fields(request_params: Dict[str, Any]) -> List[str]:
    """Remove all known provider-specific reasoning control fields."""
    removed: List[str] = []

    for key in _TOP_LEVEL_REASONING_KEYS:
        if key in request_params:
            request_params.pop(key, None)
            removed.append(key)

    extra_body = request_params.get("extra_body")
    if isinstance(extra_body, dict):
        next_extra_body = dict(extra_body)
        for key in _EXTRA_BODY_REASONING_KEYS:
            if key in next_extra_body:
                next_extra_body.pop(key, None)
                removed.append(f"extra_body.{key}")

        if next_extra_body:
            request_params["extra_body"] = next_extra_body
        else:
            request_params.pop("extra_body", None)

    request_params.pop("thinking_enabled", None)
    return removed


def _set_extra_body_fields(
    request_params: Dict[str, Any],
    fields: Dict[str, Any],
) -> Tuple[str, ...]:
    extra_body = _ensure_extra_body(request_params)
    extra_body.update(fields)
    request_params["extra_body"] = extra_body
    return tuple(f"extra_body.{key}" for key in fields.keys())


def _resolve_openai_reasoning_effort(
    model: Optional[str],
    thinking_enabled: bool,
) -> Optional[str]:
    """Map GPT-5 family reasoning control to the chat.completions field."""
    normalized_model = _normalized_model_name(model)
    if "gpt-5" not in normalized_model:
        return None

    if thinking_enabled:
        if "pro" in normalized_model:
            return "high"
        return "medium"

    # Official docs show newer GPT-5 families accepting `none`.
    if any(prefix in normalized_model for prefix in ("gpt-5.1", "gpt-5.2", "gpt-5.4")):
        return "none"

    # Older / codex-style GPT-5 variants do not consistently support `none`.
    if "codex" in normalized_model:
        return "low"

    return "minimal"


def apply_reasoning_request_fields(
    request_params: Dict[str, Any],
    *,
    provider_id: Optional[str],
    model: Optional[str],
    api_base: Optional[str],
    thinking_enabled: Optional[bool],
    reasoning_level: Optional[str] = None,
) -> Tuple[str, ...]:
    """Apply provider-aware reasoning control fields to an OpenAI-compatible request.

    显式档位（reasoning_level）优先：命中模型档位表时按档位下发；否则回落
    原来的 thinking_enabled 行为，存量配置表现不变。
    """
    clear_reasoning_request_fields(request_params)

    effective_provider_id = _normalize_provider_id(provider_id, api_base)

    supported_level = resolve_supported_reasoning_level(reasoning_level, model=model)
    if supported_level is not None:
        return _apply_reasoning_level_fields(
            request_params,
            provider_id=effective_provider_id,
            level=supported_level,
        )

    if thinking_enabled is None:
        return ()

    if effective_provider_id in {"deepseek", "zhipu", "moonshot"}:
        return _set_extra_body_fields(
            request_params,
            {
                "thinking": {
                    "type": "enabled" if thinking_enabled else "disabled",
                }
            },
        )

    if effective_provider_id == "qwen":
        return _set_extra_body_fields(
            request_params,
            {"enable_thinking": bool(thinking_enabled)},
        )

    if effective_provider_id == "openrouter":
        reasoning_payload: Dict[str, Any] = {
            "exclude": not thinking_enabled,
        }
        reasoning_payload["effort"] = "medium" if thinking_enabled else "none"
        return _set_extra_body_fields(
            request_params,
            {"reasoning": reasoning_payload},
        )

    if effective_provider_id == "openai":
        reasoning_effort = _resolve_openai_reasoning_effort(
            model=model,
            thinking_enabled=bool(thinking_enabled),
        )
        if reasoning_effort:
            request_params["reasoning_effort"] = reasoning_effort
            return ("reasoning_effort",)
        return ()

    if effective_provider_id == "groq":
        request_params["include_reasoning"] = bool(thinking_enabled)
        return ("include_reasoning",)

    return ()
