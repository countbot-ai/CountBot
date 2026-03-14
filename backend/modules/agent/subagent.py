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

    def __init__(self, provider, workspace, model: str, temperature: float = 0.7, max_tokens: int = 4096, db_session_factory=None, config_loader=None, skills=None):
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
        
        logger.debug("SubagentManager initialized")

    def _resolve_runtime_model_settings(self) -> Tuple[str, float, int]:
        """获取当前执行应使用的模型参数，优先读取最新配置。"""
        model = self.model
        temperature = self.temperature
        max_tokens = self.max_tokens

        if not self.config_loader:
            return model, temperature, max_tokens

        try:
            runtime_model_config = self.config_loader.config.model
            model = getattr(runtime_model_config, "model", model) or model
            temperature = getattr(runtime_model_config, "temperature", temperature)
            max_tokens = getattr(runtime_model_config, "max_tokens", max_tokens)
        except Exception as e:
            logger.warning(
                f"Failed to get runtime model settings from config: {e}, using manager defaults"
            )

        return model, temperature, max_tokens

    def create_task(
        self,
        label: str,
        message: str,
        session_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
        event_callback=None,
        enable_skills: bool = False,
    ) -> str:
        """
        创建新的后台任务

        Args:
            label: 任务标签
            message: 任务消息（用户侧提示词）
            session_id: 关联的会话 ID (可选)
            system_prompt: 自定义系统提示词；若提供则完全替换默认 wrapper
            enable_skills: 是否启用技能系统

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
        timeout_seconds = 600
        if self.config_loader:
            try:
                timeout_seconds = self.config_loader.config.security.subagent_timeout
                logger.debug(f"Using subagent_timeout from config: {timeout_seconds}s")
            except Exception as e:
                logger.warning(f"Failed to get subagent_timeout from config: {e}, using default: 600s")
        
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
            tool_timeout = 300
            if self.config_loader:
                try:
                    tool_timeout = self.config_loader.config.security.command_timeout
                    logger.debug(f"Using command_timeout from config: {tool_timeout}s")
                except Exception as e:
                    logger.warning(f"Failed to get command_timeout from config: {e}, using default: 300s")

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
                from backend.modules.tools.web import WebSearchTool, WebFetchTool
                tools.register(WebSearchTool())
                tools.register(WebFetchTool())
            except ImportError:
                logger.warning("Web tools not available for subagent")

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

                tool_definitions = tools.get_definitions()

                content_buffer = ""
                tool_calls_buffer = []
                runtime_model, runtime_temperature, runtime_max_tokens = (
                    self._resolve_runtime_model_settings()
                )
                
                async for chunk in self.provider.chat_stream(
                    messages=messages,
                    tools=tool_definitions,
                    model=runtime_model,
                    temperature=runtime_temperature,
                    max_tokens=runtime_max_tokens,
                ):
                    if chunk.is_content and chunk.content:
                        content_buffer += chunk.content
                    if chunk.is_tool_call and chunk.tool_call:
                        tool_calls_buffer.append(chunk.tool_call)

                if content_buffer:
                    response_chunks.append(content_buffer)

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
                    messages.append({
                        "role": "assistant",
                        "content": content_buffer or "",
                        "tool_calls": tool_call_dicts,
                    })

                    for tool_call in tool_calls_buffer:
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
                    await handler.notify_complete(None)
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
        
        prompt = f"""# 子代理 (Subagent)

你是主代理创建的子代理，专门负责完成特定任务。

## 你的任务
{task}

## 工作规则
1. **专注任务**: 只完成分配的任务，不做其他事情
2. **简洁高效**: 最终响应会报告给主代理，保持简洁但信息完整
3. **不要闲聊**: 不要发起对话或承担额外任务
4. **彻底完成**: 确保任务完整完成，提供清晰的结果总结

## 可用能力
- 读写工作空间文件
- 执行 Shell 命令
- 网络搜索和抓取网页
- 使用所有标准工具

## 限制
- 不能直接向用户发送消息（无 message 工具）
- 不能创建其他子代理（无 spawn 工具）
- 无法访问主代理的对话历史

## 工作空间
{workspace_path}

**重要提示**：
- 临时文件请写入 `temp/` 目录
- 使用相对路径时，基于工作空间根目录
"""

        # 如果启用技能系统，注入技能摘要
        if enable_skills and self.skills:
            try:
                skills_summary = self.skills.build_skills_summary()
                if skills_summary:
                    prompt += f"""

## 可用技能（Skills）

**重要**: 技能不是工具！技能是包含命令行调用示例的文档，需要先读取文档，再使用 exec 工具执行其中的命令。

以下技能已启用，需要时使用 read_file 工具读取完整内容：

{skills_summary}

**正确使用流程**:
1. 用户提到某个功能（如"生成图片"、"查天气"、"发小红书"）
2. 使用 read_file 读取对应技能文档: read_file(path='skills/<技能名>/SKILL.md')
3. 阅读文档中的命令行示例
4. 使用 exec 工具执行文档中的命令

**错误示例**: 
❌ image_gen(prompt="...")  # 错误！image-gen 不是工具
❌ weather(city="...")      # 错误！weather 不是工具

**正确示例**:
✅ read_file(path='skills/image-gen/SKILL.md')  # 先读取技能文档
✅ exec(command='python skills/image-gen/scripts/generate.py ...')  # 再执行命令
"""
            except Exception as e:
                logger.warning(f"Failed to inject skills into subagent prompt: {e}")

        prompt += """

## 完成标准
任务完成后，提供清晰的总结：
- 完成了什么
- 发现了什么（如果是调查任务）
- 遇到的问题（如果有）
- 建议的后续步骤（如果需要）"""

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
        
        if task.status != TaskStatus.RUNNING:
            logger.warning(f"Cannot cancel task {task_id}: not running")
            return False
        
        # 取消异步任务
        async_task = self.running_tasks.get(task_id)
        if async_task:
            async_task.cancel()
            logger.info(f"Cancelled task {task_id}")
            return True
        
        return False

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
