"""跨会话搜索：按关键词检索会话标题、摘要与消息内容。"""

from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.message import Message
from backend.models.session import Session
from backend.modules.multiuser.identity import AuthUser
from backend.modules.multiuser.permissions import owner_scope, require_active_user
from backend.utils.datetime_utils import to_utc_iso

router = APIRouter(
    prefix="/api",
    tags=["session-search"],
    dependencies=[Depends(require_active_user)],
)

# 摘要片段左右各截取的字符数
SNIPPET_RADIUS = 60
# 无命中关键词时的预览长度
PREVIEW_LIMIT = 120


class SessionSearchRequest(BaseModel):
    """搜索请求体。"""

    query: str = Field("", description="搜索关键词")
    limit: int = Field(20, ge=1, le=100, description="返回会话数量上限")
    per_session_snippets: int = Field(2, ge=0, le=10, description="每个会话返回的片段数")


class SessionSearchHit(BaseModel):
    """单条会话命中结果。"""

    session_id: str
    session_name: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    summary: Optional[str] = None
    message_count: int = 0
    score: float = 0.0
    snippets: List[str] = Field(default_factory=list)
    preview: str = ""


class SessionSearchResponse(BaseModel):
    hits: List[SessionSearchHit] = Field(default_factory=list)
    total: int = 0


def _escape_like(raw: str) -> str:
    """转义 LIKE 通配符。"""
    return raw.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _collapse(text: str) -> str:
    """折叠空白。"""
    return " ".join((text or "").split())


def _build_snippet(content: str, keyword: str) -> str:
    """截取关键词附近的片段。"""
    text = _collapse(content)
    if not text:
        return ""
    if not keyword:
        return text[:PREVIEW_LIMIT]

    index = text.lower().find(keyword.lower())
    if index < 0:
        return text[:PREVIEW_LIMIT]

    start = max(0, index - SNIPPET_RADIUS)
    end = min(len(text), index + len(keyword) + SNIPPET_RADIUS)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return f"{prefix}{text[start:end]}{suffix}"


@router.post("/session-search", response_model=SessionSearchResponse)
async def search_sessions(
    request: SessionSearchRequest,
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(require_active_user),
) -> SessionSearchResponse:
    """搜索当前用户可见的会话。"""
    keyword = request.query.strip()
    if not keyword:
        return SessionSearchResponse(hits=[], total=0)

    pattern = f"%{_escape_like(keyword)}%"
    scope = owner_scope(user)

    # 1) 标题 / 摘要命中
    meta_stmt = select(Session).where(
        or_(
            Session.name.like(pattern, escape="\\"),
            Session.summary.like(pattern, escape="\\"),
        )
    )
    if scope is not None:
        meta_stmt = meta_stmt.where(Session.owner_id == scope)
    meta_map: Dict[str, Session] = {
        item.id: item for item in (await db.execute(meta_stmt)).scalars().all()
    }

    # 2) 消息内容命中
    msg_stmt = (
        select(Message.session_id, Message.content)
        .join(Session, Session.id == Message.session_id)
        .where(Message.content.like(pattern, escape="\\"))
    )
    if scope is not None:
        msg_stmt = msg_stmt.where(Session.owner_id == scope)
    msg_rows = (await db.execute(msg_stmt)).all()

    match_count: Dict[str, int] = {}
    snippets: Dict[str, List[str]] = {}
    for session_id, content in msg_rows:
        match_count[session_id] = match_count.get(session_id, 0) + 1
        bucket = snippets.setdefault(session_id, [])
        if len(bucket) >= request.per_session_snippets:
            continue
        snippet = _build_snippet(content or "", keyword)
        if snippet and snippet not in bucket:
            bucket.append(snippet)

    hit_ids = set(meta_map) | set(match_count)
    if not hit_ids:
        return SessionSearchResponse(hits=[], total=0)

    # 3) 仅消息命中的会话，补齐元数据
    missing = hit_ids - set(meta_map)
    if missing:
        extra_stmt = select(Session).where(Session.id.in_(missing))
        if scope is not None:
            extra_stmt = extra_stmt.where(Session.owner_id == scope)
        for item in (await db.execute(extra_stmt)).scalars().all():
            meta_map[item.id] = item
        hit_ids &= set(meta_map)

    # 4) 每个会话的消息总数
    count_stmt = (
        select(Message.session_id, func.count(Message.id))
        .where(Message.session_id.in_(hit_ids))
        .group_by(Message.session_id)
    )
    counts: Dict[str, int] = {
        session_id: int(total) for session_id, total in (await db.execute(count_stmt)).all()
    }

    hits: List[SessionSearchHit] = []
    lowered = keyword.lower()
    for session_id in hit_ids:
        item = meta_map[session_id]
        score = float(match_count.get(session_id, 0))
        if lowered in (item.name or "").lower():
            score += 2.0  # 标题命中权重最高
        if lowered in (item.summary or "").lower():
            score += 1.0

        snippet_list = snippets.get(session_id, [])
        preview = _collapse(item.summary or "")[:PREVIEW_LIMIT]
        if not preview and snippet_list:
            preview = snippet_list[0]

        hits.append(
            SessionSearchHit(
                session_id=item.id,
                session_name=item.name,
                created_at=to_utc_iso(item.created_at),
                updated_at=to_utc_iso(item.updated_at),
                summary=item.summary,
                message_count=counts.get(session_id, 0),
                score=score,
                snippets=snippet_list,
                preview=preview,
            )
        )

    hits.sort(key=lambda hit: (hit.score, hit.updated_at or ""), reverse=True)
    return SessionSearchResponse(hits=hits[: request.limit], total=len(hits))
