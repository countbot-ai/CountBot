"""路由实例。各子模块从这里取同一个 router，避免互相导入成环。"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/admin", tags=["admin"])
