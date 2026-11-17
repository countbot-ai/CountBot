"""聊天域路由实例，各子模块共用同一 router 以避免循环导入。"""

from fastapi import APIRouter, Depends

from backend.modules.multiuser.permissions import require_active_user

router = APIRouter(
    prefix="/api/chat",
    tags=["chat"],
    dependencies=[Depends(require_active_user)],
)
