"""Anthropic Provider — 使用官方 SDK"""

import asyncio
import json
from typing import Any, AsyncIterator, Dict, List, Optional
from loguru import logger
from .base import LLMProvider, StreamChunk, ToolCall


class AnthropicProvider(LLMProvider):
    """Anthropic Provider 实现"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        default_model: str = "claude-sonnet-4-20250514",
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
            from anthropic import AsyncAnthropic
            
            model = model or self.default_model
            if not model:
                raise ValueError("必须指定模型或设置默认模型")
            
            logger.info(f"Calling Anthropic: {model}, api_base: {self.api_base}")
            
            # 初始化客户端
            client_kwargs: Dict[str, Any] = {
                "api_key": self.api_key,
                "timeout": self.timeout,
                "max_retries": 0,  # 我们自己处理重试
            }
            if self.api_base:
                client_kwargs["base_url"] = self.api_base
            
            client = AsyncAnthropic(**client_kwargs)
            
            # 转换消息格式以适配 Anthropic API
            # - system 消息提取为独立参数
            # - tool 结果消息转换为 Anthropic 格式
            system_content = None
            filtered_messages = []
            
            for msg in messages:
                if msg.get("role") == "system":
                    system_content = msg.get("content", "")
                elif msg.get("role") == "tool":
                    tool_result_msg = {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": msg.get("tool_call_id"),
                                "content": msg.get("content", "")
                            }
                        ]
                    }
                    filtered_messages.append(tool_result_msg)
                else:
                    filtered_messages.append(msg)
            
            # 准备请求参数
            request_params: Dict[str, Any] = {
                "model": model,
                "messages": filtered_messages,  # 使用过滤后的消息（不含 system）
                "temperature": temperature,
                "stream": True,
            }
            
            # 添加 system 参数（如果存在）
            if system_content:
                request_params["system"] = system_content
            
            if max_tokens and max_tokens > 0:
                request_params["max_tokens"] = max_tokens
            else:
                request_params["max_tokens"] = 4096  # Anthropic 要求必须提供
            
            # 转换工具定义格式以适配 Anthropic API
            if tools:
                anthropic_tools = []
                for tool in tools:
                    if tool.get("type") == "function" and "function" in tool:
                        func = tool["function"]
                        anthropic_tool = {
                            "name": func.get("name"),
                            "description": func.get("description", ""),
                            "input_schema": func.get("parameters", {"type": "object", "properties": {}})
                        }
                        anthropic_tools.append(anthropic_tool)
                    elif "name" in tool:
                        anthropic_tools.append(tool)
                
                if anthropic_tools:
                    request_params["tools"] = anthropic_tools
            
            request_params.update(kwargs)
            
            logger.debug(f"Anthropic params: {json.dumps({k: v for k, v in request_params.items() if k not in ['api_key', 'messages', 'system', 'tools']}, ensure_ascii=False)}")

            # 带指数退避的重试机制
            stream = None
            last_err: Optional[Exception] = None
            for attempt in range(1, self.max_retries + 1):
                try:
                    stream = await client.messages.create(**request_params)
                    break
                except Exception as e:
                    last_err = e
                    if attempt < self.max_retries:
                        wait = min(2 ** attempt, 30)
                        logger.warning(
                            f"Anthropic 调用失败 (第{attempt}/{self.max_retries}次)，"
                            f"{wait}s 后重试: {e}"
                        )
                        await asyncio.sleep(wait)
                    else:
                        logger.error(f"Anthropic 调用最终失败 ({self.max_retries}次重试耗尽): {e}")
                        raise

            tool_call_buffer: Dict[str, Dict[str, Any]] = {}
            chunk_count = 0
            content_yielded = False
            stream_done = False
            input_tokens = 0
            output_tokens = 0

            stream_retry = 0
            max_stream_retries = self.max_retries

            while not stream_done and stream_retry <= max_stream_retries:
                try:
                    async for event in stream:
                        chunk_count += 1
                        if chunk_count <= 3:
                            logger.debug(f"Anthropic event #{chunk_count}: {event}")
                        
                        # 处理不同类型的事件
                        if event.type == "message_start":
                            # 记录输入 tokens
                            if hasattr(event, "message") and hasattr(event.message, "usage"):
                                input_tokens = event.message.usage.input_tokens
                        
                        elif event.type == "content_block_start":
                            # 内容块开始 - 可能是工具调用
                            if hasattr(event, "content_block"):
                                block = event.content_block
                                if block.type == "tool_use":
                                    # 工具调用开始
                                    block_index = event.index
                                    key = f"index_{block_index}"
                                    tool_call_buffer[key] = {
                                        "id": block.id,
                                        "name": block.name,
                                        "arguments": ""
                                    }
                        
                        elif event.type == "content_block_delta":
                            content_yielded = True
                            delta = event.delta
                            
                            if delta.type == "text_delta":
                                # 文本内容
                                yield StreamChunk(content=delta.text)
                            
                            elif delta.type == "input_json_delta":
                                # 工具调用参数增量
                                block_index = event.index
                                key = f"index_{block_index}"
                                
                                if key in tool_call_buffer:
                                    tool_call_buffer[key]["arguments"] += delta.partial_json
                        
                        elif event.type == "content_block_stop":
                            # 内容块结束
                            pass
                        
                        elif event.type == "message_delta":
                            # 消息增量（包含 finish_reason 和 token 使用）
                            if hasattr(event, "delta") and hasattr(event.delta, "stop_reason"):
                                finish_reason = event.delta.stop_reason
                            
                            if hasattr(event, "usage"):
                                output_tokens = event.usage.output_tokens
                        
                        elif event.type == "message_stop":
                            # 消息结束
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
                            if input_tokens or output_tokens:
                                usage_dict = {
                                    "prompt_tokens": input_tokens,
                                    "completion_tokens": output_tokens,
                                    "total_tokens": input_tokens + output_tokens,
                                }
                            
                            yield StreamChunk(
                                finish_reason=finish_reason if 'finish_reason' in locals() else "stop",
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
                            f"Anthropic 流读取超时（第{stream_retry}/{max_stream_retries}次），"
                            f"{wait}s 后重试: {stream_err}"
                        )
                        await asyncio.sleep(wait)
                        stream = await client.messages.create(**request_params)
                        tool_call_buffer = {}
                        chunk_count = 0
                    elif content_yielded and is_timeout:
                        logger.warning(
                            f"Anthropic 流式读取超时（已发送 {chunk_count} 个 chunk），"
                            f"优雅截断并结束流: {stream_err}"
                        )
                        yield StreamChunk(finish_reason="length")
                        stream_done = True
                    else:
                        raise

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Anthropic call failed: {error_msg}")
            friendly_msg = self._format_error_message(error_msg)
            yield StreamChunk(error=friendly_msg)
    
    @staticmethod
    def _format_error_message(raw: str) -> str:
        """将 Anthropic 原始错误转换为用户友好提示"""
        lower = raw.lower()

        if any(k in lower for k in ("429", "rate limit", "quota")):
            return "请求过于频繁或 API 配额已用尽，请稍后重试或检查账户额度。"

        if any(k in lower for k in ("401", "unauthorized", "invalid.*api.*key", "authentication")):
            return "API 密钥无效或已过期，请在设置中检查并更新密钥。"

        if any(k in lower for k in ("404", "model not found", "model_not_found")):
            return "所选模型不可用，请在设置中确认模型名称是否正确。"

        if any(k in lower for k in ("context length", "max.*token", "too long")):
            return "对话上下文过长，请尝试新建会话或清除历史消息。"

        if any(k in lower for k in ("500", "502", "503", "504", "internal server error")):
            return "AI 服务暂时不可用，请稍后重试。"

        if any(k in lower for k in ("timeout", "connection", "network", "ssl")):
            return "网络连接异常，请检查网络设置后重试。"

        return f"AI 调用出错: {raw[:200]}"

    def get_default_model(self) -> str:
        """获取默认模型"""
        return self.default_model or "claude-sonnet-4-20250514"
