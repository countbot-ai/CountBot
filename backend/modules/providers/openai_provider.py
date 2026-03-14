"""OpenAI Provider — 使用官方 SDK"""

import asyncio
import json
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
        timeout: float = 600.0,
        max_retries: int = 3,
        provider_id: Optional[str] = None,
        **kwargs: Any
    ):
        super().__init__(api_key, api_base, default_model, timeout, max_retries)
        self.provider_id = provider_id
    
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
            
            model = model or self.default_model
            if not model:
                raise ValueError("必须指定模型或设置默认模型")
            
            logger.info(f"Calling OpenAI: {model}, api_base: {self.api_base}")
            
            # 初始化客户端
            client_kwargs: Dict[str, Any] = {
                "api_key": self.api_key or "not-needed",
                "timeout": self.timeout,
                "max_retries": 0,  # 我们自己处理重试
            }
            if self.api_base:
                client_kwargs["base_url"] = self.api_base
            
            client = AsyncOpenAI(**client_kwargs)
            
            # 准备请求参数
            request_params: Dict[str, Any] = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "stream": True,
            }
            
            if max_tokens and max_tokens > 0:
                request_params["max_tokens"] = max_tokens
            
            if tools:
                request_params["tools"] = tools
                request_params["tool_choice"] = "auto"
            
            request_params.update(kwargs)
            
            logger.debug(f"OpenAI params: {json.dumps({k: v for k, v in request_params.items() if k not in ['api_key', 'messages']}, ensure_ascii=False)}")

            # 带指数退避的重试机制
            stream = None
            last_err: Optional[Exception] = None
            for attempt in range(1, self.max_retries + 1):
                try:
                    stream = await client.chat.completions.create(**request_params)
                    break
                except Exception as e:
                    last_err = e
                    if attempt < self.max_retries:
                        wait = min(2 ** attempt, 30)
                        logger.warning(
                            f"OpenAI 调用失败 (第{attempt}/{self.max_retries}次)，"
                            f"{wait}s 后重试: {e}"
                        )
                        await asyncio.sleep(wait)
                    else:
                        logger.error(f"OpenAI 调用最终失败 ({self.max_retries}次重试耗尽): {e}")
                        raise

            tool_call_buffer: Dict[str, Dict[str, Any]] = {}
            reasoning_buffer = ""
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

                        # 处理内容增量
                        if hasattr(delta, "content") and delta.content:
                            content_yielded = True
                            yield StreamChunk(content=delta.content)

                        # 处理推理内容（思考模型如 DeepSeek-R1、o1 等）
                        if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                            reasoning_buffer += delta.reasoning_content
                            content_yielded = True
                            yield StreamChunk(reasoning_content=delta.reasoning_content)

                        # 处理工具调用增量
                        if hasattr(delta, "tool_calls") and delta.tool_calls:
                            content_yielded = True
                            for tc_delta in delta.tool_calls:
                                tc_id = getattr(tc_delta, "id", None)
                                tc_index = getattr(tc_delta, "index", 0)

                                # 统一使用 index 作为 key
                                key = f"index_{tc_index}"

                                # 初始化缓冲区
                                if key not in tool_call_buffer:
                                    tool_call_buffer[key] = {
                                        "id": tc_id or f"call_{tc_index}",
                                        "name": "",
                                        "arguments": ""
                                    }

                                # 更新 ID
                                if tc_id:
                                    tool_call_buffer[key]["id"] = tc_id

                                # 累积工具调用信息
                                if hasattr(tc_delta, "function"):
                                    function = tc_delta.function
                                    if hasattr(function, "name") and function.name:
                                        tool_call_buffer[key]["name"] = function.name
                                    if hasattr(function, "arguments") and function.arguments:
                                        tool_call_buffer[key]["arguments"] += function.arguments

                        # 检查是否完成
                        if choice.finish_reason:
                            # 发送所有累积的工具调用
                            for tc_data in tool_call_buffer.values():
                                if tc_data["name"]:
                                    args_str = tc_data["arguments"].strip()

                                    if not args_str:
                                        arguments = {}
                                    else:
                                        try:
                                            arguments = json.loads(args_str)
                                        except json.JSONDecodeError as e:
                                            logger.error(f"JSON parse failed: {e}, raw: {repr(args_str)}")
                                            arguments = {"raw": args_str}

                                    yield StreamChunk(
                                        tool_call=ToolCall(
                                            id=tc_data["id"],
                                            name=tc_data["name"],
                                            arguments=arguments
                                        )
                                    )

                            # 发送完成信号
                            usage_dict = None
                            if hasattr(chunk, "usage") and chunk.usage:
                                usage_dict = {
                                    "prompt_tokens": getattr(chunk.usage, "prompt_tokens", 0),
                                    "completion_tokens": getattr(chunk.usage, "completion_tokens", 0),
                                    "total_tokens": getattr(chunk.usage, "total_tokens", 0),
                                }

                            yield StreamChunk(
                                finish_reason=choice.finish_reason,
                                usage=usage_dict
                            )
                            stream_done = True
                    
                    # 流正常耗尽
                    if not stream_done:
                        stream_done = True
                        yield StreamChunk(finish_reason="stop")

                except Exception as stream_err:
                    err_str = str(stream_err)
                    is_timeout = any(k in err_str.lower() for k in ("timeout", "timed out", "read error", "socket"))

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
                        reasoning_buffer = ""
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

        except Exception as e:
            error_msg = str(e)
            logger.error(f"OpenAI call failed: {error_msg}")
            friendly_msg = self._format_error_message(error_msg)
            yield StreamChunk(error=friendly_msg)
    
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
    
    async def transcribe(
        self,
        audio_file: bytes,
        model: str = "whisper-1",
        language: Optional[str] = None,
        **kwargs: Any
    ) -> str:
        """转录音频为文本"""
        try:
            from openai import AsyncOpenAI
            import tempfile
            import os
            
            # 初始化客户端
            client_kwargs: Dict[str, Any] = {
                "api_key": self.api_key or "not-needed",
                "timeout": self.timeout,
            }
            if self.api_base:
                client_kwargs["base_url"] = self.api_base
            
            client = AsyncOpenAI(**client_kwargs)
            
            # 创建临时文件
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_file:
                temp_file.write(audio_file)
                temp_path = temp_file.name
            
            try:
                # 准备请求参数
                request_params: Dict[str, Any] = {
                    "model": model,
                    "file": open(temp_path, "rb"),
                }
                
                if language:
                    request_params["language"] = language
                
                request_params.update(kwargs)
                
                # 调用转录
                response = await client.audio.transcriptions.create(**request_params)
                
                return response.text
            
            finally:
                # 清理临时文件
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
        
        except Exception as e:
            raise RuntimeError(f"转录失败: {str(e)}") from e
