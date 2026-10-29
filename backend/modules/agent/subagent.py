"""Subagent Manager - 子 Agent 管理"""

import asyncio
import json
import time
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from loguru import logger

from backend.modules.session.usage_recorder import USAGE_KIND_SUBAGENT, record_usage
from backend.modules.tools.execution import (
    ErrorCategory,
    ExecutionState,
    SideEffectState,
    ToolExecutionInProgress,
    ToolExecutionOutcome,
    ToolExecutionRejected,
    ToolResult,
)


class TaskStatus(Enum):
    """任务状态枚举"""

    PENDING = "pending"
    # 已提交到并发队列、等待执行额度，尚未真正开始执行
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SubagentTask:
    """子 Agent 任务"""

    def __init__(
        self,
        task_id: str,
        label: str,
        message: str,
        session_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
        event_callback=None,
        enable_skills: bool = False,
    ):
        self.task_id = task_id
        self.label = label
        self.message = message
        self.session_id = session_id
        self.system_prompt = system_prompt  # custom per-agent persona; overrides default wrapper
        self.event_callback = event_callback  # async callable(event, tool_name, data)
        self.notification_handler = None  # TaskNotificationHandler (set by SpawnTool)
        self.enable_skills = enable_skills  # 是否启用技能系统
        self.model_override: Optional[Dict[str, Any]] = None  # 模型配置覆盖
        self.cancel_token = None  # 任务级别的取消令牌
        self.status = TaskStatus.PENDING
        self.progress = 0
        self.result: Optional[str] = None
        self.error: Optional[str] = None
        self.created_at = datetime.now()
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.tool_call_records: List[Dict[str, Any]] = []
        # Immutable Tool attempts are distinct from the task's propagation result.
        # Without an explicit recovery acknowledgement, later success cannot erase
        # an earlier non-success attempt.
        self.tool_outcomes: List[ToolExecutionOutcome] = []
        self.outcome: Optional[ToolResult] = None
        self.propagated_failure: Optional[ToolResult] = None
        self.active_tool_call = False
        self.task_deadline = None
        self.done_event = asyncio.Event()  # set when task reaches a terminal state
        # 无活动看门狗：impl 在每个 chunk / 每次工具结果处刷新，
        # watchdog 检测超过阈值即中止 runner
        self.last_activity: Optional[float] = None
        self.aborted_by_watchdog: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        from backend.modules.tools.outcome_projection import task_read_view
        status, projection_state, projection = task_read_view(
            self.status.value, self.outcome_projection(),
        )
        return {
            "task_id": self.task_id,
            "label": self.label,
            "message": self.message,
            "session_id": self.session_id,
            "status": status,
            "progress": self.progress,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "tool_call_records": self.tool_call_records,
            "outcome_projection": projection,
            "outcome_projection_state": projection_state,
        }

    def outcome_projection(self) -> Optional[Dict[str, Any]]:
        """分开投影 task 处置与已返回的 Tool outcome 列表。

        disposition 描述 child 任务结果，不是 physical attempt；没有 Registry
        返回值时不合成 attempt identity。
        """
        if self.outcome is None and not self.tool_outcomes:
            return None
        from backend.modules.tools.outcome_projection import (
            project_attempt, project_child_disposition,
        )

        attempts = {}
        for outcome in self.tool_outcomes:
            attempts.setdefault(
                outcome.attempt_id,
                project_attempt(
                    outcome, source="child", session_id=self.session_id,
                    task_id=self.task_id,
                ),
            )
        return {
            "disposition": (
                project_child_disposition(self.task_id, self.outcome)
                if self.outcome is not None else None
            ),
            "attempts": list(attempts.values()),
        }


class SubagentManager:
    """
    子 Agent 管理器
    
    管理后台任务的创建、执行、取消和状态查询
    """

    def __init__(self, provider, workspace, model: str, temperature: float = 0.0, max_tokens: int = 4096, db_session_factory=None, config_loader=None, skills=None, max_concurrent: int = 4, inactivity_seconds: float = 600.0):
        """初始化 SubagentManager"""
        self.provider = provider
        self.workspace = workspace
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.db_session_factory = db_session_factory
        self.config_loader = config_loader
        self.skills = skills  # 技能系统实例
        self.tasks: Dict[str, SubagentTask] = {}
        self.running_tasks: Dict[str, asyncio.Task] = {}
        self.cancel_token = None  # 全局取消令牌
        # 并发上限：超出后新任务在信号量处排队，避免无限并发调用 provider
        self.max_concurrent = max_concurrent
        self._concurrency = asyncio.Semaphore(max_concurrent)
        # 无活动超时：任务持续无 chunk / 工具结果超过该秒数即中止
        # （与 security.subagent_timeout 的总墙钟互补，productive 长任务不受误杀）
        self.inactivity_seconds = inactivity_seconds
        # 子代理结果预算：超过即截断并标注，防止长输出撑爆父上下文
        self._result_budget = 100_000

        logger.debug("SubagentManager initialized")

    @staticmethod
    def _compose_reasoning_sections(reasoning_text: str, visible_text: str) -> str:
        """在不支持独立 reasoning 面板的子代理链路中保留 reasoning 内容。"""
        normalized_reasoning = str(reasoning_text or "").strip()
        normalized_visible = str(visible_text or "").strip()

        if not normalized_reasoning:
            return normalized_visible

        sections = [f"## Reasoning\n\n{normalized_reasoning}"]
        if normalized_visible:
            sections.append(f"## Response\n\n{normalized_visible}")
        return "\n\n---\n\n".join(sections)

    def _resolve_runtime_model_settings(self) -> Tuple[str, float, int, bool]:
        """获取当前执行应使用的模型参数，优先读取最新配置。"""
        model = self.model
        temperature = self.temperature
        max_tokens = self.max_tokens
        thinking_enabled = True

        if not self.config_loader:
            return model, temperature, max_tokens, thinking_enabled

        try:
            runtime_model_config = self.config_loader.config.model
            model = getattr(runtime_model_config, "model", model) or model
            temperature = getattr(runtime_model_config, "temperature", temperature)
            max_tokens = getattr(runtime_model_config, "max_tokens", max_tokens)
            thinking_enabled = getattr(runtime_model_config, "thinking_enabled", thinking_enabled)
        except Exception as e:
            logger.warning(
                f"Failed to get runtime model settings from config: {e}, using manager defaults"
            )

        return model, temperature, max_tokens, thinking_enabled

    def create_task(
        self,
        label: str,
        message: str,
        session_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
        event_callback=None,
        enable_skills: bool = False,
        model_override: Optional[Dict[str, Any]] = None,
        cancel_token=None,
    ) -> str:
        """
        创建新的后台任务

        Args:
            label: 任务标签
            message: 任务消息（用户侧提示词）
            session_id: 关联的会话 ID (可选)
            system_prompt: 自定义系统提示词；若提供则完全替换默认 wrapper
            enable_skills: 是否启用技能系统
            model_override: 模型配置覆盖（用于团队自定义模型）

        Returns:
            str: 任务 ID
        """
        task_id = str(uuid.uuid4())

        task = SubagentTask(
            task_id=task_id,
            label=label,
            message=message,
            session_id=session_id,
            system_prompt=system_prompt,
            event_callback=event_callback,
            enable_skills=enable_skills,
        )
        
        # 保存模型覆盖配置
        task.model_override = model_override
        
        # 保存取消令牌
        task.cancel_token = cancel_token
        
        self.tasks[task_id] = task
        logger.info(f"Created task {task_id}: {label}")
        
        return task_id

    async def execute_task(self, task_id: str) -> None:
        """Schedule task execution in the background. Returns immediately."""
        # 惰性回收过期终态任务，防止 tasks 表无界增长
        await self.cleanup_old_tasks()

        task = self.tasks.get(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        if task.status != TaskStatus.PENDING:
            logger.warning(f"Task {task_id} is not pending, current status: {task.status}")
            return

        # 提交后先入队：并发额度在 _run_task 内获取，拿到额度才置 RUNNING，
        # 否则排队任务会被计入 running，突破 max_concurrent 的观测口径
        task.status = TaskStatus.QUEUED
        task.progress = 0

        logger.info(f"Queued task {task_id}: {task.label}")

        async_task = asyncio.create_task(self._run_task(task))
        self.running_tasks[task_id] = async_task
        # 任务若在首个调度点之前被取消，协程体（含 _run_task 的 finally）
        # 不会执行，done_event 无人释放；done 回调用以保证终态收敛
        async_task.add_done_callback(lambda _: self._settle_cancelled_task(task))

    async def _run_task(self, task: SubagentTask) -> None:
        handler = task.notification_handler

        # 从配置获取超时时间
        timeout_seconds = 1200
        if self.config_loader:
            try:
                timeout_seconds = self.config_loader.config.security.subagent_timeout
                logger.debug(f"Using subagent_timeout from config: {timeout_seconds}s")
            except Exception as e:
                logger.warning(f"Failed to get subagent_timeout from config: {e}, using default: 1200s")

        # 并发额度须先于 runner 获取：create_task 之后协程会在下一个调度点自行运行，
        # acquire 若只包住 await runner，则不产生任何限流作用。
        # 额度之前的排队时间不计入墙钟，超时 deadline 在取得额度后起算。
        try:
            async with self._concurrency:
                # 取得并发额度即代表真正开始执行，此时才置 RUNNING 并记开始时间
                task.status = TaskStatus.RUNNING
                task.started_at = datetime.now()
                task.task_deadline = asyncio.timeout(timeout_seconds)
                task.last_activity = time.monotonic()
                runner = asyncio.create_task(self._run_task_impl(task, handler))
                watchdog = asyncio.create_task(
                    self._inactivity_watchdog(task, runner, self.inactivity_seconds)
                )
                try:
                    async with task.task_deadline:
                        await runner
                    timed_out = task.task_deadline.expired()
                except asyncio.TimeoutError:
                    timed_out = True
                finally:
                    watchdog.cancel()
                    task.task_deadline = None

                if timed_out and (
                    task.outcome is None or task.outcome.error_category is not ErrorCategory.TIMEOUT
                ):
                    possible_effect = task.active_tool_call or any(
                        item.side_effect_state is not SideEffectState.NOT_ATTEMPTED
                        for item in task.tool_outcomes
                    )
                    task.outcome = (
                        ToolResult.unknown_outcome(
                            ErrorCategory.TIMEOUT,
                            f"子 Agent 任务超时（超过{timeout_seconds}秒），执行结果无法确认。",
                        )
                        if possible_effect else ToolResult.failure(
                            ErrorCategory.TIMEOUT,
                            f"子 Agent 任务超时（超过{timeout_seconds}秒）。",
                            side_effect_state=SideEffectState.NOT_ATTEMPTED,
                        )
                    )
                    task.status = TaskStatus.FAILED
                    task.error = task.outcome.display_text
                    task.completed_at = datetime.now()
                    logger.error(f"Task {task.task_id} timed out after {timeout_seconds}s")

                    if handler:
                        try:
                            await handler.notify_failed(task.error)
                        except Exception:
                            pass

                    await self._save_task_to_db(task)
        except asyncio.CancelledError:
            # 排队期间被取消的任务可能尚未创建 runner，此处补齐终态，
            # 避免任务长期停留在 running
            if task.status in (TaskStatus.PENDING, TaskStatus.QUEUED, TaskStatus.RUNNING):
                task.status = TaskStatus.CANCELLED
                task.error = "任务已被取消"
                task.completed_at = datetime.now()
                try:
                    await self._save_task_to_db(task)
                except Exception:
                    pass
            raise
        finally:
            if task.task_id in self.running_tasks:
                del self.running_tasks[task.task_id]
            task.done_event.set()

    async def _run_task_impl(self, task: SubagentTask, handler) -> None:
        """实际的任务执行逻辑

        阶段划分：_build_child_tool_registry（工具面）→
        _resolve_task_runtime（provider/模型参数，任务生命周期内不变量，
        循环外解析一次）→ 主循环（模型流消费 + _run_child_tool_batch）→
        结果组装与 outcome 收敛。
        """

        try:
            # 任务创建时立即保存到数据库
            await self._save_task_to_db(task)

            if handler:
                try:
                    await handler.notify_status("running", 0, "子代理已启动")
                except Exception:
                    pass

            resolved_system_prompt = (
                task.system_prompt
                if task.system_prompt
                else self._build_subagent_prompt(task.message, task.enable_skills)
            )

            messages = [
                {"role": "system", "content": resolved_system_prompt},
                {"role": "user", "content": task.message},
            ]

            tools = self._build_child_tool_registry()
            tool_timeout = self._resolve_child_tool_timeout()
            max_iterations = self._resolve_child_max_iterations()

            # provider / 模型参数在任务生命周期内是不变量，循环外解析一次
            (
                active_provider,
                runtime_model,
                runtime_temperature,
                runtime_max_tokens,
                runtime_thinking_enabled,
            ) = self._resolve_task_runtime(task)

            response_chunks = []
            iteration = 0

            while iteration < max_iterations:
                iteration += 1

                # 检查取消令牌
                if task.cancel_token and task.cancel_token.is_cancelled:
                    logger.info(f"Task {task.task_id} cancelled by user at iteration {iteration}")
                    raise asyncio.CancelledError("Task cancelled by user")

                tool_definitions = tools.get_definitions()
                turn = {
                    "content": "",
                    "reasoning": "",
                    "emitted_reasoning_header": False,
                    "emitted_reply_header": False,
                    "provider_payload": None,
                    "tool_calls": [],
                    "usage": None,
                }

                async for chunk in active_provider.chat_stream(
                    messages=messages,
                    tools=tool_definitions,
                    model=runtime_model,
                    temperature=runtime_temperature,
                    max_tokens=runtime_max_tokens,
                    thinking_enabled=runtime_thinking_enabled,
                ):
                    task.last_activity = time.monotonic()

                    if chunk.is_content and chunk.content:
                        turn["content"] += chunk.content
                        if task.event_callback:
                            try:
                                if turn["emitted_reasoning_header"] and not turn["emitted_reply_header"]:
                                    turn["emitted_reply_header"] = True
                                    await task.event_callback("chunk", "", "\n\n## Response\n\n")
                                await task.event_callback("chunk", "", chunk.content)
                            except Exception as e:
                                logger.warning(f"Failed to call event_callback for chunk: {e}")
                    if chunk.is_reasoning and chunk.reasoning_content:
                        turn["reasoning"] += chunk.reasoning_content
                        if task.event_callback:
                            try:
                                if not turn["emitted_reasoning_header"]:
                                    turn["emitted_reasoning_header"] = True
                                    await task.event_callback("chunk", "", "\n\n## Reasoning\n\n")
                                await task.event_callback("chunk", "", chunk.reasoning_content)
                            except Exception as e:
                                logger.warning(f"Failed to call event_callback for reasoning chunk: {e}")
                    if chunk.has_provider_payload and chunk.provider_payload:
                        turn["provider_payload"] = chunk.provider_payload
                    if chunk.is_tool_call and chunk.tool_call:
                        turn["tool_calls"].append(chunk.tool_call)
                    if chunk.usage:
                        turn["usage"] = chunk.usage

                # 子代理的消耗同样计入用量统计，否则成本报表会系统性偏低：
                # 团队工作流往往由多个子代理并行跑，占总消耗的比例可能很高。
                if turn["usage"]:
                    await record_usage(
                        session_id=getattr(task, "session_id", None),
                        provider=getattr(active_provider, "provider_id", None),
                        model=runtime_model or getattr(active_provider, "default_model", None),
                        kind=USAGE_KIND_SUBAGENT,
                        raw_usage=turn["usage"],
                    )

                formatted_content = self._compose_reasoning_sections(
                    turn["reasoning"],
                    turn["content"],
                )
                if formatted_content:
                    response_chunks.append(formatted_content)

                if turn["tool_calls"]:
                    await self._run_child_tool_batch(
                        task, handler, messages, turn, tools, tool_timeout,
                    )
                else:
                    break

            task.result = self._truncate_output("".join(response_chunks))
            task.status = TaskStatus.COMPLETED
            if task.propagated_failure:
                task.outcome = task.propagated_failure
                task.error = task.outcome.display_text
            else:
                task.outcome = ToolResult.success(task.result)
            task.progress = 100
            task.completed_at = datetime.now()

            logger.info(f"Task {task.task_id} finished with {task.outcome.state.value}")

            if handler:
                try:
                    if task.outcome.state is ExecutionState.SUCCEEDED:
                        await handler.notify_complete(task.result)
                    else:
                        await handler.notify_failed(task.error)
                except Exception:
                    pass

            # 任务完成时保存到数据库
            await self._save_task_to_db(task)

        except asyncio.CancelledError:
            deadline_expired = bool(task.task_deadline and task.task_deadline.expired())
            possible_effect = task.active_tool_call or any(
                item.side_effect_state is not SideEffectState.NOT_ATTEMPTED
                for item in task.tool_outcomes
            )
            if deadline_expired:
                task.outcome = (
                    ToolResult.unknown_outcome(
                        ErrorCategory.TIMEOUT,
                        "Child task timed out after Tool execution may have started.",
                    ) if possible_effect else ToolResult.failure(
                        ErrorCategory.TIMEOUT,
                        "Child task timed out before Tool execution.",
                        side_effect_state=SideEffectState.NOT_ATTEMPTED,
                    )
                )
            elif task.aborted_by_watchdog:
                task.outcome = (
                    ToolResult.unknown_outcome(
                        ErrorCategory.TIMEOUT,
                        f"子 Agent 任务超过 {self.inactivity_seconds:.0f} 秒无活动，已被中止；执行结果无法确认。",
                    ) if possible_effect else ToolResult.failure(
                        ErrorCategory.TIMEOUT,
                        f"子 Agent 任务超过 {self.inactivity_seconds:.0f} 秒无活动，已被中止。",
                        side_effect_state=SideEffectState.NOT_ATTEMPTED,
                    )
                )
            elif task.outcome is None or task.outcome.state in (
                ExecutionState.FAILED, ExecutionState.SUCCEEDED
            ):
                task.outcome = self._cancelled_outcome(task)
            task.status = (
                TaskStatus.CANCELLED if task.outcome.state is ExecutionState.CANCELLED
                else TaskStatus.FAILED
            )
            task.error = (
                "任务已被取消" if task.outcome.state is ExecutionState.CANCELLED
                else task.outcome.display_text
            )
            task.completed_at = datetime.now()
            logger.info(f"Task {task.task_id} stopped with {task.outcome.state.value}")
            if handler:
                try:
                    await handler.notify_failed(task.error)
                except Exception:
                    pass

            # 任务取消时保存到数据库
            await self._save_task_to_db(task)

        except Exception as e:
            task.status = TaskStatus.FAILED
            if task.outcome is None:
                task.outcome = ToolResult.failure(ErrorCategory.INTERNAL, str(e))
            task.error = task.outcome.display_text
            task.completed_at = datetime.now()
            logger.error(f"Task {task.task_id} failed: {e}")

            if handler:
                try:
                    await handler.notify_failed(str(e))
                except Exception:
                    pass

            # 任务失败时保存到数据库
            await self._save_task_to_db(task)

    def _truncate_output(self, text: str) -> str:
        """结果预算：超限截断并标注，防止子代理长输出撑爆父上下文。"""
        budget = self._result_budget
        if len(text) <= budget:
            return text
        return text[:budget] + (
            f"\n\n[输出超过 {budget} 字符已截断；完整长度 {len(text)} 字符]"
        )

    def _resolve_child_tool_timeout(self) -> int:
        """从配置获取子代理单次工具调用的超时时间（秒）。"""
        tool_timeout = 360
        if self.config_loader:
            try:
                tool_timeout = self.config_loader.config.security.command_timeout
                logger.debug(f"Using command_timeout from config: {tool_timeout}s")
            except Exception as e:
                logger.warning(f"Failed to get command_timeout from config: {e}, using default: 360s")
        return tool_timeout

    def _resolve_child_max_iterations(self) -> int:
        """从配置获取子代理的最大迭代次数。

        与主循环同源：0 表示不限制，需折算成内部上界，否则子代理一步都不跑。
        """
        max_iterations = 15
        if self.config_loader:
            try:
                from backend.modules.agent.loop import resolve_tool_budget

                max_iterations = resolve_tool_budget(
                    self.config_loader.config.model.max_iterations
                )
                logger.debug(f"Using max_iterations from config: {max_iterations}")
            except Exception as e:
                logger.warning(f"Failed to get max_iterations from config: {e}, using default: 15")
        return max_iterations

    def _build_child_tool_registry(self) -> "ToolRegistry":
        """构建子代理的工具面：基础文件/执行工具 + web_fetch，按禁用列表过滤。

        子代理的注册表物理上不含 spawn / workflow_run，从结构上阻断递归派发。
        """
        from backend.modules.tools.registry import ToolRegistry
        from backend.modules.tools.filesystem import ReadFileTool, WriteFileTool, EditFileTool, ListDirTool
        from backend.modules.tools.shell import ExecTool

        tools = ToolRegistry()
        disabled_tools = self._disabled_tools()
        if "read_file" not in disabled_tools:
            tools.register(ReadFileTool(self.workspace))
        if "write_file" not in disabled_tools:
            tools.register(WriteFileTool(self.workspace))
        if "edit_file" not in disabled_tools:
            tools.register(EditFileTool(self.workspace))
        if "list_dir" not in disabled_tools:
            tools.register(ListDirTool(self.workspace))
        if "exec" not in disabled_tools:
            tools.register(ExecTool(
                workspace=self.workspace,
                timeout=self._resolve_child_tool_timeout(),
                allow_dangerous=False,
                restrict_to_workspace=True,
            ))

        try:
            from backend.modules.tools.web import WebFetchTool

            if "web_fetch" not in disabled_tools:
                tools.register(WebFetchTool())
        except ImportError:
            logger.warning("Web fetch tool not available for subagent")

        return tools

    def _resolve_task_runtime(self, task: SubagentTask) -> tuple:
        """解析子代理使用的 provider 与模型参数（任务生命周期内不变量）。

        优先级：任务级 model_override（团队自定义模型）> manager 构造参数
        > 全局配置。
        """
        active_provider = self.provider
        runtime_model = self.model
        runtime_temperature = self.temperature
        runtime_max_tokens = self.max_tokens
        runtime_thinking_enabled = True

        if task.model_override:
            override_provider = task.model_override.get("provider")
            override_api_key = task.model_override.get("api_key")
            override_api_base = task.model_override.get("api_base")

            # 如果指定了不同的 provider 或 API 配置，创建新的 provider 实例
            if override_provider or override_api_key or override_api_base:
                try:
                    from backend.modules.providers.factory import create_provider
                    from backend.modules.providers.runtime import (
                        build_provider_unavailable_message,
                        get_provider_runtime_state,
                    )

                    provider_name = override_provider or self.config_loader.config.model.provider
                    runtime_state = get_provider_runtime_state(
                        self.config_loader.config,
                        provider_name,
                        api_key_override=override_api_key,
                        api_base_override=override_api_base,
                    )
                    if not runtime_state.selectable:
                        raise ValueError(
                            build_provider_unavailable_message(
                                provider_name,
                                runtime_state.reason,
                            )
                        )

                    active_provider = create_provider(
                        provider_id=provider_name,
                        api_type=runtime_state.api_type,
                        api_key=runtime_state.api_key or None,
                        api_keys=runtime_state.api_keys or None,
                        api_base=runtime_state.api_base,
                        api_mode=task.model_override.get(
                            "api_mode",
                            getattr(self.config_loader.config.model, "api_mode", "chat_completions"),
                        ),
                    )
                    logger.info(
                        f"Created custom provider for team: {provider_name}, "
                        f"api_base: {runtime_state.api_base}"
                    )
                except Exception as e:
                    logger.warning(f"Failed to create custom provider, using default: {e}")

            # 应用模型参数覆盖
            runtime_model = task.model_override.get("model", runtime_model)
            runtime_temperature = task.model_override.get("temperature", runtime_temperature)
            runtime_max_tokens = task.model_override.get("max_tokens", runtime_max_tokens)
            runtime_thinking_enabled = task.model_override.get(
                "thinking_enabled",
                runtime_thinking_enabled,
            )
            temp_label = "default" if runtime_temperature <= 0 else runtime_temperature
            max_tokens_label = "auto" if runtime_max_tokens <= 0 else runtime_max_tokens
            logger.info(
                f"Using team model override: model={runtime_model}, "
                f"temp={temp_label}, max_tokens={max_tokens_label}"
            )
        else:
            # 使用全局配置
            runtime_model, runtime_temperature, runtime_max_tokens, runtime_thinking_enabled = (
                self._resolve_runtime_model_settings()
            )

        return (
            active_provider,
            runtime_model,
            runtime_temperature,
            runtime_max_tokens,
            runtime_thinking_enabled,
        )

    async def _run_child_tool_batch(
        self,
        task: SubagentTask,
        handler,
        messages: List[Dict[str, Any]],
        turn: Dict[str, Any],
        tools,
        tool_timeout: int,
    ) -> None:
        """执行一个子代理工具调用批次（去重、逐个执行、结果入上下文）。"""
        import json

        tool_calls_buffer = turn["tool_calls"]

        # Deduplicate parallel tool calls with identical (name, arguments)
        seen_sigs: Set[str] = set()
        deduped: list = []
        for _tc in tool_calls_buffer:
            _sig = f"{_tc.name}:{json.dumps(_tc.arguments, sort_keys=True)}"
            if _sig not in seen_sigs:
                seen_sigs.add(_sig)
                deduped.append(_tc)
            else:
                logger.warning(f"[Subagent] skipping duplicate tool call: {_tc.name}")
        tool_calls_buffer = deduped

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
        assistant_message = {
            "role": "assistant",
            "content": turn["content"] or "",
            "tool_calls": tool_call_dicts,
        }
        if turn["reasoning"]:
            assistant_message["reasoning_content"] = turn["reasoning"]
        if turn["provider_payload"]:
            assistant_message.update(turn["provider_payload"])
        messages.append(assistant_message)

        for tool_call in tool_calls_buffer:
            # 检查取消令牌
            if task.cancel_token and task.cancel_token.is_cancelled:
                logger.info(f"Task {task.task_id} cancelled by user during tool execution")
                raise asyncio.CancelledError("Task cancelled by user")

            import time as _time
            _tc_start = _time.time()

            record: Dict[str, Any] = {
                "tool_call_id": tool_call.id,
                "name": tool_call.name,
                "arguments": tool_call.arguments,
                "result": None,
                "status": "running",
                "started_at": _tc_start,
            }
            task.tool_call_records.append(record)

            # 通知 handler（用于 spawn）
            if handler:
                try:
                    await handler.notify_tool_call(
                        tool_call.name,
                        tool_call.arguments,
                        tool_call_id=tool_call.id,
                    )
                except Exception:
                    pass

            # 通知 event_callback（用于 workflow）
            if task.event_callback:
                try:
                    await task.event_callback("tool_call", tool_call.name, tool_call.arguments)
                except Exception as e:
                    logger.warning(f"Failed to call event_callback for tool_call: {e}")

            operation_id = str(uuid.uuid4())
            task.active_tool_call = True
            tool_deadline = asyncio.timeout(tool_timeout)
            try:
                async with tool_deadline:
                    outcome = await tools.execute_outcome(
                        tool_name=tool_call.name,
                        arguments=tool_call.arguments,
                        operation_id=operation_id,
                        correlation_id=tool_call.id,
                        cancellation_token=task.cancel_token,
                    )
            except asyncio.TimeoutError:
                # The Registry owns attempt finalization. A timeout before
                # it returns cannot be represented as a fabricated attempt.
                task.outcome = ToolResult.unknown_outcome(
                    ErrorCategory.TIMEOUT,
                    f"Tool '{tool_call.name}' timed out; its effect is uncertain.",
                )
                raise
            # Keep the boundary marked active if cancellation escapes
            # before Registry can return its canonical outcome.
            task.active_tool_call = False

            if isinstance(outcome, ToolExecutionInProgress):
                task.outcome = ToolResult.unknown_outcome(
                    ErrorCategory.RESULT_CONTRACT,
                    outcome.display_text,
                )
                raise RuntimeError(outcome.display_text)

            if isinstance(outcome, ToolExecutionRejected):
                # No physical child attempt exists at this boundary.
                task.outcome = ToolResult.failure(
                    ErrorCategory.RESULT_CONTRACT, outcome.display_text,
                    side_effect_state=SideEffectState.NOT_ATTEMPTED,
                )
                record.update({"status": "rejected", "reason": outcome.reason,
                               "operation_id": outcome.operation_id,
                               "result": outcome.display_text})
                if task.event_callback:
                    await task.event_callback("tool_rejected", tool_call.name, outcome)
                raise RuntimeError(outcome.display_text)

            task.tool_outcomes.append(outcome)
            try:
                from backend.modules.tools.file_audit_logger import file_audit_logger
                file_audit_logger.record_outcome(
                    outcome, source="child", session_id=task.session_id,
                    task_id=task.task_id,
                )
            except Exception as exc:
                logger.warning(f"Failed to record child Tool outcome: {exc}")
            if not outcome.succeeded:
                candidate = self._result_from_tool_outcome(outcome)
                if (tool_deadline.expired() and
                        outcome.state is ExecutionState.UNKNOWN_OUTCOME):
                    # The Registry's immutable attempt may report the
                    # cancellation used to enforce this deadline. The
                    # child-owned projection records the actual cause.
                    candidate = ToolResult.unknown_outcome(
                        ErrorCategory.TIMEOUT, outcome.display_text,
                        retryable=outcome.retryable,
                        retry_safety=outcome.retry_safety,
                    )
                priority = {
                    ExecutionState.UNKNOWN_OUTCOME: 0,
                    ExecutionState.CANCELLED: 1,
                    ExecutionState.FAILED: 2,
                }
                if (task.propagated_failure is None or
                        priority[candidate.state] < priority[task.propagated_failure.state]):
                    task.propagated_failure = candidate
                task.outcome = task.propagated_failure
            result = outcome.display_text
            record.update({
                "status": "success" if outcome.succeeded else outcome.state.value.lower(),
                "state": outcome.state.value,
                "error_category": outcome.error_category.value if outcome.error_category else None,
                "side_effect_state": outcome.side_effect_state.value,
                "operation_id": outcome.operation_id,
                "attempt_id": outcome.attempt_id,
                "correlation_id": outcome.correlation_id,
            })
            if (tool_deadline.expired() and
                    outcome.state is ExecutionState.UNKNOWN_OUTCOME):
                record["projection_error_category"] = ErrorCategory.TIMEOUT.value

            record["result"] = result[:500] if result else ""
            record["duration_ms"] = round((_time.time() - _tc_start) * 1000)

            task.progress = min(90, task.progress + 5)
            task.last_activity = time.monotonic()

            # 通知 handler（用于 spawn）
            if handler:
                try:
                    await handler.notify_tool_result(
                        tool_call.name,
                        result,
                        task.progress,
                        tool_call_id=tool_call.id,
                    )
                except Exception:
                    pass

            # 通知 event_callback（用于 workflow）
            if task.event_callback:
                try:
                    await task.event_callback("tool_result", tool_call.name, outcome)
                except Exception as e:
                    logger.warning(f"Failed to call event_callback for tool_result: {e}")

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": tool_call.name,
                "content": result,
            })

            # 每次工具调用后保存到数据库
            await self._save_task_to_db(task)
            if outcome.state in (ExecutionState.CANCELLED, ExecutionState.UNKNOWN_OUTCOME):
                raise asyncio.CancelledError("Child Tool did not complete with a known result")

    async def _inactivity_watchdog(
        self,
        task: SubagentTask,
        runner: "asyncio.Task",
        inactivity_seconds: float,
        poll_seconds: float = 0.0,
    ) -> None:
        """无活动看门狗：任务长时间无 chunk / 工具结果时中止 runner。

        与固定墙钟互补——productive 长任务不受墙钟误杀（活动即续命），
        卡死的任务不必等满墙钟才被清理。活动时间戳由 impl 刷新。
        """
        if poll_seconds <= 0:
            # 轮询间隔随阈值自适应：阈值越短检查越密，保证响应及时
            poll_seconds = max(0.25, min(30.0, inactivity_seconds / 4))
        try:
            while not runner.done():
                await asyncio.sleep(poll_seconds)
                if runner.done():
                    return
                last = task.last_activity if task.last_activity is not None else time.monotonic()
                if time.monotonic() - last > inactivity_seconds:
                    logger.error(
                        f"Task {task.task_id} inactive for {inactivity_seconds}s, aborting"
                    )
                    task.aborted_by_watchdog = True
                    runner.cancel()
                    return
        except asyncio.CancelledError:
            raise

    @staticmethod
    def _result_from_tool_outcome(outcome: ToolExecutionOutcome) -> ToolResult:
        return ToolResult(
            state=outcome.state,
            display_text=outcome.display_text,
            output=outcome.output,
            error_category=outcome.error_category,
            retryable=outcome.retryable,
            retry_safety=outcome.retry_safety,
            side_effect_state=outcome.side_effect_state,
        )

    def _skills_injection_enabled(self) -> bool:
        """读取注入开关；无配置或无 config_loader 时默认开启。"""
        injection = getattr(getattr(self.config_loader, "config", None), "injection", None)
        if injection is None:
            return True
        return bool(getattr(injection, "skills_summary", True))

    def _disabled_tools(self) -> set:
        """读取注入开关中禁用的工具名集合（无配置时为空）。"""
        injection = getattr(getattr(self.config_loader, "config", None), "injection", None)
        if injection is None:
            return set()
        return {str(name).strip() for name in (injection.disabled_tools or []) if str(name).strip()}

    def _build_subagent_prompt(self, task: str, enable_skills: bool = False) -> str:
        """
        构建子 Agent 专用的系统提示词
        
        Args:
            task: 任务描述
            enable_skills: 是否启用技能系统
            
        Returns:
            str: 系统提示词
        """
        workspace_path = str(self.workspace.expanduser().resolve())

        prompt = f"""# Subagent

You are an execution subagent created by the main agent. You only handle the task below.

## Task
{task}

## Rules
- Stay inside the assigned scope; no chit-chat, no new goals.
- Your output is read by the main agent: concise, accurate, actionable.
- Verify with tools before reporting; never hand back a half-finished result.
- You cannot contact the user, spawn further subagents, or see the main agent's full history.

## Workspace
- Root: {workspace_path}
- Relative paths resolve against the workspace root
"""

        # 技能文档依赖子代理的 read_file，不可用时跳过
        disabled_tools = self._disabled_tools()
        skills_usable = "read_file" not in disabled_tools
        if enable_skills and self.skills and skills_usable and self._skills_injection_enabled():
            try:
                skills_summary = self.skills.build_skills_summary()
                if skills_summary:
                    if "exec" in disabled_tools:
                        hint = (
                            "Skills are documents, not tools: read `SKILL.md` with `read_file` "
                            "(batch several via `paths=[...]`) and follow its instructions."
                        )
                    else:
                        hint = (
                            "Skills are documents, not tools: read `SKILL.md` with `read_file` "
                            "(batch several via `paths=[...]`), then follow it using `exec`."
                        )
                    prompt += f"\n\n## Available Skills\n{hint}\n\n{skills_summary}"
            except Exception as e:
                logger.warning(f"Failed to inject skills into subagent prompt: {e}")

        prompt += """

## Done Criteria
- What you completed
- What you found (for investigation tasks)
- Open issues or risks, if any
- Next steps when useful"""

        return prompt

    async def _save_task_to_db(self, task: SubagentTask) -> None:
        """
        将任务保存到数据库
        
        Args:
            task: 子代理任务对象
        """
        if not self.db_session_factory:
            return
        
        try:
            from backend.models.task import Task
            
            async with self.db_session_factory() as db:
                # 检查记录是否已存在
                from sqlalchemy import select
                result = await db.execute(
                    select(Task).where(Task.id == task.task_id)
                )
                db_task = result.scalar_one_or_none()
                projected = task.outcome_projection()
                stored_projection = json.dumps(projected) if projected is not None else None
                
                if db_task:
                    # 更新现有任务
                    db_task.label = task.label
                    db_task.message = task.message
                    db_task.session_id = task.session_id
                    db_task.status = task.status.value
                    db_task.progress = task.progress
                    db_task.result = task.result
                    db_task.error = task.error
                    db_task.started_at = task.started_at
                    db_task.completed_at = task.completed_at
                    db_task.tool_call_records = json.dumps(task.tool_call_records)
                    db_task.outcome_projection = stored_projection
                else:
                    # 创建新任务
                    db_task = Task(
                        id=task.task_id,
                        label=task.label,
                        message=task.message,
                        session_id=task.session_id,
                        status=task.status.value,
                        progress=task.progress,
                        result=task.result,
                        error=task.error,
                        created_at=task.created_at,
                        started_at=task.started_at,
                        completed_at=task.completed_at,
                        tool_call_records=json.dumps(task.tool_call_records),
                        outcome_projection=stored_projection,
                    )
                    db.add(db_task)
                
                await db.commit()
                logger.debug(f"Task {task.task_id} saved to database")
        except Exception as e:
            logger.error(f"Failed to save task to database: {e}")

    async def cancel_task(self, task_id: str) -> bool:
        """
        取消任务
        
        Args:
            task_id: 任务 ID
            
        Returns:
            bool: 是否成功取消
        """
        task = self.tasks.get(task_id)
        if not task:
            logger.warning(f"Cannot cancel task {task_id}: not found")
            return False
        
        if task.status not in [TaskStatus.PENDING, TaskStatus.QUEUED, TaskStatus.RUNNING]:
            logger.warning(f"Cannot cancel task {task_id}: status is {task.status}")
            return False
        
        # 令牌先于 asyncio.Task 置位：执行体内部的取消检查依赖令牌，
        # 且令牌取消幂等，重复置位无副作用
        if task.cancel_token:
            task.cancel_token.cancel()
            logger.info(f"Set cancel token for task {task_id}")

        async_task = self.running_tasks.get(task_id)
        if async_task:
            async_task.cancel()
            # 立即收敛终态：等待事件循环调度会让调用方在 done_event 上空转到超时
            self._settle_cancelled_task(task)
            logger.info(f"Cancelled async task {task_id}")
            return True

        return False

    @staticmethod
    def _cancelled_outcome(task: "SubagentTask") -> ToolResult:
        """构造取消终态结果：文档里「已执行过的工具」不能再声称未尝试。"""
        possible_effect = task.active_tool_call or any(
            item.side_effect_state is not SideEffectState.NOT_ATTEMPTED
            for item in task.tool_outcomes
        )
        if possible_effect:
            return ToolResult.unknown_outcome(
                ErrorCategory.CANCELLATION,
                "Child task was cancelled after Tool execution may have started.",
            )
        return ToolResult.cancelled("Child task was cancelled.")

    def _settle_cancelled_task(self, task: "SubagentTask") -> None:
        """将取消中的任务幂等收敛到终态并释放等待方。

        排队阶段被取消的任务可能尚未启动 runner，_run_task 的 try/finally
        不会执行；缺少本收敛时任务会滞留 running，且 done_event 无人释放。

        终态必须自洽：done_event 置位即代表结果可读，所以这里连同 outcome
        一起收敛。runner 的 CancelledError 分支要到下一个调度点才跑，只置
        done_event 会让先被唤醒的消费方读到 outcome=None。
        """
        if task.status in (TaskStatus.PENDING, TaskStatus.QUEUED, TaskStatus.RUNNING):
            task.status = TaskStatus.CANCELLED
            task.error = task.error or "任务已被取消"
            task.completed_at = task.completed_at or datetime.now()
        if task.outcome is None:
            task.outcome = self._cancelled_outcome(task)
        self.running_tasks.pop(task.task_id, None)
        if not task.done_event.is_set():
            task.done_event.set()

    async def cancel_tasks(self, task_ids=None) -> int:
        """取消任务并返回取消数量。

        task_ids 为 None 时取消全部运行中任务；传入集合时只取消集合内的
        任务——调用方（如 workflow）必须传自己派发的任务集合，避免误杀
        其他会话 / 其他团队工作流的子任务。
        """
        cancelled_count = 0
        if task_ids is None:
            task_ids = list(self.running_tasks.keys())

        for task_id in task_ids:
            if await self.cancel_task(task_id):
                cancelled_count += 1

        if cancelled_count > 0:
            logger.info(f"Cancelled {cancelled_count} running tasks")

        return cancelled_count

    async def cancel_all_tasks(self) -> int:
        """取消所有运行中的任务（向后兼容入口）。

        注意：这是全表清杀。按归属取消（如 workflow 只取消自己派发的
        任务）请改用 cancel_tasks(task_ids)。
        """
        return await self.cancel_tasks(None)

    def get_task(self, task_id: str) -> Optional[SubagentTask]:
        """
        获取任务信息
        
        Args:
            task_id: 任务 ID
            
        Returns:
            SubagentTask: 任务对象，如果不存在则返回 None
        """
        return self.tasks.get(task_id)

    def list_tasks(
        self,
        status: Optional[TaskStatus] = None,
        session_id: Optional[str] = None,
    ) -> List[SubagentTask]:
        """
        列出任务
        
        Args:
            status: 过滤状态 (可选)
            session_id: 过滤会话 ID (可选)
            
        Returns:
            list: 任务列表
        """
        tasks = list(self.tasks.values())
        
        # 按状态过滤
        if status:
            tasks = [t for t in tasks if t.status == status]
        
        # 按会话过滤
        if session_id:
            tasks = [t for t in tasks if t.session_id == session_id]
        
        # 按创建时间倒序排序
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        
        return tasks

    def get_running_tasks(self) -> List[SubagentTask]:
        """
        获取所有运行中的任务
        
        Returns:
            list: 运行中的任务列表
        """
        return self.list_tasks(status=TaskStatus.RUNNING)

    def delete_task(self, task_id: str) -> bool:
        """
        删除任务

        Args:
            task_id: 任务 ID

        Returns:
            bool: 是否成功删除
        """
        task = self.tasks.get(task_id)
        if not task:
            logger.warning(f"Cannot delete task {task_id}: not found")
            return False

        # 运行中的任务先同步取消（令牌 + asyncio.Task），再移除登记；
        # 反过来先删会让取消逻辑找不到任务，运行中的幽灵任务继续写库
        if task.status in (TaskStatus.PENDING, TaskStatus.QUEUED, TaskStatus.RUNNING):
            if task.cancel_token:
                task.cancel_token.cancel()
            async_task = self.running_tasks.pop(task_id, None)
            if async_task:
                async_task.cancel()

        # 删除任务
        del self.tasks[task_id]
        logger.info(f"Deleted task {task_id}")

        return True

    def get_running_count(self) -> int:
        """正在执行中的任务数（不含排队任务）。"""
        return len([t for t in self.tasks.values() if t.status is TaskStatus.RUNNING])

    def get_stats(self) -> Dict[str, int]:
        """
        获取任务统计信息

        Returns:
            dict: 统计信息
        """
        return {
            "total": len(self.tasks),
            "pending": len([t for t in self.tasks.values() if t.status == TaskStatus.PENDING]),
            "queued": len([t for t in self.tasks.values() if t.status == TaskStatus.QUEUED]),
            "running": len([t for t in self.tasks.values() if t.status == TaskStatus.RUNNING]),
            "completed": len([t for t in self.tasks.values() if t.status == TaskStatus.COMPLETED]),
            "failed": len([t for t in self.tasks.values() if t.status == TaskStatus.FAILED]),
            "cancelled": len([t for t in self.tasks.values() if t.status == TaskStatus.CANCELLED]),
        }

    async def cleanup_old_tasks(self, max_age_hours: int = 24) -> int:
        """
        清理旧任务
        
        Args:
            max_age_hours: 最大保留时间（小时）
            
        Returns:
            int: 清理的任务数量
        """
        from datetime import timedelta
        
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        cleaned = 0
        
        for task_id, task in list(self.tasks.items()):
            # 只清理已完成、失败或取消的任务
            if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                if task.completed_at and task.completed_at < cutoff_time:
                    del self.tasks[task_id]
                    cleaned += 1
        
        if cleaned > 0:
            logger.info(f"Cleaned up {cleaned} old tasks")
        
        return cleaned
