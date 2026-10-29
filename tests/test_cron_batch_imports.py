"""cron 批量接口的导入完整性回归

`batch_create_cron_jobs` 在构造响应时使用 CronJobInfo 与 _to_shanghai_iso。
这两个名字在拆分时曾被漏导入，而函数体内的 NameError 不会在 import 阶段暴露，
只有真正执行到该分支才报错——补一条测试钉住。
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.api.cron.batch import batch_create_cron_jobs
from backend.api.cron.models import BatchCreateCronJobsRequest, CreateCronJobRequest


def _fake_job(name: str = "job"):
    job = MagicMock()
    job.id = "id-1"
    job.name = name
    job.schedule = "0 9 * * *"
    job.message = "hello"
    job.enabled = True
    job.channel = None
    job.account_id = "default"
    job.chat_id = None
    job.deliver_response = True
    job.last_run = None
    job.next_run = datetime(2026, 10, 25, 9, 0)
    job.last_status = None
    job.last_error = None
    job.last_delivery_status = None
    job.last_delivery_error = None
    job.run_count = 0
    job.error_count = 0
    job.created_at = datetime(2026, 10, 24, 12, 0)
    job.max_retries = 0
    job.retry_delay = 60
    job.delete_on_success = False
    # 这些字段必须给出具体值：裸 MagicMock 过不了 Pydantic 的 str/bool 校验
    job.model_provider = None
    job.model_name = None
    job.link_context = False
    job.is_running = False
    return job


def test_batch_create_builds_response_without_name_error():
    """走通批量创建路径：CronJobInfo/_to_shanghai_iso 必须可解析。"""
    service = MagicMock()
    service.add_job = AsyncMock(return_value=_fake_job())

    request = BatchCreateCronJobsRequest(
        jobs=[CreateCronJobRequest(name="job", schedule="0 9 * * *", message="hello")]
    )

    result = asyncio.run(batch_create_cron_jobs(request, cron_service=service))

    assert result.success_count == 1
    assert result.jobs
    # _to_shanghai_iso 生效时应带时区偏移
    assert result.jobs[0].next_run is not None
    assert "+08:00" in result.jobs[0].next_run


def test_batch_create_handles_partial_failure():
    """单个任务失败不应中断整批，且错误信息回填到 errors。"""
    service = MagicMock()
    service.add_job = AsyncMock(side_effect=RuntimeError("boom"))

    request = BatchCreateCronJobsRequest(
        jobs=[CreateCronJobRequest(name="bad", schedule="0 9 * * *", message="x")]
    )

    result = asyncio.run(batch_create_cron_jobs(request, cron_service=service))

    assert result.success_count == 0
    assert result.errors
    assert "boom" in result.errors[0]["error"]
