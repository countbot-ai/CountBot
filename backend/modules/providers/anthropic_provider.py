"""Anthropic provider with SDK and raw HTTP fallback support."""

import asyncio
import json
import re
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx
from loguru import logger

from .base import LLMProvider, StreamChunk, ToolCall

_TOOL_ARGUMENT_PARSE_ERROR_KEY = "__tool_argument_parse_error__"
_TOOL_ARGUMENT_RAW_KEY = "__tool_argument_raw__"


class AnthropicProvider(LLMProvider):
    """Anthropic-compatible provider."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        default_model: str = "claude-sonnet-4-20250514",
        timeout: float = 600.0,
        max_retries: int = 3,
        provider_id: Optional[str] = None,
        **kwargs: Any,
    ):
        super().__init__(api_key, api_base, default_model, timeout, max_retries)
        self.provider_id = provider_id

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
            friendly_msg = self._format_error_message(error_msg)
            yield StreamChunk(error=friendly_msg)

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
        system_content, filtered_messages = self._normalize_messages(messages)

        request_params: Dict[str, Any] = {
            "model": model,
            "messages": filtered_messages,
            "stream": True,
        }
        if temperature and temperature > 0:
            request_params["temperature"] = temperature
        resolved_max_tokens = self._resolve_max_tokens(max_tokens)
        if resolved_max_tokens is not None:
            request_params["max_tokens"] = resolved_max_tokens

        if system_content:
            request_params["system"] = system_content

        anthropic_tools = self._convert_tools(tools)
        if anthropic_tools:
            request_params["tools"] = anthropic_tools

        self._apply_thinking_config(request_params, thinking_enabled)
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

            filtered_messages.append(msg)

        system_content = "\n\n".join(system_parts).strip() or None
        return system_content, filtered_messages

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
                anthropic_tools.append(tool)

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
    ) -> None:
        """Inject Anthropic extended thinking config when enabled."""
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
                if attempt < self.max_retries:
                    wait = min(2**attempt, 30)
                    logger.warning(
                        f"Anthropic SDK request failed ({attempt}/{self.max_retries}), "
                        f"retrying in {wait}s: {e}"
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
                            usage=self._build_usage(input_tokens, output_tokens),
                        )
                        stream_done = True

                if not stream_done:
                    stream_done = True
                    yield StreamChunk(finish_reason="stop")

            except Exception as stream_err:
                if self._is_timeout_error(stream_err):
                    if not content_yielded and stream_retry < max_stream_retries:
                        stream_retry += 1
                        wait = min(2**stream_retry, 30)
                        logger.warning(
                            f"Anthropic SDK stream timeout ({stream_retry}/{max_stream_retries}), "
                            f"retrying in {wait}s: {stream_err}"
                        )
                        await asyncio.sleep(wait)
                        stream = await client.messages.create(**request_params)
                        tool_call_buffer = {}
                        content_block_buffer = {}
                        chunk_count = 0
                        continue

                    if content_yielded:
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
        request_payload = dict(request_params)
        injected_fallback_max_tokens = False

        for attempt in range(1, self.max_retries + 1):
            tool_call_buffer: Dict[str, Dict[str, Any]] = {}
            content_block_buffer: Dict[str, Dict[str, Any]] = {}
            chunk_count = 0
            content_yielded = False
            input_tokens = 0
            output_tokens = 0
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

                            elif event_type == "content_block_start":
                                block = event.get("content_block") or {}
                                self._register_content_block_start(
                                    content_block_buffer,
                                    event.get("index", 0),
                                    block,
                                )
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

                            elif event_type == "message_delta":
                                delta = event.get("delta") or {}
                                finish_reason = delta.get("stop_reason") or finish_reason
                                usage = event.get("usage") or {}
                                output_tokens = usage.get("output_tokens", output_tokens)

                            elif event_type == "message_stop":
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
                                    usage=self._build_usage(input_tokens, output_tokens),
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

                if attempt < self.max_retries:
                    wait = min(2**attempt, 30)
                    logger.warning(
                        f"Anthropic HTTP request failed ({attempt}/{self.max_retries}), "
                        f"retrying in {wait}s: {e}"
                    )
                    await asyncio.sleep(wait)
                    continue

                raise

    def _build_messages_url(self) -> str:
        """Resolve the messages endpoint from api_base."""
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
        self, input_tokens: int, output_tokens: int
    ) -> Optional[Dict[str, int]]:
        """Build a common usage payload."""
        if not input_tokens and not output_tokens:
            return None
        return {
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }

    def _is_timeout_error(self, error: Exception) -> bool:
        """Detect timeout-like errors."""
        if isinstance(error, httpx.TimeoutException):
            return True

        err_str = str(error).lower()
        return any(token in err_str for token in ("timeout", "timed out", "read error", "socket"))

    @staticmethod
    def _format_error_message(raw: str) -> str:
        """Convert raw provider errors to user-facing messages."""
        lower = raw.lower()

        if lower in {"", "readtimeout", "timeoutexception"}:
            return "请求超时，请检查 Base URL 是否正确，或稍后重试。"

        if "no module named 'anthropic'" in lower or 'no module named "anthropic"' in lower:
            return "未安装 anthropic Python 依赖，或当前运行环境未打包该模块。"

        if any(k in lower for k in ("429", "rate limit", "quota")):
            return "请求过于频繁或 API 配额已用尽，请稍后重试并检查额度。"

        if any(k in lower for k in ("401", "unauthorized", "invalid api key", "authentication")):
            return "API 密钥无效或已过期，请检查并更新。"

        if "http 404: not found" in lower:
            return "接口地址不存在，请检查 Base URL 是否为 Anthropic 兼容入口。"

        if any(k in lower for k in ("404", "model not found", "model_not_found")):
            return "所选模型不可用，请确认模型名称是否正确。"

        if any(k in lower for k in ("context length", "max token", "too long")):
            return "上下文过长，请减少历史消息或缩短输入。"

        if any(k in lower for k in ("500", "502", "503", "504", "internal server error")):
            return "AI 服务暂时不可用，请稍后重试。"

        if any(k in lower for k in ("timeout", "connection", "network", "ssl")):
            return "网络连接异常，请检查网络或代理设置。"

        return f"AI 调用出错: {raw[:200]}"

    def get_default_model(self) -> str:
        """Return the configured default model."""
        return self.default_model or "claude-sonnet-4-20250514"
