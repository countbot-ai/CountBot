"""Agent Loop - 核心 Agent 循环处理逻辑"""

import asyncio
import inspect
import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from loguru import logger
from backend.modules.agent.tool_events import (
    append_tool_result,
    emit_tool_event,
    notify_tool_phase,
    record_tool_conversation,
)
from backend.modules.agent.tool_signature import build_repeat_notice, tool_signature
from backend.modules.agent.runtime_resolution import (
    AgentRuntimeBases,
    resolve_execution_runtime,
)
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
from backend.modules.providers.thinking_profiles import (
    is_reasoning_off,
    normalize_reasoning_level,
)
from backend.modules.session.usage_recorder import record_usage


# max_iterations=0 表示不限制；折算成内部上界，同时防止死循环。
UNLIMITED_TOOL_BUDGET = 9999
# 同一调用最多真正执行几次，之后回放上次结果。
MAX_IDENTICAL_TOOL_CALLS = 2
# 连续熔断多少次后硬停止本轮工具调用。
MAX_CONSECUTIVE_REPEAT_SKIPS = 3
# 回放给模型的历史结果长度上限。
REPEAT_REPLAY_CHARS = 1200


def resolve_tool_budget(value: Any) -> int:
    """把 max_iterations 折算成额度上界；0/空/非法值视为不限制。"""
    try:
        budget = int(value)
    except (TypeError, ValueError):
        return UNLIMITED_TOOL_BUDGET
    if budget <= 0:
        return UNLIMITED_TOOL_BUDGET
    return budget


def _is_key_rotation_eligible_error(error_text: str) -> bool:
    """判断错误是否适合触发 key 轮换重试，分类 hint 统一取自 providers/base.py。"""
    lower = (error_text or "").lower()
    return any(hint in lower for hint in AUTH_ERROR_HINTS + RATE_LIMIT_HINTS)


@dataclass
class _LoopState:
    """process_message 主循环内共享的可变状态，各阶段方法通过它读写。"""

    messages: List[Dict[str, Any]]
    iteration: int = 0
    iteration_budget: int = 0
    total_tool_calls: int = 0
    # 本次请求的对话模式：chat 时不向模型暴露任何工具，也不注入工具相关提示
    chat_mode: str = "agent"
    # 额度不限制时，触顶也不提示「达到最大工具调用次数」
    tool_budget_unlimited: bool = False
    # 连续成功执行同一调用的次数（失败/超时不计，允许重试）
    repeat_count: int = 0
    # 上次调用指纹；换了调用即重置 repeat_count
    last_tool_signature: str = ""
    # 连续熔断次数，达到阈值后硬停止
    consecutive_repeat_skips: int = 0
    # 硬停止标记，供收尾输出说明
    repeat_stop: bool = False
    # 回放用的上次结果摘要
    tool_result_cache: Dict[str, str] = field(default_factory=dict)
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
    # 供应商服务端工具事件（展示用，同时供持久化回放）
    native_events: List[Dict[str, Any]] = field(default_factory=list)
    # 控制信号：abort / stop_loop / stop_tool_loop / rotation_restart
    abort: bool = False
    stop_loop: bool = False
    stop_tool_loop: bool = False
    rotation_restart: bool = False


class AgentLoop:
    """Agent 主循环类 - 处理消息、调用 LLM、执行工具、生成响应"""

    # 单轮最多轮换 5 次：既避免大量坏 Key 把用户拖住，又比固定 3 次更充分地利用 Key 池
    MAX_KEY_ROTATION_RETRIES = 5

    # 长任务工具自带超时，主循环不对其叠加外层 wait_for
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
        # 0 = 不限制工具调用次数
        max_iterations: int = 0,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        thinking_enabled: bool = True,
        stream_enabled: bool = True,
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
        self.stream_enabled = stream_enabled
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

    def _resolve_call_timeout(self, tool_args: Any) -> int:
        """单次工具调用的外层超时（秒），取配置默认值与入参超时的较大者。"""
        configured = self._resolve_tool_timeout_seconds()
        requested = tool_args.get("timeout") if isinstance(tool_args, dict) else None
        # timeout 可能是字符串（"180"），需一并识别
        try:
            requested_seconds = int(float(requested)) if requested is not None else 0
        except (TypeError, ValueError):
            requested_seconds = 0
        if requested_seconds > 0:
            return max(configured, requested_seconds + 5)
        return configured

    def _resolve_tool_timeout_seconds(self) -> int:
        """解析主循环工具调用超时（秒），解析失败时返回 60。"""
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
    ) -> tuple[Any, Optional[str], float, int, int, bool, bool, Optional[str]]:
        """解析当前消息执行应使用的 provider 和模型参数。"""
        return resolve_execution_runtime(
            AgentRuntimeBases(
                provider=self.provider,
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                max_iterations=self.max_iterations,
                thinking_enabled=self.thinking_enabled,
                stream_enabled=self.stream_enabled,
                reasoning_level=self.reasoning_level,
                max_retries=self.max_retries,
            ),
            model_override,
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
        native_event_handler=None,
        prefer_direct_workflow_result: bool = False,
        pending_message_provider=None,
        chat_mode: str = "agent",
    ) -> AsyncIterator[str]:
        """处理用户消息并生成流式响应，各阶段通过 _LoopState 共享状态。"""
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
            runtime_stream_enabled,
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

        # max_iterations=0（默认）表示不限制；折算值统一用于循环上界与额度校验。
        tool_budget_unlimited = resolve_tool_budget(runtime_max_iterations) == UNLIMITED_TOOL_BUDGET
        runtime_max_iterations = resolve_tool_budget(runtime_max_iterations)
        normalized_chat_mode = "chat" if str(chat_mode or "").strip().lower() == "chat" else "agent"

        native_file_blocks: List[Dict[str, Any]] = []
        if media and self.context_builder:
            native_file_blocks, handled_paths = await self._prepare_native_documents(
                media=media,
                provider=active_provider,
                model=runtime_model,
                supports_image=supports_image,
            )
            if native_file_blocks:
                media = [
                    path
                    for path in media
                    if str(path or "").strip().replace("\\", "/") not in handled_paths
                ]

        state = _LoopState(
            messages=self._prepare_messages(
                message, context, session_summary, media, channel, chat_id,
                account_id, persona_override, supports_image,
                tool_budget=None if tool_budget_unlimited else runtime_max_iterations,
                chat_mode=normalized_chat_mode,
                native_file_blocks=native_file_blocks,
                session_id=session_id,
            ),
            iteration=0,
            iteration_budget=runtime_max_iterations,
            tool_budget_unlimited=tool_budget_unlimited,
            active_provider=active_provider,
            request_trace_id=f"{session_id[:8]}-{uuid.uuid4().hex[:8]}",
            chat_mode=normalized_chat_mode,
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
                    runtime_thinking_enabled, runtime_stream_enabled, runtime_reasoning_level,
                    cancel_token, yield_intermediate, reasoning_event_handler,
                    native_event_handler,
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

    async def _prepare_native_documents(
        self,
        *,
        media: List[str],
        provider: Any,
        model: Optional[str],
        supports_image: bool = True,
    ) -> tuple[List[Dict[str, Any]], set[str]]:
        """按模型能力把附件上传为 DeepSeek file_id；失败时回落到原附件链路。"""
        try:
            from backend.modules.native_caps.files import build_document_blocks
            from backend.modules.native_caps.service import capabilities_for_provider

            caps = capabilities_for_provider(provider, model)
            if caps.document_parsing == "off":
                return [], set()
            return await build_document_blocks(
                media,
                workspace=self.context_builder.workspace,
                api_base=getattr(provider, "api_base", None),
                api_key=getattr(provider, "api_key", None),
                provider_id=getattr(provider, "provider_id", None),
                model=model,
                capabilities=caps,
                include_images=not supports_image,
            )
        except Exception as exc:
            logger.warning(f"原生文档解析准备失败，继续走原附件链路: {exc}")
            return [], set()

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
        tool_budget: Optional[int] = None,
        chat_mode: str = "agent",
        native_file_blocks: Optional[List[Dict[str, Any]]] = None,
        session_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """构建发送给模型的 messages 列表；tool_budget 为 None 表示不限额。"""
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
                tool_budget=tool_budget,
                chat_mode=chat_mode,
                native_file_blocks=native_file_blocks,
                session_id=session_id,
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
        runtime_stream_enabled: bool,
        runtime_reasoning_level: Optional[str],
        cancel_token,
        yield_intermediate: bool,
        reasoning_event_handler,
        native_event_handler=None,
    ) -> AsyncIterator[str]:
        """消费一次模型流，yield 内容 chunk，并把结果缓冲写回 state。"""
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

        # 显式选择「关闭」思考时，即使上游仍回传 reasoning（部分模型无法真正
        # 关闭），也不再向前端输出思考块，保证「关闭」的语义一致。
        explicit_level = normalize_reasoning_level(runtime_reasoning_level)
        suppress_reasoning = (
            explicit_level is not None and is_reasoning_off(explicit_level)
        )

        # 对话模式不向模型暴露任何工具：工具定义通常占总 token 的大头
        tool_definitions = (
            []
            if state.chat_mode == "chat"
            else (self.tools.get_definitions() if self.tools else [])
        )

        async for chunk in state.active_provider.chat_stream(
            messages=state.messages,
            tools=tool_definitions,
            model=runtime_model,
            temperature=runtime_temperature,
            max_tokens=runtime_max_tokens,
            thinking_enabled=runtime_thinking_enabled,
            stream_enabled=runtime_stream_enabled,
            reasoning_level=runtime_reasoning_level,
            **provider_trace_kwargs,
        ):
            if chunk.is_content and chunk.content:
                state.content_buffer += chunk.content
                if yield_intermediate:
                    yield chunk.content

            if chunk.is_tool_call and chunk.tool_call:
                # 对话模式硬性禁止工具执行：即使模型自行吐出 tool_call 也不收集，
                # 避免绕过「不提供工具定义」的约定真的跑到工具层。
                if state.chat_mode != "chat":
                    state.tool_calls_buffer.append(chunk.tool_call)

            if (
                chunk.is_reasoning
                and chunk.reasoning_content
                and not suppress_reasoning
            ):
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

            if chunk.has_native_events and chunk.native_events:
                for native_event in chunk.native_events:
                    if not isinstance(native_event, dict):
                        continue
                    state.native_events.append(native_event)
                    if native_event_handler:
                        try:
                            maybe_result = native_event_handler(native_event)
                            if inspect.isawaitable(maybe_result):
                                await maybe_result
                        except Exception as exc:
                            logger.warning(
                                f"Failed to emit native event for session {session_id}: {exc}"
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
                        # 本轮尚未输出内容：用轮换后的 provider 重发本轮，避免空回复
                        state.rotation_restart = True
                        return
                    # 本轮已有输出：继续消费当前流，避免重复内容
                    continue
                yield chunk.error
                state.abort = True
                return

        # 每次模型调用结束后记录一次用量，一轮对话可能包含多次调用
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
        """执行一个工具调用批次，状态通过 state 回传。"""
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

        executed_count = 0
        for index, tool_call in enumerate(state.tool_calls_buffer):
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
            executed_count = index + 1
            async for piece in self._run_single_tool(
                state, session_id, message, tool_call,
                cancel_token, tool_event_handler, prefer_direct_workflow_result,
            ):
                yield piece
            if state.abort:
                return
            if state.stop_tool_loop:
                break
            if state.stop_loop:
                break  # 硬停止：剩余调用不再执行

        # 提前结束时补占位结果，保持 tool_calls 与 tool 结果一一配对
        if executed_count < len(state.tool_calls_buffer):
            for tool_call in state.tool_calls_buffer[executed_count:]:
                placeholder = "[已跳过：本轮工具调用提前结束]"
                if self.context_builder:
                    state.messages = self.context_builder.add_tool_result(
                        state.messages, tool_call.id, tool_call.name, placeholder,
                    )
                else:
                    state.messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_call.name,
                        "content": placeholder,
                    })

        if state.direct_result_selected:
            state.stop_loop = True
            return

        # 工具批次结束后 tool_calls 已与结果配对，可安全插入用户补充消息
        if pending_message_provider is not None and not state.direct_result_selected:
            injected = await self._take_pending_message(
                pending_message_provider, session_id, state.request_trace_id
            )
            if injected:
                # 仅写入上下文，不进入回复流，避免被持久化为助手回复
                state.messages.append(
                    {
                        "role": "user",
                        "content": (
                            "（同一会话中用户补充了以下内容，请一并考虑）\n"
                            f"{injected}"
                        ),
                    }
                )
                # 每插入一条补充消息即增加一轮额度，使其在本任务内得到回应
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
        """执行单个工具调用并处理结果与错误，状态通过 state 回传。"""
        tool_name = tool_call.name
        tool_args = tool_call.arguments
        tool_id = tool_call.id

        logger.info(
            "开始执行工具: "
            f"trace={state.request_trace_id}, seq={state.total_tool_calls}, "
            f"name={tool_name}, tool_call_id={tool_id}"
        )

        await emit_tool_event(
            tool_event_handler,
            "tool_call",
            {
                "tool_name": tool_name,
                "arguments": tool_args,
                "session_id": session_id,
            },
            failure_message="Tool event handler failed before execution",
        )

        await notify_tool_phase(session_id, tool_name, tool_args)

        # 重复调用熔断：同名 + 归一化参数一致且已连续成功足够次数，回放上次结果
        signature = tool_signature(tool_name, tool_args)
        if state.last_tool_signature != signature:
            state.last_tool_signature = signature
            state.repeat_count = 0
        if state.repeat_count >= MAX_IDENTICAL_TOOL_CALLS:
            await self._intercept_repeat_call(
                state,
                tool_name=tool_name,
                tool_args=tool_args,
                tool_id=tool_id,
                signature=signature,
                session_id=session_id,
                tool_event_handler=tool_event_handler,
            )
            return

        # 真正进入执行流程，重置连续拦截计数
        state.consecutive_repeat_skips = 0

        start_time = time.time()
        # 每个 tool call 只创建一个 operation，Registry 为每次尝试另建 attempt_id
        operation_id = str(uuid.uuid4())
        outcome, last_error, attempt_source = await self._execute_tool_with_retries(
            tool_name=tool_name,
            tool_args=tool_args,
            tool_id=tool_id,
            operation_id=operation_id,
            session_id=session_id,
            cancel_token=cancel_token,
            tool_event_handler=tool_event_handler,
        )
        duration_ms = int((time.time() - start_time) * 1000)

        if isinstance(outcome, ToolExecutionInProgress):
            self._record_tool_in_progress(state, tool_call, outcome, operation_id)
            return

        if isinstance(outcome, ToolExecutionOutcome) and outcome.state is ExecutionState.SUCCEEDED:
            direct_result = await self._record_tool_success(
                state=state,
                tool_call=tool_call,
                outcome=outcome,
                session_id=session_id,
                message=message,
                tool_event_handler=tool_event_handler,
                duration_ms=duration_ms,
                signature=signature,
                attempt_source=attempt_source,
                prefer_direct_workflow_result=prefer_direct_workflow_result,
            )
            if state.direct_result_selected:
                if direct_result:
                    yield direct_result
                return
            return

        await self._record_tool_failure(
            state=state,
            tool_call=tool_call,
            outcome=outcome,
            last_error=last_error,
            operation_id=operation_id,
            session_id=session_id,
            message=message,
            tool_event_handler=tool_event_handler,
            duration_ms=duration_ms,
            attempt_source=attempt_source,
        )

    async def _intercept_repeat_call(
        self,
        state: "_LoopState",
        *,
        tool_name: str,
        tool_args: Any,
        tool_id: str,
        signature: str,
        session_id: str,
        tool_event_handler,
    ) -> None:
        """重复调用熔断：回放上次结果并累计硬停止计数。"""
        state.consecutive_repeat_skips += 1
        notice = build_repeat_notice(
            tool_name,
            state.repeat_count + state.consecutive_repeat_skips,
            state.tool_result_cache.get(signature),
        )
        hard_stop = state.consecutive_repeat_skips >= MAX_CONSECUTIVE_REPEAT_SKIPS
        if hard_stop:
            # 无限额度下也需要硬停止，避免空转
            state.repeat_stop = True
            state.stop_loop = True
            notice += "\n已连续多次重复同一调用，本轮工具调用到此为止。"
        logger.warning(
            "重复工具调用已熔断: "
            f"trace={state.request_trace_id}, name={tool_name}, "
            f"consecutive_skips={state.consecutive_repeat_skips}, hard_stop={hard_stop}"
        )
        # 没有真正执行，不占工具的调用额度
        state.total_tool_calls = max(0, state.total_tool_calls - 1)
        state.messages = append_tool_result(
            self.context_builder, state.messages, tool_id, tool_name, notice,
        )
        await emit_tool_event(
            tool_event_handler,
            "tool_result",
            {
                "tool_name": tool_name,
                "arguments": tool_args,
                "result": notice,
                "session_id": session_id,
                "duration_ms": 0,
                "execution_state": "REPEATED_SKIPPED",
                "operation_id": "",
                "attempt_id": "",
            },
            failure_message="Tool event handler failed on repeat skip",
        )

    async def _execute_tool_with_retries(
        self,
        *,
        tool_name: str,
        tool_args: Any,
        tool_id: str,
        operation_id: str,
        session_id: str,
        cancel_token,
        tool_event_handler,
    ) -> tuple[Any, Optional[Exception], str]:
        """带重试与审计的单次工具执行，返回 (outcome, last_error, attempt_source)。"""
        outcome = None
        last_error = None
        attempt_source = "agent_initial"

        if self.tools:
            self.tools.set_tool_event_handler(tool_event_handler)
        tool_timeout = self._resolve_call_timeout(tool_args)
        # 长任务工具自带超时，主循环不叠加外层 wait_for
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
                    # 每次获准重试后分别投影，保持各 attempt 的独立审计记录
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
                    # 仅在明确失败、可重试且安全时申请下一次尝试
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
                    # 取消后通常返回 UNKNOWN_OUTCOME，否则保留不确定性并停止重试
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

        return outcome, last_error, attempt_source

    def _record_tool_in_progress(
        self,
        state: "_LoopState",
        tool_call,
        outcome: ToolExecutionInProgress,
        operation_id: str,
    ) -> None:
        """IN_PROGRESS 只是 operation 准入结果，不记录为物理尝试终态。"""
        state.repeat_count = 0
        progress_text = outcome.display_text
        state.messages = append_tool_result(
            self.context_builder,
            state.messages,
            tool_call.id,
            tool_call.name,
            progress_text,
        )
        logger.info(
            f"Tool {tool_call.name} is still in progress: operation={operation_id}"
        )

    async def _record_tool_success(
        self,
        *,
        state: "_LoopState",
        tool_call,
        outcome: ToolExecutionOutcome,
        session_id: str,
        message: str,
        tool_event_handler,
        duration_ms: int,
        signature: str,
        attempt_source: str,
        prefer_direct_workflow_result: bool,
    ) -> Optional[str]:
        """成功路径：留痕、通知、事件回调与上下文回填；返回直接选中的工作流结果。"""
        tool_name = tool_call.name
        tool_args = tool_call.arguments
        tool_id = tool_call.id
        result = outcome.display_text
        # 只有成功才计入连续重复
        state.repeat_count += 1
        state.tool_result_cache[signature] = (result or "")[:REPEAT_REPLAY_CHARS]

        record_tool_conversation(
            session_id=session_id,
            tool_name=tool_name,
            arguments=tool_args,
            user_message=message,
            result=result,
            duration_ms=duration_ms,
            outcome=outcome,
            attempt_source=attempt_source,
        )

        await notify_tool_phase(
            session_id, tool_name, tool_args,
            result=result, phase="success",
        )

        await emit_tool_event(
            tool_event_handler,
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
            failure_message="Tool event handler failed after execution",
        )

        if tool_name == "workflow_run" and prefer_direct_workflow_result:
            state.final_content = result
            state.direct_result_selected = True
            state.stop_tool_loop = True
            return result

        state.messages = append_tool_result(
            self.context_builder, state.messages, tool_id, tool_name, result,
        )
        logger.info(
            "已追加工具结果: "
            f"trace={state.request_trace_id}, name={tool_name}, tool_call_id={tool_id}, "
            f"status=success, duration_ms={duration_ms}"
        )
        return None

    async def _record_tool_failure(
        self,
        *,
        state: "_LoopState",
        tool_call,
        outcome,
        last_error,
        operation_id: str,
        session_id: str,
        message: str,
        tool_event_handler,
        duration_ms: int,
        attempt_source: str,
    ) -> None:
        """失败/超时/未知终态路径：留痕、错误通知并回填上下文。"""
        tool_name = tool_call.name
        tool_args = tool_call.arguments
        tool_id = tool_call.id
        # 失败/超时不计入，允许重试
        state.repeat_count = 0
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
            record_tool_conversation(
                session_id=session_id,
                tool_name=tool_name,
                arguments=tool_args,
                user_message=message,
                error=error_msg,
                duration_ms=duration_ms,
                outcome=(
                    outcome if isinstance(outcome, ToolExecutionOutcome) else None
                ),
                attempt_source=attempt_source,
            )

        await notify_tool_phase(
            session_id, tool_name, tool_args,
            error=error_msg, phase="non_success",
        )

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
        await emit_tool_event(
            tool_event_handler,
            "tool_error",
            error_event,
            failure_message="Tool event handler failed on error",
        )

        state.messages = append_tool_result(
            self.context_builder, state.messages, tool_id, tool_name, error_msg,
        )
        logger.info(
            "已追加工具结果: "
            f"trace={state.request_trace_id}, name={tool_name}, tool_call_id={tool_id}, "
            f"status=error, duration_ms={duration_ms}"
        )

    def _finalize_limits(self, state: "_LoopState", runtime_max_iterations: int) -> Optional[str]:
        """检查迭代与工具额度是否耗尽，返回需要 yield 的提示文案。"""
        pending_exhausted = state.iteration >= state.iteration_budget
        if state.repeat_stop:
            logger.warning(
                f"Stopped after {MAX_CONSECUTIVE_REPEAT_SKIPS} consecutive repeated tool calls"
            )
            return "\n\n[检测到连续重复调用，已停止本轮工具调用]"
        if state.tool_call_limit_reached or pending_exhausted:
            if state.tool_budget_unlimited:
                # 触顶属于死循环级异常，只留日志，不向用户报「达到上限」
                logger.error(
                    f"Unlimited tool budget hit internal ceiling ({runtime_max_iterations}); "
                    "possible runaway loop"
                )
                return None
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
        """取出待插入的补充消息；异常按无消息处理并记录日志。"""
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
        """认证或限流错误时切换到下一个 API Key，无法轮换返回 None。"""
        if not _is_key_rotation_eligible_error(error_text):
            return None

        provider_id = getattr(current_provider, "provider_id", None)
        if not provider_id:
            return None

        from backend.modules.providers.runtime import get_key_rotator

        # 优先使用 provider 实例自带的 Key 列表与地址：
        # 多用户私有供应商的 Key 不在全局配置里，反查全局会读错甚至串用管理员 Key。
        api_keys = list(getattr(current_provider, "api_keys", None) or [])
        api_base = getattr(current_provider, "api_base", None)
        api_type = getattr(current_provider, "api_type", None)
        native_capabilities = getattr(current_provider, "native_capabilities", None)

        if not api_keys:
            from backend.modules.config.loader import config_loader
            from backend.modules.providers.runtime import get_provider_runtime_state

            runtime_state = get_provider_runtime_state(
                config_loader.config, provider_id
            )
            api_keys = runtime_state.api_keys
            api_base = api_base or runtime_state.api_base
            api_type = api_type or runtime_state.api_type

        if len(api_keys) <= 1:
            logger.debug(
                f"Key rotation skipped for {provider_id}: only {len(api_keys)} key(s) available"
            )
            return None

        # 实际可轮换次数不会超过「Key 数 - 1」，也不会超过单轮上限
        max_rotations = min(len(api_keys) - 1, self.MAX_KEY_ROTATION_RETRIES)
        if self._key_rotation_count >= max_rotations:
            logger.warning(
                f"Key rotation limit reached ({max_rotations}) for {provider_id}, "
                "stopping rotation attempts"
            )
            return None

        rotator = get_key_rotator(provider_id, api_keys)
        current_key = getattr(current_provider, "api_key", "") or ""
        lowered_error = (error_text or "").lower()
        if any(hint in lowered_error for hint in AUTH_ERROR_HINTS):
            # 认证失效通常不会自己恢复，给更长的冷却，避免下一轮立刻再撞上
            cooldown_seconds = 600.0
        elif any(hint in lowered_error for hint in RATE_LIMIT_HINTS):
            cooldown_seconds = 60.0
        else:
            cooldown_seconds = 0.0
        next_key = rotator.mark_key_failed(
            current_key,
            cooldown_seconds=cooldown_seconds,
        )

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
                api_base=api_base,
                default_model=getattr(current_provider, "default_model", None),
                api_mode=getattr(current_provider, "api_mode", "chat_completions"),
                timeout=getattr(current_provider, "timeout", 120.0),
                max_retries=getattr(current_provider, "max_retries", self.max_retries),
                provider_id=provider_id,
                api_type=api_type,
                native_capabilities=native_capabilities,
                stream_enabled=getattr(current_provider, "stream_enabled", True),
                # 明确指定本次故障转移要用的 Key，避免工厂再次轮询跳过它
                key_override=next_key,
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
        context: Optional[List[Dict[str, Any]]] = None,
        model_override: Optional[Dict[str, Any]] = None,
    ) -> str:
        """直接处理消息（CLI 或 cron 使用），返回响应文本。"""
        response_parts = []
        
        async for chunk in self.process_message(
            message=content,
            session_id=session_id,
            context=[] if context is None else context,
            channel=channel,
            chat_id=chat_id,
            account_id=account_id,
            model_override=model_override,
        ):
            response_parts.append(chunk)
        
        return "".join(response_parts)
