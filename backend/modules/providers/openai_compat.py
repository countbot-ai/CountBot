"""OpenAI chat.completions 兼容性降级。"""

import re
from typing import Any, Dict, List, Optional

from loguru import logger

from .error_messages import extract_error_text
from .thinking_profiles import clear_reasoning_request_fields

# 同一进程内多个 Provider 实例共享：同一上游的兼容性结论只需学习一次
_compatibility_cache: Dict[str, Dict[str, Any]] = {}


def compatibility_cache_key(
    provider_id: Optional[str],
    api_base: Optional[str],
    model: str,
) -> str:
    normalized_provider = (provider_id or "").strip().lower()
    normalized_base = (api_base or "").strip().lower().rstrip("/")
    normalized_model = (model or "").strip().lower()
    return f"{normalized_provider}|{normalized_base}|{normalized_model}"


def remember_compatibility(
    compatibility_key: str,
    compatibility_hints: Dict[str, Any],
) -> None:
    if not compatibility_hints:
        return

    existing = dict(_compatibility_cache.get(compatibility_key, {}))
    existing.update(compatibility_hints)
    _compatibility_cache[compatibility_key] = existing


def apply_cached_compatibility(
    request_params: Dict[str, Any],
    compatibility_key: str,
) -> None:
    profile = _compatibility_cache.get(compatibility_key)
    if not profile:
        return

    applied_changes: List[str] = []

    if (
        profile.get("strip_reasoning_request_fields")
        or profile.get("strip_extra_body_thinking")
    ) and strip_reasoning_config(request_params):
        applied_changes.append("reasoning control params")

    if profile.get(
        "strip_message_reasoning_content"
    ) and strip_message_reasoning_content(request_params):
        applied_changes.append("assistant reasoning_content")

    if profile.get("strip_multimodal_image_content") and strip_multimodal_image_content(
        request_params
    ):
        applied_changes.append("multimodal image content")

    if profile.get("strip_tool_choice") and strip_tool_choice(request_params):
        applied_changes.append("tool_choice")

    if profile.get("simplify_tool_schemas") and simplify_tool_schemas(
        request_params
    ):
        applied_changes.append("advanced tool schema keywords")

    has_explicit_temperature = "temperature" in request_params
    fixed_temperature = profile.get("fixed_temperature")
    if has_explicit_temperature and fixed_temperature is not None:
        current_temperature = request_params.get("temperature")
        if current_temperature != fixed_temperature:
            request_params["temperature"] = fixed_temperature
            applied_changes.append(
                f"temperature {current_temperature} -> {fixed_temperature}"
            )
    else:
        max_temperature = profile.get("max_temperature")
        if has_explicit_temperature and max_temperature is not None:
            raw_temperature = request_params.get("temperature")
            try:
                current_temperature = float(raw_temperature)
            except (TypeError, ValueError):
                current_temperature = None

            if (
                current_temperature is not None
                and current_temperature > float(max_temperature)
            ):
                request_params["temperature"] = float(max_temperature)
                applied_changes.append(
                    f"temperature {current_temperature} -> {float(max_temperature)}"
                )

    if applied_changes:
        logger.info(
            "Applying learned compatibility profile for OpenAI-compatible upstream: "
            + ", ".join(applied_changes)
        )


def strip_reasoning_config(request_params: Dict[str, Any]) -> bool:
    return bool(clear_reasoning_request_fields(request_params))


def strip_message_reasoning_content(request_params: Dict[str, Any]) -> bool:
    messages = request_params.get("messages")
    if not isinstance(messages, list):
        return False

    stripped = False
    sanitized_messages: List[Dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, dict):
            sanitized_messages.append(message)
            continue

        if "reasoning_content" not in message:
            sanitized_messages.append(message)
            continue

        stripped = True
        sanitized = dict(message)
        sanitized.pop("reasoning_content", None)
        sanitized_messages.append(sanitized)

    if stripped:
        request_params["messages"] = sanitized_messages

    return stripped


def strip_tool_choice(request_params: Dict[str, Any]) -> bool:
    if "tool_choice" not in request_params:
        return False

    request_params.pop("tool_choice", None)
    return True


def simplify_tool_schemas(request_params: Dict[str, Any]) -> bool:
    tools = request_params.get("tools")
    if not isinstance(tools, list):
        return False

    changed = False
    simplified_tools: List[Dict[str, Any]] = []
    for tool in tools:
        if not isinstance(tool, dict):
            simplified_tools.append(tool)
            continue

        simplified_tool = dict(tool)
        function = tool.get("function")
        if isinstance(function, dict):
            simplified_function = dict(function)
            original_parameters = function.get("parameters")
            simplified_parameters = simplify_json_schema(original_parameters)
            if simplified_parameters != original_parameters:
                simplified_function["parameters"] = simplified_parameters
                changed = True
            simplified_tool["function"] = simplified_function

        simplified_tools.append(simplified_tool)

    if changed:
        request_params["tools"] = simplified_tools

    return changed


def simplify_json_schema(schema: Any) -> Any:
    if isinstance(schema, list):
        return [simplify_json_schema(item) for item in schema]

    if not isinstance(schema, dict):
        return schema

    unsupported_keywords = {
        "oneOf",
        "anyOf",
        "allOf",
        "not",
        "$ref",
        "$defs",
        "definitions",
        "patternProperties",
        "discriminator",
        "dependentSchemas",
        "dependentRequired",
        "if",
        "then",
        "else",
        "unevaluatedProperties",
        "prefixItems",
        "contains",
        "minContains",
        "maxContains",
        "nullable",
    }

    simplified: Dict[str, Any] = {}
    for key, value in schema.items():
        if key in unsupported_keywords:
            continue
        simplified[key] = simplify_json_schema(value)

    return simplified


def clamp_temperature_to_unit_interval(
    request_params: Dict[str, Any],
) -> Optional[str]:
    raw_temperature = request_params.get("temperature")
    try:
        temperature = float(raw_temperature)
    except (TypeError, ValueError):
        return None

    clamped_temperature = min(max(temperature, 0.0), 1.0)
    if clamped_temperature == temperature:
        return None

    request_params["temperature"] = clamped_temperature
    return f"temperature {temperature} -> {clamped_temperature}"


def is_image_content_unsupported_error(error: Exception) -> bool:
    raw = extract_error_text(error)
    lower = raw.lower()
    return (
        "image_url" in lower
        and any(
            token in lower
            for token in (
                "unknown variant",
                "expected `text`",
                "expected text",
                "failed to deserialize",
                "deserialize the json body",
                "does not support image",
                "image input is not supported",
            )
        )
    )


def strip_multimodal_image_content(request_params: Dict[str, Any]) -> bool:
    messages = request_params.get("messages")
    if not isinstance(messages, list):
        return False

    changed = False
    sanitized_messages: List[Dict[str, Any]] = []

    for message in messages:
        if not isinstance(message, dict):
            sanitized_messages.append(message)
            continue

        content = message.get("content")
        if not isinstance(content, list):
            sanitized_messages.append(message)
            continue

        saw_image = False
        omitted_images = 0
        text_parts: List[str] = []

        for item in content:
            if not isinstance(item, dict):
                continue

            item_type = str(item.get("type", "") or "").strip().lower()
            if item_type == "image_url":
                saw_image = True
                omitted_images += 1
                continue

            if item_type == "text":
                text_value = item.get("text")
                if text_value is not None:
                    text_parts.append(str(text_value))

        if not saw_image:
            sanitized_messages.append(message)
            continue

        # 不支持图片的上游已经明确拒绝过一次；降级时保留占位文本，
        # 让模型知道这里原本有图片，而不是静默丢掉用户内容。
        text_parts.append(
            f"[{omitted_images} image(s) omitted: upstream model does not support image input]"
        )
        updated_message = dict(message)
        updated_message["content"] = "\n".join(part for part in text_parts if part)
        sanitized_messages.append(updated_message)
        changed = True

    if changed:
        request_params["messages"] = sanitized_messages

    return changed


def extract_fixed_temperature(error: Exception) -> Optional[float]:
    raw = extract_error_text(error)
    match = re.search(
        r"only\s+([0-9]+(?:\.[0-9]+)?)\s+is\s+allowed\s+for\s+this\s+model",
        raw,
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    try:
        return float(match.group(1))
    except ValueError:
        return None


def looks_like_tool_mismatch_error(error: Exception) -> bool:
    raw = extract_error_text(error).lower()
    return (
        "tool call and result not match" in raw
        or "tool_calls" in raw and "tool_call_id" in raw
        or "tool use" in raw and "tool result" in raw and "match" in raw
    )


def apply_invalid_params_fallback(
    request_params: Dict[str, Any],
    *,
    error: Optional[Exception] = None,
) -> Optional[Dict[str, Any]]:
    """按顺序剥离上游不接受的可选参数，返回本次降级说明与学习到的 hints。"""
    if error is not None and is_image_content_unsupported_error(error):
        if strip_multimodal_image_content(request_params):
            return {
                "description": "multimodal image content",
                "hints": {"strip_multimodal_image_content": True},
            }

    fallback_steps = (
        (
            "reasoning control params",
            strip_reasoning_config,
            {
                "strip_reasoning_request_fields": True,
                "strip_extra_body_thinking": True,
            },
        ),
        (
            "assistant reasoning_content",
            strip_message_reasoning_content,
            {"strip_message_reasoning_content": True},
        ),
        ("tool_choice", strip_tool_choice, {"strip_tool_choice": True}),
        (
            "advanced tool schema keywords",
            simplify_tool_schemas,
            {"simplify_tool_schemas": True},
        ),
    )

    for description, fallback, hints in fallback_steps:
        if fallback(request_params):
            return {
                "description": description,
                "hints": hints,
            }

    temperature_fallback = clamp_temperature_to_unit_interval(request_params)
    if temperature_fallback:
        return {
            "description": temperature_fallback,
            "hints": {"max_temperature": request_params.get("temperature")},
        }

    return None
