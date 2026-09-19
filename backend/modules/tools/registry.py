"""Tool Registry - 工具注册表"""

import asyncio
import contextvars
import re
import uuid
import time
from typing import Any, Dict, List, Optional
from datetime import datetime

from loguru import logger

from backend.modules.tools.base import Tool
from backend.modules.tools.execution_context import (
    ToolExecutionContext,
    push_tool_execution_context,
    reset_tool_execution_context,
)
from backend.modules.tools.file_audit_logger import file_audit_logger
from backend.modules.tools._failure import (
    RetryableToolError,
    classify_exception,
    format_failure,
    is_retryable,
    single_line,
)
from backend.modules.tools.execution import (
    ErrorCategory,
    AttemptTransitionError,
    CanonicalToolExecutionResult,
    OperationLedger,
    OperationIdentityCollisionError,
    ExecutionState,
    SideEffectState,
    ToolExecutionInProgress,
    ToolExecutionOutcome,
    ToolExecutionRequest,
    ToolResult,
)

# 使用 contextvars 实现异步安全的 session_id 存储
# 每个异步任务都有独立的上下文，避免并发冲突
_session_id_context: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    'session_id', default=None
)
_channel_context: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    'channel', default=None
)
_message_context: contextvars.ContextVar[Optional[Dict[str, Any]]] = contextvars.ContextVar(
    'message_context', default=None
)

# 代理上下文
_agent_type_context: contextvars.ContextVar[str] = contextvars.ContextVar(
    'agent_type', default='main'
)
_agent_id_context: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    'agent_id', default=None
)
_workflow_id_context: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    'workflow_id', default=None
)
_parent_tool_call_id_context: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    'parent_tool_call_id', default=None
)
_tool_event_handler_context: contextvars.ContextVar[Optional[Any]] = contextvars.ContextVar(
    'tool_event_handler', default=None
)

_TOOL_ARGUMENT_PARSE_ERROR_KEY = "__tool_argument_parse_error__"
_TOOL_ARGUMENT_RAW_KEY = "__tool_argument_raw__"


class ToolRegistry:
    """工具注册表 - 管理所有可用工具的注册、查询和执行"""

    def __init__(self, ledger: Optional[OperationLedger] = None):
        """初始化工具注册表"""
        self._tools: Dict[str, Tool] = {}
        self._audit_enabled: bool = True
        self._definitions_cache: Optional[List[Dict[str, Any]]] = None
        self._operation_ledger = ledger or OperationLedger()
        # 注意：不再使用实例变量存储 session_id，改用 contextvars
        logger.debug("ToolRegistry initialized (using contextvars for session isolation)")

    def set_audit_enabled(self, enabled: bool) -> None:
        """设置是否启用审计日志"""
        self._audit_enabled = enabled
        file_audit_logger.set_enabled(enabled)
        logger.debug(f"Audit logging {'enabled' if enabled else 'disabled'}")
    
    def set_session_id(self, session_id: Optional[str]) -> None:
        """设置当前上下文的会话 ID（异步安全）
        
        使用 contextvars 确保每个异步任务都有独立的 session_id，
        避免并发请求之间的相互覆盖。
        """
        _session_id_context.set(session_id)

        # 遍历所有工具，更新支持 set_session_id 的工具
        for tool in self._tools.values():
            if hasattr(tool, 'set_session_id'):
                tool.set_session_id(session_id)
    
    @property
    def _session_id(self) -> Optional[str]:
        """获取当前上下文的会话 ID（异步安全）"""
        return _session_id_context.get()

    def set_cancel_token(self, token) -> None:
        """设置取消令牌，并传递给所有支持 set_cancel_token 的工具（如 WorkflowTool）。"""
        for tool in self._tools.values():
            if hasattr(tool, 'set_cancel_token'):
                tool.set_cancel_token(token)

    def set_agent_context(
        self,
        agent_type: str = "main",
        agent_id: Optional[str] = None,
        workflow_id: Optional[str] = None,
        parent_tool_call_id: Optional[str] = None,
    ) -> None:
        """设置代理上下文信息（异步安全）
        
        Args:
            agent_type: 代理类型（main / subagent / workflow）
            agent_id: 子代理 ID
            workflow_id: 工作流 ID
            parent_tool_call_id: 父工具调用 ID
        """
        _agent_type_context.set(agent_type)
        _agent_id_context.set(agent_id)
        _workflow_id_context.set(workflow_id)
        _parent_tool_call_id_context.set(parent_tool_call_id)
    
    def set_channel(self, channel: Optional[str]) -> None:
        """设置当前上下文的消息来源渠道（异步安全）
        
        如 dingtalk, telegram, web-chat
        """
        _channel_context.set(channel)

        # 更新记忆工具的默认来源（兼容统一 memory 工具和旧版 memory_write 工具）
        memory_tool = self._tools.get('memory') or self._tools.get('memory_write')
        if memory_tool and hasattr(memory_tool, 'set_channel'):
            memory_tool.set_channel(channel)

    def set_message_context(self, message_context: Optional[Dict[str, Any]]) -> None:
        """设置当前上下文的入站消息上下文（异步安全）。"""
        _message_context.set(message_context)

        for tool in self._tools.values():
            if hasattr(tool, 'set_message_context'):
                tool.set_message_context(message_context)

    def set_tool_event_handler(self, handler: Optional[Any]) -> None:
        """设置当前工具执行的事件回调（异步安全）。"""
        _tool_event_handler_context.set(handler)

    @property
    def channel(self) -> Optional[str]:
        """获取当前上下文的渠道（异步安全）"""
        return _channel_context.get()

    @property
    def message_context(self) -> Optional[Dict[str, Any]]:
        """获取当前上下文的入站消息上下文（异步安全）。"""
        return _message_context.get()

    def register(self, tool: Tool) -> None:
        """
        注册工具
        
        Args:
            tool: 要注册的工具实例
            
        Raises:
            ValueError: 如果工具名称已存在
        """
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")
        
        self._tools[tool.name] = tool
        self._definitions_cache = None
        logger.debug(f"Registered tool: {tool.name}")

    def unregister(self, tool_name: str) -> bool:
        """
        注销工具
        
        Args:
            tool_name: 工具名称
            
        Returns:
            bool: 是否成功注销
        """
        if tool_name in self._tools:
            del self._tools[tool_name]
            self._definitions_cache = None
            logger.debug(f"Unregistered tool: {tool_name}")
            return True
        else:
            logger.warning(f"Tool '{tool_name}' not found for unregistration")
            return False

    def get_tool(self, tool_name: str) -> Optional[Tool]:
        """
        获取工具实例
        
        Args:
            tool_name: 工具名称
            
        Returns:
            Tool | None: 工具实例，如果不存在则返回 None
        """
        return self._tools.get(tool_name)

    def has_tool(self, tool_name: str) -> bool:
        """
        检查工具是否已注册
        
        Args:
            tool_name: 工具名称
            
        Returns:
            bool: 工具是否存在
        """
        return tool_name in self._tools

    def list_tools(self) -> List[str]:
        """
        列出所有已注册的工具名称
        
        Returns:
            List[str]: 工具名称列表
        """
        return list(self._tools.keys())

    @staticmethod
    def _extract_tool_argument_parse_failure(
        arguments: Dict[str, Any],
    ) -> tuple[Optional[str], Optional[str]]:
        if not isinstance(arguments, dict):
            return None, None

        parse_error = arguments.get(_TOOL_ARGUMENT_PARSE_ERROR_KEY)
        raw_arguments = arguments.get(_TOOL_ARGUMENT_RAW_KEY)
        if parse_error:
            return str(parse_error), str(raw_arguments or "")

        # 兼容旧 provider 返回的 {"raw": "..."} 格式。
        if set(arguments.keys()) == {"raw"}:
            return "Malformed JSON tool arguments", str(arguments.get("raw") or "")

        return None, None

    @staticmethod
    def _format_tool_argument_parse_error(
        tool_name: str,
        parse_error: str,
        raw_arguments: Optional[str],
    ) -> str:
        path_hint = None
        if raw_arguments:
            match = re.search(r'"path"\s*:\s*"([^"]+)"', raw_arguments)
            if match:
                path_hint = match.group(1)

        guidance = "Please regenerate the tool call with valid JSON arguments."
        if tool_name in {"write_file", "edit_file"}:
            guidance += (
                " For large HTML/code/text, write in small chunks "
                "(recommended <= 800 chars each) and use `mode=\"append\"` "
                "after the first chunk."
            )
        if path_hint:
            guidance += f" Detected path: {path_hint}."

        compact_raw = ""
        if raw_arguments:
            compact_raw = " ".join(str(raw_arguments).split())
            if len(compact_raw) > 200:
                compact_raw = compact_raw[:200] + "..."

        suffix = f" Raw prefix: {compact_raw}" if compact_raw else ""
        return (
            f"Error: Tool call arguments for '{tool_name}' were truncated or malformed "
            f"before execution ({parse_error}). {guidance}{suffix}"
        )

    @staticmethod
    def _schema_name(schema: Dict[str, Any]) -> str:
        return (schema.get("function") or schema).get("name", "")

    def get_definitions(self) -> List[Dict[str, Any]]:
        """
        获取所有工具的定义
        
        用于生成 LLM 函数调用的工具列表。
        内置工具按名称排序在前，MCP 工具按名称排序在后，
        保证跨次调用的顺序一致性，有利于 LLM prompt caching。
        
        Returns:
            List[dict]: 工具定义列表
        """
        if self._definitions_cache is None:
            definitions = [tool.get_definition() for tool in self._tools.values()]
            builtins: List[Dict[str, Any]] = []
            mcp_tools: List[Dict[str, Any]] = []
            for schema in definitions:
                name = self._schema_name(schema)
                if name.startswith("mcp_"):
                    mcp_tools.append(schema)
                else:
                    builtins.append(schema)
            builtins.sort(key=self._schema_name)
            mcp_tools.sort(key=self._schema_name)
            self._definitions_cache = builtins + mcp_tools
            logger.debug(f"Generated {len(self._definitions_cache)} tool definitions ({len(builtins)} builtin, {len(mcp_tools)} MCP)")
        return self._definitions_cache

    @staticmethod
    def _is_pre_execution_cancelled(cancellation_token: Any) -> bool:
        """无需依赖调度时序，读取常见 cancellation primitive 的状态。

PR1 只在进入 Tool body 前作出判断；执行中的 cancellation 与 effect certainty
属于后续 Tool migration 的范围。
"""

        if cancellation_token is None:
            return False
        for attribute in ("is_cancelled", "is_set", "cancelled"):
            value = getattr(cancellation_token, attribute, None)
            if callable(value):
                value = value()
            if isinstance(value, bool):
                return value
        return isinstance(cancellation_token, bool) and cancellation_token

    @staticmethod
    def _identity_collision_outcome(request: ToolExecutionRequest) -> ToolExecutionOutcome:
        """在不破坏已有 operation 的前提下，返回进入 body 前的拒绝 outcome。"""

        return ToolExecutionOutcome(
            operation_id=request.operation_id,
            attempt_id=str(uuid.uuid4()),
            attempt_ordinal=0,
            tool_name=request.tool_name,
            state=ExecutionState.FAILED,
            display_text="operation_id is already bound to a different Tool invocation.",
            duration_ms=0,
            error_category=ErrorCategory.VALIDATION,
            side_effect_state=SideEffectState.NOT_ATTEMPTED,
            correlation_id=request.correlation_id,
        )

    @staticmethod
    def _in_progress_result(
        request: ToolExecutionRequest,
        active_attempt_id: str,
    ) -> ToolExecutionInProgress:
        """Describe a matching active operation without creating an attempt."""

        return ToolExecutionInProgress(
            operation_id=request.operation_id,
            active_attempt_id=active_attempt_id,
            tool_name=request.tool_name,
            correlation_id=request.correlation_id,
            display_text="Tool operation is already in progress.",
        )

    @staticmethod
    def render_outcome(outcome: ToolExecutionOutcome) -> str:
        """为临时 text-only consumer 渲染 canonical outcome。

该 renderer 不会从文本推断任何状态。所有 caller 都直接消费
``ToolExecutionOutcome`` 后即可移除。
"""

        return outcome.display_text

    async def execute_outcome(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        *,
        operation_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        cancellation_token: Any = None,
        retry_ceiling: int = 0,
        retry_authorized: bool = False,
        proven_safe_idempotency: bool = False,
    ) -> CanonicalToolExecutionResult:
        """为一次 canonical Tool attempt 生成 authoritative outcome。

迁移期间，现有 caller 继续使用 ``execute``。新 caller 必须使用本方法，并检查
``outcome.state``，而不是依据渲染后的字符串或普通函数返回值判断结果。
"""

        request_arguments: Dict[str, Any]
        if isinstance(arguments, dict):
            request_arguments = arguments
        else:
            # 不在 ledger 中保存原始 malformed input，同时仍为被拒绝的 request
            # 分配 operation identity。
            request_arguments = {"__invalid_arguments_type__": type(arguments).__name__}

        request = ToolExecutionRequest.create(
            tool_name=tool_name,
            arguments=request_arguments,
            operation_id=operation_id,
            correlation_id=correlation_id,
            retry_ceiling=retry_ceiling,
        )
        try:
            replay = self._operation_ledger.completed_outcome(request)
            active_attempt = self._operation_ledger.active_attempt_for_operation(request)
        except OperationIdentityCollisionError:
            return self._identity_collision_outcome(request)
        if replay is not None:
            if replay.state is ExecutionState.SUCCEEDED or not retry_authorized:
                return replay
            if replay.state is ExecutionState.UNKNOWN_OUTCOME and not proven_safe_idempotency:
                return replay
        if active_attempt is not None:
            return self._in_progress_result(request, active_attempt.attempt_id)

        try:
            attempt = self._operation_ledger.create_attempt(request)
        except OperationIdentityCollisionError:
            return self._identity_collision_outcome(request)
        except AttemptTransitionError:
            # ``create_attempt`` remains the ledger authority.  A matching
            # active attempt discovered after admission is an overlapping
            # duplicate, not a new physical attempt or an unknown outcome.
            active_attempt = self._operation_ledger.active_attempt_for_operation(request)
            if active_attempt is not None:
                return self._in_progress_result(request, active_attempt.attempt_id)
            raise
        started_at = time.monotonic()

        def finalize(result: ToolResult) -> ToolExecutionOutcome:
            duration_ms = int((time.monotonic() - started_at) * 1000)
            return self._operation_ledger.finalize(
                attempt.attempt_id,
                result,
                duration_ms=duration_ms,
            )

        if self._is_pre_execution_cancelled(cancellation_token):
            return finalize(ToolResult.cancelled())

        if request.fingerprint_error is not None:
            return finalize(
                ToolResult.failure(
                    ErrorCategory.VALIDATION,
                    "Tool arguments cannot be fingerprinted for operation identity.",
                    side_effect_state=SideEffectState.NOT_ATTEMPTED,
                )
            )

        if not isinstance(arguments, dict):
            return finalize(
                ToolResult.failure(
                    ErrorCategory.VALIDATION,
                    "Tool arguments must be an object.",
                    side_effect_state=SideEffectState.NOT_ATTEMPTED,
                )
            )

        tool = self.get_tool(tool_name)
        if tool is None:
            return finalize(
                ToolResult.failure(
                    ErrorCategory.VALIDATION,
                    f"Tool '{tool_name}' is not registered.",
                    side_effect_state=SideEffectState.NOT_ATTEMPTED,
                )
            )

        parse_error, raw_arguments = self._extract_tool_argument_parse_failure(arguments)
        if parse_error:
            return finalize(
                ToolResult.failure(
                    ErrorCategory.VALIDATION,
                    self._format_tool_argument_parse_error(
                        tool_name,
                        parse_error,
                        raw_arguments,
                    ),
                    side_effect_state=SideEffectState.NOT_ATTEMPTED,
                )
            )

        try:
            errors = tool.validate_params(arguments)
        except Exception as exc:
            return finalize(
                ToolResult.failure(
                    ErrorCategory.INTERNAL,
                    f"Tool '{tool_name}' parameter validation failed: {single_line(exc)}",
                    side_effect_state=SideEffectState.NOT_ATTEMPTED,
                )
            )
        if errors:
            return finalize(
                ToolResult.failure(
                    ErrorCategory.VALIDATION,
                    f"Invalid parameters for tool '{tool_name}': " + "; ".join(errors),
                    side_effect_state=SideEffectState.NOT_ATTEMPTED,
                )
            )

        self._operation_ledger.start(attempt.attempt_id)
        context_token = push_tool_execution_context(
            ToolExecutionContext(
                session_id=self._session_id,
                tool_name=tool_name,
                event_handler=_tool_event_handler_context.get(),
            )
        )
        try:
            result = await tool.execute_outcome(**arguments)
        except asyncio.CancelledError:
            # body 已经执行，而 PR1 尚未提供 Tool-side effect marker；因此
            # cancellation 不能宣称已知未产生 effect。
            result = ToolResult.unknown_outcome(
                ErrorCategory.CANCELLATION,
                "Tool execution was cancelled after the body started.",
            )
        except Exception as exc:
            result = ToolResult.unknown_outcome(
                classify_exception(exc),
                f"Tool '{tool_name}' failed: {single_line(exc)}",
                retryable=is_retryable(exc),
            )
        finally:
            reset_tool_execution_context(context_token)

        if not isinstance(result, ToolResult):
            return finalize(
                ToolResult.unknown_outcome(
                    ErrorCategory.RESULT_CONTRACT,
                    f"Tool '{tool_name}' did not return an explicit ToolResult.",
                )
            )
        return finalize(result)

    async def execute(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        auto_record: bool = True,
        raise_on_retryable: bool = False,
    ) -> str:
        """
        执行工具
        
        Args:
            tool_name: 工具名称
            arguments: 工具参数
            auto_record: 是否自动记录到工具对话历史（默认 True）
            raise_on_retryable: 是否把可重试异常（网络/超时/连接类）以
                RetryableToolError 重新抛出供上层重试（仅主循环 opt-in，默认
                False 保持"不抛异常、返回字符串"契约）
            
        Returns:
            str: 工具执行结果（包括错误信息）
            
        Note:
            此方法默认不会抛出异常，而是返回错误字符串；仅当
            raise_on_retryable=True 时，可重试异常会以 RetryableToolError 抛出。
        """
        tool = self.get_tool(tool_name)
        
        if tool is None:
            error_msg = f"Tool '{tool_name}' not found. Please use only the tools provided in the tool definitions."
            logger.warning(f"Tool not found: {tool_name} (this may be an LLM hallucination)")
            return error_msg
        
        # 生成调用 ID
        call_id = str(uuid.uuid4())
        start_time = datetime.now()
        
        # 记录工具调用到文件（如果启用审计日志）
        if self._audit_enabled:
            file_audit_logger.record_call(
                call_id=call_id,
                tool_name=tool_name,
                arguments=arguments,
                session_id=self._session_id
            )
        
        try:
            parse_error, raw_arguments = self._extract_tool_argument_parse_failure(arguments)
            if parse_error:
                error_msg = self._format_tool_argument_parse_error(
                    tool_name,
                    parse_error,
                    raw_arguments,
                )
                logger.error(error_msg)

                if self._audit_enabled:
                    file_audit_logger.update_result(
                        call_id,
                        error_msg,
                        "error",
                        error=error_msg,
                        duration_ms=0,
                    )

                if auto_record and self._session_id:
                    try:
                        from backend.modules.tools.conversation_history import get_conversation_history
                        conversation_history = get_conversation_history()
                        conversation_history.add_conversation(
                            session_id=self._session_id,
                            tool_name=tool_name,
                            arguments=arguments,
                            error=error_msg,
                            duration_ms=0,
                        )
                    except Exception as conv_err:
                        logger.warning(f"Failed to record tool conversation: {conv_err}")

                return error_msg

            # 验证参数
            errors = tool.validate_params(arguments)
            if errors:
                error_msg = f"Error: Invalid parameters for tool '{tool_name}': " + "; ".join(errors)
                logger.error(error_msg)

                if self._audit_enabled:
                    file_audit_logger.update_result(
                        call_id,
                        error_msg,
                        "error",
                        error=error_msg,
                        duration_ms=0,
                    )
                
                # 记录到工具对话历史（参数验证失败）
                if auto_record and self._session_id:
                    try:
                        from backend.modules.tools.conversation_history import get_conversation_history
                        conversation_history = get_conversation_history()
                        conversation_history.add_conversation(
                            session_id=self._session_id,
                            tool_name=tool_name,
                            arguments=arguments,
                            error=error_msg,
                            duration_ms=0
                        )
                    except Exception as conv_err:
                        logger.warning(f"Failed to record tool conversation: {conv_err}")
                
                return error_msg
            
            logger.info(f"Executing tool: {tool_name} with arguments: {arguments}")
            context_token = push_tool_execution_context(
                ToolExecutionContext(
                    session_id=self._session_id,
                    tool_name=tool_name,
                    event_handler=_tool_event_handler_context.get(),
                )
            )
            try:
                result = await tool.execute(**arguments)
            finally:
                reset_tool_execution_context(context_token)
            
            # 计算执行时间
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            
            # 更新审计日志
            if self._audit_enabled:
                file_audit_logger.update_result(call_id, result, "success", duration_ms=duration_ms)
            
            # 记录到工具对话历史（成功）
            if auto_record and self._session_id:
                try:
                    from backend.modules.tools.conversation_history import get_conversation_history
                    conversation_history = get_conversation_history()
                    conversation_history.add_conversation(
                        session_id=self._session_id,
                        tool_name=tool_name,
                        arguments=arguments,
                        result=result,
                        duration_ms=duration_ms,
                    )
                except Exception as conv_err:
                    logger.warning(f"Failed to record tool conversation: {conv_err}")
            
            logger.info(f"Tool '{tool_name}' executed successfully")
            return result
            
        except Exception as e:
            # 失败隔离：失败细节给日志/审计（str(e) 全量），一句话模板给模型。
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

            # 可重试（网络/超时/连接类）：仅当调用方显式 opt-in 时以
            # RetryableToolError 上抛，供上层（主循环）捕获后重试。
            if raise_on_retryable and is_retryable(e):
                retryable_error = RetryableToolError(
                    tool_name=tool_name,
                    summary=f"Tool '{tool_name}' failed ({type(e).__name__}): "
                    f"{single_line(e)}",
                    next="retry the operation",
                    detail=str(e),
                )
                logger.error(
                    f"Tool '{tool_name}' failed with retryable error "
                    f"({type(e).__name__}): {e}"
                )
                # 审计落盘完整细节后上抛；不写入对话历史——本次失败将被重试覆盖，
                # 重试耗尽后的最终错误由主循环统一记录。
                if self._audit_enabled:
                    file_audit_logger.update_result(
                        call_id, str(e), "error", error=str(e), duration_ms=duration_ms
                    )
                raise retryable_error from e

            # 不可重试（参数/权限/文件类）或未 opt-in：以模板文案返回给模型。
            error_msg = format_failure(
                kind="execution_error",
                summary=f"Tool '{tool_name}' failed: {single_line(e)}",
                next="check the tool arguments and retry",
                detail=str(e),
            )
            logger.error(f"Tool '{tool_name}' failed: {e}")

            # 更新审计日志
            if self._audit_enabled:
                file_audit_logger.update_result(call_id, str(e), "error", error=str(e), duration_ms=duration_ms)

            # 记录到工具对话历史（失败）
            if auto_record and self._session_id:
                try:
                    from backend.modules.tools.conversation_history import get_conversation_history
                    conversation_history = get_conversation_history()
                    conversation_history.add_conversation(
                        session_id=self._session_id,
                        tool_name=tool_name,
                        arguments=arguments,
                        error=error_msg,
                        duration_ms=duration_ms,
                    )
                except Exception as conv_err:
                    logger.warning(f"Failed to record tool conversation: {conv_err}")

            return error_msg

    def get_stats(self) -> Dict[str, Any]:
        """
        获取注册表统计信息
        
        Returns:
            dict: 统计信息
        """
        stats = {
            "total_tools": len(self._tools),
            "tool_names": self.list_tools(),
        }
        logger.debug(f"Registry stats: {stats}")
        return stats

    def clear(self) -> None:
        """清空所有已注册的工具"""
        count = len(self._tools)
        self._tools.clear()
        logger.info(f"Cleared {count} tools from registry")

    @property
    def tool_names(self) -> List[str]:
        """
        获取所有已注册的工具名称列表
        
        Returns:
            List[str]: 工具名称列表
        """
        return list(self._tools.keys())

    def __len__(self) -> int:
        """返回已注册工具的数量"""
        return len(self._tools)

    def __contains__(self, tool_name: str) -> bool:
        """检查工具是否已注册（支持 'name' in registry 语法）"""
        return tool_name in self._tools
