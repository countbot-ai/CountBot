"""智能 Cron 调度器"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional, Callable, Awaitable

from backend.modules.cron.service import CronService, SHANGHAI_TZ
from backend.utils.logger import logger


def _now_shanghai() -> datetime:
    """获取当前北京时间（naive，无 tzinfo）"""
    return datetime.now(SHANGHAI_TZ).replace(tzinfo=None)

# 默认最大并发执行数
DEFAULT_MAX_CONCURRENT = 3
# 单个任务最大执行时间（秒）
DEFAULT_JOB_TIMEOUT = 300
# SQLite 写入重试次数
MAX_COMMIT_RETRIES = 3


class CronScheduler:
    """智能调度器 - 精确按需唤醒，支持并发控制"""
    
    def __init__(
        self,
        db_session_factory,
        on_execute: Optional[Callable[..., Awaitable[str]]] = None,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
        job_timeout: int = DEFAULT_JOB_TIMEOUT,
    ):
        self.db_session_factory = db_session_factory
        self.on_execute = on_execute
        self.job_timeout = job_timeout
        self._running = False
        self._timer_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()  # 防止并发调度问题
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._active_jobs: set[str] = set()  # 正在执行的 job_id 集合
        self._active_tasks: set[asyncio.Task] = set()  # 正在执行的 asyncio.Task
    
    async def start(self):
        """启动调度器"""
        async with self._lock:
            if self._running:
                logger.warning("Scheduler already running")
                return
            self._running = True
        
        await self._recompute_next_runs()
        self._arm_timer()
        logger.info(f"Cron scheduler started (max_concurrent={self._semaphore._value}, timeout={self.job_timeout}s)")
    
    async def stop(self):
        """停止调度器，等待正在执行的任务完成"""
        async with self._lock:
            if not self._running:
                return
            self._running = False
        
        # 取消定时器
        if self._timer_task:
            self._timer_task.cancel()
            try:
                await self._timer_task
            except asyncio.CancelledError:
                pass
            self._timer_task = None
        
        # 等待正在执行的任务完成（最多等 30 秒）
        if self._active_tasks:
            logger.info(f"Waiting for {len(self._active_tasks)} active jobs to finish...")
            done, pending = await asyncio.wait(
                self._active_tasks,
                timeout=30,
            )
            if pending:
                logger.warning(f"Force cancelling {len(pending)} jobs after timeout")
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
        
        logger.info("Cron scheduler stopped")
    
    async def _recompute_next_runs(self):
        """重新计算所有任务的下次运行时间"""
        try:
            async with self.db_session_factory() as db:
                service = CronService(db)
                jobs = await service.list_jobs(enabled_only=True)
                
                for job in jobs:
                    try:
                        next_run = service.calculate_next_run(job.schedule)
                        job.next_run = next_run
                    except Exception as e:
                        logger.error(f"Failed to compute next run for {job.id}: {e}")
                
                await self._safe_commit(db)
                logger.debug(f"Recomputed {len(jobs)} jobs")
        except Exception as e:
            logger.error(f"Failed to recompute: {e}")
    
    async def _get_next_wake_time(self) -> Optional[datetime]:
        """获取最早的任务运行时间"""
        try:
            async with self.db_session_factory() as db:
                service = CronService(db)
                jobs = await service.list_jobs(enabled_only=True)
                
                if not jobs:
                    return None
                
                next_times = [j.next_run for j in jobs if j.next_run]
                if not next_times:
                    return None
                
                return min(next_times)
        except Exception as e:
            logger.error(f"Failed to get next wake time: {e}")
            return None
    
    def _arm_timer(self):
        """调度下一个定时器"""
        if self._timer_task and not self._timer_task.done():
            self._timer_task.cancel()
        
        async def schedule_next():
            try:
                next_wake = await self._get_next_wake_time()
                
                if not next_wake or not self._running:
                    logger.debug("No jobs to schedule")
                    await asyncio.sleep(60)
                    if self._running:
                        self._arm_timer()
                    return
                
                now = _now_shanghai()
                delay = (next_wake - now).total_seconds()
                
                if delay < 0:
                    logger.warning(f"Job overdue by {abs(delay):.1f}s")
                    delay = 0
                
                logger.debug(f"Next job in {delay:.1f}s at {next_wake}")
                await asyncio.sleep(delay)
                
                if self._running:
                    await self._on_timer()
            except asyncio.CancelledError:
                logger.debug("Timer cancelled")
            except Exception as e:
                logger.error(f"Timer error: {e}")
                await asyncio.sleep(10)
                if self._running:
                    self._arm_timer()
        
        self._timer_task = asyncio.create_task(schedule_next())
    
    async def _on_timer(self):
        """定时器触发 - 执行到期任务（带并发控制）"""
        try:
            async with self.db_session_factory() as db:
                service = CronService(db)
                due_jobs = await service.get_due_jobs()
                
                if not due_jobs:
                    logger.debug("No due jobs")
                    return
                
                # 过滤掉正在执行的任务，防止重复执行
                pending = [j for j in due_jobs if j.id not in self._active_jobs]
                if not pending:
                    logger.debug("All due jobs already running, skipping")
                    return
                
                logger.info(f"Executing {len(pending)} jobs (active: {len(self._active_jobs)})")
                
                # 每个任务使用独立的 db session，通过信号量控制并发
                tasks = []
                for job in pending:
                    task = asyncio.create_task(
                        self._execute_job_safe(job),
                        name=f"cron-job-{job.id[:8]}"
                    )
                    self._active_tasks.add(task)
                    task.add_done_callback(self._active_tasks.discard)
                    tasks.append(task)
                
                await asyncio.gather(*tasks, return_exceptions=True)
        
        except Exception as e:
            logger.error(f"Timer handler error: {e}")
        
        finally:
            if self._running:
                self._arm_timer()
    
    async def _execute_job_safe(self, job):
        """带信号量、超时和独立 session 的安全执行包装"""
        async with self._semaphore:
            self._active_jobs.add(job.id)
            try:
                # 每个任务使用独立的 db session
                async with self.db_session_factory() as db:
                    service = CronService(db)
                    # 重新加载 job 以获取最新状态
                    fresh_job = await service.get_job(job.id)
                    if fresh_job and fresh_job.enabled:
                        await asyncio.wait_for(
                            self._execute_job(fresh_job, service),
                            timeout=self.job_timeout,
                        )
            except asyncio.TimeoutError:
                logger.error(f"Job {job.id} timed out after {self.job_timeout}s")
                # 超时后更新状态
                try:
                    async with self.db_session_factory() as db:
                        service = CronService(db)
                        timed_out_job = await service.get_job(job.id)
                        if timed_out_job:
                            timed_out_job.last_run = _now_shanghai()
                            timed_out_job.last_status = "error"
                            timed_out_job.last_error = f"Timed out after {self.job_timeout}s"
                            timed_out_job.error_count = (timed_out_job.error_count or 0) + 1
                            timed_out_job.run_count = (timed_out_job.run_count or 0) + 1
                            if timed_out_job.enabled:
                                try:
                                    timed_out_job.next_run = service.calculate_next_run(timed_out_job.schedule)
                                except Exception:
                                    pass
                            await self._safe_commit(db)
                except Exception as e:
                    logger.error(f"Failed to update timeout status for {job.id}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error executing job {job.id}: {e}")
            finally:
                self._active_jobs.discard(job.id)
    
    async def _execute_job(self, job, service: CronService):
        """执行单个任务"""
        started_at = _now_shanghai()
        logger.info(f"Executing: {job.name} ({job.id})")
        
        try:
            if self.on_execute:
                response = await self.on_execute(
                    job.id,
                    job.message,
                    job.channel,
                    job.chat_id,
                    job.deliver_response
                )
                
                job.last_run = started_at
                job.last_status = "ok"
                job.last_error = None
                job.last_response = response[:1000] if response else None
                job.run_count = (job.run_count or 0) + 1
                logger.info(f"Job completed: {job.name}")
            else:
                logger.warning(f"No executor: {job.name}")
                job.last_status = "skipped"
            
            if job.enabled:
                try:
                    job.next_run = service.calculate_next_run(
                        job.schedule,
                        base_time=started_at
                    )
                except Exception as e:
                    logger.error(f"Failed to calculate next run: {e}")
                    job.enabled = False
                    job.last_error = f"Invalid schedule: {e}"
            
            await self._safe_commit(service.db)
            
        except Exception as e:
            logger.error(f"Job failed: {job.name} - {e}")
            
            job.last_run = started_at
            job.last_status = "error"
            job.last_error = str(e)[:1000]
            job.error_count = (job.error_count or 0) + 1
            
            if job.enabled:
                try:
                    job.next_run = service.calculate_next_run(
                        job.schedule,
                        base_time=started_at
                    )
                except Exception:
                    job.enabled = False
                    job.last_error = f"Failed to calculate next run: {e}"
            
            await self._safe_commit(service.db)
    
    async def _safe_commit(self, db):
        """带重试的安全 commit（应对 SQLite 并发锁）"""
        for attempt in range(MAX_COMMIT_RETRIES):
            try:
                await db.commit()
                return
            except Exception as e:
                if "database is locked" in str(e).lower() and attempt < MAX_COMMIT_RETRIES - 1:
                    wait = 0.5 * (attempt + 1)
                    logger.warning(f"DB locked, retrying in {wait}s (attempt {attempt + 1})")
                    await asyncio.sleep(wait)
                else:
                    logger.error(f"Commit failed after {attempt + 1} attempts: {e}")
                    raise
    
    def is_running(self) -> bool:
        return self._running
    
    def is_job_active(self, job_id: str) -> bool:
        """检查某个任务是否正在执行"""
        return job_id in self._active_jobs
    
    @property
    def active_job_count(self) -> int:
        """当前正在执行的任务数"""
        return len(self._active_jobs)
    
    async def trigger_reschedule(self):
        """手动触发重新调度"""
        if self._running:
            logger.debug("Triggering reschedule")
            await self._recompute_next_runs()
            self._arm_timer()
