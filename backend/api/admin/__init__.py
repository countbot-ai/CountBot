"""管理员 API：用户管理、多用户策略与共享模型。"""

from backend.api.admin._router import router

# 副作用导入：完成 @router.xxx 注册，不能省略
from backend.api.admin import multiuser as _multiuser  # noqa: F401
from backend.api.admin import shared_models as _shared_models  # noqa: F401
from backend.api.admin import users as _users  # noqa: F401

__all__ = ["router"]
