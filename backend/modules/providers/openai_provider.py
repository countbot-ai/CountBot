"""OpenAI Provider — 使用官方 SDK"""

import asyncio
import json
import re
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

from loguru import logger

from . import openai_compat
from .base import (
    LLMProvider,
    StreamChunk,
    ToolCall,
    is_retryable_error,
    retry_backoff_seconds,
    read_usage_detail_int,
    has_visible_text,
)
from .error_messages import (
    format_openai_error,
    is_expected_upstream_error,
    is_invalid_params_error,
    is_timeout_exception,
    parse_json_arguments,
    summarize_error_for_log,
)
from .thinking_profiles import (
    apply_reasoning_request_fields,
    is_reasoning_off,
    normalize_reasoning_level,
)
from backend.modules.native_caps import (
    build_provider_overrides,
    resolve_native_capabilities,
)
from backend.modules.native_caps import events as native_events
from backend.modules.native_caps.deepseek import merge_tools
from backend.modules.native_caps.registry import PROTOCOL_CHAT


class OpenAIProvider(LLMProvider):
    """OpenAI Provider 实现（兼容 OpenAI API 格式的所有服务）"""

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
        self.native_capabilities = kwargs.get("native_capabilities")

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
            log_summary = summarize_error_for_log(e)
            if is_expected_upstream_error(e):
                logger.error(f"OpenAI call failed [{type(e).__name__}]: {log_summary}")
            else:
                logger.exception(
                    f"OpenAI call failed [{type(e).__name__}]: {log_summary}"
                )
            friendly_msg = format_openai_error(error_msg)
            yield StreamChunk(error=friendly_msg, raw_error=error_msg)

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
        compatibility_key = openai_compat.compatibility_cache_key(
            self.provider_id, self.api_base, model
        )
        compatibility_hints: Dict[str, Any] = {}
        compatibility_recorded = False
        request_trace_id = str(kwargs.pop("request_trace_id", "")).strip() or uuid.uuid4().hex[:8]
        # 会话/全局模型配置可切换上游流式与非流式；两条路径最终都走同一套
        # StreamChunk 协议，前端 SSE 通道无需感知差异
        stream_enabled = bool(kwargs.pop("stream_enabled", self.stream_enabled))
        sanitized_messages = self._sanitize_messages_for_chat_completions(messages)

        request_params: Dict[str, Any] = {
            "model": model,
            "messages": sanitized_messages,
            "stream": stream_enabled,
        }

        if temperature and temperature > 0:
            request_params["temperature"] = temperature

        if max_tokens and max_tokens > 0:
            request_params["max_tokens"] = max_tokens

        if tools:
            request_params["tools"] = tools
            request_params["tool_choice"] = "auto"

        native_caps = resolve_native_capabilities(
            self.provider_id, model, self.native_capabilities
        )
        native_overrides = build_provider_overrides(
            provider_id=self.provider_id,
            model=model,
            protocol=PROTOCOL_CHAT,
            capabilities=native_caps,
            thinking_enabled=kwargs.get("thinking_enabled"),
        )
        native_tools = native_overrides.get("tools") or []
        if native_tools:
            request_params["tools"] = merge_tools(
                request_params.get("tools"), native_tools
            )
            request_params["tool_choice"] = "auto"
        if native_overrides.get("safety_check"):
            # OpenAI SDK 只接受已知顶层参数，DeepSeek 扩展字段需走 extra_body
            extra_body = dict(request_params.get("extra_body") or {})
            extra_body["safety_check"] = native_overrides["safety_check"]
            request_params["extra_body"] = extra_body

        reasoning_level = kwargs.pop("reasoning_level", None)
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
        self._apply_reasoning_config(request_params, thinking_enabled, reasoning_level)
        openai_compat.apply_cached_compatibility(request_params, compatibility_key)

        logger.debug(
            f"OpenAI 请求参数 [trace={request_trace_id}]: "
            + json.dumps(
                {k: v for k, v in request_params.items() if k not in ["api_key", "messages"]},
                ensure_ascii=False,
            )
        )
        logger.debug(
            f"发往上游的工具消息序列 [trace={request_trace_id}]: "
            + self._summarize_tool_message_sequence(sanitized_messages)
        )
        logger.debug(
            f"发往上游的消息内容块 [trace={request_trace_id}]: "
            + self._summarize_content_part_types(sanitized_messages)
        )

        stream = None
        max_attempts = max(1, self.max_retries)
        attempt = 1
        while attempt <= max_attempts:
            try:
                stream = await client.chat.completions.create(**request_params)
                break
            except Exception as e:
                fixed_temperature = openai_compat.extract_fixed_temperature(e)
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

                if is_invalid_params_error(e):
                    fallback_info = openai_compat.apply_invalid_params_fallback(
                        request_params,
                        error=e,
                    )
                    if fallback_info:
                        compatibility_hints.update(fallback_info.get("hints", {}))
                        logger.warning(
                            f"OpenAI upstream rejected optional request params [trace={request_trace_id}]; "
                            f"retrying without {fallback_info['description']}"
                        )
                        continue

                error_summary = summarize_error_for_log(e)
                if openai_compat.looks_like_tool_mismatch_error(e):
                    logger.error(
                        "检测到上游工具调用不匹配错误: "
                        f"trace={request_trace_id}, model={model}, sequence="
                        f"{self._summarize_tool_message_sequence(sanitized_messages)}, error={error_summary}"
                    )

                if not is_retryable_error(e):
                    logger.warning(
                        f"OpenAI 不可重试错误 [trace={request_trace_id}]，直接上抛: {error_summary}"
                    )
                    raise

                if attempt < max_attempts:
                    wait = retry_backoff_seconds(attempt, e)
                    logger.warning(
                        f"OpenAI 调用失败 [trace={request_trace_id}] (第{attempt}/{max_attempts}次)，"
                        f"{wait:.1f}s 后重试: {error_summary}"
                    )
                    attempt += 1
                    await asyncio.sleep(wait)
                else:
                    logger.error(
                        f"OpenAI 调用最终失败 [trace={request_trace_id}] ({max_attempts}次尝试耗尽): "
                        f"{error_summary}"
                    )
                    raise

        if not stream_enabled:
            if compatibility_hints and not compatibility_recorded:
                openai_compat.remember_compatibility(compatibility_key, compatibility_hints)
            for converted in self._convert_completion_to_chunks(stream):
                yield converted
            return

        tool_call_buffer: Dict[str, Dict[str, Any]] = {}
        native_server_tool_calls: List[Dict[str, Any]] = []
        chunk_count = 0
        content_yielded = False
        stream_done = False
        stream_retry = 0
        max_stream_retries = self.max_retries

        while not stream_done and stream_retry <= max_stream_retries:
            try:
                async for chunk in stream:
                    if not compatibility_recorded and compatibility_hints:
                        openai_compat.remember_compatibility(
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
                        # 上游偶尔只回零宽字符占位，照抄会让前端渲染出空的思考块
                        if has_visible_text(reasoning_delta):
                            yield StreamChunk(reasoning_content=reasoning_delta)

                    delta_events = native_events.openai_message_events(
                        delta, include_server_tool_calls=False
                    )
                    if delta_events:
                        yield StreamChunk(native_events=delta_events)
                    choice_events = native_events.openai_server_tool_event(
                        getattr(choice, "server_tool_event", None)
                    )
                    if choice_events:
                        yield StreamChunk(native_events=choice_events)
                    raw_tool_calls = getattr(delta, "server_tool_calls", None)
                    if raw_tool_calls:
                        latest = [
                            call.model_dump()
                            if hasattr(call, "model_dump")
                            else dict(call)
                            if isinstance(call, dict)
                            else {}
                            for call in raw_tool_calls
                        ]
                        latest = [item for item in latest if item]
                        if latest:
                            native_server_tool_calls = latest

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
                            usage_dict = self._extract_chat_usage(chunk.usage)

                        for tc_data in tool_call_buffer.values():
                            if not tc_data["name"]:
                                continue

                            yield StreamChunk(
                                tool_call=ToolCall(
                                    id=tc_data["id"],
                                    name=tc_data["name"],
                                    arguments=parse_json_arguments(tc_data["arguments"]),
                                )
                            )

                        if native_server_tool_calls:
                            yield StreamChunk(
                                native_events=[
                                    {
                                        "kind": "history_blocks",
                                        "protocol": PROTOCOL_CHAT,
                                        "server_tool_calls": native_server_tool_calls,
                                    }
                                ]
                            )
                        if choice.finish_reason == "content_filter":
                            yield StreamChunk(
                                native_events=[
                                    {
                                        "kind": "refusal",
                                        "message": "内容未通过安全审核",
                                    }
                                ]
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
                if not content_yielded and is_invalid_params_error(stream_err):
                    fallback_info = openai_compat.apply_invalid_params_fallback(
                        request_params,
                        error=stream_err,
                    )
                    if fallback_info:
                        compatibility_hints.update(fallback_info.get("hints", {}))
                        logger.warning(
                            f"OpenAI upstream rejected optional request params during stream setup [trace={request_trace_id}]; "
                            f"retrying without {fallback_info['description']}"
                        )
                        stream = await client.chat.completions.create(**request_params)
                        tool_call_buffer = {}
                        chunk_count = 0
                        continue

                is_timeout = is_timeout_exception(stream_err)

                if (
                    not content_yielded
                    and is_retryable_error(stream_err)
                    and stream_retry < max_stream_retries
                ):
                    stream_retry += 1
                    wait = retry_backoff_seconds(stream_retry, stream_err)
                    logger.warning(
                        f"OpenAI 流中断 [trace={request_trace_id}]（第{stream_retry}/{max_stream_retries}次），"
                        f"{wait:.1f}s 后重试: {summarize_error_for_log(stream_err)}"
                    )
                    await asyncio.sleep(wait)
                    stream = await client.chat.completions.create(**request_params)
                    tool_call_buffer = {}
                    chunk_count = 0
                elif content_yielded and is_timeout:
                    logger.warning(
                        f"OpenAI 流式读取超时 [trace={request_trace_id}]（已发送 {chunk_count} 个 chunk），"
                        f"优雅截断并结束流: {stream_err}"
                    )
                    yield StreamChunk(finish_reason="length")
                    stream_done = True
                else:
                    raise

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

    @staticmethod
    def _flatten_message_content(content: Any) -> str:
        """把非流式响应的 content 归一化成纯文本（兼容分段 content 数组）。"""
        if isinstance(content, str):
            return content
        if not isinstance(content, list):
            return ""
        parts: List[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if not isinstance(item, dict):
                continue
            if item.get("type") in ("text", "output_text"):
                text = item.get("text")
                if text:
                    parts.append(str(text))
        return "".join(parts)

    def _convert_completion_to_chunks(self, completion: Any) -> List[StreamChunk]:
        """非流式 chat.completions 响应 -> 统一 StreamChunk 序列。"""
        chunks: List[StreamChunk] = []
        choices = getattr(completion, "choices", None) or []
        if not choices:
            chunks.append(StreamChunk(finish_reason="stop"))
            return chunks

        choice = choices[0]
        message = getattr(choice, "message", None)
        if message is not None:
            reasoning_text = self._extract_reasoning_delta(message)
            if reasoning_text and has_visible_text(reasoning_text):
                chunks.append(StreamChunk(reasoning_content=reasoning_text))

            content_text = self._flatten_message_content(
                getattr(message, "content", None)
            )
            if content_text:
                chunks.append(StreamChunk(content=content_text))

            for tool_call in getattr(message, "tool_calls", None) or []:
                function = getattr(tool_call, "function", None)
                name = getattr(function, "name", "") if function else ""
                if not name:
                    continue
                raw_arguments = getattr(function, "arguments", "") or ""
                if not isinstance(raw_arguments, str):
                    raw_arguments = json.dumps(raw_arguments, ensure_ascii=False)
                chunks.append(
                    StreamChunk(
                        tool_call=ToolCall(
                            id=getattr(tool_call, "id", None) or "call_unknown",
                            name=name,
                            arguments=parse_json_arguments(raw_arguments),
                        )
                    )
                )

            message_events = native_events.openai_message_events(message)
            if message_events:
                chunks.append(StreamChunk(native_events=message_events))
            server_tool_calls = getattr(message, "server_tool_calls", None) or []
            history_calls = [
                call.model_dump()
                if hasattr(call, "model_dump")
                else dict(call)
                if isinstance(call, dict)
                else {}
                for call in server_tool_calls
            ]
            history_calls = [item for item in history_calls if item]
            if history_calls:
                chunks.append(
                    StreamChunk(
                        native_events=[
                            {
                                "kind": "history_blocks",
                                "protocol": PROTOCOL_CHAT,
                                "server_tool_calls": history_calls,
                            }
                        ]
                    )
                )

        chunks.append(
            StreamChunk(
                finish_reason=getattr(choice, "finish_reason", None) or "stop",
                usage=self._extract_chat_usage(getattr(completion, "usage", None)),
            )
        )
        return chunks

    def _apply_reasoning_config(
        self,
        request_params: Dict[str, Any],
        thinking_enabled: Optional[bool],
        reasoning_level: Optional[str] = None,
    ) -> None:
        """对 OpenAI 兼容 provider 注入 provider-aware 的思考控制参数。"""
        applied_fields = apply_reasoning_request_fields(
            request_params,
            provider_id=self.provider_id,
            model=request_params.get("model"),
            api_base=self.api_base,
            thinking_enabled=thinking_enabled,
            reasoning_level=reasoning_level,
        )
        # 显式档位为关闭（none/off）时同样要清掉历史思考内容
        level_off = (
            normalize_reasoning_level(reasoning_level) is not None
            and is_reasoning_off(reasoning_level)
        )
        if thinking_enabled is False or level_off:
            openai_compat.strip_message_reasoning_content(request_params)

        request_params.pop("thinking_enabled", None)

        if applied_fields:
            logger.debug(
                "Applied reasoning control fields for provider "
                f"{self.provider_id or 'openai-compatible'}: {', '.join(applied_fields)}"
            )

    @staticmethod
    def _extract_chat_usage(usage: Any) -> Optional[Dict[str, int]]:
        """chat.completions 的 usage -> 内部统一字段（含缓存命中与推理明细）。

        缓存命中/推理 token 只在 *_details 子对象里（prompt_tokens_details
        .cached_tokens、completion_tokens_details.reasoning_tokens），只抄顶层
        三个整数会让缓存命中与推理统计永远是 0。
        """
        if usage is None:
            return None
        extracted: Dict[str, int] = {
            "prompt_tokens": getattr(usage, "prompt_tokens", 0),
            "completion_tokens": getattr(usage, "completion_tokens", 0),
            "total_tokens": getattr(usage, "total_tokens", 0),
        }
        cached_tokens = read_usage_detail_int(
            getattr(usage, "prompt_tokens_details", None), "cached_tokens"
        )
        if cached_tokens:
            extracted["cache_read_tokens"] = cached_tokens
        reasoning_tokens = read_usage_detail_int(
            getattr(usage, "completion_tokens_details", None), "reasoning_tokens"
        )
        if reasoning_tokens:
            extracted["reasoning_tokens"] = reasoning_tokens
        return extracted

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

    @staticmethod
    def _convert_content_blocks_for_chat_completions(content: Any) -> Any:
        """把内部图片内容块转换成 OpenAI chat.completions 的 content parts。"""
        if not isinstance(content, list):
            return content

        converted: List[Dict[str, Any]] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = str(block.get("type") or "").strip().lower()
            if block_type == "text":
                text = str(block.get("text") or "")
                if text:
                    converted.append({"type": "text", "text": text})
                continue
            if block_type == "file":
                file_id = str(block.get("file_id") or "").strip()
                if file_id:
                    converted.append({"type": "file", "file_id": file_id})
                continue
            if block_type != "image":
                continue

            media_type = str(block.get("media_type") or "image/png").strip() or "image/png"
            data = str(block.get("data") or "").strip()
            if not data:
                continue
            converted.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{media_type};base64,{data}"},
                }
            )

        if not converted:
            return ""
        if all(item.get("type") == "text" for item in converted):
            return "\n".join(str(item.get("text") or "") for item in converted)
        return converted

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
                sanitized["content"] = self._convert_content_blocks_for_chat_completions(
                    message.get("content")
                )

            if normalized_role == "assistant" and message.get("tool_calls"):
                sanitized["tool_calls"] = message.get("tool_calls")

            if normalized_role == "assistant" and message.get("server_tool_calls"):
                sanitized["server_tool_calls"] = message.get("server_tool_calls")

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

        return self._normalize_tool_message_sequence(sanitized_messages)

    @classmethod
    def _normalize_tool_message_sequence(
        cls,
        messages: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Repair obviously-invalid assistant/tool message sequences before sending upstream."""
        normalized_messages: List[Dict[str, Any]] = []
        pending_tool_call_ids: List[str] = []
        pending_tool_result_ids: set[str] = set()
        pending_assistant_index: Optional[int] = None

        def reset_pending() -> None:
            nonlocal pending_tool_call_ids, pending_tool_result_ids, pending_assistant_index
            pending_tool_call_ids = []
            pending_tool_result_ids = set()
            pending_assistant_index = None

        def drop_pending_tool_calls(reason: str) -> None:
            nonlocal normalized_messages
            if pending_assistant_index is None:
                reset_pending()
                return

            assistant_message = normalized_messages[pending_assistant_index]
            if "tool_calls" in assistant_message:
                assistant_message = dict(assistant_message)
                assistant_message.pop("tool_calls", None)
                normalized_messages[pending_assistant_index] = assistant_message
                logger.warning(
                    "Dropping dangling assistant tool_calls before upstream request: "
                    f"{reason}"
                )
            reset_pending()

        for message in messages:
            role = message.get("role")

            if role == "assistant" and message.get("tool_calls"):
                if pending_tool_call_ids:
                    drop_pending_tool_calls("previous tool call batch was incomplete")

                deduped_tool_calls: List[Dict[str, Any]] = []
                seen_tool_call_ids: set[str] = set()

                for tool_call in message.get("tool_calls", []):
                    if not isinstance(tool_call, dict):
                        continue

                    tool_call_id = str(tool_call.get("id") or "").strip()
                    function = tool_call.get("function") or {}
                    tool_name = str(function.get("name") or "").strip()

                    if tool_call_id and tool_call_id in seen_tool_call_ids:
                        logger.warning(
                            "Dropping duplicate assistant tool_call by id before upstream request: "
                            f"{tool_name} ({tool_call_id})"
                        )
                        continue

                    if tool_call_id:
                        seen_tool_call_ids.add(tool_call_id)
                    deduped_tool_calls.append(tool_call)

                updated_message = dict(message)
                if deduped_tool_calls:
                    updated_message["tool_calls"] = deduped_tool_calls
                else:
                    updated_message.pop("tool_calls", None)

                normalized_messages.append(updated_message)

                if deduped_tool_calls:
                    pending_tool_call_ids = [
                        str(tool_call.get("id") or "").strip()
                        for tool_call in deduped_tool_calls
                        if str(tool_call.get("id") or "").strip()
                    ]
                    pending_tool_result_ids = set()
                    pending_assistant_index = len(normalized_messages) - 1
                else:
                    reset_pending()
                continue

            if role == "tool":
                tool_call_id = str(message.get("tool_call_id") or "").strip()
                if not pending_tool_call_ids:
                    logger.warning(
                        "Dropping orphan tool result before upstream request: "
                        f"tool_call_id={tool_call_id or '<empty>'}"
                    )
                    continue

                if not tool_call_id or tool_call_id not in pending_tool_call_ids:
                    logger.warning(
                        "Dropping unmatched tool result before upstream request: "
                        f"tool_call_id={tool_call_id or '<empty>'}"
                    )
                    continue

                if tool_call_id in pending_tool_result_ids:
                    logger.warning(
                        "Dropping duplicate tool result before upstream request: "
                        f"tool_call_id={tool_call_id}"
                    )
                    continue

                normalized_messages.append(message)
                pending_tool_result_ids.add(tool_call_id)
                if len(pending_tool_result_ids) == len(pending_tool_call_ids):
                    reset_pending()
                continue

            if pending_tool_call_ids:
                drop_pending_tool_calls(
                    f"encountered role '{role}' before all tool results were present"
                )

            normalized_messages.append(message)

        if pending_tool_call_ids:
            drop_pending_tool_calls("message list ended before all tool results were present")

        return normalized_messages


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
    def _summarize_content_part_types(messages: List[Dict[str, Any]]) -> str:
        """只记录角色和内容块类型，不落 base64 或正文。"""
        summary: List[str] = []
        for message in messages[-4:]:
            role = str(message.get("role") or "").strip() or "unknown"
            content = message.get("content")
            if isinstance(content, list):
                types = [
                    str(item.get("type") or "").strip()
                    for item in content
                    if isinstance(item, dict)
                ]
                summary.append(f"{role}[{','.join(part for part in types if part)}]")
            else:
                summary.append(role)
        return " -> ".join(summary) if summary else "<empty>"

    @staticmethod
    def _summarize_tool_message_sequence(messages: List[Dict[str, Any]]) -> str:
        summary_parts: List[str] = []
        for message in messages[-12:]:
            role = str(message.get("role") or "").strip() or "unknown"
            if role == "assistant" and message.get("tool_calls"):
                tool_calls = message.get("tool_calls") or []
                tool_call_ids = [
                    str(tool_call.get("id") or "").strip()
                    for tool_call in tool_calls
                    if isinstance(tool_call, dict)
                ]
                compact_ids = ",".join(tool_call_ids[:3])
                if len(tool_call_ids) > 3:
                    compact_ids += ",..."
                summary_parts.append(
                    f"assistant(tool_calls={len(tool_calls)} ids=[{compact_ids}])"
                )
                continue

            if role == "tool":
                tool_call_id = str(message.get("tool_call_id") or "").strip()
                summary_parts.append(f"tool(id={tool_call_id or '<empty>'})")
                continue

            summary_parts.append(role)

        return " -> ".join(summary_parts) if summary_parts else "<empty>"

    def get_default_model(self) -> str:
        """获取默认模型"""
        return self.default_model or "gpt-4o"
