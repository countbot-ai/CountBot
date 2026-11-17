"""OpenAI Responses API（/v1/responses）实现：对外只产出 StreamChunk，全程无状态（store=false），靠 call_id 配对续轮。"""

import asyncio
import json
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

from loguru import logger

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
    format_responses_error,
    is_timeout_exception,
    parse_json_arguments,
    summarize_responses_error_for_log,
)

from .thinking_profiles import is_reasoning_off, resolve_supported_reasoning_level
from backend.modules.native_caps import (
    build_provider_overrides,
    resolve_native_capabilities,
)
from backend.modules.native_caps import events as native_events
from backend.modules.native_caps.deepseek import merge_tools
from backend.modules.native_caps.registry import PROTOCOL_RESPONSES


# 上游 status 终态（incomplete/failed）需翻译成 finish_reason 供上层判断截断。
_FINISH_REASON_BY_STATUS = {
    "completed": "stop",
    "incomplete": "length",
    "failed": "error",
    "cancelled": "stop",
}


class OpenAIResponsesProvider(LLMProvider):
    """OpenAI Responses API 实现（也可用于任何兼容 /responses 的上游）"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        default_model: str = "gpt-5.3",
        api_mode: str = "responses",
        timeout: float = 600.0,
        max_retries: int = 3,
        provider_id: Optional[str] = None,
        **kwargs: Any,
    ):
        super().__init__(api_key, api_base, default_model, timeout, max_retries)
        self.provider_id = provider_id
        self.api_mode = "responses"
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
        """流式聊天补全（Responses API）"""
        try:
            from openai import AsyncOpenAI

            raw_model = model or self.default_model
            model = self._normalize_model_name(raw_model)
            if not model:
                raise ValueError("必须指定模型或设置默认模型")
            if model != raw_model:
                logger.warning(f"模型名已自动规范化: {raw_model} -> {model}")

            logger.info(f"Calling OpenAI Responses: {model}, api_base: {self.api_base}")

            client_kwargs: Dict[str, Any] = {
                "api_key": self.api_key or "not-needed",
                "timeout": self.timeout,
                "max_retries": 0,
            }
            if self.api_base:
                client_kwargs["base_url"] = self.api_base

            client = AsyncOpenAI(**client_kwargs)

            kwargs.pop("api_mode", None)

            async for chunk in self._chat_stream_via_responses(
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
            log_summary = summarize_responses_error_for_log(e)
            if self._is_expected_upstream_error(e):
                logger.error(
                    f"OpenAI Responses call failed [{type(e).__name__}]: {log_summary}"
                )
            else:
                logger.exception(
                    f"OpenAI Responses call failed [{type(e).__name__}]: {log_summary}"
                )
            yield StreamChunk(
                error=format_responses_error(error_msg), raw_error=error_msg
            )

    async def _chat_stream_via_responses(
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
        request_trace_id = (
            str(kwargs.pop("request_trace_id", "")).strip() or uuid.uuid4().hex[:8]
        )
        stream_enabled = bool(kwargs.pop("stream_enabled", self.stream_enabled))
        instructions, input_items = self._build_responses_input(messages)

        request_params: Dict[str, Any] = {
            "model": model,
            "input": input_items,
            "stream": stream_enabled,
            # 无状态：不依赖上游保存会话，历史由本地完整回放
            "store": False,
        }

        if instructions:
            request_params["instructions"] = instructions

        # 推理模型（gpt-5 / o 系列）不接受 temperature，只有显式设置时才带
        if temperature and temperature > 0:
            request_params["temperature"] = temperature

        if max_tokens and max_tokens > 0:
            request_params["max_output_tokens"] = max_tokens

        if tools:
            request_params["tools"] = self._convert_tools_for_responses(tools)
            request_params["tool_choice"] = "auto"

        native_caps = resolve_native_capabilities(
            self.provider_id, model, self.native_capabilities
        )
        native_overrides = build_provider_overrides(
            provider_id=self.provider_id,
            model=model,
            protocol=PROTOCOL_RESPONSES,
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
            extra_body = dict(request_params.get("extra_body") or {})
            extra_body["safety_check"] = native_overrides["safety_check"]
            request_params["extra_body"] = extra_body

        thinking_enabled = kwargs.get("thinking_enabled")
        self._apply_reasoning_config(
            request_params,
            thinking_enabled,
            kwargs.get("reasoning_level"),
        )

        logger.debug(
            f"OpenAI Responses 请求参数 [trace={request_trace_id}]: "
            + json.dumps(
                {
                    k: v
                    for k, v in request_params.items()
                    if k not in ["input", "api_key"]
                },
                ensure_ascii=False,
            )
        )
        logger.debug(
            f"OpenAI Responses 输入项统计 [trace={request_trace_id}]: "
            + self._summarize_input_items(input_items)
        )

        if not stream_enabled:
            response = await self._create_stream_with_retry(
                client, request_params, request_trace_id
            )
            for chunk in self._convert_response_to_chunks(response):
                yield chunk
            return

        stream = await self._create_stream_with_retry(
            client, request_params, request_trace_id
        )

        tool_call_buffer: Dict[str, Dict[str, Any]] = {}
        content_yielded = False
        stream_done = False
        stream_retry = 0
        max_stream_retries = self.max_retries
        completed_response: Optional[Any] = None

        while not stream_done and stream_retry <= max_stream_retries:
            try:
                async for event in stream:
                    event_type = str(getattr(event, "type", "") or "")

                    if event_type == "response.output_text.delta":
                        delta = getattr(event, "delta", None)
                        if delta:
                            content_yielded = True
                            yield StreamChunk(content=delta)
                        continue

                    if event_type in (
                        "response.reasoning_summary_text.delta",
                        "response.reasoning_text.delta",
                    ):
                        delta = getattr(event, "delta", None)
                        if delta:
                            content_yielded = True
                            # 上游偶尔只回零宽字符占位，照抄会让前端渲染出空的思考块
                            if has_visible_text(delta):
                                yield StreamChunk(reasoning_content=delta)
                        continue

                    if event_type == "response.output_item.added":
                        self._register_function_call_item(
                            event, tool_call_buffer, request_trace_id
                        )
                        continue

                    if event_type == "response.function_call_arguments.delta":
                        self._append_tool_arguments(
                            event, tool_call_buffer, request_trace_id
                        )
                        content_yielded = True
                        continue

                    if event_type == "response.output_item.done":
                        # 个别上游不发送 arguments.delta，只在 done 时给完整参数
                        self._finalize_function_call_item(
                            event, tool_call_buffer, request_trace_id
                        )
                        item = getattr(event, "item", None)
                        item_events = native_events.responses_item_events(item)
                        if item_events:
                            yield StreamChunk(native_events=item_events)
                        continue

                    if event_type in ("response.completed", "response.incomplete"):
                        completed_response = getattr(event, "response", None)
                        break

                    if event_type in ("response.failed", "error"):
                        raise RuntimeError(self._extract_failure_message(event))

                if completed_response is None:
                    # 上游未发送终态事件就断流：按已累积内容收尾
                    stream_done = True
                    for pending in tool_call_buffer.values():
                        tool_call = self._yield_tool_call(pending)
                        if tool_call is not None:
                            yield StreamChunk(tool_call=tool_call)
                    yield StreamChunk(finish_reason="stop")
                    break

                stream_done = True
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

                yield StreamChunk(
                    finish_reason=self._resolve_finish_reason(completed_response),
                    usage=self._extract_usage(completed_response),
                    provider_payload=self._build_provider_payload(completed_response),
                )

            except Exception as stream_err:
                is_timeout = is_timeout_exception(stream_err)

                if (
                    not content_yielded
                    and is_retryable_error(stream_err)
                    and stream_retry < max_stream_retries
                ):
                    stream_retry += 1
                    wait = retry_backoff_seconds(stream_retry, stream_err)
                    logger.warning(
                        f"OpenAI Responses 流中断 [trace={request_trace_id}]"
                        f"（第{stream_retry}/{max_stream_retries}次），"
                        f"{wait:.1f}s 后重试: "
                        f"{summarize_responses_error_for_log(stream_err)}"
                    )
                    await asyncio.sleep(wait)
                    stream = await client.responses.create(**request_params)
                    tool_call_buffer = {}
                elif content_yielded and is_timeout:
                    logger.warning(
                        f"OpenAI Responses 流式读取超时 [trace={request_trace_id}]"
                        f"（已产生输出），优雅截断并结束流: {stream_err}"
                    )
                    yield StreamChunk(finish_reason="length")
                    stream_done = True
                else:
                    raise

    @staticmethod
    def _to_data(payload: Any) -> Dict[str, Any]:
        """SDK 对象 / dict 统一转成 dict，便于非流式响应解析。"""
        if isinstance(payload, dict):
            return payload
        if hasattr(payload, "model_dump"):
            return payload.model_dump()
        return {}

    def _convert_response_to_chunks(self, response: Any) -> List[StreamChunk]:
        """非流式 Responses 响应 -> 统一 StreamChunk 序列。"""
        data = self._to_data(response)
        chunks: List[StreamChunk] = []
        reasoning_ids: List[str] = []
        has_tool_calls = False

        for item in data.get("output") or []:
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type") or "")
            item_events = native_events.responses_item_events(item)
            if item_events:
                chunks.append(StreamChunk(native_events=item_events))

            if item_type == "reasoning":
                item_id = str(item.get("id") or "").strip()
                if item_id:
                    reasoning_ids.append(item_id)
                reasoning_text = self._collect_reasoning_text(item)
                if reasoning_text and has_visible_text(reasoning_text):
                    chunks.append(StreamChunk(reasoning_content=reasoning_text))
                continue

            if item_type == "message":
                for content in item.get("content") or []:
                    if not isinstance(content, dict):
                        continue
                    if content.get("type") in ("output_text", "text"):
                        text = str(content.get("text") or "")
                        if text:
                            chunks.append(StreamChunk(content=text))
                continue

            if item_type == "function_call":
                name = str(item.get("name") or "")
                if not name:
                    continue
                has_tool_calls = True
                raw_arguments = item.get("arguments") or ""
                if not isinstance(raw_arguments, str):
                    raw_arguments = json.dumps(raw_arguments, ensure_ascii=False)
                chunks.append(
                    StreamChunk(
                        tool_call=ToolCall(
                            id=str(item.get("call_id") or item.get("id") or "call_unknown"),
                            name=name,
                            arguments=parse_json_arguments(raw_arguments),
                        )
                    )
                )

        finish_reason = self._resolve_finish_reason_from_data(data, has_tool_calls)
        payload = (
            {"openai_reasoning_ids": reasoning_ids} if reasoning_ids else None
        )
        chunks.append(
            StreamChunk(
                finish_reason=finish_reason,
                usage=self._extract_usage_from_data(data),
                provider_payload=payload,
            )
        )
        return chunks

    @staticmethod
    def _collect_reasoning_text(item: Dict[str, Any]) -> str:
        parts: List[str] = []
        for field in ("summary", "content"):
            for entry in item.get(field) or []:
                if not isinstance(entry, dict):
                    continue
                text = entry.get("text")
                if text:
                    parts.append(str(text))
        return "".join(parts)

    @staticmethod
    def _resolve_finish_reason_from_data(
        data: Dict[str, Any],
        has_tool_calls: bool,
    ) -> str:
        if has_tool_calls:
            return "tool_calls"
        status = str(data.get("status") or "").strip().lower()
        finish_reason = _FINISH_REASON_BY_STATUS.get(status, "stop")
        if finish_reason == "length":
            details = data.get("incomplete_details") or {}
            reason = str(details.get("reason") or "").strip().lower()
            if reason == "content_filter":
                return "content_filter"
            return "length"
        return finish_reason

    @staticmethod
    def _extract_usage_from_data(data: Dict[str, Any]) -> Optional[Dict[str, int]]:
        usage = data.get("usage")
        if not isinstance(usage, dict):
            return None
        input_tokens = int(usage.get("input_tokens") or 0)
        output_tokens = int(usage.get("output_tokens") or 0)
        total_tokens = int(
            usage.get("total_tokens") or (input_tokens + output_tokens)
        )
        extracted: Dict[str, int] = {
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": total_tokens,
        }
        input_details = usage.get("input_tokens_details") or {}
        cached_tokens = read_usage_detail_int(input_details, "cached_tokens")
        if cached_tokens:
            extracted["cache_read_tokens"] = cached_tokens
        cache_write_tokens = read_usage_detail_int(
            input_details, "cache_write_tokens"
        )
        if cache_write_tokens:
            extracted["cache_write_tokens"] = cache_write_tokens
        reasoning_tokens = read_usage_detail_int(
            usage.get("output_tokens_details") or {}, "reasoning_tokens"
        )
        if reasoning_tokens:
            extracted["reasoning_tokens"] = reasoning_tokens
        return extracted

    async def _create_stream_with_retry(
        self,
        client: Any,
        request_params: Dict[str, Any],
        request_trace_id: str,
    ) -> Any:
        """建立流式连接；仅对非鉴权错误做退避重试。"""
        max_attempts = max(1, self.max_retries)
        attempt = 1
        while attempt <= max_attempts:
            try:
                return await client.responses.create(**request_params)
            except Exception as e:
                if not is_retryable_error(e):
                    logger.warning(
                        f"OpenAI Responses 不可重试错误 [trace={request_trace_id}]，"
                        f"直接上抛: {summarize_responses_error_for_log(e)}"
                    )
                    raise
                if attempt < max_attempts:
                    wait = retry_backoff_seconds(attempt, e)
                    logger.warning(
                        f"OpenAI Responses 调用失败 [trace={request_trace_id}] "
                        f"(第{attempt}/{max_attempts}次)，{wait:.1f}s 后重试: "
                        f"{summarize_responses_error_for_log(e)}"
                    )
                    attempt += 1
                    await asyncio.sleep(wait)
                else:
                    raise
        raise RuntimeError("OpenAI Responses 调用失败：重试次数耗尽")

    # ------------------------------------------------------------------
    # 请求侧：内部消息 -> responses input items
    # ------------------------------------------------------------------

    def _build_responses_input(
        self,
        messages: List[Dict[str, Any]],
    ) -> tuple[str, List[Dict[str, Any]]]:
        """把内部 chat 形态消息转成 responses 的 instructions + input。

        - system / developer 合并进 instructions（responses 没有 system 消息）
        - assistant.tool_calls -> function_call item（call_id 原样保留）
        - role=tool -> function_call_output item
        """
        instruction_parts: List[str] = []
        input_items: List[Dict[str, Any]] = []

        for message in messages:
            role = str(message.get("role", "") or "").strip()
            if role not in {"system", "developer", "user", "assistant", "tool"}:
                continue

            if role in {"system", "developer"}:
                text = self._flatten_text(message.get("content"))
                if text:
                    instruction_parts.append(text)
                continue

            if role == "tool":
                call_id = str(message.get("tool_call_id") or "").strip()
                if not call_id:
                    continue
                input_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": self._flatten_text(message.get("content")),
                    }
                )
                continue

            if role == "user":
                content = self._convert_content_for_responses(message.get("content"))
                if content:
                    input_items.append(
                        {"type": "message", "role": "user", "content": content}
                    )
                continue

            # assistant；assistant 只能带 output_text，用 input_text 会被上游 400
            content = self._convert_content_for_responses(
                message.get("content"), text_part_type="output_text"
            )
            if content:
                input_items.append(
                    {"type": "message", "role": "assistant", "content": content}
                )
            for tool_call in message.get("tool_calls") or []:
                if not isinstance(tool_call, dict):
                    continue
                function = tool_call.get("function") or {}
                name = str(function.get("name") or "").strip()
                if not name:
                    continue
                input_items.append(
                    {
                        "type": "function_call",
                        "call_id": str(tool_call.get("id") or "").strip()
                        or f"call_{uuid.uuid4().hex[:16]}",
                        "name": name,
                        "arguments": self._normalize_arguments_text(
                            function.get("arguments")
                        ),
                    }
                )

        return "\n\n".join(instruction_parts), input_items

    @staticmethod
    def _flatten_text(content: Any) -> str:
        """把任意内部 content 压平成纯文本（用于 instructions / 工具输出）。"""
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: List[str] = []
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                    continue
                if not isinstance(block, dict):
                    continue
                if str(block.get("type") or "").lower() == "text":
                    parts.append(str(block.get("text") or ""))
            return "\n".join(p for p in parts if p)
        return str(content)

    @staticmethod
    def _convert_content_for_responses(
        content: Any,
        *,
        text_part_type: str = "input_text",
    ) -> List[Dict[str, Any]]:
        """内部 content -> responses content parts（input_text / input_image）。

        text_part_type 由角色决定：user/system 用 input_text，
        assistant 用 output_text（上游对 assistant 只接受 output_text/refusal）。
        """
        if content is None:
            return []
        if isinstance(content, str):
            return [{"type": text_part_type, "text": content}] if content else []

        converted: List[Dict[str, Any]] = []
        if isinstance(content, list):
            for block in content:
                if isinstance(block, str):
                    if block:
                        converted.append({"type": text_part_type, "text": block})
                    continue
                if not isinstance(block, dict):
                    continue
                block_type = str(block.get("type") or "").strip().lower()
                if block_type == "text":
                    text = str(block.get("text") or "")
                    if text:
                        converted.append({"type": text_part_type, "text": text})
                    continue
                if block_type == "file":
                    file_id = str(block.get("file_id") or "").strip()
                    if file_id:
                        converted.append({"type": "input_file", "file_id": file_id})
                    continue
                if block_type != "image":
                    continue
                media_type = (
                    str(block.get("media_type") or "image/png").strip() or "image/png"
                )
                data = str(block.get("data") or "").strip()
                if not data:
                    continue
                converted.append(
                    {
                        "type": "input_image",
                        "image_url": f"data:{media_type};base64,{data}",
                    }
                )
        return converted

    @staticmethod
    def _normalize_arguments_text(raw: Any) -> str:
        """工具参数统一成 JSON 字符串，responses 不接受对象形态。"""
        if raw is None:
            return "{}"
        if isinstance(raw, str):
            text = raw.strip()
            return text or "{}"
        try:
            return json.dumps(raw, ensure_ascii=False)
        except (TypeError, ValueError):
            return "{}"

    @staticmethod
    def _convert_tools_for_responses(
        tools: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """chat.completions 的嵌套 function 工具定义 -> responses 扁平定义。"""
        converted: List[Dict[str, Any]] = []
        for tool in tools:
            if not isinstance(tool, dict):
                continue
            function = tool.get("function")
            if isinstance(function, dict):
                name = str(function.get("name") or "").strip()
                if not name:
                    continue
                item: Dict[str, Any] = {
                    "type": "function",
                    "name": name,
                    "parameters": function.get("parameters") or {"type": "object"},
                }
                description = function.get("description")
                if description:
                    item["description"] = str(description)
                converted.append(item)
            elif tool.get("type") == "function" and tool.get("name"):
                # 已经是 responses 形态
                converted.append(dict(tool))
        return converted

    def _apply_reasoning_config(
        self,
        request_params: Dict[str, Any],
        thinking_enabled: Optional[bool],
        reasoning_level: Optional[str] = None,
    ) -> None:
        """把内部思考开关 / 档位映射到 responses 的 reasoning.effort / summary。

        chat.completions 那套 provider 专属字段（extra_body.thinking /
        enable_thinking / reasoning_effort）在 responses 上无意义，必须丢弃，
        否则上游直接 400。显式档位优先：命中档位时原样作为 effort 下发
        （档位表之外的模型也支持，用户自定义档位不会被拦）。
        思考摘要不是默认行为：不显式请求 summary，上游一个思考事件都不发，
        前端就只剩耗时、没有思考内容。
        """
        request_params.pop("thinking_enabled", None)

        supported_level = resolve_supported_reasoning_level(
            reasoning_level,
            model=str(request_params.get("model") or ""),
        )
        if supported_level is not None:
            if is_reasoning_off(supported_level):
                # 官方 Responses 用 reasoning.effort=none 关闭思考；
                # 仅官方 openai 老代际需要按模型收敛，避免不支持的 effort 值。
                from .thinking_profiles import _resolve_openai_reasoning_effort

                provider_id = (self.provider_id or "").strip().lower()
                if provider_id in ("", "openai"):
                    off_effort = _resolve_openai_reasoning_effort(
                        model=str(request_params.get("model") or ""),
                        thinking_enabled=False,
                    )
                else:
                    off_effort = "none"

                reasoning: Dict[str, Any] = {"summary": None}
                if off_effort:
                    reasoning["effort"] = off_effort
                request_params["reasoning"] = reasoning
                return

            request_params["reasoning"] = {
                "effort": supported_level,
                "summary": "auto",
            }
            return

        if thinking_enabled is None:
            return

        reasoning = {}
        if thinking_enabled:
            effort = self._resolve_reasoning_effort(
                model=str(request_params.get("model") or ""),
            )
            if effort:
                reasoning["effort"] = effort
            reasoning["summary"] = "auto"
        else:
            # reasoning item 无法单独关闭（模型自己决定），关闭思考时只关摘要以省 token
            reasoning["summary"] = None

        if reasoning:
            request_params["reasoning"] = reasoning

    @staticmethod
    def _resolve_reasoning_effort(model: str) -> Optional[str]:
        from .thinking_profiles import _resolve_openai_reasoning_effort

        return _resolve_openai_reasoning_effort(model=model, thinking_enabled=True)

    # ------------------------------------------------------------------
    # 流式事件解析
    # ------------------------------------------------------------------

    def _register_function_call_item(
        self,
        event: Any,
        buffer: Dict[str, Dict[str, Any]],
        trace_id: str,
    ) -> None:
        item = getattr(event, "item", None)
        if item is None or getattr(item, "type", "") != "function_call":
            return
        self._upsert_function_call(item, buffer, trace_id)

    def _finalize_function_call_item(
        self,
        event: Any,
        buffer: Dict[str, Dict[str, Any]],
        trace_id: str,
    ) -> None:
        item = getattr(event, "item", None)
        if item is None or getattr(item, "type", "") != "function_call":
            return
        entry = self._upsert_function_call(item, buffer, trace_id)
        full_arguments = getattr(item, "arguments", None)
        # 仅在无 delta 时用 done 里的完整参数兜底，否则会与已累积 delta 重复拼接
        if full_arguments and not entry["arguments"]:
            entry["arguments"] = str(full_arguments)

    def _upsert_function_call(
        self,
        item: Any,
        buffer: Dict[str, Dict[str, Any]],
        trace_id: str,
    ) -> Dict[str, Any]:
        call_id = str(getattr(item, "call_id", "") or "").strip()
        item_id = str(getattr(item, "id", "") or "").strip()
        # delta 事件只带 item_id，故缓冲 key 用 item.id；call_id 仅作对外 ToolCall.id
        key = item_id or call_id or f"call_{len(buffer)}"

        entry = buffer.get(key)
        if entry is None:
            entry = {
                "id": call_id or item_id or key,
                "name": "",
                "arguments": "",
                # output_index 用于 delta 缺 item_id 时回查
                "output_index": getattr(item, "output_index", None),
            }
            buffer[key] = entry
            logger.debug(
                f"Responses 工具调用开始 [trace={trace_id}]: key={key}, "
                f"name={getattr(item, 'name', '')}"
            )

        name = str(getattr(item, "name", "") or "").strip()
        if name:
            entry["name"] = name
        return entry

    def _append_tool_arguments(
        self,
        event: Any,
        buffer: Dict[str, Dict[str, Any]],
        trace_id: str,
    ) -> None:
        delta = str(getattr(event, "delta", "") or "")
        if not delta:
            return

        key = str(getattr(event, "item_id", "") or "").strip()
        entry = buffer.get(key)
        if entry is None:
            # 部分上游只在 arguments.delta 上给 output_index
            output_index = getattr(event, "output_index", None)
            entry = next(
                (
                    candidate
                    for candidate in buffer.values()
                    if output_index is not None
                    and candidate.get("output_index") == output_index
                ),
                None,
            )
        if entry is None:
            logger.warning(
                f"Responses 工具参数无法匹配调用项 [trace={trace_id}]: "
                f"item_id={key or '<empty>'}, delta={delta[:80]!r}"
            )
            return

        entry["arguments"] += delta

    @staticmethod
    def _resolve_finish_reason(response: Any) -> str:
        status = str(getattr(response, "status", "") or "").strip().lower()
        finish_reason = _FINISH_REASON_BY_STATUS.get(status, "stop")

        if finish_reason == "length":
            details = getattr(response, "incomplete_details", None)
            reason = str(getattr(details, "reason", "") or "").strip().lower()
            # content_filter 与 max_output_tokens 均属 incomplete，前者单列以便上层区分过滤与截断
            if reason == "content_filter":
                return "content_filter"
            return "length"

        # 有工具调用时优先标记 tool_calls，保持与 chat.completions 一致
        for item in getattr(response, "output", None) or []:
            if getattr(item, "type", "") == "function_call":
                return "tool_calls"

        return finish_reason

    @staticmethod
    def _extract_usage(response: Any) -> Optional[Dict[str, int]]:
        usage = getattr(response, "usage", None)
        if usage is None:
            return None
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        total_tokens = int(
            getattr(usage, "total_tokens", 0) or (input_tokens + output_tokens)
        )
        extracted: Dict[str, int] = {
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": total_tokens,
        }
        # 缓存命中/写入与推理 token 只在 *_details 子对象里，顶层没有；
        # 不显式带出来会让缓存命中与推理统计永远记成 0。
        input_details = getattr(usage, "input_tokens_details", None)
        cached_tokens = read_usage_detail_int(input_details, "cached_tokens")
        if cached_tokens:
            extracted["cache_read_tokens"] = cached_tokens
        cache_write_tokens = read_usage_detail_int(input_details, "cache_write_tokens")
        if cache_write_tokens:
            extracted["cache_write_tokens"] = cache_write_tokens
        reasoning_tokens = read_usage_detail_int(
            getattr(usage, "output_tokens_details", None), "reasoning_tokens"
        )
        if reasoning_tokens:
            extracted["reasoning_tokens"] = reasoning_tokens
        return extracted

    @staticmethod
    def _build_provider_payload(response: Any) -> Optional[Dict[str, Any]]:
        """记录 reasoning item 的 id，供后续排查（不回放给上游）。"""
        reasoning_ids: List[str] = []
        for item in getattr(response, "output", None) or []:
            if getattr(item, "type", "") == "reasoning":
                item_id = str(getattr(item, "id", "") or "").strip()
                if item_id:
                    reasoning_ids.append(item_id)
        if not reasoning_ids:
            return None
        return {"openai_reasoning_ids": reasoning_ids}

    @staticmethod
    def _extract_failure_message(event: Any) -> str:
        response = getattr(event, "response", None)
        for candidate in (
            getattr(response, "error", None),
            getattr(event, "error", None),
            event,
        ):
            if candidate is None:
                continue
            message = getattr(candidate, "message", None)
            if message:
                return str(message)
            code = getattr(candidate, "code", None)
            if code:
                return str(code)
        return "上游返回失败事件"

    # ------------------------------------------------------------------
    # 通用辅助
    # ------------------------------------------------------------------

    @staticmethod
    def _summarize_input_items(input_items: List[Dict[str, Any]]) -> str:
        counts: Dict[str, int] = {}
        for item in input_items:
            item_type = str(item.get("type") or "unknown")
            if item_type == "message":
                item_type = f"message:{item.get('role', '')}"
            counts[item_type] = counts.get(item_type, 0) + 1
        return json.dumps(counts, ensure_ascii=False)

    @staticmethod
    def _yield_tool_call(tc_data: Dict[str, Any]) -> Optional[ToolCall]:
        """把缓冲区里的工具调用转成 ToolCall；无名称时返回 None。"""
        if not tc_data.get("name"):
            return None
        return ToolCall(
            id=tc_data["id"],
            name=tc_data["name"],
            arguments=parse_json_arguments(
                tc_data["arguments"]
            ),
        )

    @staticmethod
    def _normalize_model_name(model: Optional[str]) -> str:
        return str(model or "").strip()

    @staticmethod
    def _is_expected_upstream_error(error: Exception) -> bool:
        try:
            import openai

            expected = tuple(
                cls
                for cls in (
                    getattr(openai, "APIStatusError", None),
                    getattr(openai, "APIConnectionError", None),
                )
                if cls is not None
            )
            return bool(expected) and isinstance(error, expected)
        except Exception:
            return False

    def get_default_model(self) -> str:
        """获取默认模型"""
        return self.default_model or "gpt-5.3"
