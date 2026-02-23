"""Memory API 端点

提供记忆的 HTTP 接口:
- GET /api/memory/long-term — 读取全部记忆
- PUT /api/memory/long-term — 覆盖写入记忆
- GET /api/memory/stats — 获取记忆统计
- GET /api/memory/recent — 获取最近记忆
- POST /api/memory/search — 搜索记忆
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from loguru import logger
from pydantic import BaseModel, Field

from backend.modules.agent.memory import MemoryStore
from backend.modules.config.loader import config_loader

router = APIRouter(prefix="/api/memory", tags=["memory"])


class MemoryContentResponse(BaseModel):
    content: str = Field(..., description="记忆内容")


class UpdateMemoryRequest(BaseModel):
    content: str = Field(..., description="记忆内容")


class UpdateMemoryResponse(BaseModel):
    success: bool = Field(..., description="是否成功")
    message: str | None = Field(None, description="消息")


class MemoryStatsResponse(BaseModel):
    total: int
    sources: dict[str, int]
    date_range: str


class SearchRequest(BaseModel):
    keywords: str = Field(..., description="搜索关键词，空格分隔")
    max_results: int = Field(15, description="最大返回条数")


class SearchResponse(BaseModel):
    results: str
    total: int


from backend.modules.config.loader import config_loader
from backend.utils.paths import WORKSPACE_DIR


def get_memory_store() -> MemoryStore:
    config = config_loader.config
    workspace = Path(config.workspace.path) if config.workspace.path else WORKSPACE_DIR
    memory_dir = workspace / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    return MemoryStore(memory_dir)


@router.get("/long-term", response_model=MemoryContentResponse)
async def get_long_term_memory() -> MemoryContentResponse:
    """获取全部记忆"""
    try:
        memory = get_memory_store()
        content = memory.read_all()
        return MemoryContentResponse(content=content)
    except Exception as e:
        logger.exception(f"Failed to get memory: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/long-term", response_model=UpdateMemoryResponse)
async def update_long_term_memory(request: UpdateMemoryRequest) -> UpdateMemoryResponse:
    """覆盖写入全部记忆"""
    try:
        memory = get_memory_store()
        memory.write_all(request.content)
        return UpdateMemoryResponse(success=True, message="Memory updated")
    except Exception as e:
        logger.exception(f"Failed to update memory: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", response_model=MemoryStatsResponse)
async def get_memory_stats() -> MemoryStatsResponse:
    """获取记忆统计"""
    try:
        memory = get_memory_store()
        stats = memory.get_stats()
        return MemoryStatsResponse(**stats)
    except Exception as e:
        logger.exception(f"Failed to get memory stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recent", response_model=MemoryContentResponse)
async def get_recent_memory(count: int = 10) -> MemoryContentResponse:
    """获取最近 N 条记忆"""
    try:
        memory = get_memory_store()
        content = memory.get_recent(count)
        return MemoryContentResponse(content=content)
    except Exception as e:
        logger.exception(f"Failed to get recent memory: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search", response_model=SearchResponse)
async def search_memory(request: SearchRequest) -> SearchResponse:
    """搜索记忆"""
    try:
        memory = get_memory_store()
        keyword_list = request.keywords.strip().split()
        results = memory.search(keyword_list, max_results=request.max_results)
        stats = memory.get_stats()
        return SearchResponse(results=results, total=stats["total"])
    except Exception as e:
        logger.exception(f"Failed to search memory: {e}")
        raise HTTPException(status_code=500, detail=str(e))
