"""Subagent Manager - 子 Agent 管理"""

import asyncio
import json
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from loguru import logger


class TaskStatus(Enum):
    """任务状态枚举"""

    PENDING = "pending"
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
        self.done_event = asyncio.Event()  # set when task reaches a terminal state

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "label": self.label,
            "message": self.message,
            "session_id": self.session_id,
            "status": self.status.value,
            "progress": self.progress,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "tool_call_records": self.tool_call_records,
        }


class SubagentManager:
    """
    子 Agent 管理器
    
    管理后台任务的创建、执行、取消和状态查询
    """

    def __init__(self, provider, workspace, model: str, temperature: float = 0.0, max_tokens: int = 4096, db_session_factory=None, config_loader=None, skills=None):
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
        
        logger.debug("SubagentManager initialized")

    @staticmethod
    def _compose_reasoning_sections(reasoning_text: str, visible_text: str) -> str:
        """在不支持独立 reasoning 面板的子代理链路中保留 reasoning 内容。"""
        normalized_reasoning = str(reasoning_text or "").strip()
        normalized_visible = str(visible_text or "").strip()

        if not normalized_reasoning:
            return normalized_visible

        sections = [f"## 思考过程\n\n{normalized_reasoning}"]
        if normalized_visible:
            sections.append(f"## 回复\n\n{normalized_visible}")
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
        task = self.tasks.get(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        if task.status != TaskStatus.PENDING:
            logger.warning(f"Task {task_id} is not pending, current status: {task.status}")
            return

        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now()
        task.progress = 0

        logger.info(f"Starting task {task_id}: {task.label}")

        async_task = asyncio.create_task(self._run_task(task))
        self.running_tasks[task_id] = async_task

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
        
        try:
            await asyncio.wait_for(
                self._run_task_impl(task, handler),
                timeout=timeout_seconds
            )
        except asyncio.TimeoutError:
            task.status = TaskStatus.FAILED
            task.error = f"任务超时（超过{timeout_seconds}秒）"
            task.completed_at = datetime.now()
            logger.error(f"Task {task.task_id} timed out after {timeout_seconds}s")
            
            if handler:
                try:
                    await handler.notify_failed(task.error)
                except Exception:
                    pass
            
            await self._save_task_to_db(task)
        finally:
            if task.task_id in self.running_tasks:
                del self.running_tasks[task.task_id]
            task.done_event.set()

    async def _run_task_impl(self, task: SubagentTask, handler) -> None:
        """实际的任务执行逻辑"""

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

            from backend.modules.tools.registry import ToolRegistry
            from backend.modules.tools.filesystem import ReadFileTool, WriteFileTool, EditFileTool, ListDirTool
            from backend.modules.tools.shell import ExecTool

            # 从配置获取工具超时时间
            tool_timeout = 360
            if self.config_loader:
                try:
                    tool_timeout = self.config_loader.config.security.command_timeout
                    logger.debug(f"Using command_timeout from config: {tool_timeout}s")
                except Exception as e:
                    logger.warning(f"Failed to get command_timeout from config: {e}, using default: 360s")

            tools = ToolRegistry()
            tools.register(ReadFileTool(self.workspace))
            tools.register(WriteFileTool(self.workspace))
            tools.register(EditFileTool(self.workspace))
            tools.register(ListDirTool(self.workspace))
            tools.register(ExecTool(
                workspace=self.workspace,
                timeout=tool_timeout,
                allow_dangerous=False,
                restrict_to_workspace=True,
            ))

            try:
                from backend.modules.tools.web import WebFetchTool

                tools.register(WebFetchTool())
            except ImportError:
                logger.warning("Web fetch tool not available for subagent")

            response_chunks = []
            iteration = 0
            
            # 从配置获取最大迭代次数
            max_iterations = 15
            if self.config_loader:
                try:
                    config = self.config_loader.config
                    max_iterations = config.model.max_iterations
                    logger.debug(f"Using max_iterations from config: {max_iterations}")
                except Exception as e:
                    logger.warning(f"Failed to get max_iterations from config: {e}, using default: 15")

            while iteration < max_iterations:
                iteration += 1

                # 检查取消令牌
                if task.cancel_token and task.cancel_token.is_cancelled:
                    logger.info(f"Task {task.task_id} cancelled by user at iteration {iteration}")
                    raise asyncio.CancelledError("Task cancelled by user")

                tool_definitions = tools.get_definitions()

                content_buffer = ""
                reasoning_buffer = ""
                emitted_reasoning_header = False
                emitted_reply_header = False
                provider_payload = None
                tool_calls_buffer = []
                
                # 确定使用的 provider 和模型参数
                active_provider = self.provider
                runtime_model = self.model
                runtime_temperature = self.temperature
                runtime_max_tokens = self.max_tokens
                runtime_thinking_enabled = True
                
                # 优先使用任务的模型覆盖配置（团队自定义模型）
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
                                api_key=runtime_state.api_key or None,
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
                        if task.event_callback:
                            try:
                                if emitted_reasoning_header and not emitted_reply_header:
                                    emitted_reply_header = True
                                    await task.event_callback("chunk", "", "\n\n## 回复\n\n")
                                await task.event_callback("chunk", "", chunk.content)
                            except Exception as e:
                                logger.warning(f"Failed to call event_callback for chunk: {e}")
                    if chunk.is_reasoning and chunk.reasoning_content:
                        reasoning_buffer += chunk.reasoning_content
                        if task.event_callback:
                            try:
                                if not emitted_reasoning_header:
                                    emitted_reasoning_header = True
                                    await task.event_callback("chunk", "", "\n\n## 思考过程\n\n")
                                await task.event_callback("chunk", "", chunk.reasoning_content)
                            except Exception as e:
                                logger.warning(f"Failed to call event_callback for reasoning chunk: {e}")
                    if chunk.has_provider_payload and chunk.provider_payload:
                        provider_payload = chunk.provider_payload
                    if chunk.is_tool_call and chunk.tool_call:
                        tool_calls_buffer.append(chunk.tool_call)

                formatted_content = self._compose_reasoning_sections(
                    reasoning_buffer,
                    content_buffer,
                )
                if formatted_content:
                    response_chunks.append(formatted_content)

                if tool_calls_buffer:
                    import json

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
                        "content": content_buffer or "",
                        "tool_calls": tool_call_dicts,
                    }
                    if reasoning_buffer:
                        assistant_message["reasoning_content"] = reasoning_buffer
                    if provider_payload:
                        assistant_message.update(provider_payload)
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

                        try:
                            result = await asyncio.wait_for(
                                tools.execute(
                                    tool_name=tool_call.name,
                                    arguments=tool_call.arguments
                                ),
                                timeout=tool_timeout
                            )
                            record["status"] = "success"
                        except asyncio.TimeoutError:
                            result = f"Error: Tool '{tool_call.name}' execution timed out after {tool_timeout} seconds. The tool may be stuck or the operation is taking too long."
                            logger.error(f"Tool {tool_call.name} timed out after {tool_timeout}s")
                            record["status"] = "timeout"

                        record["result"] = result[:500] if result else ""
                        record["duration_ms"] = round((_time.time() - _tc_start) * 1000)

                        task.progress = min(90, task.progress + 5)

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
                                await task.event_callback("tool_result", tool_call.name, result)
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
                else:
                    break

            task.result = "".join(response_chunks)
            task.status = TaskStatus.COMPLETED
            task.progress = 100
            task.completed_at = datetime.now()

            logger.info(f"Task {task.task_id} completed successfully")

            if handler:
                try:
                    await handler.notify_complete(task.result)
                except Exception:
                    pass
            
            # 任务完成时保存到数据库
            await self._save_task_to_db(task)

        except asyncio.CancelledError:
            task.status = TaskStatus.CANCELLED
            task.completed_at = datetime.now()
            logger.info(f"Task {task.task_id} was cancelled")
            if handler:
                try:
                    await handler.notify_failed("任务已取消")
                except Exception:
                    pass
            
            # 任务取消时保存到数据库
            await self._save_task_to_db(task)

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.completed_at = datetime.now()
            logger.error(f"Task {task.task_id} failed: {e}")

            if handler:
                try:
                    await handler.notify_failed(str(e))
                except Exception:
                    pass
            
            # 任务失败时保存到数据库
            await self._save_task_to_db(task)

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

        prompt = f"""# 子代理

你是主代理创建的执行子代理，只负责当前任务。

## 任务
{task}

## 规则
- 专注分配任务，不扩展范围，不闲聊。
- 输出给主代理看，保持简洁、准确、可执行。
- 需要时主动用工具查证并完成验证，不要把半成品交回去。
- 不能直接联系用户，不能再创建子代理，也拿不到主代理完整对话历史。

## 工作空间
- 根目录: {workspace_path}
- 临时文件写入 `temp/`
- 相对路径都基于工作空间根目录
"""

        # 如果启用技能系统，注入技能摘要
        if enable_skills and self.skills:
            try:
                skills_summary = self.skills.build_skills_summary()
                if skills_summary:
                    prompt += (
                        "\n\n## 可用技能（Skills）\n"
                        "下面展示的是技能元信息里的完整 description，不是技能全文。"
                        "技能是文档，不是工具。需要时先用 `read_file` 读取对应 `SKILL.md`，"
                        "默认首次整文件读取；只有文档很大且目标段落明确时才用 `start_line/end_line`。"
                        "如果需要同时查看多个 Skills，优先一次调用 "
                        "`read_file(paths=['skills/a/SKILL.md', 'skills/b/SKILL.md'])` 批量读取，减少工具调用次数。"
                        "读完后再按文档说明调用 `exec`。\n\n"
                        f"{skills_summary}"
                    )
            except Exception as e:
                logger.warning(f"Failed to inject skills into subagent prompt: {e}")

        prompt += """

## 完成标准
- 说明完成了什么
- 说明发现了什么（若是调查任务）
- 说明遗留问题或风险（若有）
- 需要时给出下一步建议"""

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
                # 检查任务是否已存在
                from sqlalchemy import select
                result = await db.execute(
                    select(Task).where(Task.id == task.task_id)
                )
                db_task = result.scalar_one_or_none()
                
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
        
        if task.status not in [TaskStatus.PENDING, TaskStatus.RUNNING]:
            logger.warning(f"Cannot cancel task {task_id}: status is {task.status}")
            return False
        
        # 设置任务的取消令牌
        if task.cancel_token:
            task.cancel_token.cancel()
            logger.info(f"Set cancel token for task {task_id}")
        
        # 取消异步任务
        async_task = self.running_tasks.get(task_id)
        if async_task:
            async_task.cancel()
            logger.info(f"Cancelled async task {task_id}")
            return True
        
        return False

    async def cancel_all_tasks(self) -> int:
        """
        取消所有运行中的任务
        
        Returns:
            int: 取消的任务数量
        """
        cancelled_count = 0
        running_task_ids = list(self.running_tasks.keys())
        
        for task_id in running_task_ids:
            if await self.cancel_task(task_id):
                cancelled_count += 1
        
        if cancelled_count > 0:
            logger.info(f"Cancelled {cancelled_count} running tasks")
        
        return cancelled_count

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
        
        # 如果任务正在运行，先取消
        if task.status == TaskStatus.RUNNING:
            asyncio.create_task(self.cancel_task(task_id))
        
        # 删除任务
        del self.tasks[task_id]
        logger.info(f"Deleted task {task_id}")
        
        return True

    def get_running_count(self) -> int:
        """Return the number of currently running subagents."""
        return len(self.running_tasks)

    def get_stats(self) -> Dict[str, int]:
        """
        获取任务统计信息
        
        Returns:
            dict: 统计信息
        """
        return {
            "total": len(self.tasks),
            "pending": len([t for t in self.tasks.values() if t.status == TaskStatus.PENDING]),
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
