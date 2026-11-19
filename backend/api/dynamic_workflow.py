"""Dynamic Workflow 的运行查询与控制 API。"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from backend.modules.multiuser.identity import AuthUser
from backend.modules.multiuser.permissions import require_active_user

router = APIRouter(prefix="/api/dynamic-workflow", tags=["dynamic-workflow"])

_service = None


def set_dynamic_workflow_service(service) -> None:
    global _service
    _service = service


def get_dynamic_workflow_service():
    if _service is None:
        raise RuntimeError("Dynamic Workflow service is not initialized")
    return _service


class DynamicWorkflowRunRequest(BaseModel):
    program: Dict[str, Any]
    run_id: str = Field(..., min_length=1, max_length=128)
    confirmed: bool = False


async def _execution_context(request: Request, user: AuthUser):
    if user.is_admin:
        shared = request.app.state.shared
        return {
            "workspace": str(shared["workspace"]),
            "runtime": shared,
            "user": user,
        }
    runtime = await request.app.state.user_runtime_manager.get(user)
    return {
        "workspace": str(runtime.workspace),
        "runtime": runtime,
        "user": user,
    }


class DynamicWorkflowTemplateRequest(BaseModel):
    template_id: str = Field(..., min_length=1, max_length=128)
    name: str = Field(..., min_length=1, max_length=200)
    program: Dict[str, Any]


@router.post("/templates")
async def save_template(payload: DynamicWorkflowTemplateRequest, user: AuthUser = Depends(require_active_user)):
    return await get_dynamic_workflow_service().save_template(
        template_id=payload.template_id,
        owner_id=user.owner_id,
        name=payload.name,
        program=payload.program,
    )


@router.get("/templates/{template_id}")
async def get_template(template_id: str, user: AuthUser = Depends(require_active_user)):
    record = await get_dynamic_workflow_service().get_template(template_id, owner_id=user.owner_id)
    if record is None:
        return {"found": False}
    return record


@router.post("/runs")
async def start_run(payload: DynamicWorkflowRunRequest, request: Request, user: AuthUser = Depends(require_active_user)):
    context = await _execution_context(request, user)
    return await get_dynamic_workflow_service().start(
        run_id=payload.run_id,
        owner_id=user.owner_id,
        session_id=None,
        workspace=context["workspace"],
        program=payload.program,
        runtime=context["runtime"],
        user=user,
        confirmed=payload.confirmed,
    )


class DynamicWorkflowTemplateRunRequest(BaseModel):
    template_id: str = Field(..., min_length=1, max_length=128)
    run_id: str = Field(..., min_length=1, max_length=128)


@router.post("/template-runs")
async def start_template_run(payload: DynamicWorkflowTemplateRunRequest, request: Request, user: AuthUser = Depends(require_active_user)):
    context = await _execution_context(request, user)
    template = await get_dynamic_workflow_service().get_template(
        payload.template_id, owner_id=user.owner_id,
    )
    if template is None:
        return {"found": False}
    return await get_dynamic_workflow_service().start(
        run_id=payload.run_id,
        owner_id=user.owner_id,
        session_id=None,
        workspace=context["workspace"],
        program=template["program"],
        runtime=context["runtime"],
        user=user,
        confirmed=True,
    )


@router.get("/runs/{run_id}")
async def get_run(run_id: str, user: AuthUser = Depends(require_active_user)):
    record = await get_dynamic_workflow_service().get_run(run_id, owner_id=user.owner_id)
    if record is None:
        return {"found": False}
    return record


@router.post("/runs/{run_id}/resume")
async def resume_run(run_id: str, request: Request, user: AuthUser = Depends(require_active_user)):
    context = await _execution_context(request, user)
    return await get_dynamic_workflow_service().resume(
        run_id=run_id,
        owner_id=user.owner_id,
        runtime=context["runtime"],
        user=user,
    )


class DynamicWorkflowAmendRequest(BaseModel):
    program: Dict[str, Any]


@router.post("/runs/{run_id}/amend")
async def amend_run(run_id: str, payload: DynamicWorkflowAmendRequest, request: Request, user: AuthUser = Depends(require_active_user)):
    context = await _execution_context(request, user)
    return await get_dynamic_workflow_service().amend(
        run_id=run_id,
        owner_id=user.owner_id,
        program=payload["program"],
        runtime=context["runtime"],
        user=user,
    )


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str, user: AuthUser = Depends(require_active_user)):
    service = get_dynamic_workflow_service()
    record = await service.get_run(run_id, owner_id=user.owner_id)
    if record is None:
        return {"cancelled": False}
    return {"cancelled": service.cancel(run_id)}
