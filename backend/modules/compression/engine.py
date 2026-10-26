"""压缩引擎：瘦身 → 边界 → 摘要 → 组装四阶段；失败路径返回原始历史。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from loguru import logger

from backend.modules.compression.assembly import (
    assemble_head,
    assemble_tail,
    build_compressed,
    fresh_copy,
)
from backend.modules.compression.boundaries import sanitize_tool_pairs
from backend.modules.compression.engine_prompt import (
    SUMMARY_PREFIX,
    build_summary_prompt,
    summary_template,
)
from backend.modules.compression.marker import strip_persistence_markers
from backend.modules.compression.model_meta import ContextResolution
from backend.modules.compression.pruner import prune_tool_results
from backend.modules.compression.settings import CompactionSettings
from backend.modules.compression.summarizer import (
    FailureClass,
    Summarizer,
    deterministic_summary,
)
from backend.modules.compression.tokens import (
    content_text,
    estimate_messages_tokens,
)
from backend.modules.compression.window import plan_window

# 压缩说明：追加在系统提示末尾，向模型声明历史已被折叠
COMPRESSION_NOTE = (
    "\n\n[Earlier conversation turns were compacted into a summary. "
    "Everything before the summary is background reference only.]"
)

# 压缩收益下限：节省比例低于该值时不提交，避免摘要冗长反而撑大上下文
MIN_SAVINGS_RATIO = 0.05


@dataclass
class CompactionResult:
    """一次压缩的完整结果。"""

    ok: bool
    reason: str
    messages: Optional[List[Dict[str, Any]]] = None
    before_tokens: int = 0
    after_tokens: int = 0
    summarized_count: int = 0
    kept_count: int = 0
    pruned_count: int = 0
    summary_deterministic: bool = False
    failure: FailureClass = FailureClass.NONE
    elapsed_seconds: float = 0.0
    # 边界与阈值的诊断信息，供界面与日志展示
    diagnostics: Dict[str, Any] = field(default_factory=dict)

    @property
    def saved_tokens(self) -> int:
        return max(0, self.before_tokens - self.after_tokens)

    @property
    def savings_ratio(self) -> float:
        if self.before_tokens <= 0:
            return 0.0
        return self.saved_tokens / self.before_tokens

    def as_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "reason": self.reason,
            "before_tokens": self.before_tokens,
            "after_tokens": self.after_tokens,
            "saved_tokens": self.saved_tokens,
            "savings_ratio": round(self.savings_ratio, 4),
            "summarized_count": self.summarized_count,
            "kept_count": self.kept_count,
            "pruned_count": self.pruned_count,
            "summary_deterministic": self.summary_deterministic,
            "failure": self.failure.value,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "diagnostics": self.diagnostics,
        }


class CompressionEngine:
    """上下文压缩引擎。"""

    def __init__(
        self,
        settings: CompactionSettings,
        *,
        provider=None,
        model: str = "",
        context_length: Optional[int] = None,
        quiet: bool = False,
        config: Any = None,
    ) -> None:
        self.settings = settings
        self.provider = provider
        self.model = model
        self.quiet = quiet
        self.compression_count = 0
        # 上一轮摘要正文：增量更新的输入，也是判别会话是否已被压缩过的依据
        self._previous_summary = ""
        self._resolution: Optional[ContextResolution] = None
        # 应用配置：用于读取用户在模型条目上填写的上下文窗口
        self._config = config
        self._windows_synced = False
        if context_length is not None:
            self._resolution = ContextResolution(int(context_length), "explicit")
        self._summarizer = Summarizer(
            provider,
            model=model,
            max_tokens=settings.summary_max_tokens,
            summary_max_chars=settings.summary_max_chars,
            input_max_chars=settings.summary_input_max_chars,
            cooldown_seconds=settings.cooldown_seconds if hasattr(settings, "cooldown_seconds") else 300.0,
            abort_on_failure=settings.abort_on_summary_failure,
        )

    # -- 解析与判据 -------------------------------------------------------

    def bind_provider(self, provider, model: str = "") -> None:
        """绑定生成摘要所用的 provider（可与会话主 provider 不同）。"""
        self.provider = provider
        if model:
            self.model = model
        self._summarizer.provider = provider
        self._summarizer.model = self.model

    def resolve_context(self, configured: Optional[int] = None, api_base: str = "") -> ContextResolution:
        """解析并缓存模型的上下文窗口。

        构造时若带了应用配置，先从模型条目同步用户填写的窗口，避免走家族兜底。
        """
        from backend.modules.compression.model_meta import (
            get_resolver,
            sync_configured_windows,
        )

        if self._config is not None and not self._windows_synced:
            count = sync_configured_windows(self._config)
            self._windows_synced = True
            if count and not self.quiet:
                logger.debug(f"已同步 {count} 个模型条目的上下文窗口")

        if self._resolution is None or configured:
            self._resolution = get_resolver().resolve(
                self.model, configured=configured, api_base=api_base
            )
        return self._resolution

    @property
    def context_length(self) -> int:
        return self.resolve_context().context_length

    @property
    def threshold_tokens(self) -> int:
        return self.settings.threshold(self.context_length, self.model)

    @property
    def tail_token_budget(self) -> int:
        return self.settings.tail_budget(self.threshold_tokens, self.context_length)

    @property
    def previous_summary(self) -> str:
        return self._previous_summary

    def should_compress(self, messages: Sequence[Dict[str, Any]], current_tokens: Optional[int] = None) -> bool:
        """是否达到压缩门槛。

        以 token 水位为主判据：条数反映不了上下文体积。条数只作兜底，防止大量短
        消息堆高结构开销。``current_tokens`` 为空时按消息估算。
        """
        if not self.settings.enabled:
            return False
        if len(messages) > max(1, self.settings.message_threshold):
            return True
        tokens = current_tokens if current_tokens is not None else estimate_messages_tokens(messages)
        return tokens > self.threshold_tokens

    def has_content_to_compress(self, messages: Sequence[Dict[str, Any]]) -> bool:
        """是否存在可摘要区段，供手动压缩跳过无谓的模型调用。"""
        plan = self._plan(messages)
        return plan.has_middle

    def reset_session(self) -> None:
        """会话重置：清除上一轮摘要与计数。"""
        self._previous_summary = ""
        self.compression_count = 0

    # -- 主流程 -----------------------------------------------------------

    def _plan(self, messages: Sequence[Dict[str, Any]]):
        return plan_window(
            messages,
            tail_budget=self.tail_token_budget,
            protect_first_n=self.settings.protect_first_n,
            protect_last_n=self.settings.protect_last_n,
            context_length=self.context_length,
        )

    async def compress(
        self,
        messages: Sequence[Dict[str, Any]],
        *,
        force: bool = False,
        focus_topic: Optional[str] = None,
        memory_context: str = "",
        current_tokens: Optional[int] = None,
    ) -> CompactionResult:
        """压缩历史。

        Args:
            messages: 完整消息列表
            force: 跳过阈值判定与冷却，供手动压缩使用
            focus_topic: 手动压缩指定的关注主题
            memory_context: 需要保留的运行时上下文
            current_tokens: 上游上报的真实 token 数，优先于估算
        """
        started = time.monotonic()
        before_tokens = current_tokens if current_tokens else estimate_messages_tokens(messages)

        if not force and not self.should_compress(messages, current_tokens):
            return CompactionResult(
                ok=False,
                reason="below_threshold",
                before_tokens=before_tokens,
                elapsed_seconds=time.monotonic() - started,
            )

        compatible = [message for message in messages if isinstance(message, dict)]

        # 阶段 1：瘦身（不调用模型）
        pruned_messages, pruned_count = prune_tool_results(
            compatible,
            protect_tail_count=self.settings.protect_last_n,
            protect_tail_tokens=self.tail_token_budget,
            context_length=self.context_length,
        )

        # 阶段 2：边界
        plan = self._plan(pruned_messages)
        if not plan.has_middle:
            return CompactionResult(
                ok=False,
                reason="no_compressible_window",
                before_tokens=before_tokens,
                pruned_count=pruned_count,
                elapsed_seconds=time.monotonic() - started,
                diagnostics={"plan": plan.as_dict()},
            )

        to_summarize = pruned_messages[plan.compress_start:plan.compress_end]

        # 阶段 3：摘要
        has_user_turn = any(
            message.get("role") == "user" and content_text(message.get("content")).strip()
            for message in compatible
        )
        outcome = await self._summarizer.summarize(
            to_summarize,
            previous_summary=self._previous_summary,
            focus_topic=focus_topic,
            memory_context=memory_context,
            has_user_turn=has_user_turn,
            bypass_cooldown=force,
        )
        if not outcome.ok or not outcome.text:
            return CompactionResult(
                ok=False,
                reason=f"summary_failed:{outcome.failure.value}",
                before_tokens=before_tokens,
                summarized_count=len(to_summarize),
                pruned_count=pruned_count,
                failure=outcome.failure,
                elapsed_seconds=time.monotonic() - started,
                diagnostics={"plan": plan.as_dict(), "summary": outcome.as_dict()},
            )

        # 阶段 4：组装
        head = assemble_head(pruned_messages, plan.compress_start, COMPRESSION_NOTE)
        tail = assemble_tail(pruned_messages, plan.compress_end)
        compressed = build_compressed(
            head, tail, outcome.text, compress_start=plan.compress_start
        )
        compressed = sanitize_tool_pairs(compressed)
        strip_persistence_markers(compressed)

        after_tokens = estimate_messages_tokens(compressed)
        if after_tokens >= before_tokens:
            # 压缩后未减小：回退原历史并记录以供观测
            return CompactionResult(
                ok=False,
                reason="no_reduction",
                before_tokens=before_tokens,
                after_tokens=after_tokens,
                summarized_count=len(to_summarize),
                kept_count=len(tail),
                pruned_count=pruned_count,
                elapsed_seconds=time.monotonic() - started,
                diagnostics={"plan": plan.as_dict(), "summary": outcome.as_dict()},
            )

        self.compression_count += 1
        self._previous_summary = outcome.text

        if not self.quiet:
            logger.info(
                "压缩完成 #%d：%d 条 → %d 条，%d → %d tokens（省 %d，%.0f%%）%s",
                self.compression_count,
                len(compatible),
                len(compressed),
                before_tokens,
                after_tokens,
                before_tokens - after_tokens,
                (before_tokens - after_tokens) / before_tokens * 100 if before_tokens else 0,
                "（确定性摘要）" if outcome.deterministic else "",
            )

        return CompactionResult(
            ok=True,
            reason="ok",
            messages=compressed,
            before_tokens=before_tokens,
            after_tokens=after_tokens,
            summarized_count=len(to_summarize),
            kept_count=len(tail) + len(head),
            pruned_count=pruned_count,
            summary_deterministic=outcome.deterministic,
            failure=outcome.failure,
            elapsed_seconds=time.monotonic() - started,
            diagnostics={"plan": plan.as_dict(), "summary": outcome.as_dict()},
        )

    def compress_sync_summary(self, messages: Sequence[Dict[str, Any]]) -> str:
        """本地生成确定性摘要，不需要模型调用。

        供无法等待模型响应、但仍需连续性载体的场景使用。
        """
        return deterministic_summary(messages, self._previous_summary)


def build_engine(
    *,
    provider=None,
    model: str = "",
    config=None,
    context_length: Optional[int] = None,
    quiet: bool = False,
) -> CompressionEngine:
    """按应用配置构造压缩引擎。

    调用方每次新建实例，使上一轮摘要随请求生命周期结束，不跨会话累积。
    """
    settings = CompactionSettings.from_config(config) if config is not None else CompactionSettings()
    return CompressionEngine(
        settings,
        provider=provider,
        model=model,
        context_length=context_length,
        quiet=quiet,
        config=config,
    )
