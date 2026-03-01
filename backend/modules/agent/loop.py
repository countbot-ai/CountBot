"""Agent Loop - 核心 Agent 循环处理逻辑"""

import asyncio
import json
import time
from pathlib import Path
from typing import Any, AsyncIterator, List, Dict, Optional
from dataclasses import dataclass, field

from loguru import logger
from backend.modules.tools.conversation_history import get_conversation_history


@dataclass
class AgentResponse:
    """Agent 响应数据类，用于收集流式响应的完整内容"""

    content: str = ""
    tool_calls: List[Any] = field(default_factory=list)
    reasoning: str = ""
    finish_reason: Optional[str] = None


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
        model: str | None = None,
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
            f"AgentLoop initialized: workspace={workspace}, "
            f"max_iterations={max_iterations}, max_retries={max_retries}, "
            f"temperature={temperature}, max_tokens={max_tokens}"
        )

    async def process_message(
        self,
        message: str,
        session_id: str,
        context: list[dict[str, Any]] | None = None,
        media: list[str] | None = None,
        channel: str | None = None,
        chat_id: str | None = None,
        cancel_token=None,
    ) -> AsyncIterator[str]:
        """处理用户消息并生成流式响应"""
        logger.info(f"Processing message for session {session_id}: {message[:50]}...")

        # 1. 初始化上下文和工具
        self._initialize_tools(session_id, channel)
        messages = self._build_initial_messages(
            message, context, media, channel, chat_id
        )

        iteration = 0
        total_tool_calls = 0
        final_content = ""

        try:
            while iteration < self.max_iterations:
                iteration += 1

                # 检查是否被取消
                if cancel_token and cancel_token.is_cancelled:
                    logger.info(
                        f"Agent loop cancelled at iteration {iteration}: {session_id}"
                    )
                    return

                logger.debug(
                    f"Agent iteration {iteration}/{self.max_iterations}, total tool calls: {total_tool_calls}"
                )

                # 2. 获取 LLM 响应
                response = AgentResponse()
                async for chunk in self._stream_llm_response(messages, response):
                    if isinstance(chunk, str):
                        yield chunk
                    else:
                        # 错误情况
                        yield chunk
                        return

                if response.content:
                    final_content = response.content
                    logger.info(
                        f"AI完整响应 (长度: {len(response.content)}字符):\n{response.content}"
                    )

                # 3. 如果没有工具调用，结束循环
                if not response.tool_calls:
                    logger.info("No tool calls, ending agent loop")
                    break

                # 4. 更新助手消息到历史
                self._add_assistant_message(messages, response)

                # 5. 执行工具调用
                tool_results_count = await self._process_tool_calls(
                    response.tool_calls,
                    messages,
                    session_id,
                    message,
                    total_tool_calls,
                    cancel_token,
                )

                total_tool_calls += tool_results_count

                # 检查是否被取消（在工具执行后）
                if cancel_token and cancel_token.is_cancelled:
                    return

            # 6. 检查是否达到限制
            if (
                iteration >= self.max_iterations
                or total_tool_calls >= self.max_iterations
            ):
                warning_msg = self._handle_limit_reached(iteration, total_tool_calls)
                yield warning_msg
                final_content += warning_msg

            # 7. 保存会话和日志
            self._finalize_session(session_id, message, final_content)

        except Exception as e:
            logger.exception(f"Error in agent loop: {e}")
            raise

    def _initialize_tools(self, session_id: str, channel: str | None):
        """初始化工具配置"""
        if self.tools:
            self.tools.set_session_id(session_id)
            self.tools.set_channel(channel)

            spawn_tool = self.tools.get_tool("spawn")
            if spawn_tool and hasattr(spawn_tool, "set_context"):
                spawn_tool.set_context(session_id)

    def _build_initial_messages(
        self,
        message: str,
        context: list[dict[str, Any]] | None,
        media: list[str] | None,
        channel: str | None,
        chat_id: str | None,
    ) -> list[dict[str, Any]]:
        """构建初始消息列表"""
        if self.context_builder and context is not None:
            return self.context_builder.build_messages(
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
            messages.append(
                {
                    "role": "user",
                    "content": message,
                }
            )
            return messages

    async def _stream_llm_response(
        self, messages: list[dict[str, Any]], response: AgentResponse
    ) -> AsyncIterator[str | Any]:
        """流式获取 LLM 响应并填充 response 对象"""
        tool_definitions = self.tools.get_definitions() if self.tools else []

        async for chunk in self.provider.chat_stream(
            messages=messages,
            tools=tool_definitions,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        ):
            if chunk.is_content and chunk.content:
                response.content += chunk.content
                yield chunk.content

            if chunk.is_tool_call and chunk.tool_call:
                response.tool_calls.append(chunk.tool_call)

            if chunk.is_reasoning and chunk.reasoning_content:
                response.reasoning += chunk.reasoning_content

            if chunk.is_done and chunk.finish_reason:
                response.finish_reason = chunk.finish_reason

            if chunk.is_error:
                yield chunk.error

    def _add_assistant_message(
        self, messages: list[dict[str, Any]], response: AgentResponse
    ):
        """添加助手消息到历史记录"""
        tool_call_dicts = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.name,
                    "arguments": json.dumps(tc.arguments),
                },
            }
            for tc in response.tool_calls
        ]

        if self.context_builder:
            # ContextBuilder 可能会返回新的 messages 列表
            updated_messages = self.context_builder.add_assistant_message(
                messages,
                response.content or None,
                tool_call_dicts,
                reasoning_content=response.reasoning or None,
            )
            # 如果返回了新对象，则更新原列表内容；如果是同一对象，则无需操作（因为已经append了）
            if updated_messages is not messages:
                messages.clear()
                messages.extend(updated_messages)
        else:
            msg = {
                "role": "assistant",
                "content": response.content or "",
                "tool_calls": tool_call_dicts,
            }
            if response.reasoning:
                msg["reasoning_content"] = response.reasoning
            messages.append(msg)

    async def _process_tool_calls(
        self,
        tool_calls: list[Any],
        messages: list[dict[str, Any]],
        session_id: str,
        user_message: str,
        current_total_calls: int,
        cancel_token: Any,
    ) -> int:
        """处理工具调用列表，返回执行的工具数量"""
        executed_count = 0

        for tool_call in tool_calls:
            if current_total_calls + executed_count >= self.max_iterations:
                logger.warning(
                    f"Reached max tool calls limit ({self.max_iterations}), "
                    f"skipping remaining tool calls in this iteration"
                )
                break

            if cancel_token and cancel_token.is_cancelled:
                logger.info(f"Agent loop cancelled before tool execution: {session_id}")
                break

            executed_count += 1

            # 执行单个工具
            await self._execute_and_record_single_tool(
                tool_call,
                messages,
                session_id,
                user_message,
                executed_count + current_total_calls,
            )

        return executed_count

    async def _execute_and_record_single_tool(
        self,
        tool_call: Any,
        messages: list[dict[str, Any]],
        session_id: str,
        user_message: str,
        call_index: int,
    ):
        """执行单个工具并记录结果"""
        tool_name = tool_call.name
        tool_args = tool_call.arguments
        tool_id = tool_call.id

        logger.info(
            f"Executing tool {call_index}/{self.max_iterations}: "
            f"{tool_name} with args: {json.dumps(tool_args, ensure_ascii=False)}"
        )

        # 1. 发送开始通知
        await self._notify_tool_start(session_id, tool_name, tool_args)

        start_time = time.time()
        result = None
        error_msg = None

        # 2. 执行工具（带重试）
        try:
            result = await self._execute_tool_with_retry(tool_name, tool_args)
        except Exception as e:
            error_msg = (
                f"Tool execution failed after {self.max_retries} attempts: {str(e)}"
            )
            logger.error(f"Tool {tool_name} failed permanently: {error_msg}")

        duration_ms = int((time.time() - start_time) * 1000)

        # 3. 记录历史和发送结果通知
        await self._record_tool_execution(
            session_id,
            tool_name,
            tool_args,
            user_message,
            result,
            error_msg,
            duration_ms,
        )

        # 4. 更新消息历史
        self._add_tool_result_to_messages(
            messages, tool_id, tool_name, result, error_msg
        )

    async def _execute_tool_with_retry(self, tool_name: str, tool_args: dict) -> str:
        """执行工具，包含重试逻辑"""
        last_error = None
        for attempt in range(self.max_retries):
            try:
                result = await self.execute_tool(tool_name, tool_args)
                logger.debug(f"Tool {tool_name} executed successfully")
                return result
            except Exception as e:
                last_error = e
                logger.warning(
                    f"Tool {tool_name} failed (attempt {attempt + 1}/{self.max_retries}): {e}"
                )
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay)

        raise last_error

    async def _notify_tool_start(self, session_id: str, tool_name: str, args: dict):
        """发送工具开始通知"""
        try:
            from backend.ws.tool_notifications import notify_tool_execution

            await notify_tool_execution(
                session_id=session_id,
                tool_name=tool_name,
                arguments=args,
            )
        except Exception as e:
            logger.warning(f"Failed to send tool notification: {e}")

    async def _record_tool_execution(
        self, session_id, tool_name, args, user_message, result, error, duration_ms
    ):
        """记录工具执行结果到数据库和发送通知"""
        # 记录到数据库
        try:
            conversation_history = get_conversation_history()
            conversation_history.add_conversation(
                session_id=session_id,
                tool_name=tool_name,
                arguments=args,
                user_message=user_message,
                result=result,
                error=error,
                duration_ms=duration_ms,
            )
        except Exception as e:
            logger.warning(f"Failed to record tool conversation: {e}")

        # 发送通知
        try:
            from backend.ws.tool_notifications import notify_tool_execution

            await notify_tool_execution(
                session_id=session_id,
                tool_name=tool_name,
                arguments=args,
                result=result,
                error=error,
            )
        except Exception as e:
            logger.warning(f"Failed to send tool result notification: {e}")

    def _add_tool_result_to_messages(
        self, messages, tool_id, tool_name, result, error_msg
    ):
        """添加工具结果到消息列表"""
        content = result if result is not None else error_msg

        if self.context_builder:
            updated_messages = self.context_builder.add_tool_result(
                messages,
                tool_id,
                tool_name,
                content,
            )
            if updated_messages is not messages:
                messages.clear()
                messages.extend(updated_messages)
        else:
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "name": tool_name,
                    "content": content,
                }
            )

    def _handle_limit_reached(self, iteration: int, total_tool_calls: int) -> str:
        """处理达到限制的情况"""
        if total_tool_calls >= self.max_iterations:
            logger.warning(f"Max tool calls ({self.max_iterations}) reached")
            return f"\n\n[达到最大工具调用次数 {self.max_iterations}]"
        else:
            logger.warning(f"Max iterations ({self.max_iterations}) reached")
            return f"\n\n[达到最大迭代次数 {self.max_iterations}]"

    def _finalize_session(self, session_id: str, message: str, final_content: str):
        """保存会话和日志"""
        # 保存到会话
        if self.session_manager and final_content:
            try:
                session = self.session_manager.get_or_create(session_id)
                session.add_message("user", message)
                session.add_message("assistant", final_content)
                self.session_manager.save(session)
            except Exception as e:
                logger.warning(f"Failed to save session: {e}")

        # 记录审计日志
        if self.tools and final_content:
            try:
                from backend.modules.tools.file_audit_logger import file_audit_logger

                file_audit_logger.record_ai_response(
                    session_id=session_id,
                    user_message=message,
                    ai_response=final_content,
                    duration_ms=None,
                )
            except Exception as e:
                logger.warning(f"Failed to record AI response to audit log: {e}")

    async def execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
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

        async for chunk in self.process_message(
            message=content,
            session_id=session_id,
            channel=channel,
            chat_id=chat_id,
        ):
            response_parts.append(chunk)

        return "".join(response_parts)
