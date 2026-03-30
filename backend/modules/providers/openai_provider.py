"""OpenAI Provider — 使用官方 SDK"""

import asyncio
import json
import re
from typing import Any, AsyncIterator, Dict, List, Optional

from loguru import logger

from .base import LLMProvider, StreamChunk, ToolCall

_TOOL_ARGUMENT_PARSE_ERROR_KEY = "__tool_argument_parse_error__"
_TOOL_ARGUMENT_RAW_KEY = "__tool_argument_raw__"


class OpenAIProvider(LLMProvider):
    """OpenAI Provider 实现（兼容 OpenAI API 格式的所有服务）"""

    _compatibility_cache: Dict[str, Dict[str, Any]] = {}

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        default_model: str = "gpt-4o",
        api_mode: str = "chat_completions",
        timeout: float = 600.0,
        max_retries: int = 3,
        provider_id: Optional[str] = None,
        **kwargs: Any,
    ):
        super().__init__(api_key, api_base, default_model, timeout, max_retries)
        self.provider_id = provider_id
        self.api_mode = "chat_completions"

    async def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """流式聊天补全"""
        try:
            from openai import AsyncOpenAI

            raw_model = model or self.default_model
            model = self._normalize_model_name(raw_model)
            if not model:
                raise ValueError("必须指定模型或设置默认模型")
            if model != raw_model:
                logger.warning(f"模型名已自动规范化: {raw_model} -> {model}")

            logger.info(f"Calling OpenAI: {model}, api_base: {self.api_base}")

            client_kwargs: Dict[str, Any] = {
                "api_key": self.api_key or "not-needed",
                "timeout": self.timeout,
                "max_retries": 0,
            }
            if self.api_base:
                client_kwargs["base_url"] = self.api_base

            client = AsyncOpenAI(**client_kwargs)

            kwargs.pop("api_mode", None)

            async for chunk in self._chat_stream_via_chat_completions(
                client=client,
                messages=messages,
                tools=tools,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs,
            ):
                yield chunk

        except Exception as e:
            error_msg = str(e) or type(e).__name__
            log_summary = self._summarize_error_for_log(e)
            if self._is_expected_upstream_error(e):
                logger.error(f"OpenAI call failed [{type(e).__name__}]: {log_summary}")
            else:
                logger.exception(
                    f"OpenAI call failed [{type(e).__name__}]: {log_summary}"
                )
            friendly_msg = self._format_error_message(error_msg)
            yield StreamChunk(error=friendly_msg)

    async def _chat_stream_via_chat_completions(
        self,
        *,
        client: Any,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        model: str,
        max_tokens: int,
        temperature: float,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        compatibility_key = self._get_compatibility_cache_key(model)
        compatibility_hints: Dict[str, Any] = {}
        compatibility_recorded = False

        request_params: Dict[str, Any] = {
            "model": model,
            "messages": self._sanitize_messages_for_chat_completions(messages),
            "stream": True,
        }

        if temperature and temperature > 0:
            request_params["temperature"] = temperature

        if max_tokens and max_tokens > 0:
            request_params["max_tokens"] = max_tokens

        if tools:
            request_params["tools"] = tools
            request_params["tool_choice"] = "auto"

        request_params.update(kwargs)
        thinking_enabled = kwargs.get("thinking_enabled")
        if self._should_disable_thinking_for_tool_calls(
            model=model,
            tools=tools,
            thinking_enabled=thinking_enabled,
        ):
            logger.info(
                "Disabling thinking for tool-enabled Moonshot/Kimi request "
                "to preserve tool-call argument budget"
            )
            thinking_enabled = False
        self._apply_reasoning_config(request_params, thinking_enabled)
        self._apply_cached_compatibility(request_params, compatibility_key)

        logger.debug(
            "OpenAI params: "
            + json.dumps(
                {k: v for k, v in request_params.items() if k not in ["api_key", "messages"]},
                ensure_ascii=False,
            )
        )

        stream = None
        max_attempts = max(1, self.max_retries)
        attempt = 1
        while attempt <= max_attempts:
            try:
                stream = await client.chat.completions.create(**request_params)
                break
            except Exception as e:
                fixed_temperature = self._extract_fixed_temperature(e)
                current_temperature = request_params.get("temperature")
                if (
                    fixed_temperature is not None
                    and current_temperature != fixed_temperature
                ):
                    compatibility_hints["fixed_temperature"] = fixed_temperature
                    logger.warning(
                        f"OpenAI upstream requires fixed temperature for {model}; "
                        f"retrying with {current_temperature} -> {fixed_temperature}"
                    )
                    request_params["temperature"] = fixed_temperature
                    continue

                if self._is_invalid_params_error(e):
                    fallback_info = self._apply_invalid_params_fallback(
                        request_params
                    )
                    if fallback_info:
                        compatibility_hints.update(fallback_info.get("hints", {}))
                        logger.warning(
                            "OpenAI upstream rejected optional request params; "
                            f"retrying without {fallback_info['description']}"
                        )
                        continue

                error_summary = self._summarize_error_for_log(e)
                if attempt < max_attempts:
                    wait = min(2 ** attempt, 30)
                    logger.warning(
                        f"OpenAI 调用失败 (第{attempt}/{max_attempts}次)，"
                        f"{wait}s 后重试: {error_summary}"
                    )
                    attempt += 1
                    await asyncio.sleep(wait)
                else:
                    logger.error(
                        f"OpenAI 调用最终失败 ({max_attempts}次尝试耗尽): {error_summary}"
                    )
                    raise

        tool_call_buffer: Dict[str, Dict[str, Any]] = {}
        chunk_count = 0
        content_yielded = False
        stream_done = False
        stream_retry = 0
        max_stream_retries = self.max_retries

        while not stream_done and stream_retry <= max_stream_retries:
            try:
                async for chunk in stream:
                    if not compatibility_recorded and compatibility_hints:
                        self._remember_compatibility(
                            compatibility_key,
                            compatibility_hints,
                        )
                        compatibility_recorded = True

                    chunk_count += 1
                    if chunk_count <= 3:
                        logger.debug(f"OpenAI chunk #{chunk_count}: {chunk}")

                    if not chunk.choices:
                        continue

                    choice = chunk.choices[0]
                    delta = choice.delta

                    if hasattr(delta, "content") and delta.content:
                        content_yielded = True
                        yield StreamChunk(content=delta.content)

                    reasoning_delta = self._extract_reasoning_delta(delta)
                    if reasoning_delta:
                        content_yielded = True
                        yield StreamChunk(reasoning_content=reasoning_delta)

                    if hasattr(delta, "tool_calls") and delta.tool_calls:
                        content_yielded = True
                        for tc_delta in delta.tool_calls:
                            tc_id = getattr(tc_delta, "id", None)
                            tc_index = getattr(tc_delta, "index", 0)
                            key = f"index_{tc_index}"

                            if key not in tool_call_buffer:
                                tool_call_buffer[key] = {
                                    "id": tc_id or f"call_{tc_index}",
                                    "name": "",
                                    "arguments": "",
                                }

                            if tc_id:
                                tool_call_buffer[key]["id"] = tc_id

                            if hasattr(tc_delta, "function"):
                                function = tc_delta.function
                                if hasattr(function, "name") and function.name:
                                    tool_call_buffer[key]["name"] = function.name
                                if hasattr(function, "arguments") and function.arguments:
                                    tool_call_buffer[key]["arguments"] += function.arguments

                    if choice.finish_reason:
                        usage_dict = None
                        if hasattr(chunk, "usage") and chunk.usage:
                            usage_dict = {
                                "prompt_tokens": getattr(chunk.usage, "prompt_tokens", 0),
                                "completion_tokens": getattr(chunk.usage, "completion_tokens", 0),
                                "total_tokens": getattr(chunk.usage, "total_tokens", 0),
                            }

                        for tc_data in tool_call_buffer.values():
                            if not tc_data["name"]:
                                continue

                            yield StreamChunk(
                                tool_call=ToolCall(
                                    id=tc_data["id"],
                                    name=tc_data["name"],
                                    arguments=self._parse_json_arguments(tc_data["arguments"]),
                                )
                            )

                        yield StreamChunk(
                            finish_reason=choice.finish_reason,
                            usage=usage_dict,
                        )
                        stream_done = True
                        break

                if not stream_done:
                    stream_done = True
                    yield StreamChunk(finish_reason="stop")

            except Exception as stream_err:
                if not content_yielded and self._is_invalid_params_error(stream_err):
                    fallback_info = self._apply_invalid_params_fallback(
                        request_params
                    )
                    if fallback_info:
                        compatibility_hints.update(fallback_info.get("hints", {}))
                        logger.warning(
                            "OpenAI upstream rejected optional request params during stream setup; "
                            f"retrying without {fallback_info['description']}"
                        )
                        stream = await client.chat.completions.create(**request_params)
                        tool_call_buffer = {}
                        chunk_count = 0
                        continue

                is_timeout = self._is_timeout_exception(stream_err)

                if not content_yielded and is_timeout and stream_retry < max_stream_retries:
                    stream_retry += 1
                    wait = min(2 ** stream_retry, 30)
                    logger.warning(
                        f"OpenAI 流读取超时（第{stream_retry}/{max_stream_retries}次），"
                        f"{wait}s 后重试: {stream_err}"
                    )
                    await asyncio.sleep(wait)
                    stream = await client.chat.completions.create(**request_params)
                    tool_call_buffer = {}
                    chunk_count = 0
                elif content_yielded and is_timeout:
                    logger.warning(
                        f"OpenAI 流式读取超时（已发送 {chunk_count} 个 chunk），"
                        f"优雅截断并结束流: {stream_err}"
                    )
                    yield StreamChunk(finish_reason="length")
                    stream_done = True
                else:
                    raise

    @staticmethod
    def _parse_json_arguments(raw: str) -> Dict[str, Any]:
        args_str = (raw or "").strip()
        if not args_str:
            return {}

        try:
            parsed = json.loads(args_str)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse failed: {e}, raw: {repr(args_str)}")
            return {
                _TOOL_ARGUMENT_PARSE_ERROR_KEY: f"{type(e).__name__}: {e}",
                _TOOL_ARGUMENT_RAW_KEY: args_str,
            }

        if isinstance(parsed, dict):
            return parsed
        return {"value": parsed}

    @staticmethod
    def _is_timeout_exception(error: Exception) -> bool:
        """Detect timeout-like failures even when str(error) is empty."""
        try:
            import httpx

            if isinstance(error, httpx.TimeoutException):
                return True
        except Exception:
            pass

        err_type = type(error).__name__.lower()
        err_text = f"{str(error)} {repr(error)}".lower()
        timeout_hints = (
            "timeout",
            "timed out",
            "readtimeout",
            "connecttimeout",
            "read error",
            "socket",
        )
        return any(hint in err_type or hint in err_text for hint in timeout_hints)

    @staticmethod
    def _coerce_reasoning_text(value: Any) -> str:
        """Normalize provider-specific reasoning payloads into plain text."""
        if value is None:
            return ""

        if isinstance(value, str):
            return value

        if isinstance(value, list):
            parts: List[str] = []
            for item in value:
                normalized = OpenAIProvider._coerce_reasoning_text(item)
                if normalized:
                    parts.append(normalized)
            return "".join(parts)

        if isinstance(value, dict):
            for key in ("text", "content", "reasoning_content", "reasoning", "thinking"):
                normalized = OpenAIProvider._coerce_reasoning_text(value.get(key))
                if normalized:
                    return normalized
            try:
                return json.dumps(value, ensure_ascii=False)
            except TypeError:
                return str(value)

        return str(value)

    @classmethod
    def _extract_reasoning_delta(cls, delta: Any) -> str:
        """Read reasoning tokens from multiple OpenAI-compatible delta shapes."""
        for field_name in ("reasoning_content", "reasoning", "thinking"):
            if hasattr(delta, field_name):
                normalized = cls._coerce_reasoning_text(getattr(delta, field_name))
                if normalized:
                    return normalized

        model_extra = getattr(delta, "model_extra", None)
        if isinstance(model_extra, dict):
            for field_name in ("reasoning_content", "reasoning", "thinking"):
                normalized = cls._coerce_reasoning_text(model_extra.get(field_name))
                if normalized:
                    return normalized

        return ""

    def _apply_reasoning_config(
        self,
        request_params: Dict[str, Any],
        thinking_enabled: Optional[bool],
    ) -> None:
        """对 OpenAI 兼容 provider 注入 thinking 开关。"""
        if thinking_enabled is None:
            request_params.pop("thinking_enabled", None)
            return

        extra_body = request_params.get("extra_body")
        if not isinstance(extra_body, dict):
            extra_body = {}

        extra_body["thinking"] = {
            "type": "enabled" if thinking_enabled else "disabled"
        }
        request_params["extra_body"] = extra_body
        request_params.pop("thinking_enabled", None)

    def _should_disable_thinking_for_tool_calls(
        self,
        *,
        model: str,
        tools: Optional[List[Dict[str, Any]]],
        thinking_enabled: Optional[bool],
    ) -> bool:
        """Moonshot/Kimi tool calls are more reliable without verbose reasoning output."""
        if not tools or thinking_enabled is not True:
            return False

        provider_id = (self.provider_id or "").strip().lower()
        normalized_model = (model or "").strip().lower()
        api_base = (self.api_base or "").strip().lower()
        return (
            provider_id == "moonshot"
            or normalized_model.startswith("kimi-")
            or "moonshot.cn" in api_base
        )

    def _sanitize_messages_for_chat_completions(
        self,
        messages: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Normalize internal messages to OpenAI v1 chat.completions shape."""
        sanitized_messages: List[Dict[str, Any]] = []

        for message in messages:
            role = str(message.get("role", "") or "").strip()
            if role not in {"system", "developer", "user", "assistant", "tool"}:
                continue

            normalized_role = "system" if role == "developer" else role
            sanitized: Dict[str, Any] = {"role": normalized_role}
            if "content" in message:
                sanitized["content"] = message.get("content")

            if normalized_role == "assistant" and message.get("tool_calls"):
                sanitized["tool_calls"] = message.get("tool_calls")

            if normalized_role == "tool" and message.get("tool_call_id"):
                sanitized["tool_call_id"] = message.get("tool_call_id")

            if (
                normalized_role == "assistant"
                and message.get("reasoning_content") is not None
            ):
                sanitized["reasoning_content"] = message.get("reasoning_content")

            # Preserve optional participant naming on roles that may legally carry it.
            if normalized_role in {"system", "user", "assistant"} and message.get("name"):
                sanitized["name"] = message.get("name")

            sanitized_messages.append(sanitized)

        return sanitized_messages


    @staticmethod
    def _normalize_model_name(model: Optional[str]) -> str:
        normalized = str(model or "").strip()
        if not normalized:
            return ""

        match = re.fullmatch(r"gpt[-_\s]?(\d+(?:\.\d+)*)", normalized, flags=re.IGNORECASE)
        if match:
            return f"gpt-{match.group(1)}"

        return normalized

    @staticmethod
    def _extract_error_text(error: Exception) -> str:
        response = getattr(error, "response", None)
        text = getattr(response, "text", None)
        if isinstance(text, str) and text.strip():
            return text
        return str(error) or repr(error)

    @staticmethod
    def _extract_status_code(error: Exception) -> Optional[int]:
        status_code = getattr(error, "status_code", None)
        if isinstance(status_code, int):
            return status_code

        response = getattr(error, "response", None)
        response_status = getattr(response, "status_code", None)
        if isinstance(response_status, int):
            return response_status

        return None

    @classmethod
    def _extract_fixed_temperature(cls, error: Exception) -> Optional[float]:
        raw = cls._extract_error_text(error)
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

    @classmethod
    def _is_expected_upstream_error(cls, error: Exception) -> bool:
        status_code = cls._extract_status_code(error)
        if status_code is not None and status_code >= 400:
            return True

        if cls._is_timeout_exception(error):
            return True

        raw = cls._extract_error_text(error).lower()
        return "<html" in raw or "<!doctype html" in raw

    @classmethod
    def _is_invalid_params_error(cls, error: Exception) -> bool:
        status_code = cls._extract_status_code(error)
        raw = cls._extract_error_text(error).lower()
        return (
            status_code == 400
            or "invalid params" in raw
            or "invalid parameter" in raw
            or "invalid_request_error" in raw
            or "requestparamserror" in raw
        )

    @staticmethod
    def _strip_reasoning_config(request_params: Dict[str, Any]) -> bool:
        extra_body = request_params.get("extra_body")
        if not isinstance(extra_body, dict) or "thinking" not in extra_body:
            request_params.pop("thinking_enabled", None)
            return False

        extra_body = dict(extra_body)
        extra_body.pop("thinking", None)
        if extra_body:
            request_params["extra_body"] = extra_body
        else:
            request_params.pop("extra_body", None)

        request_params.pop("thinking_enabled", None)
        return True

    @staticmethod
    def _strip_message_reasoning_content(request_params: Dict[str, Any]) -> bool:
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

    @staticmethod
    def _strip_tool_choice(request_params: Dict[str, Any]) -> bool:
        if "tool_choice" not in request_params:
            return False

        request_params.pop("tool_choice", None)
        return True

    @classmethod
    def _simplify_tool_schemas(cls, request_params: Dict[str, Any]) -> bool:
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
                simplified_parameters = cls._simplify_json_schema(original_parameters)
                if simplified_parameters != original_parameters:
                    simplified_function["parameters"] = simplified_parameters
                    changed = True
                simplified_tool["function"] = simplified_function

            simplified_tools.append(simplified_tool)

        if changed:
            request_params["tools"] = simplified_tools

        return changed

    @classmethod
    def _simplify_json_schema(cls, schema: Any) -> Any:
        if isinstance(schema, list):
            return [cls._simplify_json_schema(item) for item in schema]

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
            simplified[key] = cls._simplify_json_schema(value)

        return simplified

    @staticmethod
    def _clamp_temperature_to_unit_interval(
        request_params: Dict[str, Any]
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

    def _get_compatibility_cache_key(self, model: str) -> str:
        provider_id = (self.provider_id or "").strip().lower()
        api_base = (self.api_base or "").strip().lower().rstrip("/")
        normalized_model = (model or "").strip().lower()
        return f"{provider_id}|{api_base}|{normalized_model}"

    @classmethod
    def _remember_compatibility(
        cls,
        compatibility_key: str,
        compatibility_hints: Dict[str, Any],
    ) -> None:
        if not compatibility_hints:
            return

        existing = dict(cls._compatibility_cache.get(compatibility_key, {}))
        existing.update(compatibility_hints)
        cls._compatibility_cache[compatibility_key] = existing

    @classmethod
    def _apply_cached_compatibility(
        cls,
        request_params: Dict[str, Any],
        compatibility_key: str,
    ) -> None:
        profile = cls._compatibility_cache.get(compatibility_key)
        if not profile:
            return

        applied_changes: List[str] = []

        if profile.get("strip_extra_body_thinking") and cls._strip_reasoning_config(
            request_params
        ):
            applied_changes.append("extra_body.thinking")

        if profile.get(
            "strip_message_reasoning_content"
        ) and cls._strip_message_reasoning_content(request_params):
            applied_changes.append("assistant reasoning_content")

        if profile.get("strip_tool_choice") and cls._strip_tool_choice(request_params):
            applied_changes.append("tool_choice")

        if profile.get("simplify_tool_schemas") and cls._simplify_tool_schemas(
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

    @classmethod
    def _apply_invalid_params_fallback(
        cls,
        request_params: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        fallback_steps = (
            (
                "extra_body.thinking",
                cls._strip_reasoning_config,
                {"strip_extra_body_thinking": True},
            ),
            (
                "assistant reasoning_content",
                cls._strip_message_reasoning_content,
                {"strip_message_reasoning_content": True},
            ),
            ("tool_choice", cls._strip_tool_choice, {"strip_tool_choice": True}),
            (
                "advanced tool schema keywords",
                cls._simplify_tool_schemas,
                {"simplify_tool_schemas": True},
            ),
        )

        for description, fallback, hints in fallback_steps:
            if fallback(request_params):
                return {
                    "description": description,
                    "hints": hints,
                }

        temperature_fallback = cls._clamp_temperature_to_unit_interval(request_params)
        if temperature_fallback:
            return {
                "description": temperature_fallback,
                "hints": {"max_temperature": request_params.get("temperature")},
            }

        return None

    @classmethod
    def _summarize_error_for_log(cls, error: Exception) -> str:
        status_code = cls._extract_status_code(error)
        raw = cls._extract_error_text(error)
        compact = " ".join((raw or "").split())
        lower = compact.lower()

        if "<html" in lower or "<!doctype html" in lower:
            title_match = re.search(r"<title>(.*?)</title>", raw, flags=re.IGNORECASE | re.DOTALL)
            ray_match = re.search(r"Cloudflare Ray ID:\s*([A-Za-z0-9-]+)", raw, flags=re.IGNORECASE)
            title = title_match.group(1).strip() if title_match else "HTML error page"
            parts = []
            if status_code is not None:
                parts.append(f"status={status_code}")
            parts.append(title)
            if ray_match:
                parts.append(f"ray_id={ray_match.group(1)}")
            return ", ".join(parts)

        if status_code is not None:
            compact = f"status={status_code}, {compact}"

        return compact[:300]

    @staticmethod
    def _format_error_message(raw: str) -> str:
        """将 OpenAI 原始错误转换为用户友好提示"""
        lower = raw.lower()

        if any(k in lower for k in ("429", "余额不足", "quota", "rate limit", "insufficient_quota", "insufficient balance", "资源包", "balance")):
            if "余额" in raw or "资源包" in raw or "充值" in raw or "balance" in lower:
                return "API 账户余额不足，请前往服务商控制台充值后重试。"
            return "请求过于频繁或 API 配额已用尽，请稍后重试或检查账户额度。"

        if any(k in lower for k in ("401", "unauthorized", "invalid.*api.*key", "authentication", "token is unusable", "invalid token", "api key")):
            return "API 密钥无效或已过期，请在设置中检查并更新密钥。"

        if any(k in lower for k in ("404", "model not found", "model_not_found", "does not exist")):
            return "所选模型不可用，请在设置中确认模型名称是否正确。"

        if any(k in lower for k in ("context length", "max.*token", "too long", "context_length_exceeded")):
            return "对话上下文过长，请尝试新建会话或清除历史消息。"

        if any(k in lower for k in ("500", "502", "503", "504", "internal server error", "service unavailable")):
            return "AI 服务暂时不可用，请稍后重试。"

        if any(k in lower for k in ("timeout", "connection", "network", "ssl", "timed out")):
            return "网络连接异常，请检查网络设置后重试。"

        return f"AI 调用出错: {raw[:200]}"

    def get_default_model(self) -> str:
        """获取默认模型"""
        return self.default_model or "gpt-4o"
