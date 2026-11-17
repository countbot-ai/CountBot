"""运行期 provider 与模型参数解析。"""

from dataclasses import dataclass
from typing import Any, Dict, Optional

from loguru import logger


@dataclass
class AgentRuntimeBases:
    """AgentLoop 的基线运行配置（未应用 model_override 前）。"""

    provider: Any
    model: Optional[str]
    temperature: float
    max_tokens: int
    max_iterations: int
    thinking_enabled: bool
    stream_enabled: bool
    reasoning_level: Optional[str]
    max_retries: int


def resolve_execution_runtime(
    bases: AgentRuntimeBases,
    model_override: Optional[Dict[str, Any]] = None,
) -> tuple[Any, Optional[str], float, int, int, bool, bool, Optional[str]]:
    """解析当前消息执行应使用的 provider 和模型参数。"""
    base_provider = bases.provider
    base_model = bases.model
    base_temperature = bases.temperature
    base_max_tokens = bases.max_tokens
    base_max_iterations = bases.max_iterations
    base_thinking_enabled = bases.thinking_enabled
    base_stream_enabled = bases.stream_enabled
    base_reasoning_level = bases.reasoning_level
    base_api_mode = getattr(base_provider, "api_mode", "chat_completions")

    if not model_override:
        return (
            base_provider,
            base_model,
            base_temperature,
            base_max_tokens,
            base_max_iterations,
            base_thinking_enabled,
            base_stream_enabled,
            base_reasoning_level,
        )

    candidate_provider = base_provider
    candidate_model = model_override.get("model", base_model)
    candidate_temperature = model_override.get("temperature", base_temperature)
    candidate_max_tokens = model_override.get("max_tokens", base_max_tokens)
    candidate_max_iterations = model_override.get(
        "max_iterations",
        base_max_iterations,
    )
    candidate_api_mode = model_override.get("api_mode", base_api_mode)
    candidate_thinking_enabled = model_override.get(
        "thinking_enabled",
        base_thinking_enabled,
    )
    candidate_stream_enabled = model_override.get("stream_enabled")
    if candidate_stream_enabled is None:
        candidate_stream_enabled = base_stream_enabled
    candidate_reasoning_level = model_override.get(
        "reasoning_level",
        base_reasoning_level,
    )

    override_provider = model_override.get("provider")
    override_api_key = model_override.get("api_key") or None
    override_api_base = model_override.get("api_base") or None
    # 调用方已按身份解析好 provider 实例（如普通用户的自有模型），直接使用
    override_provider_instance = model_override.get("provider_instance")

    if override_provider_instance is not None:
        candidate_provider = override_provider_instance
    elif override_provider or override_api_key or override_api_base:
        try:
            from backend.modules.providers import create_provider
            from backend.modules.config.loader import config_loader
            from backend.modules.providers.runtime import (
                build_provider_unavailable_message,
                get_provider_runtime_state,
            )

            provider_id = override_provider or config_loader.config.model.provider
            runtime_state = get_provider_runtime_state(
                config_loader.config,
                provider_id,
                api_key_override=override_api_key,
                api_base_override=override_api_base,
            )
            if not runtime_state.selectable:
                raise ValueError(
                    build_provider_unavailable_message(
                        provider_id,
                        runtime_state.reason,
                    )
                )

            candidate_provider = create_provider(
                api_key=runtime_state.api_key or None,
                api_keys=runtime_state.api_keys or None,
                api_base=runtime_state.api_base,
                default_model=candidate_model,
                api_mode=candidate_api_mode,
                timeout=getattr(base_provider, "timeout", 120.0),
                max_retries=getattr(
                    base_provider, "max_retries", bases.max_retries
                ),
                provider_id=provider_id,
                api_type=runtime_state.api_type,
                stream_enabled=candidate_stream_enabled,
            )
        except Exception as exc:
            logger.warning(
                "Failed to create runtime provider override, falling back to base runtime config: "
                f"{exc}"
            )
            return (
                base_provider,
                base_model,
                base_temperature,
                base_max_tokens,
                base_max_iterations,
                base_thinking_enabled,
                base_stream_enabled,
                base_reasoning_level,
            )

    return (
        candidate_provider,
        candidate_model,
        candidate_temperature,
        candidate_max_tokens,
        candidate_max_iterations,
        candidate_thinking_enabled,
        candidate_stream_enabled,
        candidate_reasoning_level,
    )
