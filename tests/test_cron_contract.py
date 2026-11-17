"""Cron 推送、参数边界与更新语义回归测试。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from backend.api.cron._common import validate_channel_push_for_user
from backend.api.cron.models import CreateCronJobRequest


def _request(**overrides):
    values = {
        "deliver_response": True,
        "channel": "web",
        "account_id": "default",
        "chat_id": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_web_push_is_allowed_without_chat_id():
    # 网页推送由 WebSocket 站内通知承接，不需要 chat_id
    await validate_channel_push_for_user(
        SimpleNamespace(is_admin=True),
        _request(channel="web", chat_id=""),
    )


@pytest.mark.asyncio
async def test_chat_target_is_required_for_real_channel():
    with pytest.raises(HTTPException) as exc:
        await validate_channel_push_for_user(
            SimpleNamespace(is_admin=True),
            _request(channel="telegram", chat_id=""),
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_push_only_channel_does_not_require_chat_id():
    await validate_channel_push_for_user(
        SimpleNamespace(is_admin=True),
        _request(channel="serverchan", chat_id=""),
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"max_retries": 6},
        {"retry_delay": 9},
        {"retry_delay": 3601},
        {"message": "x" * 10001},
    ],
)
def test_request_bounds_reject_out_of_range(payload):
    base = {
        "name": "边界测试",
        "schedule": "0 9 * * *",
        "message": "hello",
    }
    base.update(payload)
    with pytest.raises(ValidationError):
        CreateCronJobRequest(**base)


@pytest.mark.parametrize(
    "response",
    [
        "所选模型不可用，请在设置中确认模型名称是否正确。\n\n上游原始返回：Error code: 503",
        "请求过于频繁，上游限流，请稍后重试。\n\n上游原始返回：429",
        "AI 调用出错\n\n上游原始返回：unknown error",
    ],
)
def test_provider_error_text_is_detected(response):
    from backend.modules.cron.executor import CronExecutor

    assert CronExecutor._is_provider_error_response(response)


def test_normal_response_is_not_provider_error():
    from backend.modules.cron.executor import CronExecutor

    assert not CronExecutor._is_provider_error_response("任务执行完成，一切正常")


@pytest.mark.asyncio
async def test_executor_accepts_web_delivery():
    from backend.modules.cron.executor import CronExecutor

    executor = CronExecutor(agent=object(), bus=None)
    await executor._deliver_response_or_raise(
        channel="web",
        account_id=None,
        chat_id=None,
        response="hello",
        job_id="job-1",
    )


@pytest.mark.asyncio
async def test_service_rejects_blank_name_or_message():
    from backend.database import AsyncSessionLocal, init_db
    from backend.modules.cron.service import CronService

    await init_db()
    async with AsyncSessionLocal() as session:
        service = CronService(session)
        with pytest.raises(ValueError):
            await service.add_job(
                name="   ",
                schedule="0 9 * * *",
                message="hello",
            )
        with pytest.raises(ValueError):
            await service.add_job(
                name="blank message",
                schedule="0 9 * * *",
                message="   ",
            )


@pytest.mark.asyncio
async def test_scheduler_web_delivery_marks_ok_when_online():
    from backend.modules.cron.scheduler import CronScheduler

    scheduler = CronScheduler.__new__(CronScheduler)
    job = SimpleNamespace(
        id="web-job",
        name="web notification",
        channel="web",
        deliver_response=True,
        owner_id=None,
        last_delivery_status=None,
        last_delivery_error=None,
    )

    async def online(*args, **kwargs):
        return 1

    scheduler._broadcast_web_result = online
    assert await scheduler._finalize_web_delivery(job, "ok", response="hello") == 1
    assert job.last_delivery_status == "ok"
    assert job.last_delivery_error is None


@pytest.mark.asyncio
async def test_scheduler_web_delivery_marks_failed_when_offline():
    from backend.modules.cron.scheduler import CronScheduler

    scheduler = CronScheduler.__new__(CronScheduler)
    job = SimpleNamespace(
        id="web-job",
        name="web notification",
        channel="web",
        deliver_response=True,
        owner_id=None,
        last_delivery_status=None,
        last_delivery_error=None,
    )

    async def offline(*args, **kwargs):
        return 0

    scheduler._broadcast_web_result = offline
    assert await scheduler._finalize_web_delivery(job, "ok", response="hello") == 0
    assert job.last_delivery_status == "failed"
    assert "未送达" in job.last_delivery_error


@pytest.mark.asyncio
async def test_delete_job_with_persisted_running_status_is_rejected():
    from backend.api.cron.jobs import delete_cron_job

    service = SimpleNamespace(
        scheduler=SimpleNamespace(is_job_active=lambda job_id: False),
        get_job=AsyncMock(return_value=SimpleNamespace(id="running-job", last_status="running")),
        delete_job=AsyncMock(return_value=True),
    )
    with pytest.raises(HTTPException) as exc:
        await delete_cron_job("running-job", service)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_delete_running_job_is_rejected():
    from backend.api.cron.jobs import delete_cron_job

    service = SimpleNamespace(
        scheduler=SimpleNamespace(is_job_active=lambda job_id: True),
        get_job=AsyncMock(return_value=SimpleNamespace(id="running-job", last_status=None)),
        delete_job=AsyncMock(return_value=True),
    )
    with pytest.raises(HTTPException) as exc:
        await delete_cron_job("running-job", service)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_update_clear_delivery_resets_target_fields():
    from backend.database import AsyncSessionLocal, init_db
    from backend.modules.cron.service import CronService

    await init_db()
    async with AsyncSessionLocal() as session:
        service = CronService(session)
        job = await service.add_job(
            name=f"__cron_clear_{uuid4().hex[:8]}__",
            schedule="0 9 * * *",
            message="hello",
            deliver_response=True,
            channel="telegram",
            account_id="default",
            chat_id="chat-1",
        )
        try:
            updated = await service.update_job(
                job.id,
                deliver_response=False,
                clear_delivery=True,
            )
            assert updated is not None
            assert updated.deliver_response is False
            assert updated.channel is None
            assert updated.account_id is None
            assert updated.chat_id is None
        finally:
            await service.delete_job(job.id)
