"""设置域路由实例，各子模块共用同一 router 以避免循环导入。"""

from fastapi import APIRouter, Depends

from backend.modules.multiuser.permissions import require_admin

router = APIRouter(
    prefix="/api/settings",
    tags=["settings"],
    dependencies=[Depends(require_admin)],
)
