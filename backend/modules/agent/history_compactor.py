"""会话历史压缩。

把过长的历史折叠成一条摘要加最近若干条原文，控制单次请求的上下文长度。

切点有硬性约束：工具调用成对出现（assistant 的 tool_calls 与随后的
tool 结果），切在中间会产生孤儿 tool_calls，多数上游返回 400。切点只能
落在 user 或 assistant 消息上，同一批工具结果不能拆开。

本模块不关心调用方是哪个渠道。
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from loguru import logger

# 摘要提示词：强调保留可复用的硬事实，避免摘要变成无信息量的复述
SUMMARY_SYSTEM_PROMPT = (
    "You compress a conversation into a compact brief for another assistant that "
    "will continue the same task.\n"
    "Keep exact names, file paths, commands, numbers, error messages and decisions. "
    "Drop greetings, filler and repeated restatements.\n"
    "Write in the language used by the conversation. Output only the brief, "
    "as short structured notes."
)


# ---------------------------------------------------------------------------
# token 估算
# ---------------------------------------------------------------------------


def estimate_tokens(text: str) -> int:
    """粗略估算一段文本的 token 数。

    不引入分词器，各供应商分词不同且加载重。CJK 字符按 1:1、其余按
    4:1 估算，中英混排误差约 ±20%，用于压缩触发的量级判断；计费以
    供应商上报为准。
    """
    if not text:
        return 0
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    non_cjk = len(text) - cjk
    return cjk + non_cjk // 4


def estimate_messages_tokens(messages: Sequence[Dict]) -> int:
    """估算整段历史的 token 数，含每条消息的结构开销。"""
    total = 0
    for message in messages:
        content = message.get("content")
        if isinstance(content, list):
            # 多模态：只统计文本块
            content = " ".join(
                str(item.get("text") or "")
                for item in content
                if isinstance(item, dict)
            )
        total += estimate_tokens(str(content or ""))
        # role、分隔符与 tool_calls 结构开销
        total += 4
        calls = message.get("tool_calls")
        if calls:
            for call in calls:
                function = (call or {}).get("function") or {}
                total += estimate_tokens(str(function.get("name") or ""))
                total += estimate_tokens(str(function.get("arguments") or ""))
                total += 4
    return total


@dataclass
class CompactionResult:
    """一次压缩的完整结果，含成败、原因与前后 token 数。

    compress() 把所有失败都压成一个 None，调用方无法区分未达阈值、
    摘要失败还是压缩无效；需要区分时用 compress_with_detail()。
    """

    ok: bool
    reason: str
    before_tokens: int = 0
    after_tokens: int = 0
    summarized_count: int = 0
    kept_count: int = 0
    messages: Optional[List[Dict]] = field(default=None)

    @property
    def saved_tokens(self) -> int:
        return max(0, self.before_tokens - self.after_tokens)

    def as_dict(self) -> Dict:
        """供日志与接口序列化使用。"""
        return {
            "ok": self.ok,
            "reason": self.reason,
            "before_tokens": self.before_tokens,
            "after_tokens": self.after_tokens,
            "saved_tokens": self.saved_tokens,
            "summarized_count": self.summarized_count,
            "kept_count": self.kept_count,
        }


def _is_tool_message(message: Dict) -> bool:
    """是否工具结果消息。"""
    return str(message.get("role") or "") == "tool"


def _has_tool_calls(message: Dict) -> bool:
    """该消息是否携带工具调用。"""
    return bool(message.get("tool_calls"))


def is_safe_cut_point(messages: Sequence[Dict], index: int) -> bool:
    """判断在 ``index`` 处切分是否安全。

    安全意味着：``messages[index:]`` 作为保留部分时，不会以工具结果或工具调用
    的中间位置开头。

    Args:
        messages: 完整消息列表
        index: 候选切分位置，表示保留 messages[index:]

    Returns:
        可安全切分返回 True
    """
    if index <= 0 or index >= len(messages):
        return True

    head = messages[index]
    role = str(head.get("role") or "")

    # 保留段不能以工具结果开头：它的 tool_call 会在被摘要掉的部分里
    if role == "tool":
        return False

    # 前一条若是带 tool_calls 的 assistant，说明这批工具结果还没结束
    previous = messages[index - 1]
    if _has_tool_calls(previous) and _is_tool_message(head):
        return False

    return True


def find_cut_index(
    messages: Sequence[Dict],
    min_keep_recent: int,
) -> int:
    """从尾部反向推进，找出既满足保留条数又落在安全边界的切点。

    找不到安全切点时返回 0，表示「不压缩」——宁可不压，也不产生非法请求。

    Args:
        messages: 完整消息列表
        min_keep_recent: 至少保留的最近消息条数。为避开工具调用对，
            实际保留可能少于此值；全局找不到安全切点时不压缩。

    Returns:
        切分位置（保留 messages[cut:]）
    """
    total = len(messages)
    if total == 0:
        return 0

    desired = max(1, min(min_keep_recent, total))
    candidate = total - desired

    # 从候选位置向后找最近的合法切点（保留更少原文，换取消息合法）
    for index in range(candidate, total):
        if is_safe_cut_point(messages, index):
            return index

    # 向后找不到，再向前找（保留更多原文）
    for index in range(candidate - 1, 0, -1):
        if is_safe_cut_point(messages, index):
            return index

    return 0


def split_for_summary(
    messages: Sequence[Dict],
    min_keep_recent: int,
) -> Tuple[List[Dict], List[Dict]]:
    """把历史切成「待摘要部分」和「保留原文部分」。

    Returns:
        (to_summarize, to_keep)；无法安全切分时返回 (空列表, 全部消息)
    """
    cut = find_cut_index(messages, min_keep_recent)
    if cut <= 0:
        return [], list(messages)
    return list(messages[:cut]), list(messages[cut:])


def should_compress(
    messages: Sequence[Dict],
    threshold: int = 15,
    *,
    token_threshold: Optional[int] = None,
) -> bool:
    """是否达到压缩门槛。

    以 token 水位为主判据：条数反映不了上下文体积，一条长日志和一百条
    短对话是两个量级。条数只作兜底，防止大量短消息堆高结构开销。

    Args:
        messages: 历史消息
        threshold: 条数兜底阈值
        token_threshold: token 阈值；为 None 时只看条数（保持旧行为兼容）
    """
    if len(messages) > max(1, threshold):
        return True
    if token_threshold is not None and token_threshold > 0:
        return estimate_messages_tokens(messages) > token_threshold
    return False


def _render_message_for_summary(message: Dict) -> str:
    """把单条消息渲染成摘要输入的一行文本。"""
    role = str(message.get("role") or "unknown")
    content = message.get("content")

    if isinstance(content, list):
        # 多模态内容只取文本片段，避免把 base64 塞进摘要请求
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
        content = "\n".join(parts)

    text = str(content or "").strip()

    tool_calls = message.get("tool_calls")
    if tool_calls:
        names = []
        for call in tool_calls:
            if isinstance(call, dict):
                function = call.get("function") or {}
                name = function.get("name") or call.get("name")
                if name:
                    names.append(str(name))
        if names:
            suffix = f"[tool calls: {', '.join(names)}]"
            text = f"{text}\n{suffix}" if text else suffix

    # 单条消息限长，避免某条超长输出挤占整个摘要预算
    if len(text) > 2000:
        text = text[:2000] + "…"
    return f"{role}: {text}"


class HistoryCompactor:
    """历史压缩器：负责切分与摘要生成。"""

    def __init__(
        self,
        provider,
        *,
        min_keep_recent: int = 10,
        threshold: int = 15,
        char_limit: int = 12000,
        max_tokens: int = 800,
        summary_max_chars: int = 4000,
        token_threshold: Optional[int] = 80_000,
    ) -> None:
        self.provider = provider
        self.min_keep_recent = min_keep_recent
        self.threshold = threshold
        self.char_limit = char_limit
        self.max_tokens = max_tokens
        # 摘要超过上限说明模型没按简短要求输出，这次结果不可用
        self.summary_max_chars = summary_max_chars
        # token 水位阈值：判据主口径，条数仅作兜底
        self.token_threshold = token_threshold

    def should_compress(self, messages: Sequence[Dict]) -> bool:
        """是否达到压缩门槛（token 为主，条数为辅）。"""
        return should_compress(
            messages, self.threshold, token_threshold=self.token_threshold
        )

    def plan(self, messages: Sequence[Dict]) -> Tuple[List[Dict], List[Dict]]:
        """计算切分方案。"""
        return split_for_summary(messages, self.min_keep_recent)

    async def compress_with_detail(
        self, messages: Sequence[Dict]
    ) -> CompactionResult:
        """压缩历史并返回结构化结果。

        compress() 把所有失败都压成一个 None；这里保留原因与前后 token，
        供调用方记录指标或决定重试。
        """
        before_tokens = estimate_messages_tokens(messages)

        if not self.should_compress(messages):
            return CompactionResult(
                ok=False, reason="below_threshold", before_tokens=before_tokens
            )

        to_summarize, to_keep = self.plan(messages)
        if not to_summarize:
            logger.info("History compression skipped: no safe cut point found")
            return CompactionResult(
                ok=False, reason="no_safe_cut_point", before_tokens=before_tokens
            )

        summary = await self._summarize(to_summarize)
        if not summary:
            return CompactionResult(
                ok=False, reason="summary_failed", before_tokens=before_tokens
            )

        # 摘要本身必须有上限：模型偶尔不遵守「简短」指令，输出比原文还长，
        # 那样压缩不但没缩短上下文，反而更长。超限说明该次摘要不可用，
        # 直接放弃压缩，让调用方沿用原始历史。
        if len(summary) > self.summary_max_chars:
            logger.warning(
                "Compaction summary too long "
                f"({len(summary)} > {self.summary_max_chars} chars); skipping"
            )
            return CompactionResult(
                ok=False,
                reason="summary_too_long",
                before_tokens=before_tokens,
                summarized_count=len(to_summarize),
            )

        compacted = [
            {
                "role": "system",
                "content": f"## Previous Conversation Summary\n\n{summary}",
            }
        ] + to_keep

        after_tokens = estimate_messages_tokens(compacted)

        # 压缩后反而更长（摘要本身很啰嗦）时明确标记，便于统计发现
        if after_tokens >= before_tokens:
            logger.warning(
                "Compaction did not reduce tokens "
                f"({before_tokens} -> {after_tokens}); keeping original"
            )
            return CompactionResult(
                ok=False,
                reason="no_reduction",
                before_tokens=before_tokens,
                after_tokens=after_tokens,
                summarized_count=len(to_summarize),
                kept_count=len(to_keep),
            )

        return CompactionResult(
            ok=True,
            reason="ok",
            before_tokens=before_tokens,
            after_tokens=after_tokens,
            summarized_count=len(to_summarize),
            kept_count=len(to_keep),
            messages=compacted,
        )

    async def compress(self, messages: Sequence[Dict]) -> Optional[List[Dict]]:
        """压缩历史；无需压缩或失败时返回 None，由调用方沿用原始历史。

        保留该签名以兼容既有调用方；需要区分失败原因时用
        :meth:`compress_with_detail`。
        """
        result = await self.compress_with_detail(messages)
        return result.messages if result.ok else None

    async def _summarize(self, messages: Sequence[Dict]) -> Optional[str]:
        """调用模型生成摘要。"""
        if self.provider is None:
            return None

        rendered = "\n".join(
            _render_message_for_summary(message) for message in messages
        )
        if len(rendered) > self.char_limit:
            # 超长时保留尾部：较早的细节通常已被后续消息覆盖
            rendered = "…(earlier messages omitted)\n" + rendered[-self.char_limit:]

        try:
            chunks: List[str] = []
            async for chunk in self.provider.chat_stream(
                messages=[
                    {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            "Summarize the conversation below into a compact brief.\n\n"
                            f"{rendered}"
                        ),
                    },
                ],
                tools=None,
                max_tokens=self.max_tokens,
            ):
                if getattr(chunk, "is_content", False) and chunk.content:
                    chunks.append(chunk.content)
            summary = "".join(chunks).strip()
            return self._strip_preamble(summary) or None
        except Exception as exc:
            logger.warning(f"Failed to summarize history: {exc}")
            return None

    @staticmethod
    def _strip_preamble(summary: str) -> str:
        """去掉模型偶尔加上的「以下是摘要」类前缀，避免污染注入文本。"""
        if not summary:
            return ""
        cleaned = re.sub(
            r"^(here is|以下是|下面是)[^\n:：]*[:：]\s*",
            "",
            summary,
            flags=re.IGNORECASE,
        )
        return cleaned.strip()
