"""摘要生成与失败分类：可重试失败按冷却阶梯重试，终态失败降级为确定性摘要。"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence

from loguru import logger

from backend.modules.compression.engine_prompt import (
    COMPRESSED_SUMMARY_HAS_USER_TURN_KEY,
    FALLBACK_SUMMARY_MAX_CHARS,
    NO_USER_TASK_SENTINEL,
    build_summary_prompt,
    render_for_summary,
    strip_summary_prefix,
    summary_template,
    with_summary_prefix,
)
from backend.modules.compression.marker import elide
from backend.modules.compression.pruner import tool_calls_by_id
from backend.modules.compression.summary_stub import summarize_tool_result
from backend.modules.compression.tokens import content_text, estimate_tokens

# 由压缩自身写入的合成用户行，不参与诉求提取
_SYNTHETIC_USER_PREFIXES = (
    "[CONTEXT COMPACTION",
    "[CONTEXT SUMMARY]",
)

# 确定性摘要保留的最近轮次条数
_LAST_TURNS_LIMIT = 8

# 摘要输入中单条记录上限，避免超长工具输出挤占输入预算
RECORD_MAX_CHARS = 2_000

# 终态失败标记：命中即降级，不重试
_TERMINAL_MARKERS: Dict[str, tuple] = {
    "access_or_quota": (
        "insufficient_quota",
        "quota exceeded",
        "out of funds",
        "out of credits",
        "exceeded your current quota",
        "billing",
        "payment required",
        "http 402",
    ),
    "missing_credential": (
        "invalid api key",
        "incorrect api key",
        "authentication",
        "unauthorized",
        "http 401",
        "http 403",
        "no api key",
    ),
}

# 可重试标记：命中后按冷却阶梯重试
_RETRYABLE_MARKERS = (
    "timeout",
    "timed out",
    "read timeout",
    "connection reset",
    "connection aborted",
    "temporarily unavailable",
    "overloaded",
    "rate limit",
    "http 429",
    "http 500",
    "http 502",
    "http 503",
    "http 504",
)

# 截断标记：输出达上限被截断，摘要不完整
TRUNCATED_MARKER = "finish_reason=length"

# 模型附加的前言式前缀，需剥离以免污染注入文本
_PREAMBLE_RE = re.compile(r"^(here is|以下是|下面是)[^\n:：]*[:：]\s*", re.IGNORECASE)


class FailureClass(str, Enum):
    """摘要失败分类。"""

    NONE = "none"
    TIMEOUT = "timeout"
    OVERLOAD = "overload"
    ACCESS_OR_QUOTA = "access_or_quota"
    MISSING_CREDENTIAL = "missing_credential"
    EMPTY_SUMMARY = "empty_summary"
    SUMMARY_TOO_LONG = "summary_too_long"
    TRUNCATED = "truncated"
    UNKNOWN = "unknown"

    @property
    def retryable(self) -> bool:
        return self in (FailureClass.TIMEOUT, FailureClass.OVERLOAD, FailureClass.UNKNOWN)

    @property
    def terminal(self) -> bool:
        return self in (
            FailureClass.ACCESS_OR_QUOTA,
            FailureClass.MISSING_CREDENTIAL,
        )


def classify_failure(error: Optional[BaseException], message: str = "") -> FailureClass:
    """按异常文本与消息内容分类失败。"""
    text = f"{message} {error}" if error else message
    lowered = text.lower()
    for name, markers in _TERMINAL_MARKERS.items():
        if any(marker in lowered for marker in markers):
            return FailureClass(name)
    if TRUNCATED_MARKER in text:
        return FailureClass.TRUNCATED
    if any(marker in lowered for marker in ("overloaded", "rate limit")) or "http 429" in lowered:
        return FailureClass.OVERLOAD
    if any(marker in lowered for marker in _RETRYABLE_MARKERS):
        return FailureClass.TIMEOUT
    return FailureClass.UNKNOWN


@dataclass
class SummaryOutcome:
    """一次摘要请求的结果。"""

    text: Optional[str]
    ok: bool
    failure: FailureClass = FailureClass.NONE
    deterministic: bool = False
    # 输出是否被长度上限截断：仍可用但不完整
    truncated: bool = False
    # 实际耗时（秒）
    elapsed_seconds: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "failure": self.failure.value,
            "deterministic": self.deterministic,
            "truncated": self.truncated,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
        }


def deterministic_summary(
    messages: Sequence[Dict[str, Any]], previous_summary: str = ""
) -> str:
    """不调用模型的结构化摘要，在摘要服务不可用时保留历史轮廓。"""
    user_asks: List[str] = []
    actions: List[str] = []
    relevant_files: List[str] = []
    blockers: List[str] = []
    last_turns: List[str] = []
    call_index = tool_calls_by_id(messages)
    path_re = re.compile(r"[\w./-]*[/\\][\w./\\-]+")

    for message in messages:
        role = str(message.get("role") or "unknown")
        raw = content_text(message.get("content")).strip()
        if path_re.findall(raw):
            for found in path_re.findall(raw)[:3]:
                if found not in relevant_files:
                    relevant_files.append(found)
        tool_names = [
            (call.get("function") or {}).get("name") or call.get("name")
            for call in (message.get("tool_calls") or [])
            if isinstance(call, dict)
        ]
        tool_names = [str(name) for name in tool_names if name]

        text = raw[:600] if len(raw) > 600 else raw
        if text.strip():
            label = "INTERNAL CONTEXT" if _is_synthetic_user(role, raw) else role.upper()
            entry = f"{label}: {text.strip()}"
            if tool_names:
                entry = f"tool calls: {', '.join(tool_names[:6])}; {entry}"
            last_turns.append(entry)
            del last_turns[:-_LAST_TURNS_LIMIT]

        if role == "user" and text.strip() and not _is_synthetic_user(role, raw):
            user_asks.append(text.strip())
        elif role == "assistant":
            if tool_names:
                actions.append("Called tool(s): " + ", ".join(tool_names[:6]))
            elif text.strip():
                actions.append(text.strip())
        elif role == "tool":
            tool_name, tool_args = call_index.get(
                str(message.get("tool_call_id") or ""), ("unknown", "")
            )
            actions.append(summarize_tool_result(tool_name, tool_args, text or ""))
            if re.search(
                r"\b(error|failed|exception|traceback|timeout|timed out|fatal)\b",
                text or "",
                re.IGNORECASE,
            ):
                blockers.append(text[:500])

    active_task = f"User asked: {user_asks[-1]!r}" if user_asks else NO_USER_TASK_SENTINEL
    previous_note = ""
    if previous_summary:
        bounded = elide(previous_summary.strip(), 3_000)
        previous_note = (
            "\n\n## Previous Summary Snapshot\n"
            f"{bounded}\n\n"
            "The previous compaction summary above remains background continuity context "
            "because the latest LLM summary update failed."
        )

    body = f"""## Historical Task Snapshot
{active_task}

## Goal
Recovered from a deterministic fallback because the LLM context summarizer was unavailable. Continue from the protected recent messages after this summary and use current file and system state for exact details.{previous_note}

## Constraints & Preferences
- This fallback was generated locally without an LLM summary call.
- Secrets and credentials were redacted before preservation.
- The summary may be incomplete; prefer verifying current files, git state, processes, and test results instead of assuming omitted details.

## Completed Actions
{chr(10).join(f"{i}. {item}" for i, item in enumerate(actions[:12], start=1)) if actions else "None recoverable from compacted turns."}

## Active State
Unknown from deterministic fallback. Inspect current repository or session state if needed.

## Blocked
{_bullets(blockers, limit=5)}

## Key Decisions
None recoverable from deterministic fallback.

## Resolved Questions
None recoverable from deterministic fallback.

## Relevant Files
{_bullets(relevant_files, limit=12)}

## Last Dropped Turns
{_bullets(last_turns, limit=_LAST_TURNS_LIMIT)}

## Critical Context
Summary generation was unavailable, so this is a best-effort deterministic fallback for {len(messages)} compacted message(s)."""

    return elide(with_summary_prefix(body.strip()), FALLBACK_SUMMARY_MAX_CHARS)


def _is_synthetic_user(role: str, raw: str) -> bool:
    if role != "user":
        return False
    return any(raw.startswith(prefix) for prefix in _SYNTHETIC_USER_PREFIXES)


def _bullets(items: Sequence[str], limit: int) -> str:
    if not items:
        return "None."
    return "\n".join(f"- {item}" for item in items[:limit])


class Summarizer:
    """摘要生成器：模型优先，失败分类后可重试，终态失败降级为确定性摘要。"""

    def __init__(
        self,
        provider,
        *,
        model: str = "",
        max_tokens: int = 2_000,
        summary_max_chars: int = 8_000,
        input_max_chars: int = 160_000,
        cooldown_seconds: float = 300.0,
        abort_on_failure: bool = False,
    ) -> None:
        self.provider = provider
        self.model = model
        self.max_tokens = max_tokens
        self.summary_max_chars = summary_max_chars
        self.input_max_chars = input_max_chars
        self.cooldown_seconds = cooldown_seconds
        self.abort_on_failure = abort_on_failure
        self.last_failure = FailureClass.NONE
        self.consecutive_failures = 0
        self._cooldown_until = 0.0

    @property
    def in_cooldown(self) -> bool:
        return time.monotonic() < self._cooldown_until

    def clear_cooldown(self) -> None:
        """清除冷却，供手动压缩立即重试。"""
        self._cooldown_until = 0.0
        self.consecutive_failures = 0

    def _arm_cooldown(self, seconds: float) -> None:
        self._cooldown_until = time.monotonic() + max(0.0, seconds)

    async def summarize(
        self,
        messages: Sequence[Dict[str, Any]],
        *,
        previous_summary: str = "",
        focus_topic: Optional[str] = None,
        memory_context: str = "",
        has_user_turn: bool = True,
        bypass_cooldown: bool = False,
    ) -> SummaryOutcome:
        """生成摘要。

        调用失败时依分类决定返回确定性摘要还是放弃（``ok=False``，由调用方沿用原历史）。
        """
        if self.provider is None:
            return SummaryOutcome(deterministic_summary(messages, previous_summary), True, deterministic=True)

        if self.in_cooldown and not bypass_cooldown:
            # 冷却期内不重复调用模型，避免为同一失败路径重复付费
            return SummaryOutcome(
                deterministic_summary(messages, previous_summary),
                True,
                FailureClass.UNKNOWN,
                deterministic=True,
            )

        prompt = build_summary_prompt(
            self._bound_input(render_for_summary(messages)),
            previous_summary=strip_summary_prefix(previous_summary),
            focus_topic=focus_topic,
            memory_context=memory_context,
            has_user_turn=has_user_turn,
        )

        started = time.monotonic()
        summary, finish_reason, error = await self._stream_summary(prompt, self.max_tokens)

        # 推理型模型可能耗尽固定输出预算，致正文为空或截断：以不限长度重试一次
        if error is None and (not summary or "length" in finish_reason.lower()):
            retry_summary, retry_finish, retry_error = await self._stream_summary(prompt, 0)
            if retry_error is None and retry_summary and len(retry_summary) >= len(summary):
                summary, finish_reason, error = retry_summary, retry_finish, None

        if error is not None:
            exc = error
            elapsed = time.monotonic() - started
            failure = classify_failure(exc)
            self.last_failure = failure
            self.consecutive_failures += 1
            if failure.retryable:
                from backend.modules.compression.settings import TIMEOUT_COOLDOWN_LADDER

                index = min(self.consecutive_failures - 1, len(TIMEOUT_COOLDOWN_LADDER) - 1)
                self._arm_cooldown(float(TIMEOUT_COOLDOWN_LADDER[index]))
            else:
                self._arm_cooldown(self.cooldown_seconds)
            logger.warning(f"摘要生成失败（{failure.value}）：{exc}")
            if failure.terminal and self.abort_on_failure:
                return SummaryOutcome(None, False, failure, elapsed_seconds=elapsed)
            return SummaryOutcome(
                deterministic_summary(messages, previous_summary),
                True,
                failure,
                deterministic=True,
                elapsed_seconds=elapsed,
            )

        elapsed = time.monotonic() - started
        summary = _PREAMBLE_RE.sub("", summary.strip())

        if not summary:
            self.last_failure = FailureClass.EMPTY_SUMMARY
            self.consecutive_failures += 1
            self._arm_cooldown(self.cooldown_seconds)
            return SummaryOutcome(
                deterministic_summary(messages, previous_summary),
                True,
                FailureClass.EMPTY_SUMMARY,
                deterministic=True,
                elapsed_seconds=elapsed,
            )

        if "length" in finish_reason.lower():
            self.last_failure = FailureClass.TRUNCATED
            self.consecutive_failures += 1
            self._arm_cooldown(self.cooldown_seconds)
            # 截断摘要字段基本完整，优于确定性回退；仅内容过短时放弃
            if len(summary) >= self.summary_max_chars * 0.3:
                return SummaryOutcome(
                    summary, True, FailureClass.TRUNCATED,
                    truncated=True, elapsed_seconds=elapsed,
                )
            return SummaryOutcome(
                deterministic_summary(messages, previous_summary),
                True,
                FailureClass.TRUNCATED,
                deterministic=True,
                truncated=True,
                elapsed_seconds=elapsed,
            )

        if len(summary) > self.summary_max_chars:
            # 模型未遵守长度约束：追加更严格限制后重试一次；大历史下超长属常态
            shrunk = prompt + (
                "\n\nSTRICT LIMIT: Output at most "
                f"{self.summary_max_chars // 2} characters. "
                "Compress each section to bullet phrases; drop any detail not needed to continue the work."
            )
            retry_summary, retry_finish, retry_error = await self._stream_summary(shrunk, 0)
            if retry_error is None:
                retry_summary = _PREAMBLE_RE.sub("", retry_summary.strip())
                if retry_summary and len(retry_summary) <= self.summary_max_chars:
                    self.last_failure = FailureClass.NONE
                    self.consecutive_failures = 0
                    self._cooldown_until = 0.0
                    return SummaryOutcome(
                        retry_summary,
                        True,
                        FailureClass.NONE,
                        truncated="length" in retry_finish.lower(),
                        elapsed_seconds=time.monotonic() - started,
                    )
            # 收窄后仍超长：摘要不可用，放弃本次压缩
            self.last_failure = FailureClass.SUMMARY_TOO_LONG
            self.consecutive_failures += 1
            self._arm_cooldown(self.cooldown_seconds)
            return SummaryOutcome(
                None, False, FailureClass.SUMMARY_TOO_LONG, elapsed_seconds=elapsed
            )

        self.last_failure = FailureClass.NONE
        self.consecutive_failures = 0
        self._cooldown_until = 0.0
        return SummaryOutcome(summary, True, elapsed_seconds=elapsed)

    async def _stream_summary(
        self, prompt: str, max_tokens: int
    ) -> tuple:
        """执行一次摘要流式调用，返回 ``(正文, finish_reason, 异常)``。

        ``max_tokens`` 为 0 表示不限输出长度：推理型模型会耗尽固定预算，导致正文
        为空或截断。
        """
        chunks: List[str] = []
        finish_reason = ""
        try:
            kwargs = {} if max_tokens <= 0 else {"max_tokens": max_tokens}
            async for chunk in self.provider.chat_stream(
                messages=[{"role": "user", "content": prompt}],
                tools=None,
                model=self.model or None,
                **kwargs,
            ):
                if getattr(chunk, "is_content", False) and chunk.content:
                    chunks.append(chunk.content)
                reason = getattr(chunk, "finish_reason", None)
                if reason:
                    finish_reason = str(reason)
        except Exception as exc:  # noqa: BLE001 - 失败分类需要原始异常
            return "", finish_reason, exc
        return "".join(chunks), finish_reason, None

    def _bound_input(self, rendered: str) -> str:
        """限制摘要输入长度；超长时保留尾部，较早细节通常已被后续轮次覆盖。"""
        if len(rendered) <= self.input_max_chars:
            return rendered
        return "…(earlier messages omitted)\n" + rendered[-self.input_max_chars:]


def build_summary_metadata(has_user_turn: bool) -> Dict[str, Any]:
    """压缩后写在消息上的标记，供前端识别摘要行。"""
    return {
        "COMPRESSED_SUMMARY_METADATA_KEY": True,
        COMPRESSED_SUMMARY_HAS_USER_TURN_KEY: bool(has_user_turn),
    }
