"""Provider-specific reasoning / thinking request helpers."""

from __future__ import annotations

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
) -> Tuple[str, ...]:
    """Apply provider-aware reasoning control fields to an OpenAI-compatible request."""
    clear_reasoning_request_fields(request_params)

    if thinking_enabled is None:
        return ()

    effective_provider_id = _normalize_provider_id(provider_id, api_base)

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
