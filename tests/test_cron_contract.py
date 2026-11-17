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
async def test_web_push_is_rejected_even_for_admin():
    with pytest.raises(HTTPException) as exc:
        await validate_channel_push_for_user(
            SimpleNamespace(is_admin=True),
            _request(channel="web"),
        )
    assert exc.value.status_code == 400


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


@pytest.mark.asyncio
async def test_delete_job_with_persisted_running_status_is_rejected():
    from backend.api.cron.jobs import delete_cron_job

    service = SimpleNamespace(
        scheduler=SimpleNamespace(is_job_active=lambda job_id: False),
        get_job=AsyncMock(return_value=SimpleNamespace(last_status="running")),
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
