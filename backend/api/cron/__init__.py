"""Cron API。

子模块按职责分组（模型、校验、任务增删改查、批量操作、执行记录、
会话归属等），本模块重新导出全部对外符号，
``from backend.api.cron import router`` 等既有导入方式不受影响。
"""

from backend.api.cron._common import (
    BUILTIN_PREFIX,
    _SHANGHAI_TZ,
    _now_beijing,
    _to_shanghai_iso,
    get_cron_service,
    router,
)
from backend.api.cron.helpers import _find_cron_session, _get_cron_job_or_404
from backend.api.cron.models import (
    BatchCreateCronJobsRequest,
    BatchCreateCronJobsResponse,
    BatchDeleteCronJobsRequest,
    BatchDeleteCronJobsResponse,
    CleanupCronSessionRequest,
    CleanupCronSessionResponse,
    CreateCronJobRequest,
    CronJobDetailResponse,
    CronJobInfo,
    CronJobMessagesResponse,
    CronJobResponse,
    CronSessionMessage,
    DeleteCronJobResponse,
    ExecuteCronJobResponse,
    ListCronJobsResponse,
    ResetCronSessionResponse,
    UpdateCronJobRequest,
    ValidateCronRequest,
    ValidateCronResponse,
)

# 导入路由模块以完成 @router.xxx 装饰器注册（副作用导入，不能省略）
from backend.api.cron import batch as _batch  # noqa: F401
from backend.api.cron import execution as _execution  # noqa: F401
from backend.api.cron import jobs as _jobs  # noqa: F401
from backend.api.cron import session as _session  # noqa: F401

# 路由处理函数也随原模块一起对外可见，重新导出以保持导入面完全一致
from backend.api.cron.batch import (
    batch_create_cron_jobs,
    batch_delete_cron_jobs,
)
from backend.api.cron.execution import (
    trigger_cron_job,
    validate_cron_schedule,
)
from backend.api.cron.jobs import (
    create_cron_job,
    delete_cron_job,
    get_cron_job_detail,
    list_cron_jobs,
    update_cron_job,
)
from backend.api.cron.session import (
    cleanup_cron_job_session,
    get_cron_job_messages,
    reset_cron_job_session,
)

__all__ = [
    "router",
    "BUILTIN_PREFIX",
    "get_cron_service",
    "CronJobInfo",
    "ListCronJobsResponse",
    "CreateCronJobRequest",
    "UpdateCronJobRequest",
    "CronJobResponse",
    "DeleteCronJobResponse",
    "ExecuteCronJobResponse",
    "ValidateCronRequest",
    "ValidateCronResponse",
    "BatchCreateCronJobsRequest",
    "BatchCreateCronJobsResponse",
    "BatchDeleteCronJobsRequest",
    "BatchDeleteCronJobsResponse",
    "CronJobDetailResponse",
    "CronSessionMessage",
    "CronJobMessagesResponse",
    "CleanupCronSessionRequest",
    "CleanupCronSessionResponse",
    "ResetCronSessionResponse",
    "list_cron_jobs",
    "create_cron_job",
    "update_cron_job",
    "delete_cron_job",
    "get_cron_job_detail",
    "get_cron_job_messages",
    "cleanup_cron_job_session",
    "reset_cron_job_session",
    "trigger_cron_job",
    "validate_cron_schedule",
    "batch_create_cron_jobs",
    "batch_delete_cron_jobs",
]

