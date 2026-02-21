"""Cron 工具 - Agent 可以管理定时任务"""

from typing import Any

from backend.modules.tools.base import Tool
from backend.modules.cron.service import CronService
from backend.utils.logger import logger


class CronTool(Tool):
    """定时任务工具 - Agent 可以创建和管理定时任务
    
    功能:
    - 创建定时任务
    - 列出所有任务
    - 删除任务
    - 启用/禁用任务
    - 自动设置渠道上下文
    """
    
    name = "cron"
    description = """Schedule reminders and recurring tasks using cron expressions.

Actions:
- add: Create a new scheduled job
- list: List all scheduled jobs
- remove: Remove a job by ID
- enable: Enable a disabled job
- disable: Disable a job

Cron expression format: "minute hour day month weekday"
Examples:
- "0 9 * * *" - Every day at 9:00 AM
- "*/5 * * * *" - Every 5 minutes
- "0 0 * * 0" - Every Sunday at midnight
- "0 12 * * 1-5" - Every weekday at noon

Examples:
- Schedule daily reminder: {"action": "add", "name": "Daily standup", "schedule": "0 9 * * *", "message": "Time for daily standup!"}
- List jobs: {"action": "list"}
- Remove job: {"action": "remove", "job_id": "abc123"}
- Disable job: {"action": "disable", "job_id": "abc123"}
"""
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "list", "remove", "enable", "disable"],
                "description": "Action to perform"
            },
            "name": {
                "type": "string",
                "description": "Job name (required for add)"
            },
            "schedule": {
                "type": "string",
                "description": "Cron expression like '0 9 * * *' (required for add)"
            },
            "message": {
                "type": "string",
                "description": "Message to execute when job runs (required for add)"
            },
            "job_id": {
                "type": "string",
                "description": "Job ID (required for remove/enable/disable)"
            },
            "deliver_to_channel": {
                "type": "boolean",
                "description": "Whether to send response to current channel (optional for add, default: false)"
            }
        },
        "required": ["action"]
    }
    
    def __init__(self, cron_service: CronService):
        """
        Args:
            cron_service: Cron 服务实例
        """
        self.cron_service = cron_service
        self.channel: str = "web"
        self.chat_id: str = "system"
    
    def set_context(self, channel: str, chat_id: str):
        """设置会话上下文
        
        Args:
            channel: 渠道名称
            chat_id: 聊天 ID
        """
        self.channel = channel
        self.chat_id = chat_id
        logger.debug(f"CronTool context set: channel={channel}, chat_id={chat_id}")
    
    async def execute(self, **kwargs: Any) -> str:
        """执行工具"""
        action = kwargs.get("action")
        
        if action == "add":
            return await self._add_job(
                name=kwargs.get("name"),
                schedule=kwargs.get("schedule"),
                message=kwargs.get("message"),
                deliver_to_channel=kwargs.get("deliver_to_channel", False)
            )
        elif action == "list":
            return await self._list_jobs()
        elif action == "remove":
            return await self._remove_job(kwargs.get("job_id"))
        elif action == "enable":
            return await self._toggle_job(kwargs.get("job_id"), True)
        elif action == "disable":
            return await self._toggle_job(kwargs.get("job_id"), False)
        else:
            return f"Unknown action: {action}"
    
    async def _add_job(
        self,
        name: str,
        schedule: str,
        message: str,
        deliver_to_channel: bool = False
    ) -> str:
        """添加定时任务"""
        if not name or not schedule or not message:
            return "Error: name, schedule, and message are required"
        
        try:
            # 创建任务，自动关联当前渠道
            job = await self.cron_service.add_job(
                name=name,
                schedule=schedule,
                message=message,
                enabled=True,
                channel=self.channel if deliver_to_channel else None,
                chat_id=self.chat_id if deliver_to_channel else None,
                deliver_response=deliver_to_channel
            )
            
            logger.info(f"Cron job created by agent: {name} ({job.id})")
            
            # 格式化响应
            response = f"Created job '{job.name}' (ID: {job.id})\n"
            response += f"Schedule: {schedule}\n"
            response += f"Next run: {job.next_run.strftime('%Y-%m-%d %H:%M:%S UTC') if job.next_run else 'N/A'}\n"
            
            if deliver_to_channel:
                response += f"Will deliver to: {self.channel}:{self.chat_id}"
            
            return response
            
        except ValueError as e:
            return f"Invalid cron expression: {e}"
        except Exception as e:
            logger.error(f"Failed to create cron job: {e}")
            return f"Failed to create job: {e}"
    
    async def _list_jobs(self) -> str:
        """列出所有任务"""
        try:
            jobs = await self.cron_service.list_jobs()
            
            if not jobs:
                return "No scheduled jobs."
            
            lines = ["Scheduled jobs:\n"]
            for i, job in enumerate(jobs, 1):
                status = "Enabled" if job.enabled else "Disabled"
                next_run = job.next_run.strftime("%Y-%m-%d %H:%M:%S UTC") if job.next_run else "N/A"
                last_run = job.last_run.strftime("%Y-%m-%d %H:%M:%S UTC") if job.last_run else "Never"
                
                lines.append(f"{i}. {job.name} ({status})")
                lines.append(f"   ID: {job.id}")
                lines.append(f"   Schedule: {job.schedule}")
                lines.append(f"   Message: {job.message[:50]}{'...' if len(job.message) > 50 else ''}")
                lines.append(f"   Next run: {next_run}")
                lines.append(f"   Last run: {last_run}")
                
                if job.last_status:
                    status_icon = "OK" if job.last_status == "ok" else "FAIL"
                    lines.append(f"   Last status: {status_icon} {job.last_status}")
                
                if job.run_count:
                    lines.append(f"   Runs: {job.run_count} (Errors: {job.error_count or 0})")
                
                if job.channel:
                    lines.append(f"   Channel: {job.channel}:{job.chat_id}")
                
                lines.append("")  # 空行分隔
            
            return "\n".join(lines)
            
        except Exception as e:
            logger.error(f"Failed to list cron jobs: {e}")
            return f"Failed to list jobs: {e}"
    
    async def _remove_job(self, job_id: str) -> str:
        """删除任务"""
        if not job_id:
            return "Error: job_id is required"
        
        try:
            # 先获取任务信息
            job = await self.cron_service.get_job(job_id)
            if not job:
                return f"Job {job_id} not found"
            
            job_name = job.name
            
            # 删除任务
            success = await self.cron_service.delete_job(job_id)
            
            if success:
                logger.info(f"Cron job removed by agent: {job_id}")
                return f"Removed job '{job_name}' ({job_id})"
            else:
                return f"Job {job_id} not found"
                
        except Exception as e:
            logger.error(f"Failed to remove cron job: {e}")
            return f"Failed to remove job: {e}"
    
    async def _toggle_job(self, job_id: str, enabled: bool) -> str:
        """启用/禁用任务"""
        if not job_id:
            return "Error: job_id is required"
        
        try:
            job = await self.cron_service.update_job(job_id, enabled=enabled)
            
            if job:
                status = "enabled" if enabled else "disabled"
                logger.info(f"Cron job {status} by agent: {job_id}")
                
                response = f"Job '{job.name}' {status}"
                if enabled and job.next_run:
                    response += f"\nNext run: {job.next_run.strftime('%Y-%m-%d %H:%M:%S UTC')}"
                
                return response
            else:
                return f"Job {job_id} not found"
                
        except Exception as e:
            logger.error(f"Failed to toggle cron job: {e}")
            return f"Failed to toggle job: {e}"
