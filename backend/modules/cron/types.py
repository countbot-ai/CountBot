"""Cron 模块类型定义"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class JobStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DISABLED = "disabled"


@dataclass
class CronJobInfo:
    """Cron 任务信息"""
    id: str
    name: str
    schedule: str
    message: str
    enabled: bool
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    created_at: Optional[datetime] = None
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "schedule": self.schedule,
            "message": self.message,
            "enabled": self.enabled,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


@dataclass
class JobExecutionResult:
    """任务执行结果"""
    job_id: str
    success: bool
    started_at: datetime
    completed_at: datetime
    error: Optional[str] = None
    output: Optional[str] = None
    
    @property
    def duration(self) -> float:
        return (self.completed_at - self.started_at).total_seconds()
    
    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "success": self.success,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "duration": self.duration,
            "error": self.error,
            "output": self.output,
        }


@dataclass
class CronSchedule:
    """Cron 调度表达式"""
    expression: str
    description: str
    next_run: datetime
    
    def to_dict(self) -> dict:
        return {
            "expression": self.expression,
            "description": self.description,
            "next_run": self.next_run.isoformat(),
        }
