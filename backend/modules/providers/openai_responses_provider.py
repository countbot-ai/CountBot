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
    _TOOL_ARGUMENT_PARSE_ERROR_KEY,
    _TOOL_ARGUMENT_RAW_KEY,
    is_auth_error,
    read_usage_detail_int,
    append_upstream_detail,
    has_visible_text,
)

from .thinking_profiles import is_reasoning_off, resolve_supported_reasoning_level


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
            log_summary = self._summarize_error_for_log(e)
            if self._is_expected_upstream_error(e):
                logger.error(
                    f"OpenAI Responses call failed [{type(e).__name__}]: {log_summary}"
                )
            else:
                logger.exception(
                    f"OpenAI Responses call failed [{type(e).__name__}]: {log_summary}"
                )
            yield StreamChunk(
                error=self._format_error_message(error_msg), raw_error=error_msg
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
        instructions, input_items = self._build_responses_input(messages)

        request_params: Dict[str, Any] = {
            "model": model,
            "input": input_items,
            "stream": True,
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
                            arguments=self._parse_json_arguments(tc_data["arguments"]),
                        )
                    )

                yield StreamChunk(
                    finish_reason=self._resolve_finish_reason(completed_response),
                    usage=self._extract_usage(completed_response),
                    provider_payload=self._build_provider_payload(completed_response),
                )

            except Exception as stream_err:
                is_timeout = self._is_timeout_exception(stream_err)
                is_connection = self._is_connection_error(stream_err)

                if (
                    not content_yielded
                    and (is_timeout or is_connection)
                    and stream_retry < max_stream_retries
                ):
                    stream_retry += 1
                    wait = min(2 ** stream_retry, 30)
                    reason = "超时" if is_timeout else "连接中断"
                    logger.warning(
                        f"OpenAI Responses 流读取{reason} [trace={request_trace_id}]"
                        f"（第{stream_retry}/{max_stream_retries}次），{wait}s 后重试: {stream_err}"
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
                if is_auth_error(e):
                    logger.warning(
                        f"OpenAI Responses 认证/密钥错误 [trace={request_trace_id}]，"
                        f"不重试，直接上抛: {self._summarize_error_for_log(e)}"
                    )
                    raise
                if attempt < max_attempts:
                    wait = min(2 ** attempt, 30)
                    logger.warning(
                        f"OpenAI Responses 调用失败 [trace={request_trace_id}] "
                        f"(第{attempt}/{max_attempts}次)，{wait}s 后重试: "
                        f"{self._summarize_error_for_log(e)}"
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
            reasoning: Dict[str, Any] = {"effort": supported_level}
            if not is_reasoning_off(supported_level):
                reasoning["summary"] = "auto"
            request_params["reasoning"] = reasoning
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
    def _yield_tool_call(tc_data: Dict[str, Any]) -> Optional[ToolCall]:
        """把缓冲区里的工具调用转成 ToolCall；无名称时返回 None。"""
        if not tc_data.get("name"):
            return None
        return ToolCall(
            id=tc_data["id"],
            name=tc_data["name"],
            arguments=OpenAIResponsesProvider._parse_json_arguments(
                tc_data["arguments"]
            ),
        )

    @staticmethod
    def _normalize_model_name(model: Optional[str]) -> str:
        return str(model or "").strip()

    @staticmethod
    def _is_timeout_exception(error: Exception) -> bool:
        """超时判定：与 chat.completions 实现保持一致的口径。"""
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
    def _is_connection_error(error: Exception) -> bool:
        """上游在流式响应中途关闭连接等传输层错误。"""
        try:
            import httpx

            if isinstance(
                error,
                (
                    httpx.RemoteProtocolError,
                    httpx.ReadError,
                    httpx.WriteError,
                    httpx.ConnectError,
                ),
            ):
                return True
        except Exception:
            pass

        err_type = type(error).__name__.lower()
        return err_type in {
            "remoteprotocolerror",
            "readerror",
            "writeerror",
            "connecterror",
            "protocolerror",
        }

    @staticmethod
    def _is_auth_error(error: Exception) -> bool:
        return is_auth_error(error)

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

    @staticmethod
    def _summarize_error_for_log(error: Exception) -> str:
        status_code = getattr(error, "status_code", None)
        message = str(error) or repr(error)
        compact = " ".join(message.split())
        if "api_key" in compact.lower() or "apikey" in compact.lower():
            compact = "<redacted>"
        prefix = f"[{status_code}] " if status_code else ""
        return f"{prefix}{type(error).__name__}: {compact[:300]}"

    @staticmethod
    def _format_error_message(raw: str) -> str:
        """将上游原始错误转换为用户友好提示（Responses 侧口径），并附上原始返回。"""
        return append_upstream_detail(
            OpenAIResponsesProvider._friendly_error_message(raw), raw
        )

    @staticmethod
    def _friendly_error_message(raw: str) -> str:
        lower = raw.lower()

        if any(
            k in lower
            for k in ("401", "unauthorized", "invalid api key", "invalid_api_key",
                      "authentication", "invalid token", "api key")
        ):
            return "API 密钥无效或已过期，请在设置中检查并更新密钥。"

        # 余额/欠费类优先：这类响应常同时带 quota 字样，先判余额再判限流
        if any(
            k in lower
            for k in ("余额", "资源包", "充值", "欠费", "insufficient balance",
                      "insufficient_quota", "no credit")
        ) or ("403" in lower and any(k in lower for k in ("quota", "balance", "额度"))):
            return "API 账户余额不足或额度已用尽，请前往服务商控制台充值后重试。"

        if any(
            k in lower
            for k in ("429", "rate limit", "rate_limit", "too many requests",
                      "overloaded", "负载已饱和", "capacity")
        ):
            return "请求过于频繁，上游限流，请稍后重试。"

        if any(
            k in lower
            for k in ("404", "model not found", "model_not_found", "does not exist")
        ):
            return "所选模型不可用，请在设置中确认模型名称是否正确。"

        if any(
            k in lower
            for k in ("/responses", "responses api", "unknown url", "not supported")
        ):
            return (
                "该供应商不支持 Responses API，请在供应商设置中把 API 格式"
                "改为 chat.completions 后重试。"
            )

        if any(
            k in lower
            for k in ("context length", "max_output_tokens", "max.*token",
                      "too long", "context_length_exceeded")
        ):
            return "对话上下文或输出长度超出限制，请尝试新建会话或减少输出长度。"

        if any(k in lower for k in ("timeout", "timed out", "readtimeout")):
            return "请求超时，请稍后重试或检查网络连接。"

        for hint in ("connection error", "network", "ssl", "connection refused"):
            if hint in lower:
                return "网络连接异常，请检查网络设置后重试。"

        # 兜底不再重复拼接原始文本，统一由 append_upstream_detail 附在提示后面
        return "AI 调用出错"

    def get_default_model(self) -> str:
        """获取默认模型"""
        return self.default_model or "gpt-5.3"
