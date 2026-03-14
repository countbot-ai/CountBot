"""Agent Loop - 核心 Agent 循环处理逻辑"""

import asyncio
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
        temperature: float = 0.7,
        max_tokens: int = 4096,
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
        
        logger.debug(
            f"AgentLoop initialized: max_iterations={max_iterations}, max_retries={max_retries}"
        )

    async def process_message(
        self,
        message: str,
        session_id: str,
        context: Optional[List[Dict[str, Any]]] = None,
        media: Optional[List[str]] = None,
        channel: Optional[str] = None,
        chat_id: Optional[str] = None,
        cancel_token=None,
        yield_intermediate: bool = True,
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
            )
        else:
            if context is None:
                context = []
            
            messages = list(context)
            messages.append({
                "role": "user",
                "content": message,
            })
        
        iteration = 0
        total_tool_calls = 0
        final_content = ""

        try:
            while iteration < self.max_iterations:
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
                
                async for chunk in self.provider.chat_stream(
                    messages=messages,
                    tools=tool_definitions,
                    model=self.model,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                ):
                    if chunk.is_content and chunk.content:
                        content_buffer += chunk.content
                        if yield_intermediate:
                            yield chunk.content
                    
                    if chunk.is_tool_call and chunk.tool_call:
                        tool_calls_buffer.append(chunk.tool_call)
                    
                    if chunk.is_reasoning and chunk.reasoning_content:
                        reasoning_buffer += chunk.reasoning_content
                    
                    if chunk.is_done and chunk.finish_reason:
                        finish_reason = chunk.finish_reason
                    
                    if chunk.is_error:
                        # Yield friendly error to user and stop
                        yield chunk.error
                        return
                
                if content_buffer:
                    final_content = content_buffer
                
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
                        )
                    else:
                        msg = {
                            "role": "assistant",
                            "content": content_buffer or "",
                            "tool_calls": tool_call_dicts,
                        }
                        if reasoning_buffer:
                            msg["reasoning_content"] = reasoning_buffer
                        messages.append(msg)
                    
                    for tool_call in tool_calls_buffer:
                        if total_tool_calls >= self.max_iterations:
                            logger.warning(
                                f"Reached max tool calls limit ({self.max_iterations}), "
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
                else:
                    if not yield_intermediate and content_buffer:
                        yield content_buffer
                    break
            
            # 检查是否达到限制
            if iteration >= self.max_iterations or total_tool_calls >= self.max_iterations:
                if total_tool_calls >= self.max_iterations:
                    logger.warning(f"Max tool calls ({self.max_iterations}) reached")
                    warning_msg = f"\n\n[达到最大工具调用次数 {self.max_iterations}]"
                else:
                    logger.warning(f"Max iterations ({self.max_iterations}) reached")
                    warning_msg = f"\n\n[达到最大迭代次数 {self.max_iterations}]"
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
    ) -> str:
        """
        直接处理消息（用于 CLI 或 cron 使用）
        
        Args:
            content: 消息内容
            session_id: 会话标识符
            channel: 来源渠道（用于上下文）
            chat_id: 来源聊天 ID（用于上下文）
        
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
        ):
            response_parts.append(chunk)
        
        return "".join(response_parts)
