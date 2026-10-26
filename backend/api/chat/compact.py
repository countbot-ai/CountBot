"""手动上下文压缩端点：跳过自动路径的阈值与冷却，压缩结果写入会话摘要字段（原文不动、可逆）。"""

from __future__ import annotations

from typing import List, Optional

from fastapi import Depends, HTTPException, status
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.chat._router import router as _router
from backend.api.chat.loop_factory import get_agent_loop
from backend.database import get_db
from backend.modules.agent.loop import AgentLoop
from backend.modules.compression import CompressionEngine, CompactionSettings
from backend.modules.compression.tokens import estimate_messages_tokens
from backend.modules.session import ConversationContextService

# 压缩至少需要的历史条数：低于此值不存在可摘要区段
MIN_MESSAGES_FOR_COMPACTION = 4

# 取历史上限：压缩本身为缩短上下文，无需加载全量历史
HISTORY_LIMIT_FOR_COMPACTION = 400


class CompactRequest(BaseModel):
    """手动压缩请求。"""

    focus_topic: Optional[str] = Field(
        None,
        max_length=200,
        description="关注主题：摘要优先保留与该主题相关的细节",
    )
    memory_context: Optional[str] = Field(
        None,
        max_length=6_000,
        description="需要保留的运行时上下文，作为摘要的背景信息",
    )


class CompactResponse(BaseModel):
    """手动压缩结果。"""

    success: bool
    session_id: str
    reason: str
    before_tokens: int
    after_tokens: int
    saved_tokens: int
    savings_ratio: float
    summarized_messages: int
    pruned_tool_results: int
    summary_deterministic: bool
    message: str


@_router.post("/sessions/{session_id}/compact", response_model=CompactResponse)
async def compact_session_context(
    session_id: str,
    payload: Optional[CompactRequest] = None,
    db: AsyncSession = Depends(get_db),
    agent_loop: AgentLoop = Depends(get_agent_loop),
) -> CompactResponse:
    """手动压缩会话上下文（结果写回会话摘要字段，原文保留、可逆）。"""
    request = payload or CompactRequest()

    context_service = ConversationContextService(db)
    session_row = await context_service.get_session(session_id)
    if session_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found",
        )

    # 用与 Web 会话相同的路径取历史：它负责还原思考内容与工具配对，直接读库表会缺配对
    context_payload = await context_service.build_model_context(
        session_id=session_id,
        max_history_messages=HISTORY_LIMIT_FOR_COMPACTION,
    )
    message_dicts: List[dict] = [
        message for message in context_payload.history if isinstance(message, dict)
    ]
    if len(message_dicts) < MIN_MESSAGES_FOR_COMPACTION:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="会话历史过短，没有可压缩的内容",
        )

    engine = CompressionEngine(
        CompactionSettings.from_config(getattr(agent_loop, "config", None)),
        provider=getattr(agent_loop, "provider", None),
        model=getattr(agent_loop, "model", "") or "",
        quiet=False,
        config=getattr(agent_loop, "config", None),
    )

    if not engine.has_content_to_compress(message_dicts):
        return CompactResponse(
            success=False,
            session_id=session_id,
            reason="no_compressible_window",
            before_tokens=estimate_messages_tokens(message_dicts),
            after_tokens=estimate_messages_tokens(message_dicts),
            saved_tokens=0,
            savings_ratio=0.0,
            summarized_messages=0,
            pruned_tool_results=0,
            summary_deterministic=False,
            message="当前上下文没有可压缩的部分（受保护内容已占满窗口）",
        )

    try:
        result = await engine.compress(
            message_dicts,
            force=True,
            focus_topic=request.focus_topic,
            memory_context=request.memory_context or "",
        )
    except Exception as exc:
        logger.exception(f"手动压缩失败：{exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"压缩失败：{exc}",
        )

    if not result.ok:
        reason_text = {
            "no_reduction": "摘要未能缩短上下文，已保留原历史",
            "no_compressible_window": "当前上下文没有可压缩的部分",
        }.get(result.reason, f"压缩未生效：{result.reason}")
        return CompactResponse(
            success=False,
            session_id=session_id,
            reason=result.reason,
            before_tokens=result.before_tokens,
            after_tokens=result.after_tokens or result.before_tokens,
            saved_tokens=result.saved_tokens,
            savings_ratio=result.savings_ratio,
            summarized_messages=result.summarized_count,
            pruned_tool_results=result.pruned_count,
            summary_deterministic=result.summary_deterministic,
            message=reason_text,
        )

    # 摘要写回会话：后续请求据此重建压缩后的上下文
    summary_text = engine.previous_summary
    await context_service.update_session_summary(session_id, summary_text)

    logger.info(
        f"[compact] 会话 {session_id} 手动压缩："
        f"{result.before_tokens} → {result.after_tokens} tokens，"
        f"摘要 {result.summarized_count} 条，瘦身 {result.pruned_count} 处"
    )

    return CompactResponse(
        success=True,
        session_id=session_id,
        reason=result.reason,
        before_tokens=result.before_tokens,
        after_tokens=result.after_tokens,
        saved_tokens=result.saved_tokens,
        savings_ratio=round(result.savings_ratio, 4),
        summarized_messages=result.summarized_count,
        pruned_tool_results=result.pruned_count,
        summary_deterministic=result.summary_deterministic,
        message=(
            f"已压缩：{result.before_tokens} → {result.after_tokens} tokens，"
            f"节省 {result.savings_ratio * 100:.0f}%"
        ),
    )
