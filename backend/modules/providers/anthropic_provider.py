"""Anthropic provider with SDK and raw HTTP fallback support."""

import asyncio
import json
import re
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx
from loguru import logger

from .base import (
    LLMProvider,
    StreamChunk,
    ToolCall,
    _TOOL_ARGUMENT_PARSE_ERROR_KEY,
    _TOOL_ARGUMENT_RAW_KEY,
    has_visible_text,
    is_retryable_error,
    retry_backoff_seconds,
)

from .error_messages import format_anthropic_error

from .thinking_profiles import is_reasoning_off, resolve_supported_reasoning_level
from backend.modules.native_caps import (
    build_provider_overrides,
    resolve_native_capabilities,
)
from backend.modules.native_caps import events as native_events
from backend.modules.native_caps.deepseek import merge_tools
from backend.modules.native_caps.registry import (
    PROTOCOL_ANTHROPIC,
    resolve_anthropic_base,
)


class AnthropicProvider(LLMProvider):
    """Anthropic-compatible provider."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        default_model: str = "claude-sonnet-4-6",
        timeout: float = 600.0,
        max_retries: int = 3,
        provider_id: Optional[str] = None,
        **kwargs: Any,
    ):
        super().__init__(api_key, api_base, default_model, timeout, max_retries)
        self.provider_id = provider_id
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
        """Stream chat completions."""
        try:
            model = model or self.default_model
            if not model:
                raise ValueError("Must set a model before calling Anthropic.")

            request_params = self._build_request_params(
                messages=messages,
                tools=tools,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs,
            )

            logger.info(f"Calling Anthropic-compatible API: {model}, api_base: {self.api_base}")

            if not bool(request_params.get("stream", True)):
                async for chunk in self._chat_non_stream(
                    request_params=request_params,
                ):
                    yield chunk
                return

            if self._should_use_sdk():
                try:
                    from anthropic import AsyncAnthropic
                except ModuleNotFoundError:
                    logger.warning(
                        "anthropic package not installed; falling back to raw HTTP client"
                    )
                else:
                    async for chunk in self._chat_stream_via_sdk(
                        AsyncAnthropic=AsyncAnthropic,
                        request_params=request_params,
                    ):
                        yield chunk
                    return

            async for chunk in self._chat_stream_via_httpx(request_params=request_params):
                yield chunk

        except Exception as e:
            error_msg = str(e).strip() or e.__class__.__name__
            logger.error(f"Anthropic call failed: {error_msg!r}")
            friendly_msg = format_anthropic_error(error_msg)
            yield StreamChunk(error=friendly_msg, raw_error=error_msg)

    def _should_use_sdk(self) -> bool:
        """Use the official SDK only for the official Anthropic provider."""
        return self.provider_id in (None, "", "anthropic")

    def _build_request_params(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        model: str,
        max_tokens: int,
        temperature: float,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        thinking_enabled = kwargs.pop("thinking_enabled", None)
        reasoning_level = kwargs.pop("reasoning_level", None)
        stream_enabled = bool(kwargs.pop("stream_enabled", self.stream_enabled))
        system_content, filtered_messages = self._normalize_messages(messages)

        request_params: Dict[str, Any] = {
            "model": model,
            "messages": filtered_messages,
            "stream": stream_enabled,
        }
        if temperature and temperature > 0:
            request_params["temperature"] = temperature
        resolved_max_tokens = self._resolve_max_tokens(max_tokens)
        if resolved_max_tokens is not None:
            request_params["max_tokens"] = resolved_max_tokens

        # system prompt 为纯静态前缀，以 content block + ephemeral cache point
        # 打缓存断点：前缀稳定时整段命中 prompt cache，显著降低重复输入成本。
        if system_content:
            request_params["system"] = [
                {
                    "type": "text",
                    "text": system_content,
                    "cache_control": {"type": "ephemeral"},
                }
            ]

        anthropic_tools = self._convert_tools(tools)
        native_caps = resolve_native_capabilities(
            self.provider_id, model, self.native_capabilities
        )
        native_overrides = build_provider_overrides(
            provider_id=self.provider_id,
            model=model,
            protocol=PROTOCOL_ANTHROPIC,
            capabilities=native_caps,
            thinking_enabled=thinking_enabled,
        )
        anthropic_tools = merge_tools(
            anthropic_tools, native_overrides.get("tools")
        )
        if anthropic_tools:
            request_params["tools"] = anthropic_tools
        if native_overrides.get("safety_check"):
            request_params["safety_check"] = native_overrides["safety_check"]

        self._apply_thinking_config(request_params, thinking_enabled, reasoning_level)
        request_params.update(kwargs)

        logger.debug(
            "Anthropic params: "
            + json.dumps(
                {
                    k: v
                    for k, v in request_params.items()
                    if k not in {"api_key", "messages", "system", "tools"}
                },
                ensure_ascii=False,
            )
        )
        return request_params

    def _resolve_max_tokens(self, max_tokens: int) -> Optional[int]:
        """Resolve max_tokens for Anthropic-compatible APIs.

        Official Anthropic requires max_tokens on every Messages request.
        Compatible providers may accept omitted max_tokens, so preserve the
        "0 means do not send" behavior there.
        """
        if max_tokens and max_tokens > 0:
            return max_tokens

        if self._requires_max_tokens():
            fallback_max_tokens = 4096
            logger.info(
                "Anthropic Messages API requires max_tokens; "
                f"using fallback {fallback_max_tokens} because configured value is {max_tokens!r}"
            )
            return fallback_max_tokens

        return None

    def _requires_max_tokens(self) -> bool:
        """Whether the upstream API requires max_tokens to be present."""
        provider_id = (self.provider_id or "").lower()
        api_base = (self.api_base or "").lower()
        return provider_id in ("", "anthropic") or "api.anthropic.com" in api_base

    @staticmethod
    def _is_missing_max_tokens_error(error: Exception) -> bool:
        message = str(error).lower()
        hints = (
            "max_tokens must be positive",
            "max_tokens is required",
            "max_tokens must be",
            "max_tokens should be",
            "missing required parameter",
        )
        return "max_tokens" in message and any(hint in message for hint in hints)

    def _normalize_messages(
        self, messages: List[Dict[str, Any]]
    ) -> tuple[Optional[str], List[Dict[str, Any]]]:
        """Convert generic chat messages to Anthropic format."""
        system_parts: List[str] = []
        filtered_messages: List[Dict[str, Any]] = []

        for msg in messages:
            role = msg.get("role")
            if role == "system":
                content = msg.get("content", "")
                if isinstance(content, str) and content:
                    system_parts.append(content)
                continue

            if role == "tool":
                filtered_messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": msg.get("tool_call_id"),
                                "content": msg.get("content", ""),
                            }
                        ],
                    }
                )
                continue

            if role == "assistant" and msg.get("anthropic_content_blocks"):
                filtered_messages.append(
                    {
                        "role": "assistant",
                        "content": msg.get("anthropic_content_blocks"),
                    }
                )
                continue

            if role == "assistant" and msg.get("tool_calls"):
                assistant_content: List[Dict[str, Any]] = []
                content = msg.get("content", "")
                if isinstance(content, str) and content:
                    assistant_content.append({"type": "text", "text": content})

                for tool_call in msg.get("tool_calls", []):
                    function = tool_call.get("function") or {}
                    arguments = function.get("arguments", {})
                    if isinstance(arguments, str):
                        try:
                            arguments = json.loads(arguments)
                        except json.JSONDecodeError:
                            arguments = {"raw": arguments}

                    assistant_content.append(
                        {
                            "type": "tool_use",
                            "id": tool_call.get("id"),
                            "name": function.get("name"),
                            "input": arguments if isinstance(arguments, dict) else {"value": arguments},
                        }
                    )

                filtered_messages.append(
                    {
                        "role": "assistant",
                        "content": assistant_content or [{"type": "text", "text": ""}],
                    }
                )
                continue

            # Anthropic Messages 仅接受 role/content 两个字段，其余键（如
            # reasoning_content）会被判定为非法参数，故重建而不是原样透传。
            content = msg.get("content", "")
            if isinstance(content, list):
                content = self._convert_user_content_blocks(content)
            filtered_messages.append(
                {"role": role, "content": content}
            )

        system_content = "\n\n".join(system_parts).strip() or None
        return system_content, filtered_messages

    @staticmethod
    def _convert_user_content_blocks(content: List[Any]) -> List[Dict[str, Any]]:
        """把内部图片内容块转换成 Anthropic Messages 的 content blocks。"""
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
                if not file_id:
                    continue
                media_type = str(block.get("media_type") or "").strip()
                declared_type = str(block.get("block_type") or "").strip().lower()
                target_type = declared_type or (
                    "image" if media_type.startswith("image/") else "document"
                )
                if target_type not in ("image", "document"):
                    target_type = "document"
                converted.append(
                    {
                        "type": target_type,
                        "source": {"type": "file", "file_id": file_id},
                    }
                )
                continue
            if block_type != "image":
                continue

            media_type = str(block.get("media_type") or "image/png").strip() or "image/png"
            data = str(block.get("data") or "").strip()
            if not data:
                continue
            converted.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": data,
                    },
                }
            )

        return converted or [{"type": "text", "text": ""}]

    def _convert_tools(
        self, tools: Optional[List[Dict[str, Any]]]
    ) -> Optional[List[Dict[str, Any]]]:
        """Convert OpenAI-style tools to Anthropic tools."""
        if not tools:
            return None

        anthropic_tools: List[Dict[str, Any]] = []
        for tool in tools:
            if tool.get("type") == "function" and "function" in tool:
                func = tool["function"]
                anthropic_tools.append(
                    {
                        "name": func.get("name"),
                        "description": func.get("description", ""),
                        "input_schema": func.get(
                            "parameters", {"type": "object", "properties": {}}
                        ),
                    }
                )
            elif "name" in tool:
                # 复制一份再附加 cache_control，避免污染调用方持有的原始 tool dict
                anthropic_tools.append(dict(tool))

        # 给最后一个 tool 打静态 cache point：工具定义在会话内不变，
        # 配合 system 断点一起覆盖请求头部。
        if anthropic_tools:
            anthropic_tools[-1]["cache_control"] = {"type": "ephemeral"}

        return anthropic_tools or None

    @staticmethod
    def _ensure_content_block(
        content_block_buffer: Dict[str, Dict[str, Any]],
        index: int,
        block_type: str,
    ) -> Dict[str, Any]:
        key = f"index_{index}"
        block = content_block_buffer.get(key)
        if block is None:
            block = {"type": block_type}
            if block_type == "text":
                block["text"] = ""
            elif block_type == "thinking":
                block["thinking"] = ""
                block["signature"] = ""
            elif block_type == "tool_use":
                block["id"] = f"call_{index}"
                block["name"] = ""
                block["input_json"] = ""
                block["input"] = {}
                block["saw_json_delta"] = False
            content_block_buffer[key] = block
        return block

    def _register_content_block_start(
        self,
        content_block_buffer: Dict[str, Dict[str, Any]],
        index: int,
        block: Dict[str, Any],
    ) -> None:
        block_type = block.get("type")
        if not block_type:
            return

        key = f"index_{index}"

        if block_type == "text":
            content_block_buffer[key] = {
                "type": "text",
                "text": block.get("text", "") or "",
            }
            return

        if block_type == "thinking":
            content_block_buffer[key] = {
                "type": "thinking",
                "thinking": block.get("thinking", "") or "",
                "signature": block.get("signature", "") or "",
            }
            return

        if block_type == "redacted_thinking":
            redacted = {"type": "redacted_thinking"}
            for field in ("data", "thinking", "signature"):
                if block.get(field):
                    redacted[field] = block[field]
            content_block_buffer[key] = redacted
            return

        if block_type == "tool_use":
            initial_input = block.get("input")
            content_block_buffer[key] = {
                "type": "tool_use",
                "id": block.get("id") or f"call_{index}",
                "name": block.get("name", ""),
                "input_json": self._serialize_tool_input(initial_input),
                "input": initial_input if isinstance(initial_input, dict) else {},
                "saw_json_delta": False,
            }
            return

        content_block_buffer[key] = dict(block)

    def _finalize_content_blocks(
        self,
        content_block_buffer: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        blocks: List[Dict[str, Any]] = []
        for key in sorted(
            content_block_buffer.keys(),
            key=lambda item: int(item.split("_", 1)[1]),
        ):
            block = content_block_buffer[key]
            block_type = block.get("type")

            if block_type == "text":
                blocks.append(
                    {
                        "type": "text",
                        "text": block.get("text", "") or "",
                    }
                )
                continue

            if block_type == "thinking":
                thinking_block = {
                    "type": "thinking",
                    "thinking": block.get("thinking", "") or "",
                }
                if block.get("signature"):
                    thinking_block["signature"] = block["signature"]
                blocks.append(thinking_block)
                continue

            if block_type == "redacted_thinking":
                redacted_block = {"type": "redacted_thinking"}
                for field in ("data", "thinking", "signature"):
                    if block.get(field):
                        redacted_block[field] = block[field]
                blocks.append(redacted_block)
                continue

            if block_type == "tool_use":
                input_value = block.get("input")
                input_json = (block.get("input_json") or "").strip()
                if input_json:
                    try:
                        input_value = json.loads(input_json)
                    except json.JSONDecodeError:
                        input_value = {"raw": input_json}
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": block.get("id") or "call_unknown",
                        "name": block.get("name") or "",
                        "input": input_value if isinstance(input_value, dict) else {"value": input_value},
                    }
                )
                continue

            blocks.append(dict(block))

        return blocks

    def _apply_thinking_config(
        self,
        request_params: Dict[str, Any],
        thinking_enabled: Optional[bool],
        reasoning_level: Optional[str] = None,
    ) -> None:
        """Inject Anthropic extended thinking config when enabled.

        显式档位优先：新版 Claude 用 `thinking.type=adaptive` + `output_config.effort`
        表达强度（档位原样下发，含用户自定义档位）；档位为关闭时直接移除 thinking。
        未给档位时保持原行为（budget_tokens），避免影响存量模型。
        """
        supported_level = resolve_supported_reasoning_level(
            reasoning_level,
            model=str(request_params.get("model") or ""),
        )
        if str(self.provider_id or "").lower() == "deepseek":
            # DeepSeek 的 Anthropic 兼容端点只认 thinking.type，不接受 budget_tokens
            request_params.pop("output_config", None)
            if thinking_enabled is False or (
                supported_level is not None and is_reasoning_off(supported_level)
            ):
                request_params["thinking"] = {"type": "disabled"}
            elif thinking_enabled is True:
                request_params["thinking"] = {"type": "enabled"}
            return

        if supported_level is not None:
            if is_reasoning_off(supported_level):
                request_params.pop("thinking", None)
                request_params.pop("output_config", None)
                return
            request_params["thinking"] = {"type": "adaptive"}
            request_params["output_config"] = {"effort": supported_level}
            return

        request_params.pop("output_config", None)

        if thinking_enabled is None:
            request_params.pop("thinking", None)
            return

        if not thinking_enabled:
            request_params.pop("thinking", None)
            return

        try:
            max_tokens = int(request_params.get("max_tokens") or 0)
        except (TypeError, ValueError):
            max_tokens = 0

        if max_tokens <= 0:
            logger.debug(
                "Skipping Anthropic thinking config because max_tokens is unset; "
                "extended thinking requires an explicit max_tokens budget."
            )
            request_params.pop("thinking", None)
            return

        if max_tokens <= 1024:
            logger.warning(
                "Anthropic thinking requested but max_tokens <= 1024; "
                "skipping thinking config because budget_tokens must be >= 1024 and < max_tokens."
            )
            request_params.pop("thinking", None)
            return

        budget_tokens = min(max_tokens - 1, 1024)
        if budget_tokens < 1024:
            request_params.pop("thinking", None)
            return

        request_params["thinking"] = {
            "type": "enabled",
            "budget_tokens": budget_tokens,
        }

    async def _chat_non_stream(
        self,
        *,
        request_params: Dict[str, Any],
    ) -> AsyncIterator[StreamChunk]:
        """非流式请求：SDK 与裸 HTTP 两条实现都收敛到统一 StreamChunk。"""
        if self._should_use_sdk():
            try:
                from anthropic import AsyncAnthropic
            except ModuleNotFoundError:
                logger.warning(
                    "anthropic package not installed; falling back to raw HTTP client"
                )
            else:
                payload = await self._create_message_with_retry(
                    AsyncAnthropic=AsyncAnthropic,
                    request_params=dict(request_params),
                )
                for chunk in self._convert_message_to_chunks(payload):
                    yield chunk
                return

        payload = await self._create_message_via_httpx(
            request_params=dict(request_params),
        )
        for chunk in self._convert_message_to_chunks(payload):
            yield chunk

    async def _create_message_with_retry(
        self,
        *,
        AsyncAnthropic: Any,
        request_params: Dict[str, Any],
    ) -> Any:
        client_kwargs: Dict[str, Any] = {
            "api_key": self.api_key,
            "timeout": self.timeout,
            "max_retries": 0,
        }
        if self.api_base:
            client_kwargs["base_url"] = self.api_base
        client = AsyncAnthropic(**client_kwargs)

        for attempt in range(1, self.max_retries + 1):
            try:
                return await client.messages.create(**request_params)
            except Exception as e:
                if not is_retryable_error(e):
                    raise
                if attempt < self.max_retries:
                    wait = retry_backoff_seconds(attempt, e)
                    logger.warning(
                        f"Anthropic SDK non-stream request failed ({attempt}/{self.max_retries}), "
                        f"retrying in {wait:.1f}s: {e}"
                    )
                    await asyncio.sleep(wait)
                    continue
                raise
        raise RuntimeError("Anthropic SDK non-stream request exhausted retries")

    async def _create_message_via_httpx(
        self,
        *,
        request_params: Dict[str, Any],
    ) -> Any:
        request_url = self._build_messages_url()
        headers = self._build_headers()
        headers["Accept"] = "application/json"
        if str(self.provider_id or "").lower() == "deepseek":
            caps = resolve_native_capabilities(
                self.provider_id,
                request_params.get("model"),
                self.native_capabilities,
            )
            if caps.document_parsing != "off":
                headers["anthropic-beta"] = "files-api-2025-04-14"
        request_payload = dict(request_params)
        injected_fallback_max_tokens = False

        for attempt in range(1, self.max_retries + 1):
            try:
                timeout = httpx.Timeout(self.timeout)
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(
                        request_url,
                        headers=headers,
                        json=request_payload,
                    )
                    await self._raise_for_status(response)
                    return response.json()
            except Exception as e:
                if (
                    not injected_fallback_max_tokens
                    and not request_payload.get("max_tokens")
                    and self._is_missing_max_tokens_error(e)
                ):
                    request_payload["max_tokens"] = 4096
                    injected_fallback_max_tokens = True
                    logger.warning(
                        "Anthropic-compatible upstream rejected missing max_tokens; "
                        "retrying with fallback max_tokens=4096"
                    )
                    continue

                if not is_retryable_error(e):
                    raise
                if attempt < self.max_retries:
                    wait = retry_backoff_seconds(attempt, e)
                    logger.warning(
                        f"Anthropic HTTP non-stream request failed ({attempt}/{self.max_retries}), "
                        f"retrying in {wait:.1f}s: {e}"
                    )
                    await asyncio.sleep(wait)
                    continue
                raise
        raise RuntimeError("Anthropic HTTP non-stream request exhausted retries")

    def _convert_message_to_chunks(self, payload: Any) -> List[StreamChunk]:
        """非流式 Messages 响应 -> 统一 StreamChunk（含回放用 content blocks）。"""
        if hasattr(payload, "model_dump"):
            data = payload.model_dump()
        elif isinstance(payload, dict):
            data = payload
        else:
            data = {}

        chunks: List[StreamChunk] = []
        blocks: List[Dict[str, Any]] = []
        tool_chunks: List[StreamChunk] = []

        for block in data.get("content") or []:
            if not isinstance(block, dict):
                continue
            block_type = str(block.get("type") or "")

            if block_type == "text":
                text = str(block.get("text") or "")
                if text:
                    chunks.append(StreamChunk(content=text))
                blocks.append({"type": "text", "text": text})
                continue

            if block_type == "thinking":
                thinking = str(block.get("thinking") or "")
                if thinking and has_visible_text(thinking):
                    chunks.append(StreamChunk(reasoning_content=thinking))
                thinking_block = {"type": "thinking", "thinking": thinking}
                if block.get("signature"):
                    thinking_block["signature"] = block["signature"]
                blocks.append(thinking_block)
                continue

            if block_type == "redacted_thinking":
                redacted = {"type": "redacted_thinking"}
                for field in ("data", "thinking", "signature"):
                    if block.get(field):
                        redacted[field] = block[field]
                blocks.append(redacted)
                continue

            if block_type == "tool_use":
                tool_id = str(block.get("id") or "")
                tool_name = str(block.get("name") or "")
                tool_input = block.get("input")
                if tool_name:
                    arguments = (
                        tool_input
                        if isinstance(tool_input, dict)
                        else self._parse_tool_arguments(tool_input)
                    )
                    tool_chunks.append(
                        StreamChunk(
                            tool_call=ToolCall(
                                id=tool_id or "call_unknown",
                                name=tool_name,
                                arguments=arguments,
                            )
                        )
                    )
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": tool_id,
                        "name": tool_name,
                        "input": tool_input if isinstance(tool_input, dict) else {},
                    }
                )

        if blocks:
            chunks.append(
                StreamChunk(provider_payload={"anthropic_content_blocks": blocks})
            )
        chunks.extend(tool_chunks)

        usage = data.get("usage") or {}
        chunks.append(
            StreamChunk(
                finish_reason=str(data.get("stop_reason") or "stop"),
                usage=self._build_usage(
                    int(usage.get("input_tokens") or 0),
                    int(usage.get("output_tokens") or 0),
                    int(usage.get("cache_read_input_tokens") or 0),
                    int(usage.get("cache_creation_input_tokens") or 0),
                ),
            )
        )
        return chunks

    @staticmethod
    def _parse_tool_arguments(raw: Any) -> Dict[str, Any]:
        if isinstance(raw, dict):
            return raw
        text = str(raw or "").strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {_TOOL_ARGUMENT_RAW_KEY: text}
        return parsed if isinstance(parsed, dict) else {"value": parsed}

    async def _chat_stream_via_sdk(
        self,
        *,
        AsyncAnthropic: Any,
        request_params: Dict[str, Any],
    ) -> AsyncIterator[StreamChunk]:
        """Stream using the official Anthropic SDK."""
        client_kwargs: Dict[str, Any] = {
            "api_key": self.api_key,
            "timeout": self.timeout,
            "max_retries": 0,
        }
        if self.api_base:
            client_kwargs["base_url"] = self.api_base

        client = AsyncAnthropic(**client_kwargs)

        stream = None
        for attempt in range(1, self.max_retries + 1):
            try:
                stream = await client.messages.create(**request_params)
                break
            except Exception as e:
                if not is_retryable_error(e):
                    logger.warning(f"Anthropic 不可重试错误，直接上抛: {e}")
                    raise

                if attempt < self.max_retries:
                    wait = retry_backoff_seconds(attempt, e)
                    logger.warning(
                        f"Anthropic SDK request failed ({attempt}/{self.max_retries}), "
                        f"retrying in {wait:.1f}s: {e}"
                    )
                    await asyncio.sleep(wait)
                else:
                    raise

        tool_call_buffer: Dict[str, Dict[str, Any]] = {}
        content_block_buffer: Dict[str, Dict[str, Any]] = {}
        chunk_count = 0
        content_yielded = False
        stream_done = False
        input_tokens = 0
        output_tokens = 0
        cache_read_input_tokens = 0
        cache_creation_input_tokens = 0
        finish_reason = "stop"

        stream_retry = 0
        max_stream_retries = self.max_retries

        while not stream_done and stream_retry <= max_stream_retries:
            try:
                async for event in stream:
                    chunk_count += 1
                    if chunk_count <= 3:
                        logger.debug(f"Anthropic SDK event #{chunk_count}: {event}")

                    if event.type == "message_start":
                        if hasattr(event, "message") and hasattr(event.message, "usage"):
                            input_tokens = getattr(event.message.usage, "input_tokens", 0)
                            cache_read_input_tokens = getattr(
                                event.message.usage, "cache_read_input_tokens", 0
                            )
                            cache_creation_input_tokens = getattr(
                                event.message.usage, "cache_creation_input_tokens", 0
                            )

                    elif event.type == "content_block_start":
                        block = getattr(event, "content_block", None)
                        if block:
                            block_dict = {
                                field: getattr(block, field)
                                for field in ("type", "id", "name", "input", "text", "thinking", "signature", "data")
                                if hasattr(block, field)
                            }
                            self._register_content_block_start(
                                content_block_buffer,
                                event.index,
                                block_dict,
                            )
                            if getattr(block, "type", None) == "tool_use":
                                key = f"index_{event.index}"
                                tool_call_buffer[key] = {
                                    "id": getattr(block, "id", None) or f"call_{event.index}",
                                    "name": getattr(block, "name", ""),
                                    "arguments": self._serialize_tool_input(getattr(block, "input", None)),
                                    "saw_json_delta": False,
                                }

                    elif event.type == "content_block_delta":
                        content_yielded = True
                        delta = event.delta

                        if delta.type == "text_delta":
                            if delta.text:
                                block = self._ensure_content_block(
                                    content_block_buffer,
                                    event.index,
                                    "text",
                                )
                                block["text"] = f"{block.get('text', '')}{delta.text}"
                                yield StreamChunk(content=delta.text)
                        elif delta.type == "thinking_delta":
                            thinking = getattr(delta, "thinking", "")
                            if thinking:
                                block = self._ensure_content_block(
                                    content_block_buffer,
                                    event.index,
                                    "thinking",
                                )
                                block["thinking"] = f"{block.get('thinking', '')}{thinking}"
                                if has_visible_text(thinking):
                                    yield StreamChunk(reasoning_content=thinking)
                        elif delta.type == "signature_delta":
                            signature = getattr(delta, "signature", "")
                            block = self._ensure_content_block(
                                content_block_buffer,
                                event.index,
                                "thinking",
                            )
                            block["signature"] = signature
                        elif delta.type == "input_json_delta":
                            key = f"index_{event.index}"
                            tool_call_buffer.setdefault(
                                key,
                                {
                                    "id": f"call_{event.index}",
                                    "name": "",
                                    "arguments": "",
                                    "saw_json_delta": False,
                                },
                            )
                            block = self._ensure_content_block(
                                content_block_buffer,
                                event.index,
                                "tool_use",
                            )
                            if not tool_call_buffer[key]["saw_json_delta"]:
                                tool_call_buffer[key]["arguments"] = ""
                                tool_call_buffer[key]["saw_json_delta"] = True
                                block["input_json"] = ""
                                block["saw_json_delta"] = True
                            tool_call_buffer[key]["arguments"] += delta.partial_json
                            block["input_json"] = f"{block.get('input_json', '')}{delta.partial_json}"

                    elif event.type == "message_delta":
                        if hasattr(event, "delta") and hasattr(event.delta, "stop_reason"):
                            finish_reason = event.delta.stop_reason or finish_reason
                        if hasattr(event, "usage"):
                            output_tokens = getattr(event.usage, "output_tokens", 0)
                            cache_read_input_tokens = getattr(
                                event.usage, "cache_read_input_tokens", cache_read_input_tokens
                            )
                            cache_creation_input_tokens = getattr(
                                event.usage, "cache_creation_input_tokens", cache_creation_input_tokens
                            )

                    elif event.type == "message_stop":
                        finalized_blocks = self._finalize_content_blocks(content_block_buffer)
                        if finalized_blocks:
                            yield StreamChunk(
                                provider_payload={
                                    "anthropic_content_blocks": finalized_blocks,
                                }
                            )
                        for chunk in self._flush_tool_calls(tool_call_buffer):
                            yield chunk
                        yield StreamChunk(
                            finish_reason=finish_reason,
                            usage=self._build_usage(
                                input_tokens,
                                output_tokens,
                                cache_read_input_tokens,
                                cache_creation_input_tokens,
                            ),
                        )
                        stream_done = True

                if not stream_done:
                    stream_done = True
                    yield StreamChunk(finish_reason="stop")

            except Exception as stream_err:
                is_timeout = self._is_timeout_error(stream_err)

                if (
                    not content_yielded
                    and is_retryable_error(stream_err)
                    and stream_retry < max_stream_retries
                ):
                    stream_retry += 1
                    wait = retry_backoff_seconds(stream_retry, stream_err)
                    logger.warning(
                        f"Anthropic SDK stream interrupted "
                        f"({stream_retry}/{max_stream_retries}), "
                        f"retrying in {wait:.1f}s: {stream_err}"
                    )
                    await asyncio.sleep(wait)
                    stream = await client.messages.create(**request_params)
                    tool_call_buffer = {}
                    content_block_buffer = {}
                    chunk_count = 0
                    continue

                if content_yielded and is_timeout:
                    logger.warning(
                        f"Anthropic SDK stream timed out after {chunk_count} chunks: "
                        f"{stream_err}"
                    )
                    yield StreamChunk(finish_reason="length")
                    stream_done = True
                    continue

                raise

    async def _chat_stream_via_httpx(
        self, *, request_params: Dict[str, Any]
    ) -> AsyncIterator[StreamChunk]:
        """Stream using raw HTTP for Anthropic-compatible providers."""
        request_url = self._build_messages_url()
        headers = self._build_headers()
        if str(self.provider_id or "").lower() == "deepseek":
            caps = resolve_native_capabilities(
                self.provider_id,
                request_params.get("model"),
                self.native_capabilities,
            )
            if caps.document_parsing != "off":
                headers["anthropic-beta"] = "files-api-2025-04-14"
        request_payload = dict(request_params)
        injected_fallback_max_tokens = False

        for attempt in range(1, self.max_retries + 1):
            tool_call_buffer: Dict[str, Dict[str, Any]] = {}
            content_block_buffer: Dict[str, Dict[str, Any]] = {}
            chunk_count = 0
            content_yielded = False
            input_tokens = 0
            output_tokens = 0
            cache_read_input_tokens = 0
            cache_creation_input_tokens = 0
            finish_reason = "stop"

            try:
                timeout = httpx.Timeout(self.timeout)
                async with httpx.AsyncClient(timeout=timeout) as client:
                    async with client.stream(
                        "POST",
                        request_url,
                        headers=headers,
                        json=request_payload,
                    ) as response:
                        await self._raise_for_status(response)

                        async for event in self._iter_sse_events(response):
                            chunk_count += 1
                            if chunk_count <= 3:
                                logger.debug(
                                    "Anthropic HTTP event "
                                    f"#{chunk_count}: {json.dumps(event, ensure_ascii=False)}"
                                )

                            event_type = event.get("type")

                            if event_type == "message_start":
                                usage = (event.get("message") or {}).get("usage") or {}
                                input_tokens = usage.get("input_tokens", input_tokens)
                                cache_read_input_tokens = usage.get(
                                    "cache_read_input_tokens", cache_read_input_tokens
                                )
                                cache_creation_input_tokens = usage.get(
                                    "cache_creation_input_tokens", cache_creation_input_tokens
                                )

                            elif event_type == "content_block_start":
                                block = event.get("content_block") or {}
                                self._register_content_block_start(
                                    content_block_buffer,
                                    event.get("index", 0),
                                    block,
                                )
                                block_events = native_events.anthropic_block_events(block)
                                if block_events:
                                    yield StreamChunk(native_events=block_events)
                                if block.get("type") == "tool_use":
                                    index = event.get("index", 0)
                                    initial_input = block.get("input")
                                    tool_call_buffer[f"index_{index}"] = {
                                        "id": block.get("id") or f"call_{index}",
                                        "name": block.get("name", ""),
                                        "arguments": self._serialize_tool_input(initial_input),
                                        "saw_json_delta": False,
                                    }

                            elif event_type == "content_block_delta":
                                content_yielded = True
                                delta = event.get("delta") or {}
                                delta_type = delta.get("type")

                                if delta_type == "text_delta":
                                    text = delta.get("text", "")
                                    if text:
                                        block = self._ensure_content_block(
                                            content_block_buffer,
                                            event.get("index", 0),
                                            "text",
                                        )
                                        block["text"] = f"{block.get('text', '')}{text}"
                                        yield StreamChunk(content=text)
                                elif delta_type == "thinking_delta":
                                    thinking = delta.get("thinking", "")
                                    if thinking:
                                        block = self._ensure_content_block(
                                            content_block_buffer,
                                            event.get("index", 0),
                                            "thinking",
                                        )
                                        block["thinking"] = f"{block.get('thinking', '')}{thinking}"
                                        # 上游偶尔只回零宽字符占位，对外不输出空思考块
                                        if has_visible_text(thinking):
                                            yield StreamChunk(reasoning_content=thinking)
                                elif delta_type == "signature_delta":
                                    block = self._ensure_content_block(
                                        content_block_buffer,
                                        event.get("index", 0),
                                        "thinking",
                                    )
                                    block["signature"] = delta.get("signature", "")
                                elif delta_type == "input_json_delta":
                                    index = event.get("index", 0)
                                    key = f"index_{index}"
                                    tool_call_buffer.setdefault(
                                        key,
                                        {
                                            "id": f"call_{index}",
                                            "name": "",
                                            "arguments": "",
                                            "saw_json_delta": False,
                                        },
                                    )
                                    block = self._ensure_content_block(
                                        content_block_buffer,
                                        index,
                                        "tool_use",
                                    )
                                    if not tool_call_buffer[key]["saw_json_delta"]:
                                        tool_call_buffer[key]["arguments"] = ""
                                        tool_call_buffer[key]["saw_json_delta"] = True
                                        block["input_json"] = ""
                                        block["saw_json_delta"] = True
                                    tool_call_buffer[key]["arguments"] += delta.get(
                                        "partial_json", ""
                                    )
                                    block["input_json"] = (
                                        f"{block.get('input_json', '')}{delta.get('partial_json', '')}"
                                    )
                                elif delta_type == "citations_delta":
                                    citation = delta.get("citation") or {}
                                    citation_events = native_events.anthropic_delta_events(delta)
                                    block = self._ensure_content_block(
                                        content_block_buffer,
                                        event.get("index", 0),
                                        "text",
                                    )
                                    if isinstance(citation, dict) and citation.get("url"):
                                        block.setdefault("citations", []).append(citation)
                                    if citation_events:
                                        yield StreamChunk(native_events=citation_events)

                            elif event_type == "message_delta":
                                delta = event.get("delta") or {}
                                finish_reason = delta.get("stop_reason") or finish_reason
                                if finish_reason == "refusal":
                                    stop_details = delta.get("stop_details") or {}
                                    yield StreamChunk(
                                        native_events=[
                                            {
                                                "kind": "refusal",
                                                "message": str(
                                                    stop_details.get("explanation")
                                                    or "内容未通过安全审核"
                                                ),
                                            }
                                        ]
                                    )
                                usage = event.get("usage") or {}
                                output_tokens = usage.get("output_tokens", output_tokens)
                                cache_read_input_tokens = usage.get(
                                    "cache_read_input_tokens", cache_read_input_tokens
                                )
                                cache_creation_input_tokens = usage.get(
                                    "cache_creation_input_tokens", cache_creation_input_tokens
                                )

                            elif event_type == "message_stop":
                                finalized_blocks = self._finalize_content_blocks(content_block_buffer)
                                history_blocks = native_events.history_blocks_from_anthropic(
                                    finalized_blocks
                                )
                                if history_blocks:
                                    yield StreamChunk(
                                        native_events=[
                                            {
                                                "kind": "history_blocks",
                                                "protocol": PROTOCOL_ANTHROPIC,
                                                "blocks": history_blocks,
                                            }
                                        ]
                                    )
                                if finalized_blocks:
                                    yield StreamChunk(
                                        provider_payload={
                                            "anthropic_content_blocks": finalized_blocks,
                                        }
                                    )
                                for chunk in self._flush_tool_calls(tool_call_buffer):
                                    yield chunk
                                yield StreamChunk(
                                    finish_reason=finish_reason,
                                    usage=self._build_usage(
                                        input_tokens,
                                        output_tokens,
                                        cache_read_input_tokens,
                                        cache_creation_input_tokens,
                                    ),
                                )
                                return

                            elif event_type == "error":
                                error = event.get("error") or {}
                                message = error.get("message") or json.dumps(
                                    error, ensure_ascii=False
                                )
                                raise RuntimeError(message)

                yield StreamChunk(
                    finish_reason=finish_reason,
                    usage=self._build_usage(input_tokens, output_tokens),
                )
                return

            except Exception as e:
                if (
                    not injected_fallback_max_tokens
                    and not request_payload.get("max_tokens")
                    and self._is_missing_max_tokens_error(e)
                ):
                    fallback_max_tokens = 4096
                    request_payload["max_tokens"] = fallback_max_tokens
                    injected_fallback_max_tokens = True
                    logger.warning(
                        "Anthropic-compatible upstream rejected missing max_tokens; "
                        f"retrying with fallback max_tokens={fallback_max_tokens}: {e}"
                    )
                    continue

                if self._is_timeout_error(e) and content_yielded:
                    logger.warning(
                        f"Anthropic HTTP stream timed out after {chunk_count} events: {e}"
                    )
                    yield StreamChunk(finish_reason="length")
                    return

                if not is_retryable_error(e):
                    logger.warning(f"Anthropic HTTP 不可重试错误，直接上抛: {e}")
                    raise

                if attempt < self.max_retries:
                    wait = retry_backoff_seconds(attempt, e)
                    logger.warning(
                        f"Anthropic HTTP request failed ({attempt}/{self.max_retries}), "
                        f"retrying in {wait:.1f}s: {e}"
                    )
                    await asyncio.sleep(wait)
                    continue

                raise

    def _build_messages_url(self) -> str:
        """Resolve the messages endpoint from api_base."""
        if str(self.provider_id or "").lower() == "deepseek":
            base = resolve_anthropic_base(self.api_base).rstrip("/")
        else:
            base = (self.api_base or "https://api.anthropic.com").rstrip("/")
        if base.endswith("/v1/messages"):
            return base
        if base.endswith("/messages"):
            return base
        if re.search(r"/v\d+$", base):
            return f"{base}/messages"
        if base.endswith("/v1"):
            return f"{base}/messages"
        return f"{base}/v1/messages"

    def _build_headers(self) -> Dict[str, str]:
        """Build headers for raw HTTP calls."""
        headers = {
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }

        if self.api_key:
            headers["x-api-key"] = self.api_key
            if self.provider_id in {"custom_anthropic", "minimax"}:
                headers["Authorization"] = f"Bearer {self.api_key}"

        return headers

    async def _raise_for_status(self, response: httpx.Response) -> None:
        """Raise readable errors for HTTP responses."""
        if response.status_code < 400:
            return

        body_text = (await response.aread()).decode("utf-8", errors="ignore").strip()
        message = body_text or response.reason_phrase or f"HTTP {response.status_code}"

        try:
            payload = json.loads(body_text)
        except Exception:
            payload = None

        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                message = error.get("message") or json.dumps(error, ensure_ascii=False)
            elif error:
                message = str(error)

        raise RuntimeError(f"HTTP {response.status_code}: {message}")

    async def _iter_sse_events(
        self, response: httpx.Response
    ) -> AsyncIterator[Dict[str, Any]]:
        """Parse SSE events from an Anthropic-compatible stream."""
        event_type: Optional[str] = None
        data_lines: List[str] = []

        async for raw_line in response.aiter_lines():
            line = raw_line.strip()

            if not line:
                event = self._parse_sse_event(event_type, data_lines)
                event_type = None
                data_lines = []
                if event is not None:
                    yield event
                continue

            if line.startswith("event:"):
                event_type = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].lstrip())

        event = self._parse_sse_event(event_type, data_lines)
        if event is not None:
            yield event

    def _parse_sse_event(
        self, event_type: Optional[str], data_lines: List[str]
    ) -> Optional[Dict[str, Any]]:
        """Convert buffered SSE data to JSON."""
        if not data_lines:
            return None

        data = "\n".join(data_lines).strip()
        if not data or data == "[DONE]":
            return None

        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            logger.debug(f"Skipping non-JSON SSE payload ({event_type}): {data!r}")
            return None

        if isinstance(payload, dict) and "type" not in payload and event_type:
            payload["type"] = event_type

        return payload if isinstance(payload, dict) else None

    def _serialize_tool_input(self, value: Any) -> str:
        """Serialize initial tool input fragments."""
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False)

    def _flush_tool_calls(
        self, tool_call_buffer: Dict[str, Dict[str, Any]]
    ) -> List[StreamChunk]:
        """Convert buffered tool call fragments to output chunks."""
        chunks: List[StreamChunk] = []
        for tc_data in tool_call_buffer.values():
            if not tc_data.get("name"):
                continue

            args_str = (tc_data.get("arguments") or "").strip()
            if not args_str:
                arguments: Dict[str, Any] = {}
            else:
                try:
                    arguments = json.loads(args_str)
                except json.JSONDecodeError as e:
                    logger.error(f"JSON parse failed: {e}, raw: {args_str!r}")
                    arguments = {
                        _TOOL_ARGUMENT_PARSE_ERROR_KEY: f"{type(e).__name__}: {e}",
                        _TOOL_ARGUMENT_RAW_KEY: args_str,
                    }

            chunks.append(
                StreamChunk(
                    tool_call=ToolCall(
                        id=tc_data.get("id") or "call_unknown",
                        name=tc_data["name"],
                        arguments=arguments,
                    )
                )
            )

        return chunks

    def _build_usage(
        self,
        input_tokens: int,
        output_tokens: int,
        cache_read_input_tokens: int = 0,
        cache_creation_input_tokens: int = 0,
    ) -> Optional[Dict[str, int]]:
        """Build a common usage payload, including prompt cache metrics."""
        if not input_tokens and not output_tokens:
            return None
        usage: Dict[str, int] = {
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }
        if cache_read_input_tokens:
            usage["cache_read_input_tokens"] = cache_read_input_tokens
        if cache_creation_input_tokens:
            usage["cache_creation_input_tokens"] = cache_creation_input_tokens
        return usage

    def _is_timeout_error(self, error: Exception) -> bool:
        """Detect timeout-like errors."""
        if isinstance(error, httpx.TimeoutException):
            return True

        err_str = str(error).lower()
        return any(token in err_str for token in ("timeout", "timed out", "read error", "socket"))

    def get_default_model(self) -> str:
        """Return the configured default model."""
        return self.default_model or "claude-sonnet-4-6"
