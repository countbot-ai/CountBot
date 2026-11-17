"""head / middle / tail 边界计算：尾部按 token 预算走查，锚点约束把切点前拉。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from backend.modules.compression.boundaries import (
    align_backward,
    align_forward,
    has_tool_calls,
    role_of,
    turn_pair_end,
)
from backend.modules.compression.tokens import estimate_message_tokens, content_text

# 尾部条数下限的硬上限，避免大量小消息撑大保护范围
MAX_TAIL_MESSAGE_FLOOR = 8
MIN_TAIL_MESSAGES = 3

# 摘要预留：为摘要正文预留空间，否则保留段加摘要仍可能超预算
SUMMARY_RESERVE_TOKENS = 2_000

# 重启后探测「已压缩过」的窗口：续接会话的头部可能带交接摘要
RESTART_HANDOFF_PROBE_EXTRA_MESSAGES = 4


@dataclass
class WindowPlan:
    """一次边界计算的结果。"""

    head_end: int
    compress_start: int
    compress_end: int
    tail_budget: int
    soft_ceiling: int
    # 走查是否因锚点被迫超出软上限（仅用于诊断）
    anchor_overflow: bool = False

    @property
    def has_middle(self) -> bool:
        return self.compress_start < self.compress_end

    @property
    def kept_count(self) -> int:
        return self.head_end + max(0, self.compress_end - self.compress_start)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "head_end": self.head_end,
            "compress_start": self.compress_start,
            "compress_end": self.compress_end,
            "tail_budget": self.tail_budget,
            "soft_ceiling": self.soft_ceiling,
            "has_middle": self.has_middle,
            "anchor_overflow": self.anchor_overflow,
        }


def count_head(messages: Sequence[Dict[str, Any]], protect_first_n: int) -> int:
    """头部保护条数：系统提示恒保护，另加配置的非系统消息条数。"""
    head = 0
    non_system = 0
    for message in messages:
        if role_of(message) == "system":
            head += 1
            continue
        if non_system < protect_first_n:
            non_system += 1
            head += 1
            continue
        break
    return head


def measure_tail(
    messages: Sequence[Dict[str, Any]],
    *,
    head_end: int,
    token_budget: int,
    min_tail: int,
    ceiling: int,
) -> Tuple[int, int]:
    """从尾部向前累计 token，返回 ``(切点, 累计量)``。

    累计量达到 ``ceiling`` 时停止，保留 ``min_tail`` 条的下限优先保证连续性。
    """
    total = len(messages)
    accumulated = 0
    cut = total
    for index in range(total - 1, head_end - 1, -1):
        tokens = estimate_message_tokens(messages[index])
        kept = total - index
        if accumulated + tokens > ceiling and kept >= min_tail:
            break
        accumulated += tokens
        cut = index
    return cut, accumulated


def _last_real_user_index(messages: Sequence[Dict[str, Any]], head_end: int) -> int:
    """最新的、承载任务的用户消息下标，找不到返回 -1。"""
    for index in range(len(messages) - 1, head_end - 1, -1):
        message = messages[index]
        if role_of(message) != "user":
            continue
        if content_has_text(message.get("content")):
            return index
    return -1


def content_has_text(content: Any) -> bool:
    """内容是否含非空文本（图片-only 的消息不算可执行用户输入）。"""
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        return any(
            isinstance(part, dict) and isinstance(part.get("text"), str) and part["text"].strip()
            for part in content
        )
    return False


def _last_assistant_index(messages: Sequence[Dict[str, Any]], head_end: int) -> int:
    """最新的、带正文的助手回复下标；无带正文的则退回最新助手消息。"""
    fallback = -1
    for index in range(len(messages) - 1, head_end - 1, -1):
        message = messages[index]
        if role_of(message) != "assistant":
            continue
        if fallback < 0:
            fallback = index
        if content_has_text(message.get("content")):
            return index
    return fallback


def _anchor_user(
    messages: Sequence[Dict[str, Any]], cut: int, head_end: int
) -> int:
    """保证最新用户消息留在尾部。

    工具组对齐可能把切点推到该消息之后；一旦被摘要，摘要前缀会指示模型只回答其后的
    消息，当前任务将静默丢失。若钳制会使该消息与其回复分离，则改为整轮推到摘要侧。
    """
    user_index = _last_real_user_index(messages, head_end)
    if user_index < 0 or user_index >= cut:
        return cut
    adjusted = max(user_index, head_end + 1)
    if adjusted > user_index:
        # 钳制会让用户消息与其回复分离：整轮一起摘要
        return max(turn_pair_end(messages, user_index), head_end + 1)
    return adjusted


def _anchor_assistant(
    messages: Sequence[Dict[str, Any]], cut: int, head_end: int, ceiling: int
) -> int:
    """保证最新助手回复留在尾部，且不因此把过量内容一起保留。

    长回合里 assistant 消息可能只带 ``tool_calls`` 而没有正文，此时「最新带正文的
    助手回复」其实是上一轮的收尾；锚定它会保留整个超限回合，使中间段塌缩为空。
    因此在锚定区段含工具调用且超出软上限时，保留走查得到的切点。
    """
    assistant_index = _last_assistant_index(messages, head_end)
    if assistant_index < 0 or assistant_index >= cut:
        return cut
    anchored = align_backward(messages, assistant_index)
    if any(has_tool_calls(messages[i]) for i in range(anchored, cut)):
        if sum(estimate_message_tokens(messages[i]) for i in range(anchored, cut)) > ceiling:
            return cut
    return max(anchored, head_end + 1)


def _is_blank_echo(messages: Sequence[Dict[str, Any]], index: int) -> bool:
    """该助手行是否为空回声：正文与紧邻的上一条用户消息相同。

    空回声是助手复述用户的产物，不构成进展；若视为可压缩内容，摘要段将只包含一次
    复述，压缩后体积反而增大。
    """
    message = messages[index]
    if role_of(message) != "assistant":
        return False
    if message.get("tool_calls"):
        return False
    text = content_text(message.get("content")).strip()
    if not text:
        return False
    probe = index - 1
    while probe >= 0:
        if role_of(messages[probe]) == "user":
            return content_text(messages[probe].get("content")).strip() == text
        probe -= 1
    return False


def drop_blank_echoes(messages: Sequence[Dict[str, Any]], head_end: int) -> set:
    """标记头部之后的空回声行，返回其下标集合。"""
    return {
        index
        for index in range(max(0, head_end), len(messages))
        if _is_blank_echo(messages, index)
    }


def _raise_past_blank_echoes(
    messages: Sequence[Dict[str, Any]], head_end: int, cut: int
) -> int:
    """把摘要段末端推过全部空回声行。

    否则可摘要内容只剩一次复述，压缩将无收益；被拒后同一水位会反复触发。
    """
    echoes = drop_blank_echoes(messages, head_end)
    if not echoes:
        return cut
    last_echo = max(echoes)
    if last_echo < cut:
        return cut
    candidate = align_forward(messages, last_echo + 1)
    # 推过空回声后必须仍有可摘要区段，否则保持原切点
    return candidate if candidate > head_end else cut


def plan_window(
    messages: Sequence[Dict[str, Any]],
    *,
    tail_budget: int,
    protect_first_n: int,
    protect_last_n: int,
    context_length: int = 0,
    allow_split_turn: bool = True,
) -> WindowPlan:
    """计算压缩窗口。

    Args:
        messages: 完整消息列表
        tail_budget: 尾部原文的 token 预算
        protect_first_n: 头部额外保护的非系统消息条数
        protect_last_n: 尾部最少保留条数（受硬上限约束）
        context_length: 上下文窗口，用于限制软上限的绝对比例
        allow_split_turn: 是否允许拆分超限的进行中轮次。手动压缩开启，使体量异常的
            当前轮仍能推进；滚动压缩关闭，只处理完整轮次

    Returns:
        :class:`WindowPlan`
    """
    total = len(messages)
    if total <= 1:
        return WindowPlan(0, 0, 0, tail_budget, tail_budget)

    soft_ceiling = int(tail_budget * 1.5)
    if context_length > 0:
        # 小窗口下超预算部分可能已占请求的可观比例，软上限不能只看倍数
        from backend.modules.compression.pruner import TAIL_MAX_CONTEXT_FRACTION

        soft_ceiling = min(soft_ceiling, int(context_length * TAIL_MAX_CONTEXT_FRACTION))
    soft_ceiling = max(soft_ceiling, tail_budget)
    head_end = align_forward(messages, count_head(messages, protect_first_n))

    available = max(0, total - head_end - 1)
    floor = min(max(MIN_TAIL_MESSAGES, protect_last_n), MAX_TAIL_MESSAGE_FLOOR, available) if available > 1 else 0

    # 条数下限有条件：软上限足以容纳下限条空消息的协议开销时不设下限，否则单条超大
    # 消息会借下限突破 token 上限；仅当软上限连下限都容不下时，连续性优先于条数。
    empty_row_cost = estimate_message_tokens({"role": "user", "content": ""})
    walk_floor = 0 if soft_ceiling >= floor * empty_row_cost else floor

    cut, accumulated = measure_tail(
        messages, head_end=head_end, token_budget=tail_budget, min_tail=floor, ceiling=soft_ceiling
    )
    # 整段都在软上限内：改用原始预算重切，保证存在值得压缩的中间段
    if cut <= head_end and 0 < accumulated <= soft_ceiling:
        cut, _ = measure_tail(
            messages, head_end=head_end, token_budget=tail_budget, min_tail=floor, ceiling=tail_budget
        )

    fallback_cut = total - floor
    # 最新一条消息必须留在尾部：它若单独超限，走查将一条都不接收
    cut = min(cut, total - max(walk_floor, 1))
    if cut <= head_end:
        cut = max(fallback_cut, head_end + 1)
    cut = align_backward(messages, cut)

    # 剔除空回声：助手行原样复述用户提问，不构成进展，且会使可摘要区段塌缩为空
    drop_blank_echoes(messages, head_end)
    cut = _raise_past_blank_echoes(messages, head_end, cut)

    overflow = False
    user_index = _last_real_user_index(messages, head_end)
    anchored_user = _anchor_user(messages, cut, head_end)
    split_turn = False
    if (
        allow_split_turn
        and anchored_user < cut
        and content_has_text(messages[user_index].get("content"))
        and estimate_message_tokens(messages[user_index]) <= soft_ceiling
        and any(has_tool_calls(messages[i]) for i in range(user_index, cut))
        and measure_tail(
            messages, head_end=anchored_user, token_budget=soft_ceiling, min_tail=0, ceiling=soft_ceiling
        )[0] > anchored_user
    ):
        # 进行中轮次单独超出软上限：保留工具组对齐的切点，使当前请求随摘要交接
        split_turn = True
        overflow = True
    else:
        cut = anchored_user

    if not split_turn:
        cut = _anchor_assistant(messages, cut, head_end, soft_ceiling)

    cut = min(total, align_forward(messages, max(cut, head_end + 1)))
    return WindowPlan(
        head_end=head_end,
        compress_start=head_end,
        compress_end=cut,
        tail_budget=tail_budget,
        soft_ceiling=soft_ceiling,
        anchor_overflow=overflow,
    )


def has_content_to_compress(
    messages: Sequence[Dict[str, Any]],
    *,
    tail_budget: int,
    protect_first_n: int,
    protect_last_n: int,
    context_length: int = 0,
) -> bool:
    """是否存在非空的可摘要区段，供手动压缩跳过无谓的模型调用。"""
    plan = plan_window(
        messages,
        tail_budget=tail_budget,
        protect_first_n=protect_first_n,
        protect_last_n=protect_last_n,
        context_length=context_length,
    )
    return plan.has_middle
