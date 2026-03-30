"""Agent Loop - 核心 Agent 循环处理逻辑"""

import asyncio
import inspect
import json
import time
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from loguru import logger
from backend.modules.tools.conversation_history import get_conversation_history


class AgentLoop:
    """Agent 主循环类 - 处理消息、调用 LLM、执行工具、生成响应"""

    def __init__(
        self,
        provider,
        workspace: Path,
        tools,
        context_builder=None,
        session_manager=None,
        subagent_manager=None,
        model: Optional[str] = None,
        max_iterations: int = 25,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        thinking_enabled: bool = True,
    ):
        self.provider = provider
        self.workspace = workspace
        self.tools = tools
        self.context_builder = context_builder
        self.session_manager = session_manager
        self.subagent_manager = subagent_manager
        self.model = model
        self.max_iterations = max_iterations
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.thinking_enabled = thinking_enabled
        
        logger.debug(
            f"AgentLoop initialized: max_iterations={max_iterations}, max_retries={max_retries}"
        )

    def _resolve_execution_runtime(
        self,
        model_override: Optional[Dict[str, Any]] = None,
    ) -> tuple[Any, Optional[str], float, int, int, bool]:
        """解析当前消息执行应使用的 provider 和模型参数。"""
        base_provider = self.provider
        base_model = self.model
        base_temperature = self.temperature
        base_max_tokens = self.max_tokens
        base_max_iterations = self.max_iterations
        base_thinking_enabled = self.thinking_enabled
        base_api_mode = getattr(base_provider, "api_mode", "chat_completions")

        if not model_override:
            return (
                base_provider,
                base_model,
                base_temperature,
                base_max_tokens,
                base_max_iterations,
                base_thinking_enabled,
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

        override_provider = model_override.get("provider")
        override_api_key = model_override.get("api_key") or None
        override_api_base = model_override.get("api_base") or None

        if override_provider or override_api_key or override_api_base:
            try:
                from backend.modules.providers import create_provider
                from backend.modules.config.loader import config_loader
                from backend.modules.providers.runtime import get_provider_runtime_state

                provider_id = override_provider or config_loader.config.model.provider
                runtime_state = get_provider_runtime_state(
                    config_loader.config,
                    provider_id,
                    api_key_override=override_api_key,
                    api_base_override=override_api_base,
                )
                if not runtime_state.selectable:
                    raise ValueError(
                        f"Provider '{provider_id}' is unavailable: {runtime_state.reason}"
                    )

                candidate_provider = create_provider(
                    api_key=runtime_state.api_key or None,
                    api_base=runtime_state.api_base,
                    default_model=candidate_model,
                    api_mode=candidate_api_mode,
                    timeout=getattr(self.provider, "timeout", 120.0),
                    max_retries=getattr(self.provider, "max_retries", self.max_retries),
                    provider_id=provider_id,
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
                )

        return (
            candidate_provider,
            candidate_model,
            candidate_temperature,
            candidate_max_tokens,
            candidate_max_iterations,
            candidate_thinking_enabled,
        )

    async def process_message(
        self,
        message: str,
        session_id: str,
        context: Optional[List[Dict[str, Any]]] = None,
        media: Optional[List[str]] = None,
        channel: Optional[str] = None,
        chat_id: Optional[str] = None,
        account_id: Optional[str] = None,
        cancel_token=None,
        yield_intermediate: bool = True,
        model_override: Optional[Dict[str, Any]] = None,
        persona_override=None,
        tool_event_handler=None,
        reasoning_event_handler=None,
        prefer_direct_workflow_result: bool = False,
    ) -> AsyncIterator[str]:
        """处理用户消息并生成流式响应"""
        logger.debug(f"Processing message for session {session_id}")
        
        # 设置工具注册表的会话ID（用于审计日志）和渠道信息
        if self.tools:
            self.tools.set_session_id(session_id)
            self.tools.set_channel(channel)
            # 将取消令牌传递给支持中断的工具（如 WorkflowTool）
            if cancel_token and hasattr(self.tools, 'set_cancel_token'):
                self.tools.set_cancel_token(cancel_token)

            spawn_tool = self.tools.get_tool("spawn")
            if spawn_tool and hasattr(spawn_tool, 'set_context'):
                spawn_tool.set_context(session_id)
        
        if self.context_builder and context is not None:
            messages = self.context_builder.build_messages(
                history=context,
                current_message=message,
                media=media,
                channel=channel,
                chat_id=chat_id,
                account_id=account_id,
                persona_config=persona_override,
            )
        else:
            if context is None:
                context = []
            
            messages = list(context)
            messages.append({
                "role": "user",
                "content": message,
            })

        (
            active_provider,
            runtime_model,
            runtime_temperature,
            runtime_max_tokens,
            runtime_max_iterations,
            runtime_thinking_enabled,
        ) = self._resolve_execution_runtime(model_override)
        
        iteration = 0
        total_tool_calls = 0
        final_content = ""
        direct_result_selected = False

        try:
            while iteration < runtime_max_iterations:
                iteration += 1
                
                if cancel_token and cancel_token.is_cancelled:
                    logger.debug(f"Agent loop cancelled at iteration {iteration}")
                    return
                
                logger.debug(f"Iteration {iteration}: {total_tool_calls} tool calls")
                
                tool_definitions = self.tools.get_definitions() if self.tools else []
                
                content_buffer = ""
                tool_calls_buffer = []
                finish_reason = None
                reasoning_buffer = ""
                provider_payload = None
                
                async for chunk in active_provider.chat_stream(
                    messages=messages,
                    tools=tool_definitions,
                    model=runtime_model,
                    temperature=runtime_temperature,
                    max_tokens=runtime_max_tokens,
                    thinking_enabled=runtime_thinking_enabled,
                ):
                    if chunk.is_content and chunk.content:
                        content_buffer += chunk.content
                        if yield_intermediate:
                            yield chunk.content
                    
                    if chunk.is_tool_call and chunk.tool_call:
                        tool_calls_buffer.append(chunk.tool_call)
                    
                    if chunk.is_reasoning and chunk.reasoning_content:
                        reasoning_buffer += chunk.reasoning_content
                        if reasoning_event_handler:
                            try:
                                maybe_result = reasoning_event_handler(
                                    chunk.reasoning_content
                                )
                                if inspect.isawaitable(maybe_result):
                                    await maybe_result
                            except Exception as exc:
                                logger.warning(
                                    f"Failed to emit reasoning chunk for session {session_id}: {exc}"
                                )
                    
                    if chunk.has_provider_payload and chunk.provider_payload:
                        provider_payload = chunk.provider_payload

                    if chunk.is_done and chunk.finish_reason:
                        finish_reason = chunk.finish_reason
                    
                    if chunk.is_error:
                        # Yield friendly error to user and stop
                        yield chunk.error
                        return
                
                if content_buffer:
                    final_content = content_buffer
                elif reasoning_buffer and not tool_calls_buffer:
                    final_content = reasoning_buffer
                
                if tool_calls_buffer:
                    tool_call_dicts = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments),
                            },
                        }
                        for tc in tool_calls_buffer
                    ]
                    
                    if self.context_builder:
                        messages = self.context_builder.add_assistant_message(
                            messages,
                            content_buffer or None,
                            tool_call_dicts,
                            reasoning_content=reasoning_buffer or None,
                            provider_payload=provider_payload,
                        )
                    else:
                        msg = {
                            "role": "assistant",
                            "content": content_buffer or "",
                            "tool_calls": tool_call_dicts,
                        }
                        if reasoning_buffer:
                            msg["reasoning_content"] = reasoning_buffer
                        if provider_payload:
                            msg.update(provider_payload)
                        messages.append(msg)
                    
                    for tool_call in tool_calls_buffer:
                        if total_tool_calls >= runtime_max_iterations:
                            logger.warning(
                                f"Reached max tool calls limit ({runtime_max_iterations}), "
                                f"skipping remaining tool calls in this iteration"
                            )
                            break
                        
                        if cancel_token and cancel_token.is_cancelled:
                            logger.debug(f"Agent loop cancelled before tool execution")
                            return

                        total_tool_calls += 1
                        tool_name = tool_call.name
                        tool_args = tool_call.arguments
                        tool_id = tool_call.id

                        logger.debug(f"Executing tool {total_tool_calls}: {tool_name}")

                        if tool_event_handler:
                            try:
                                maybe_result = tool_event_handler(
                                    "tool_call",
                                    {
                                        "tool_name": tool_name,
                                        "arguments": tool_args,
                                        "session_id": session_id,
                                    },
                                )
                                if inspect.isawaitable(maybe_result):
                                    await maybe_result
                            except Exception as e:
                                logger.warning(f"Tool event handler failed before execution: {e}")
                        
                        try:
                            from backend.ws.tool_notifications import notify_tool_execution
                            await notify_tool_execution(
                                session_id=session_id,
                                tool_name=tool_name,
                                arguments=tool_args,
                            )
                        except Exception as e:
                            logger.warning(f"Failed to send tool notification: {e}")
                        
                        start_time = time.time()
                        result = None
                        last_error = None
                        
                        if self.tools:
                            self.tools.set_tool_event_handler(tool_event_handler)
                        try:
                            for attempt in range(self.max_retries):
                                try:
                                    result = await self.execute_tool(tool_name, tool_args)
                                    logger.debug(f"Tool {tool_name} succeeded")
                                    break
                                except Exception as e:
                                    last_error = e
                                    logger.warning(
                                        f"Tool {tool_name} failed (attempt {attempt + 1}/{self.max_retries}): {e}"
                                    )
                                    if attempt < self.max_retries - 1:
                                        await asyncio.sleep(self.retry_delay)
                        finally:
                            if self.tools:
                                self.tools.set_tool_event_handler(None)
                        
                        duration_ms = int((time.time() - start_time) * 1000)
                        
                        if result is not None:
                            try:
                                conversation_history = get_conversation_history()
                                conversation_history.add_conversation(
                                    session_id=session_id,
                                    tool_name=tool_name,
                                    arguments=tool_args,
                                    user_message=message,
                                    result=result,
                                    duration_ms=duration_ms
                                )
                            except Exception as e:
                                logger.warning(f"Failed to record tool conversation: {e}")
                            
                            try:
                                from backend.ws.tool_notifications import notify_tool_execution
                                await notify_tool_execution(
                                    session_id=session_id,
                                    tool_name=tool_name,
                                    arguments=tool_args,
                                    result=result,
                                )
                            except Exception as e:
                                logger.warning(f"Failed to send tool result notification: {e}")

                            if tool_event_handler:
                                try:
                                    maybe_result = tool_event_handler(
                                        "tool_result",
                                        {
                                            "tool_name": tool_name,
                                            "arguments": tool_args,
                                            "result": result,
                                            "session_id": session_id,
                                            "duration_ms": duration_ms,
                                        },
                                    )
                                    if inspect.isawaitable(maybe_result):
                                        await maybe_result
                                except Exception as e:
                                    logger.warning(f"Tool event handler failed after execution: {e}")

                            if tool_name == "workflow_run" and prefer_direct_workflow_result:
                                final_content = result
                                direct_result_selected = True
                                if result:
                                    yield result
                                break
                            
                            if self.context_builder:
                                messages = self.context_builder.add_tool_result(
                                    messages,
                                    tool_id,
                                    tool_name,
                                    result,
                                )
                            else:
                                messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_id,
                                    "name": tool_name,
                                    "content": result,
                                })
                        else:
                            error_msg = f"Tool execution failed after {self.max_retries} attempts: {str(last_error)}"
                            logger.error(f"Tool {tool_name} failed permanently: {error_msg}")
                            
                            try:
                                conversation_history = get_conversation_history()
                                conversation_history.add_conversation(
                                    session_id=session_id,
                                    tool_name=tool_name,
                                    arguments=tool_args,
                                    user_message=message,
                                    error=error_msg,
                                    duration_ms=duration_ms
                                )
                            except Exception as e:
                                logger.warning(f"Failed to record tool conversation: {e}")
                            
                            try:
                                from backend.ws.tool_notifications import notify_tool_execution
                                await notify_tool_execution(
                                    session_id=session_id,
                                    tool_name=tool_name,
                                    arguments=tool_args,
                                    error=error_msg,
                                )
                            except Exception as e:
                                logger.warning(f"Failed to send tool error notification: {e}")

                            if tool_event_handler:
                                try:
                                    maybe_result = tool_event_handler(
                                        "tool_error",
                                        {
                                            "tool_name": tool_name,
                                            "arguments": tool_args,
                                            "error": error_msg,
                                            "session_id": session_id,
                                            "duration_ms": duration_ms,
                                        },
                                    )
                                    if inspect.isawaitable(maybe_result):
                                        await maybe_result
                                except Exception as e:
                                    logger.warning(f"Tool event handler failed on error: {e}")
                            
                            if self.context_builder:
                                messages = self.context_builder.add_tool_result(
                                    messages,
                                    tool_id,
                                    tool_name,
                                    error_msg,
                                )
                            else:
                                messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_id,
                                    "name": tool_name,
                                    "content": error_msg,
                                })
                    if direct_result_selected:
                        break
                else:
                    if not yield_intermediate and content_buffer:
                        yield content_buffer
                    break

                if direct_result_selected:
                    break
            
            # 检查是否达到限制
            if iteration >= runtime_max_iterations or total_tool_calls >= runtime_max_iterations:
                if total_tool_calls >= runtime_max_iterations:
                    logger.warning(f"Max tool calls ({runtime_max_iterations}) reached")
                    warning_msg = f"\n\n[达到最大工具调用次数 {runtime_max_iterations}]"
                else:
                    logger.warning(f"Max iterations ({runtime_max_iterations}) reached")
                    warning_msg = f"\n\n[达到最大迭代次数 {runtime_max_iterations}]"
                yield warning_msg
                final_content += warning_msg
            
            # 保存到会话（如果有 session_manager）
            if self.session_manager and final_content:
                try:
                    session = self.session_manager.get_or_create(session_id)
                    session.add_message("user", message)
                    session.add_message("assistant", final_content)
                    self.session_manager.save(session)
                except Exception as e:
                    logger.warning(f"Failed to save session: {e}")
            
            # 记录AI完整响应到审计日志
            if self.tools and final_content:
                try:
                    from backend.modules.tools.file_audit_logger import file_audit_logger
                    file_audit_logger.record_ai_response(
                        session_id=session_id,
                        user_message=message,
                        ai_response=final_content,
                        duration_ms=None  # 暂时不记录耗时
                    )
                except Exception as e:
                    logger.warning(f"Failed to record AI response to audit log: {e}")
                
        except Exception as e:
            logger.exception(f"Error in agent loop: {e}")
            raise

    async def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> str:
        """
        执行工具调用
        
        Args:
            tool_name: 工具名称
            arguments: 工具参数
            
        Returns:
            str: 工具执行结果
            
        Raises:
            ValueError: 工具不存在
            Exception: 工具执行失败
        """
        if not self.tools:
            raise ValueError("ToolRegistry not initialized")
        
        logger.debug(f"Executing tool: {tool_name}")
        
        try:
            result = await self.tools.execute(tool_name, arguments, auto_record=False)
            return result
            
        except Exception as e:
            logger.error(f"Tool execution failed: {tool_name} - {e}")
            raise

    async def process_direct(
        self,
        content: str,
        session_id: str = "cli:direct",
        channel: str = "cli",
        chat_id: str = "direct",
        account_id: Optional[str] = None,
    ) -> str:
        """
        直接处理消息（用于 CLI 或 cron 使用）
        
        Args:
            content: 消息内容
            session_id: 会话标识符
            channel: 来源渠道（用于上下文）
            chat_id: 来源聊天 ID（用于上下文）
            account_id: 当前机器人账号 ID（多机器人渠道）
        
        Returns:
            Agent 的响应
        """
        response_parts = []
        
        # 传入空的 context 列表
        async for chunk in self.process_message(
            message=content,
            session_id=session_id,
            context=[],  
            channel=channel,
            chat_id=chat_id,
            account_id=account_id,
        ):
            response_parts.append(chunk)
        
        return "".join(response_parts)
