"""Agent Loop - 核心 Agent 循环处理逻辑"""

import asyncio
import inspect
import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from loguru import logger
from backend.modules.tools.conversation_history import get_conversation_history
from backend.modules.tools.outcome_projection import project_attempt
from backend.modules.tools.execution import (
    ExecutionState,
    RetrySafety,
    SideEffectState,
    ToolExecutionInProgress,
    ToolExecutionOutcome,
    ToolExecutionRejected,
)
from backend.modules.providers.base import AUTH_ERROR_HINTS, RATE_LIMIT_HINTS
from backend.modules.providers.media_capabilities import resolve_supports_image
from backend.modules.session.usage_recorder import record_usage


def _is_key_rotation_eligible_error(error_text: str) -> bool:
    """判断错误是否适合触发 key 轮换重试。

    分类 hint 统一维护在 providers/base.py（单一来源），此处直接引用。
    """
    lower = (error_text or "").lower()
    return any(hint in lower for hint in AUTH_ERROR_HINTS + RATE_LIMIT_HINTS)


@dataclass
class _LoopState:
    """process_message 主循环内共享的可变状态。

    各阶段方法（_consume_model_stream / _execute_tool_batch /
    _run_single_tool）通过本容器读写循环状态。
    """

    messages: List[Dict[str, Any]]
    iteration: int = 0
    iteration_budget: int = 0
    total_tool_calls: int = 0
    final_content: str = ""
    direct_result_selected: bool = False
    tool_call_limit_reached: bool = False
    active_provider: Any = None
    request_trace_id: str = ""
    # 本轮模型流的产出缓冲（_consume_model_stream 每轮写回）
    content_buffer: str = ""
    tool_calls_buffer: List[Any] = None
    reasoning_buffer: str = ""
    provider_payload: Any = None
    finish_reason: Optional[str] = None
    # 控制信号：
    # abort —— 立即结束整个生成器（用户取消 / 不可恢复错误）
    # stop_loop —— 结束 while 主循环（工具额度耗尽 / direct workflow 结果）
    # stop_tool_loop —— 跳过本批次剩余工具（direct workflow 结果命中）
    # rotation_restart —— key 轮换成功且本轮无内容输出，用新 provider 重发本轮
    abort: bool = False
    stop_loop: bool = False
    stop_tool_loop: bool = False
    rotation_restart: bool = False


class AgentLoop:
    """Agent 主循环类 - 处理消息、调用 LLM、执行工具、生成响应"""

    MAX_KEY_ROTATION_RETRIES = 3

    # 自管闹钟的长任务工具：内部自带超时等待与超时返回文案
    # （spawn 等子代理至 subagent_timeout；workflow_run 驱动多子代理；
    #  external_coding_agent 按 profile timeout 运行），
    # 主循环外层 wait_for 对其豁免，避免被默认短超时误杀长任务。
    _SELF_ALARMING_TOOLS = frozenset({"spawn", "workflow_run", "external_coding_agent"})

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
        reasoning_level: Optional[str] = None,
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
        self.reasoning_level = reasoning_level
        self._key_rotation_count = 0
        
        logger.debug(
            f"AgentLoop initialized: max_iterations={max_iterations}, max_retries={max_retries}"
        )

    @staticmethod
    def _summarize_tool_calls_for_log(tool_calls: List[Any]) -> str:
        parts = []
        for tool_call in tool_calls:
            tool_id = str(getattr(tool_call, "id", "") or "").strip() or "<empty>"
            tool_name = str(getattr(tool_call, "name", "") or "").strip() or "<unknown>"
            parts.append(f"{tool_name}#{tool_id}")
        return ", ".join(parts) if parts else "<none>"

    def _resolve_tool_timeout_seconds(self) -> int:
        """解析主循环工具调用超时（秒）。

        来自 config.agent.tool_timeout_seconds，默认 60；解析失败时兜底默认值。
        """
        try:
            from backend.modules.config.loader import config_loader

            return config_loader.config.agent.tool_timeout_seconds
        except Exception as e:
            logger.warning(
                f"Failed to resolve tool timeout config: {e}, using default: 60s"
            )
            return 60

    def _resolve_execution_runtime(
        self,
        model_override: Optional[Dict[str, Any]] = None,
    ) -> tuple[Any, Optional[str], float, int, int, bool, Optional[str]]:
        """解析当前消息执行应使用的 provider 和模型参数。"""
        base_provider = self.provider
        base_model = self.model
        base_temperature = self.temperature
        base_max_tokens = self.max_tokens
        base_max_iterations = self.max_iterations
        base_thinking_enabled = self.thinking_enabled
        base_reasoning_level = self.reasoning_level
        base_api_mode = getattr(base_provider, "api_mode", "chat_completions")

        if not model_override:
            return (
                base_provider,
                base_model,
                base_temperature,
                base_max_tokens,
                base_max_iterations,
                base_thinking_enabled,
                base_reasoning_level,
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
        candidate_reasoning_level = model_override.get(
            "reasoning_level",
            base_reasoning_level,
        )

        override_provider = model_override.get("provider")
        override_api_key = model_override.get("api_key") or None
        override_api_base = model_override.get("api_base") or None

        if override_provider or override_api_key or override_api_base:
            try:
                from backend.modules.providers import create_provider
                from backend.modules.config.loader import config_loader
                from backend.modules.providers.runtime import (
                    build_provider_unavailable_message,
                    get_provider_runtime_state,
                )

                provider_id = override_provider or config_loader.config.model.provider
                runtime_state = get_provider_runtime_state(
                    config_loader.config,
                    provider_id,
                    api_key_override=override_api_key,
                    api_base_override=override_api_base,
                )
                if not runtime_state.selectable:
                    raise ValueError(
                        build_provider_unavailable_message(
                            provider_id,
                            runtime_state.reason,
                        )
                    )

                candidate_provider = create_provider(
                    api_key=runtime_state.api_key or None,
                    api_keys=runtime_state.api_keys or None,
                    api_base=runtime_state.api_base,
                    default_model=candidate_model,
                    api_mode=candidate_api_mode,
                    timeout=getattr(self.provider, "timeout", 120.0),
                    max_retries=getattr(self.provider, "max_retries", self.max_retries),
                    provider_id=provider_id,
                    api_type=runtime_state.api_type,
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
                    base_reasoning_level,
                )

        return (
            candidate_provider,
            candidate_model,
            candidate_temperature,
            candidate_max_tokens,
            candidate_max_iterations,
            candidate_thinking_enabled,
            candidate_reasoning_level,
        )

    async def process_message(
        self,
        message: str,
        session_id: str,
        context: Optional[List[Dict[str, Any]]] = None,
        session_summary: Optional[str] = None,
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
        pending_message_provider=None,
    ) -> AsyncIterator[str]:
        """处理用户消息并生成流式响应

        Args:
            pending_message_provider: 可选的无参可调用对象。每轮工具批次执行完毕后
                调用一次，返回该会话在等待期间新到、尚未处理的消息文本；返回空值时
                表示没有插话。用于让用户在 Agent 干活的间隙补充信息，而不是另起一轮
                并发处理。

        主循环阶段划分：_consume_model_stream（消费模型流）→
        _execute_tool_batch（工具批次，内部逐工具走 _run_single_tool）→
        _finalize_limits（限额检查），各阶段通过 _LoopState 共享状态。
        """
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

        (
            active_provider,
            runtime_model,
            runtime_temperature,
            runtime_max_tokens,
            runtime_max_iterations,
            runtime_thinking_enabled,
            runtime_reasoning_level,
        ) = self._resolve_execution_runtime(model_override)

        supports_image = resolve_supports_image(
            provider_id=getattr(active_provider, "provider_id", None),
            model=runtime_model or getattr(active_provider, "default_model", None),
            override=(model_override or {}).get("supports_image"),
        )
        logger.debug(
            "图片输入能力: "
            f"provider={getattr(active_provider, 'provider_id', None) or '<default>'}, "
            f"model={runtime_model or getattr(active_provider, 'default_model', None) or '<default>'}, "
            f"override={(model_override or {}).get('supports_image')}, "
            f"supports_image={supports_image}"
        )

        state = _LoopState(
            messages=self._prepare_messages(
                message, context, session_summary, media, channel, chat_id,
                account_id, persona_override, supports_image,
            ),
            iteration=0,
            iteration_budget=runtime_max_iterations,
            active_provider=active_provider,
            request_trace_id=f"{session_id[:8]}-{uuid.uuid4().hex[:8]}",
        )
        self._key_rotation_count = 0

        logger.info(
            "Agent 循环请求开始: "
            f"trace={state.request_trace_id}, session={session_id}, model={runtime_model or '<default>'}"
        )

        try:
            while state.iteration < state.iteration_budget:
                state.iteration += 1

                if cancel_token and cancel_token.is_cancelled:
                    logger.debug(f"Agent loop cancelled at iteration {state.iteration}")
                    return

                logger.debug(f"Iteration {state.iteration}: {state.total_tool_calls} tool calls")

                async for piece in self._consume_model_stream(
                    state, session_id,
                    runtime_model, runtime_temperature, runtime_max_tokens,
                    runtime_thinking_enabled, runtime_reasoning_level,
                    cancel_token, yield_intermediate, reasoning_event_handler,
                ):
                    yield piece
                if state.abort:
                    return
                if state.rotation_restart:
                    # key 轮换成功且本轮无内容输出：用新 provider 重发本轮
                    state.rotation_restart = False
                    continue

                if state.content_buffer:
                    state.final_content = state.content_buffer
                elif state.reasoning_buffer and not state.tool_calls_buffer:
                    state.final_content = state.reasoning_buffer

                if state.tool_calls_buffer:
                    async for piece in self._execute_tool_batch(
                        state, session_id, message, runtime_max_iterations,
                        cancel_token, tool_event_handler,
                        pending_message_provider, prefer_direct_workflow_result,
                    ):
                        yield piece
                    if state.abort:
                        return
                    if state.stop_loop:
                        break
                else:
                    if not yield_intermediate and state.content_buffer:
                        yield state.content_buffer
                    break

                if state.direct_result_selected:
                    break

            warning_msg = self._finalize_limits(state, runtime_max_iterations)
            if warning_msg:
                yield warning_msg
                state.final_content += warning_msg

            # 保存到会话（如果有 session_manager）
            if self.session_manager and state.final_content:
                try:
                    session = self.session_manager.get_or_create(session_id)
                    session.add_message("user", message)
                    session.add_message("assistant", state.final_content)
                    self.session_manager.save(session)
                except Exception as e:
                    logger.warning(f"Failed to save session: {e}")

            # 记录AI完整响应到审计日志
            if self.tools and state.final_content:
                try:
                    from backend.modules.tools.file_audit_logger import file_audit_logger
                    file_audit_logger.record_ai_response(
                        session_id=session_id,
                        user_message=message,
                        ai_response=state.final_content,
                        duration_ms=None  # 暂时不记录耗时
                    )
                except Exception as e:
                    logger.warning(f"Failed to record AI response to audit log: {e}")

        except Exception as e:
            logger.exception(f"Error in agent loop: {e}")
            raise

    def _prepare_messages(
        self,
        message: str,
        context: Optional[List[Dict[str, Any]]],
        session_summary: Optional[str],
        media: Optional[List[str]],
        channel: Optional[str],
        chat_id: Optional[str],
        account_id: Optional[str],
        persona_override,
        supports_image: bool,
    ) -> List[Dict[str, Any]]:
        """构建发送给模型的 messages 列表（原 process_message 前段）。"""
        if self.context_builder and context is not None:
            return self.context_builder.build_messages(
                history=context,
                current_message=message,
                session_summary=session_summary,
                media=media,
                channel=channel,
                chat_id=chat_id,
                account_id=account_id,
                persona_config=persona_override,
                supports_image=supports_image,
            )

        if context is None:
            context = []
        messages = list(context)
        messages.append({
            "role": "user",
            "content": message,
        })
        return messages

    async def _consume_model_stream(
        self,
        state: "_LoopState",
        session_id: str,
        runtime_model: Optional[str],
        runtime_temperature: float,
        runtime_max_tokens: int,
        runtime_thinking_enabled: bool,
        runtime_reasoning_level: Optional[str],
        cancel_token,
        yield_intermediate: bool,
        reasoning_event_handler,
    ) -> AsyncIterator[str]:
        """消费一次模型流，yield 内容 chunk，缓冲写回 state。

        - is_error 且 key rotation 可用：替换 state.active_provider、回退
          state.iteration，继续消费当前流剩余 chunk（原 continue 语义）；
        - is_error 且无法 rotation：yield 错误文本并置 state.abort。
        """
        state.content_buffer = ""
        state.tool_calls_buffer = []
        state.finish_reason = None
        state.reasoning_buffer = ""
        state.provider_payload = None
        # 本轮的用量：供应商通常在最后一个 chunk 里上报，此处按覆盖方式收集
        usage_payload = None
        provider_trace_kwargs: Dict[str, Any] = {}
        if state.active_provider.__class__.__module__.endswith(".openai_provider"):
            provider_trace_kwargs["request_trace_id"] = state.request_trace_id

        tool_definitions = self.tools.get_definitions() if self.tools else []

        async for chunk in state.active_provider.chat_stream(
            messages=state.messages,
            tools=tool_definitions,
            model=runtime_model,
            temperature=runtime_temperature,
            max_tokens=runtime_max_tokens,
            thinking_enabled=runtime_thinking_enabled,
            reasoning_level=runtime_reasoning_level,
            **provider_trace_kwargs,
        ):
            if chunk.is_content and chunk.content:
                state.content_buffer += chunk.content
                if yield_intermediate:
                    yield chunk.content

            if chunk.is_tool_call and chunk.tool_call:
                state.tool_calls_buffer.append(chunk.tool_call)

            if chunk.is_reasoning and chunk.reasoning_content:
                state.reasoning_buffer += chunk.reasoning_content
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
                state.provider_payload = chunk.provider_payload

            if chunk.usage:
                usage_payload = chunk.usage

            if chunk.is_done and chunk.finish_reason:
                state.finish_reason = chunk.finish_reason

            if chunk.is_error:
                error_text = chunk.raw_error or chunk.error or ""
                rotated_provider = self._try_key_rotation(
                    state.active_provider, error_text
                )
                if rotated_provider is not None:
                    state.active_provider = rotated_provider
                    state.iteration -= 1
                    self._key_rotation_count += 1
                    await asyncio.sleep(1.0)
                    if not state.content_buffer:
                        # 本轮尚未输出内容：错误意味着整个响应已无效，
                        # 用轮换后的 provider 重新发起本轮，避免流结束后
                        # 走 else 分支 break 导致用户收到空回复
                        state.rotation_restart = True
                        return
                    # 本轮已有内容输出（已实时 yield 给用户）：重发会造成
                    # 重复，继续消费当前流剩余 chunk
                    continue
                yield chunk.error
                state.abort = True
                return

        # 每次模型调用结束后记录一次用量：一轮对话可能包含多次调用
        # （工具结果返回后继续推理），逐次记录才能看清成本分布。
        if usage_payload:
            await record_usage(
                session_id=session_id,
                provider=getattr(state.active_provider, "provider_id", None),
                model=runtime_model or getattr(state.active_provider, "default_model", None),
                turn_index=state.iteration,
                raw_usage=usage_payload,
            )

    async def _execute_tool_batch(
        self,
        state: "_LoopState",
        session_id: str,
        message: str,
        runtime_max_iterations: int,
        cancel_token,
        tool_event_handler,
        pending_message_provider,
        prefer_direct_workflow_result: bool,
    ) -> AsyncIterator[str]:
        """执行一个工具调用批次（原 process_message 工具分支）。

        yield：direct workflow 结果；状态通过 state 传回
        （stop_loop=结束主循环，abort=立即终止生成器）。
        """
        deduped_tool_calls = []
        seen_tool_call_ids = set()
        for tc in state.tool_calls_buffer:
            if tc.id and tc.id in seen_tool_call_ids:
                logger.warning(
                    f"Skipping duplicate tool call by id in main loop: {tc.name} ({tc.id})"
                )
                continue

            if tc.id:
                seen_tool_call_ids.add(tc.id)
            deduped_tool_calls.append(tc)

        state.tool_calls_buffer = deduped_tool_calls

        logger.info(
            "已接收工具批次: "
            f"trace={state.request_trace_id}, iteration={state.iteration}, count={len(state.tool_calls_buffer)}, "
            f"calls=[{self._summarize_tool_calls_for_log(state.tool_calls_buffer)}]"
        )

        remaining_tool_slots = runtime_max_iterations - state.total_tool_calls
        if remaining_tool_slots <= 0:
            logger.warning(
                "Reached max tool call limit before executing a new tool call batch; "
                "aborting batch to avoid sending unmatched tool results upstream"
            )
            state.tool_call_limit_reached = True
            state.stop_loop = True
            return
        if len(state.tool_calls_buffer) > remaining_tool_slots:
            logger.warning(
                f"Truncating tool call batch from {len(state.tool_calls_buffer)} to "
                f"{remaining_tool_slots} to keep tool_calls/tool_results aligned"
            )
            state.tool_calls_buffer = state.tool_calls_buffer[:remaining_tool_slots]

        tool_call_dicts = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.name,
                    "arguments": json.dumps(tc.arguments),
                },
            }
            for tc in state.tool_calls_buffer
        ]

        if self.context_builder:
            state.messages = self.context_builder.add_assistant_message(
                state.messages,
                state.content_buffer or None,
                tool_call_dicts,
                reasoning_content=state.reasoning_buffer or None,
                provider_payload=state.provider_payload,
            )
        else:
            msg = {
                "role": "assistant",
                "content": state.content_buffer or "",
                "tool_calls": tool_call_dicts,
            }
            if state.reasoning_buffer:
                msg["reasoning_content"] = state.reasoning_buffer
            if state.provider_payload:
                msg.update(state.provider_payload)
            state.messages.append(msg)

        for tool_call in state.tool_calls_buffer:
            if state.total_tool_calls >= runtime_max_iterations:
                logger.warning(
                    f"Reached max tool calls limit ({runtime_max_iterations}), "
                    f"skipping remaining tool calls in this iteration"
                )
                break

            if cancel_token and cancel_token.is_cancelled:
                logger.debug(f"Agent loop cancelled before tool execution")
                state.abort = True
                return

            state.total_tool_calls += 1
            async for piece in self._run_single_tool(
                state, session_id, message, tool_call,
                cancel_token, tool_event_handler, prefer_direct_workflow_result,
            ):
                yield piece
            if state.abort:
                return
            if state.stop_tool_loop:
                break
        if state.direct_result_selected:
            state.stop_loop = True
            return

        # 工具批次已全部执行完毕：此时历史里 assistant(tool_calls) 与
        # 对应的 tool 结果已在上下文内配对完成，是插入用户补充消息的
        # 安全位置。若在此处插入，下一轮模型能看到新信息并继续处理。
        if pending_message_provider is not None and not state.direct_result_selected:
            injected = await self._take_pending_message(
                pending_message_provider, session_id, state.request_trace_id
            )
            if injected:
                # 仅写入上下文，不进入回复流：该内容由用户发出，若作为助手输出
                # 会被持久化为一轮助手回复
                state.messages.append(
                    {
                        "role": "user",
                        "content": (
                            "（同一会话中用户补充了以下内容，请一并考虑）\n"
                            f"{injected}"
                        ),
                    }
                )
                # 每吸收一条插话即放行一轮（budget 同步 +1），
                # 使插话在本任务内得到回应，而非被静默丢弃
                state.iteration_budget += 1

    async def _run_single_tool(
        self,
        state: "_LoopState",
        session_id: str,
        message: str,
        tool_call,
        cancel_token,
        tool_event_handler,
        prefer_direct_workflow_result: bool,
    ) -> AsyncIterator[str]:
        """执行单个工具调用并处理其结果/错误（原逐工具循环体）。

        yield：direct workflow 结果。状态通过 state 传回
        （stop_tool_loop=跳过本批次剩余工具，abort=立即终止生成器）。
        """
        tool_name = tool_call.name
        tool_args = tool_call.arguments
        tool_id = tool_call.id

        logger.info(
            "开始执行工具: "
            f"trace={state.request_trace_id}, seq={state.total_tool_calls}, "
            f"name={tool_name}, tool_call_id={tool_id}"
        )

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
        # 一个 LLM Tool call 只创建一个 operation；tool_id 仅用于关联。
        # Registry 为获准执行的每次物理尝试另建 attempt_id。
        operation_id = str(uuid.uuid4())
        outcome = None
        last_error = None
        attempt_source = "agent_initial"

        if self.tools:
            self.tools.set_tool_event_handler(tool_event_handler)
        tool_timeout = self._resolve_tool_timeout_seconds()
        # 自管闹钟的长任务工具（spawn / workflow_run /
        # external_coding_agent）内部已有有界等待与超时返回文案，
        # 主循环不叠加外层 wait_for，避免长任务被默认短超时误杀。
        uses_outer_timeout = tool_name not in self._SELF_ALARMING_TOOLS
        try:
            for attempt in range(max(1, self.max_retries)):
                # 后续尝试若在返回前抛异常，不得沿用上一次的终态。
                outcome = None
                try:
                    if uses_outer_timeout:
                        outcome = await asyncio.wait_for(
                            self.execute_tool(
                                tool_name, tool_args,
                                operation_id=operation_id,
                                correlation_id=tool_id,
                                retry_ceiling=max(0, self.max_retries - 1),
                                retry_authorized=attempt > 0,
                                cancellation_token=cancel_token,
                            ),
                            timeout=tool_timeout,
                        )
                    else:
                        outcome = await self.execute_tool(
                            tool_name, tool_args,
                            operation_id=operation_id,
                            correlation_id=tool_id,
                            retry_ceiling=max(0, self.max_retries - 1),
                            retry_authorized=attempt > 0,
                            cancellation_token=cancel_token,
                        )
                    if isinstance(outcome, (ToolExecutionInProgress, ToolExecutionRejected)):
                        break
                    attempt_source = (
                        "mcp_safe_retry"
                        if attempt > 0 and tool_name.startswith("mcp_")
                        and outcome.retry_safety is RetrySafety.SAFE
                        else "agent_retry" if attempt > 0 else "agent_initial"
                    )
                    # outcome 来自 Registry；每次获准重试返回后分别投影，
                    # 让同一 operation 下的各 attempt 保持独立审计记录。
                    try:
                        from backend.modules.tools.file_audit_logger import file_audit_logger
                        file_audit_logger.record_outcome(
                            outcome,
                            source=attempt_source,
                            session_id=session_id,
                        )
                    except Exception as exc:
                        logger.warning(f"Failed to record Tool outcome: {exc}")
                    if outcome.state is ExecutionState.SUCCEEDED:
                        logger.debug(f"Tool {tool_name} succeeded")
                        break
                    # 仅明确失败、可重试且安全时才申请下一次尝试；
                    # Registry ledger 仍负责核对前次终态并准入新 attempt。
                    if not (
                        outcome.state is ExecutionState.FAILED
                        and outcome.retryable
                        and outcome.retry_safety is RetrySafety.SAFE
                        and outcome.side_effect_state is not SideEffectState.UNKNOWN
                        and attempt < max(1, self.max_retries) - 1
                    ):
                        break
                    logger.warning(
                        f"Tool {tool_name} failed safely (attempt {attempt + 1}/{self.max_retries})"
                    )
                    await asyncio.sleep(self.retry_delay)
                except asyncio.TimeoutError:
                    # Registry 通常在取消后返回 UNKNOWN_OUTCOME；若未返回，
                    # 仍保留副作用不确定性，且不再发起下一次尝试。
                    last_error = (
                        f"Tool '{tool_name}' timed out after {tool_timeout}s; "
                        "execution and side effects may have occurred."
                    )
                    logger.error(
                        f"Tool {tool_name} timed out after "
                        f"{tool_timeout}s"
                    )
                    break
                except Exception as e:
                    # 边界意外上抛时没有可信的重试安全证明，停止重试。
                    last_error = e
                    logger.exception(f"Canonical Tool execution failed: {tool_name}")
                    break
        finally:
            if self.tools:
                self.tools.set_tool_event_handler(None)

        duration_ms = int((time.time() - start_time) * 1000)

        if isinstance(outcome, ToolExecutionInProgress):
            # IN_PROGRESS 只是 operation 准入结果，不记录为物理尝试终态。
            progress_text = outcome.display_text
            if self.context_builder:
                state.messages = self.context_builder.add_tool_result(
                    state.messages, tool_id, tool_name, progress_text,
                )
            else:
                state.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "name": tool_name,
                    "content": progress_text,
                })
            logger.info(
                f"Tool {tool_name} is still in progress: operation={operation_id}"
            )
        elif isinstance(outcome, ToolExecutionOutcome) and outcome.state is ExecutionState.SUCCEEDED:
            result = outcome.display_text
            try:
                conversation_history = get_conversation_history()
                conversation_history.add_conversation(
                    session_id=session_id,
                    tool_name=tool_name,
                    arguments=tool_args,
                    user_message=message,
                    result=result,
                    duration_ms=duration_ms,
                    outcome_projection=project_attempt(
                        outcome, source=attempt_source,
                        session_id=session_id,
                    ),
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
                    phase="success",
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
                            "execution_state": outcome.state.value,
                            "operation_id": outcome.operation_id,
                            "attempt_id": outcome.attempt_id,
                        },
                    )
                    if inspect.isawaitable(maybe_result):
                        await maybe_result
                except Exception as e:
                    logger.warning(f"Tool event handler failed after execution: {e}")

            if tool_name == "workflow_run" and prefer_direct_workflow_result:
                state.final_content = result
                state.direct_result_selected = True
                state.stop_tool_loop = True
                if result:
                    yield result
                return

            if self.context_builder:
                state.messages = self.context_builder.add_tool_result(
                    state.messages,
                    tool_id,
                    tool_name,
                    result,
                )
            else:
                state.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "name": tool_name,
                    "content": result,
                })
            logger.info(
                "已追加工具结果: "
                f"trace={state.request_trace_id}, name={tool_name}, tool_call_id={tool_id}, "
                f"status=success, duration_ms={duration_ms}"
            )
        else:
            if outcome is not None:
                error_msg = outcome.display_text
                if (not isinstance(outcome, ToolExecutionRejected)
                        and outcome.state is ExecutionState.UNKNOWN_OUTCOME):
                    error_msg = (
                        "Tool outcome is unknown; side effects may have occurred. "
                        + error_msg
                    )
            else:
                error_msg = str(last_error or "Tool execution produced no outcome.")
            logger.error(f"Tool {tool_name} did not succeed: {error_msg}")

            if not isinstance(outcome, ToolExecutionRejected):
                try:
                    conversation_history = get_conversation_history()
                    conversation_history.add_conversation(
                        session_id=session_id,
                        tool_name=tool_name,
                        arguments=tool_args,
                        user_message=message,
                        error=error_msg,
                        duration_ms=duration_ms,
                        outcome_projection=(
                            project_attempt(
                                outcome, source=attempt_source,
                                session_id=session_id,
                            ) if isinstance(outcome, ToolExecutionOutcome) else None
                        ),
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
                    phase="non_success",
                )
            except Exception as e:
                logger.warning(f"Failed to send tool error notification: {e}")

            if tool_event_handler:
                try:
                    error_event = {
                        "tool_name": tool_name,
                        "arguments": tool_args,
                        "error": error_msg,
                        "session_id": session_id,
                        "duration_ms": duration_ms,
                        "operation_id": outcome.operation_id if outcome else operation_id,
                    }
                    if isinstance(outcome, ToolExecutionOutcome):
                        error_event["execution_state"] = outcome.state.value
                        error_event["attempt_id"] = outcome.attempt_id
                    elif isinstance(outcome, ToolExecutionRejected):
                        error_event["rejection_reason"] = outcome.reason
                    else:
                        error_event["execution_state"] = None
                        error_event["attempt_id"] = None
                    maybe_result = tool_event_handler(
                        "tool_error",
                        error_event,
                    )
                    if inspect.isawaitable(maybe_result):
                        await maybe_result
                except Exception as e:
                    logger.warning(f"Tool event handler failed on error: {e}")

            if self.context_builder:
                state.messages = self.context_builder.add_tool_result(
                    state.messages,
                    tool_id,
                    tool_name,
                    error_msg,
                )
            else:
                state.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "name": tool_name,
                    "content": error_msg,
                })
            logger.info(
                "已追加工具结果: "
                f"trace={state.request_trace_id}, name={tool_name}, tool_call_id={tool_id}, "
                f"status=error, duration_ms={duration_ms}"
            )

    def _finalize_limits(self, state: "_LoopState", runtime_max_iterations: int) -> Optional[str]:
        """检查迭代/工具额度是否耗尽，返回需要 yield 的提示文案（或 None）。

        插话的额度放宽已在吸收插话处完成（_execute_tool_batch），此处只做
        耗尽判定与提示文案。注意：不做 total_tool_calls 的独立判断——
        工具额度导致批次中止时 tool_call_limit_reached 已置位；插话放行的
        纯文本收尾轮（无新工具调用）不应被工具额度误伤而追加警告。
        """
        pending_exhausted = state.iteration >= state.iteration_budget
        if state.tool_call_limit_reached or pending_exhausted:
            if state.tool_call_limit_reached:
                logger.warning(f"Max tool calls ({runtime_max_iterations}) reached")
                return f"\n\n[达到最大工具调用次数 {runtime_max_iterations}]"
            logger.warning(f"Max iterations ({runtime_max_iterations}) reached")
            return f"\n\n[达到最大迭代次数 {runtime_max_iterations}]"
        return None


    async def _take_pending_message(
        self,
        pending_message_provider,
        session_id: str,
        request_trace_id: str,
    ) -> Optional[str]:
        """从排队消息提供者取出待插入的补充消息。

        提供者可以是同步函数，也可以返回 awaitable。任何异常都只记录日志并按
        「没有补充消息」处理——插话是增强能力，不允许因为取消息失败而打断主循环。
        """
        try:
            result = pending_message_provider()
            if inspect.isawaitable(result):
                result = await result
            text = str(result or "").strip()
        except Exception as exc:
            logger.warning(
                f"Failed to take pending message for session {session_id}: {exc}"
            )
            return None

        if not text:
            return None

        logger.info(
            "已插入排队消息: "
            f"trace={request_trace_id}, session={session_id}, chars={len(text)}"
        )
        return text

    def _try_key_rotation(
        self,
        current_provider: Any,
        error_text: str,
    ) -> Optional[Any]:
        """尝试通过 key 轮换恢复请求。

        当错误是认证/限流相关时，切换到下一个 API Key 并返回新的 provider。
        如果无法轮换（只有一个 key 或不适用），返回 None。
        """
        if not _is_key_rotation_eligible_error(error_text):
            return None

        if self._key_rotation_count >= self.MAX_KEY_ROTATION_RETRIES:
            logger.warning(
                f"Key rotation limit reached ({self.MAX_KEY_ROTATION_RETRIES}), "
                f"stopping rotation attempts"
            )
            return None

        provider_id = getattr(current_provider, "provider_id", None)
        if not provider_id:
            return None

        from backend.modules.providers.runtime import get_key_rotator, KeyRotator
        from backend.modules.config.loader import config_loader
        from backend.modules.providers.runtime import get_provider_runtime_state

        config = config_loader.config
        runtime_state = get_provider_runtime_state(config, provider_id)
        api_keys = runtime_state.api_keys

        if len(api_keys) <= 1:
            logger.debug(
                f"Key rotation skipped for {provider_id}: only {len(api_keys)} key(s) available"
            )
            return None

        rotator = get_key_rotator(provider_id, api_keys)
        current_key = getattr(current_provider, "api_key", "") or ""
        next_key = rotator.mark_key_failed(current_key)

        if not next_key or next_key == current_key:
            logger.warning(
                f"Key rotation exhausted for {provider_id}: no alternative key available"
            )
            return None

        logger.info(
            f"Key rotation for {provider_id}: switching from "
            f"{current_key[:8]}... to {next_key[:8]}... "
            f"(error: {error_text[:100]})"
        )

        from backend.modules.providers import create_provider

        try:
            new_provider = create_provider(
                api_key=next_key,
                api_keys=api_keys,
                api_base=runtime_state.api_base,
                default_model=getattr(current_provider, "default_model", None),
                api_mode=getattr(current_provider, "api_mode", "chat_completions"),
                timeout=getattr(current_provider, "timeout", 120.0),
                max_retries=getattr(current_provider, "max_retries", self.max_retries),
                provider_id=provider_id,
                api_type=runtime_state.api_type,
            )
            return new_provider
        except Exception as exc:
            logger.warning(f"Failed to create rotated provider: {exc}")
            return None

    async def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        *,
        operation_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        cancellation_token=None,
        retry_ceiling: int = 0,
        retry_authorized: bool = False,
    ):
        """将 Tool 调用交给 Registry，并原样返回结构化结果或进行中准入结果。"""
        if not self.tools:
            raise ValueError("ToolRegistry not initialized")
        logger.debug(f"执行工具: {tool_name}")
        return await self.tools.execute_outcome(
            tool_name=tool_name,
            arguments=arguments,
            operation_id=operation_id,
            correlation_id=correlation_id,
            cancellation_token=cancellation_token,
            retry_ceiling=retry_ceiling,
            retry_authorized=retry_authorized,
        )

    async def process_direct(
        self,
        content: str,
        session_id: str = "cli:direct",
        channel: str = "cli",
        chat_id: str = "direct",
        account_id: Optional[str] = None,
        model_override: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        直接处理消息（用于 CLI 或 cron 使用）
        
        Args:
            content: 消息内容
            session_id: 会话标识符
            channel: 来源渠道（用于上下文）
            chat_id: 来源聊天 ID（用于上下文）
            account_id: 当前机器人账号 ID（多机器人渠道）
            model_override: 本次执行的模型覆盖（定时任务指定模型时使用）
        
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
            model_override=model_override,
        ):
            response_parts.append(chunk)
        
        return "".join(response_parts)
