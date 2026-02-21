"""Cron 定时任务服务"""

import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from croniter import croniter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.cron_job import CronJob
from backend.modules.cron.types import CronJobInfo, JobExecutionResult, CronSchedule
from backend.utils.logger import logger

# 北京时区 UTC+8
SHANGHAI_TZ = timezone(timedelta(hours=8))


class CronService:
    """Cron 定时任务服务"""

    def __init__(self, db: AsyncSession, scheduler=None):
        self.db = db
        self.scheduler = scheduler
        self._running_jobs: dict[str, asyncio.Task] = {}

    async def add_job(
        self,
        name: str,
        schedule: str,
        message: str,
        enabled: bool = True,
        channel: Optional[str] = None,
        chat_id: Optional[str] = None,
        deliver_response: bool = False
    ) -> CronJob:
        """添加定时任务"""
        if not self.validate_schedule(schedule):
            raise ValueError(f"Invalid cron: {schedule}")
        
        next_run = self.calculate_next_run(schedule) if enabled else None
        
        job = CronJob(
            id=str(uuid.uuid4()),
            name=name,
            schedule=schedule,
            message=message,
            enabled=enabled,
            channel=channel,
            chat_id=chat_id,
            deliver_response=deliver_response,
            next_run=next_run,
            created_at=datetime.now(SHANGHAI_TZ).replace(tzinfo=None),
            updated_at=datetime.now(SHANGHAI_TZ).replace(tzinfo=None)
        )
        
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)
        
        logger.info(f"Created job: {name} ({job.id})")
        
        if self.scheduler and enabled:
            try:
                await self.scheduler.trigger_reschedule()
            except Exception as e:
                logger.error(f"Failed to reschedule: {e}")
        
        return job

    async def get_job(self, job_id: str) -> Optional[CronJob]:
        """获取任务"""
        result = await self.db.execute(
            select(CronJob).where(CronJob.id == job_id)
        )
        return result.scalar_one_or_none()

    async def list_jobs(self, enabled_only: bool = False) -> list[CronJob]:
        """列出所有任务"""
        query = select(CronJob).order_by(CronJob.created_at.desc())
        
        if enabled_only:
            query = query.where(CronJob.enabled == True)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_job(
        self,
        job_id: str,
        name: Optional[str] = None,
        schedule: Optional[str] = None,
        message: Optional[str] = None,
        enabled: Optional[bool] = None,
        channel: Optional[str] = None,
        chat_id: Optional[str] = None,
        deliver_response: Optional[bool] = None
    ) -> Optional[CronJob]:
        """更新任务"""
        job = await self.get_job(job_id)
        if job is None:
            return None
        
        if name is not None:
            job.name = name
        
        if schedule is not None:
            if not self.validate_schedule(schedule):
                raise ValueError(f"Invalid cron: {schedule}")
            job.schedule = schedule
        
        if message is not None:
            job.message = message
        
        if enabled is not None:
            job.enabled = enabled
        
        if channel is not None:
            job.channel = channel
        
        if chat_id is not None:
            job.chat_id = chat_id
        
        if deliver_response is not None:
            job.deliver_response = deliver_response
        
        if job.enabled:
            job.next_run = self.calculate_next_run(job.schedule)
        else:
            job.next_run = None
        
        job.updated_at = datetime.now(SHANGHAI_TZ).replace(tzinfo=None)
        
        await self.db.commit()
        await self.db.refresh(job)
        
        logger.info(f"Updated job: {job.name} ({job_id})")
        
        if self.scheduler:
            try:
                await self.scheduler.trigger_reschedule()
            except Exception as e:
                logger.error(f"Failed to reschedule: {e}")
        
        return job

    async def delete_job(self, job_id: str) -> bool:
        """删除任务"""
        job = await self.get_job(job_id)
        if job is None:
            return False
        
        if job_id in self._running_jobs:
            self._running_jobs[job_id].cancel()
            del self._running_jobs[job_id]
        
        await self.db.delete(job)
        await self.db.commit()
        
        logger.info(f"Deleted job: {job.name} ({job_id})")
        
        if self.scheduler:
            try:
                await self.scheduler.trigger_reschedule()
            except Exception as e:
                logger.error(f"Failed to reschedule: {e}")
        
        return True

    async def get_due_jobs(self) -> list[CronJob]:
        """获取到期任务（基于北京时间）"""
        now = datetime.now(SHANGHAI_TZ).replace(tzinfo=None)
        result = await self.db.execute(
            select(CronJob)
            .where(CronJob.enabled == True)
            .where(CronJob.next_run <= now)
            .order_by(CronJob.next_run.asc())
        )
        return list(result.scalars().all())

    def validate_schedule(self, schedule: str) -> bool:
        """验证 Cron 表达式"""
        try:
            croniter(schedule)
            return True
        except Exception:
            return False

    def calculate_next_run(
        self,
        schedule: str,
        base_time: Optional[datetime] = None
    ) -> datetime:
        """计算下次运行时间（基于北京时间）"""
        if base_time is None:
            base_time = datetime.now(SHANGHAI_TZ).replace(tzinfo=None)
        
        try:
            cron = croniter(schedule, base_time)
            return cron.get_next(datetime)
        except Exception as e:
            raise ValueError(f"Invalid cron: {schedule}") from e

    def get_schedule_description(self, schedule: str) -> str:
        """获取 Cron 表达式描述"""
        try:
            parts = schedule.split()
            if len(parts) != 5:
                return schedule
            
            minute, hour, day, month, weekday = parts
            descriptions = []
            
            if minute == "*":
                descriptions.append("每分钟")
            elif minute.startswith("*/"):
                descriptions.append(f"每 {minute[2:]} 分钟")
            else:
                descriptions.append(f"在第 {minute} 分钟")
            
            if hour == "*":
                descriptions.append("每小时")
            elif hour.startswith("*/"):
                descriptions.append(f"每 {hour[2:]} 小时")
            else:
                descriptions.append(f"在 {hour} 点")
            
            if day != "*":
                descriptions.append(f"每月第 {day} 天")
            
            if month != "*":
                descriptions.append(f"在 {month} 月")
            
            if weekday != "*":
                weekday_names = {
                    "0": "周日", "1": "周一", "2": "周二",
                    "3": "周三", "4": "周四", "5": "周五", "6": "周六"
                }
                descriptions.append(f"在{weekday_names.get(weekday, weekday)}")
            
            return " ".join(descriptions)
            
        except Exception:
            return schedule

    def to_job_info(self, job: CronJob) -> CronJobInfo:
        """转换为 CronJobInfo"""
        return CronJobInfo(
            id=job.id,
            name=job.name,
            schedule=job.schedule,
            message=job.message,
            enabled=job.enabled,
            last_run=job.last_run,
            next_run=job.next_run,
            created_at=job.created_at
        )

    async def get_job_info(self, job_id: str) -> Optional[CronJobInfo]:
        """获取任务信息"""
        job = await self.get_job(job_id)
        if job is None:
            return None
        return self.to_job_info(job)

    async def list_job_infos(self, enabled_only: bool = False) -> list[CronJobInfo]:
        """列出所有任务信息"""
        jobs = await self.list_jobs(enabled_only=enabled_only)
        return [self.to_job_info(job) for job in jobs]
