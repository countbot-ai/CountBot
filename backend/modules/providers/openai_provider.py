"""OpenAI Provider — 使用官方 SDK"""

import asyncio
import json
import re
from typing import Any, AsyncIterator, Dict, List, Optional

from loguru import logger

from .base import LLMProvider, StreamChunk, ToolCall


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

    async def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
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
        request_params: Dict[str, Any] = {
            "model": model,
            "messages": self._sanitize_messages_for_chat_completions(messages),
            "temperature": temperature,
            "stream": True,
        }

        if max_tokens and max_tokens > 0:
            request_params["max_tokens"] = max_tokens

        if tools:
            request_params["tools"] = tools
            request_params["tool_choice"] = "auto"

        request_params.update(kwargs)
        self._apply_reasoning_config(request_params, kwargs.get("thinking_enabled"))

        logger.debug(
            "OpenAI params: "
            + json.dumps(
                {k: v for k, v in request_params.items() if k not in ["api_key", "messages"]},
                ensure_ascii=False,
            )
        )

        stream = None
        max_attempts = max(1, self.max_retries)
        for attempt in range(1, max_attempts + 1):
            try:
                stream = await client.chat.completions.create(**request_params)
                break
            except Exception as e:
                error_summary = self._summarize_error_for_log(e)
                if attempt < max_attempts:
                    wait = min(2 ** attempt, 30)
                    logger.warning(
                        f"OpenAI 调用失败 (第{attempt}/{max_attempts}次)，"
                        f"{wait}s 后重试: {error_summary}"
                    )
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
            return {"raw": args_str}

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

        provider_id = (self.provider_id or "").lower()
        api_base = (self.api_base or "").lower()
        is_official_openai = provider_id == "openai" or "api.openai.com" in api_base
        if is_official_openai:
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

    @staticmethod
    def _sanitize_messages_for_chat_completions(
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
    def _is_expected_upstream_error(cls, error: Exception) -> bool:
        status_code = cls._extract_status_code(error)
        if status_code is not None and status_code >= 400:
            return True

        if cls._is_timeout_exception(error):
            return True

        raw = cls._extract_error_text(error).lower()
        return "<html" in raw or "<!doctype html" in raw

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
