"""记忆 HTTP 接口。

旧端点保持原语义，避免前端与既有脚本被迫同时改动；新增端点补齐结构化查看与
生命周期操作。pin / 删除在这里传 ``allow_pinned=True``：pinned 只限制模型侧自动
改写，人工在面板里的操作不受该约束。
"""

from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from loguru import logger
from pydantic import BaseModel, Field

from backend.modules.config.loader import config_loader
from backend.modules.memory import MemoryDenied, MemoryKind, MemoryService
from backend.utils.paths import WORKSPACE_DIR

router = APIRouter(prefix="/api/memory", tags=["memory"])


class MemoryContentResponse(BaseModel):
    content: str = Field(..., description="记忆内容")


class UpdateMemoryRequest(BaseModel):
    content: str = Field(..., description="记忆内容")


class UpdateMemoryResponse(BaseModel):
    success: bool = Field(..., description="是否成功")
    message: Optional[str] = Field(None, description="消息")


class MemoryStatsResponse(BaseModel):
    total: int
    sources: Dict[str, int]
    date_range: str
    layers: Dict[str, int] = Field(default_factory=dict)


class SearchRequest(BaseModel):
    keywords: str = Field(..., description="搜索关键词，空格分隔")
    max_results: int = Field(15, description="最大返回条数")


class SearchResponse(BaseModel):
    results: str
    total: int


class MemoryEntryResponse(BaseModel):
    id: str
    key: str
    value: str
    kind: str
    confidence: str
    source: str
    updated_at: str
    hits: int
    superseded_by: Optional[str] = None
    superseded_from: Optional[str] = None
    deleted_at: Optional[str] = None


class MemoryEntryListResponse(BaseModel):
    total: int
    entries: List[MemoryEntryResponse]


class PinRequest(BaseModel):
    pinned: bool = Field(True, description="True 置顶，False 取消置顶")


def get_memory_store() -> MemoryService:
    config = config_loader.config
    workspace = Path(config.workspace.path) if config.workspace.path else WORKSPACE_DIR
    memory_dir = workspace / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    return MemoryService(memory_dir)


def _to_response(entry) -> MemoryEntryResponse:
    return MemoryEntryResponse(
        id=entry.id,
        key=entry.key,
        value=entry.value,
        kind=entry.kind.value,
        confidence=entry.confidence.value,
        source=entry.source,
        updated_at=entry.updated_at,
        hits=entry.hits,
        superseded_by=entry.superseded_by,
        superseded_from=entry.superseded_from,
        deleted_at=entry.deleted_at,
    )


@router.get("/long-term", response_model=MemoryContentResponse)
async def get_long_term_memory() -> MemoryContentResponse:
    """获取断言层的 markdown 视图。"""
    try:
        memory = get_memory_store()
        return MemoryContentResponse(content=memory.read_all())
    except Exception as e:
        logger.exception(f"Failed to get memory: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/long-term", response_model=UpdateMemoryResponse)
async def update_long_term_memory(request: UpdateMemoryRequest) -> UpdateMemoryResponse:
    """按视图整体替换断言层；冷存档不受影响。"""
    try:
        memory = get_memory_store()
        memory.write_all(request.content)
        return UpdateMemoryResponse(success=True, message="Memory updated")
    except Exception as e:
        logger.exception(f"Failed to update memory: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", response_model=MemoryStatsResponse)
async def get_memory_stats() -> MemoryStatsResponse:
    """获取记忆统计。"""
    try:
        memory = get_memory_store()
        stats = memory.stats()
        return MemoryStatsResponse(**stats)
    except Exception as e:
        logger.exception(f"Failed to get memory stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recent", response_model=MemoryContentResponse)
async def get_recent_memory(count: int = 10) -> MemoryContentResponse:
    """获取最近 N 条断言。"""
    try:
        memory = get_memory_store()
        return MemoryContentResponse(content=memory.get_recent(count))
    except Exception as e:
        logger.exception(f"Failed to get recent memory: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search", response_model=SearchResponse)
async def search_memory(request: SearchRequest) -> SearchResponse:
    """按关键词搜索断言与冷存档。"""
    try:
        memory = get_memory_store()
        results = memory.search(request.keywords.strip().split(), max_results=request.max_results)
        return SearchResponse(results=results, total=memory.stats()["total"])
    except Exception as e:
        logger.exception(f"Failed to search memory: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/entries", response_model=MemoryEntryListResponse)
async def list_memory_entries(
    kind: Optional[str] = Query(None, description="pinned / recent / archived"),
    limit: int = Query(50, ge=1, le=500),
    include_inactive: bool = Query(False, description="包含被取代或已删除的条目"),
) -> MemoryEntryListResponse:
    """结构化列出条目，供面板展示与失效排查。"""
    try:
        memory = get_memory_store()
        if kind and kind not in {item.value for item in MemoryKind}:
            raise HTTPException(status_code=400, detail=f"unknown kind: {kind}")
        entries = memory.list_entries(
            kind=MemoryKind(kind) if kind else None,
            limit=limit,
            include_inactive=include_inactive,
        )
        return MemoryEntryListResponse(total=len(entries), entries=[_to_response(item) for item in entries])
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to list memory entries: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/entries/{entry_id}/pin", response_model=MemoryEntryResponse)
async def set_memory_pinned(entry_id: str, request: PinRequest) -> MemoryEntryResponse:
    """置顶或取消置顶。置顶后模型侧不再能改写该条目。"""
    try:
        memory = get_memory_store()
        entry = memory.set_pinned(entry_id, request.pinned)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"memory entry '{entry_id}' not found")
        return _to_response(entry)
    except HTTPException:
        raise
    except MemoryDenied as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Failed to pin memory entry: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/entries/{entry_id}", response_model=UpdateMemoryResponse)
async def delete_memory_entry(entry_id: str) -> UpdateMemoryResponse:
    """软删除条目；保留可恢复。"""
    try:
        memory = get_memory_store()
        if not memory.forget(entry_id, allow_pinned=True):
            raise HTTPException(status_code=404, detail=f"active memory entry '{entry_id}' not found")
        return UpdateMemoryResponse(success=True, message="Memory entry removed")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to delete memory entry: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/entries/{entry_id}/restore", response_model=UpdateMemoryResponse)
async def restore_memory_entry(entry_id: str) -> UpdateMemoryResponse:
    """恢复被软删除的条目。"""
    try:
        memory = get_memory_store()
        if not memory.restore(entry_id):
            raise HTTPException(status_code=404, detail=f"deleted memory entry '{entry_id}' not found")
        return UpdateMemoryResponse(success=True, message="Memory entry restored")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to restore memory entry: {e}")
        raise HTTPException(status_code=500, detail=str(e))
