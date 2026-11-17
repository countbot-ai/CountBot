"""Cron 调度器并发边界回归测试。"""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from backend.modules.cron.service import CronService
from backend.modules.cron.scheduler import CronScheduler


@asynccontextmanager
async def _fake_db():
    yield object()


def _job(job_id: str):
    return SimpleNamespace(id=job_id, enabled=True, next_run=None)


@pytest.mark.asyncio
async def test_on_timer_returns_before_batch_finishes(monkeypatch):
    """到期批次启动后应立即重新布防，不能等待整批任务结束。"""
    scheduler = CronScheduler(db_session_factory=_fake_db, max_concurrent=2)
    started: list[str] = []
    release = asyncio.Event()

    async def fake_execute(job):
        started.append(job.id)
        await release.wait()

    async def fake_due(self):
        return [_job("a"), _job("b")]

    monkeypatch.setattr(scheduler, "_execute_job_safe", fake_execute)
    monkeypatch.setattr(CronService, "get_due_jobs", fake_due)

    await asyncio.wait_for(scheduler._on_timer(), timeout=0.5)
    await asyncio.sleep(0)
    assert sorted(started) == ["a", "b"]
    assert scheduler._active_jobs == {"a", "b"}

    release.set()
    await asyncio.gather(*list(scheduler._active_tasks), return_exceptions=True)
    assert scheduler._active_jobs == set()


@pytest.mark.asyncio
async def test_on_timer_skips_jobs_reserved_by_first_batch(monkeypatch):
    """同一批任务仍在执行时，下一次触发不能重复启动它们。"""
    scheduler = CronScheduler(db_session_factory=_fake_db, max_concurrent=2)
    started: list[str] = []
    release = asyncio.Event()

    async def fake_execute(job):
        started.append(job.id)
        await release.wait()

    async def fake_due(self):
        return [_job("a"), _job("b")]

    monkeypatch.setattr(scheduler, "_execute_job_safe", fake_execute)
    monkeypatch.setattr(CronService, "get_due_jobs", fake_due)

    await scheduler._on_timer()
    await asyncio.sleep(0)
    await scheduler._on_timer()
    await asyncio.sleep(0)
    assert sorted(started) == ["a", "b"]

    release.set()
    await asyncio.gather(*list(scheduler._active_tasks), return_exceptions=True)


@pytest.mark.asyncio
async def test_manual_runs_share_concurrency_limit(monkeypatch):
    """手动触发也必须经过信号量，不能绕过 max_concurrent。"""
    scheduler = CronScheduler(db_session_factory=_fake_db, max_concurrent=1)
    started: list[str] = []
    release = asyncio.Event()

    async def fake_get_job(service, job_id):
        return _job(job_id)

    async def fake_execute_job(job, service, manual=False):
        started.append(job.id)
        await release.wait()

    monkeypatch.setattr(CronService, "get_job", fake_get_job)
    monkeypatch.setattr(scheduler, "_execute_job", fake_execute_job)

    first = asyncio.create_task(scheduler.run_job_manually("a"))
    second = asyncio.create_task(scheduler.run_job_manually("b"))

    for _ in range(20):
        await asyncio.sleep(0)
    assert started == ["a"]
    assert len(scheduler._active_tasks) == 2

    release.set()
    await asyncio.gather(first, second, return_exceptions=True)
    assert started == ["a", "b"]
    assert scheduler._active_tasks == set()
