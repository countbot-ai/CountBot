"""压缩参数与阈值派生：阈值以模型上下文窗口为基准，而非固定 token 数。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

# 触发压缩的窗口比例：达到该比例即压缩，而不是等超窗失败
DEFAULT_THRESHOLD_PERCENT = 0.50

# 阈值不得超过窗口该比例：接近上限的阈值不可达，而上游会静默截断超窗请求而不报错，
# 导致会话卡死
MIN_CTX_TRIGGER_RATIO = 0.85

# 尾部预算占阈值的比例
DEFAULT_TARGET_RATIO = 0.20
TARGET_RATIO_MIN = 0.10
TARGET_RATIO_MAX = 0.80

# lean 模式：尾部按窗口比例夹取，避免大窗口模型保留过量原文
TAIL_WINDOW_RATIO = 0.025
TAIL_WINDOW_FLOOR = 10_000
TAIL_WINDOW_CEILING = 25_000

# 保护窗口：系统提示恒保护，另加固定条数的头部非系统消息
DEFAULT_PROTECT_FIRST_N = 3
DEFAULT_PROTECT_LAST_N = 20

# 条数兜底阈值：大量短消息堆高结构开销时，token 尚未超限也需压缩
DEFAULT_MESSAGE_THRESHOLD = 15

# 摘要失败后的冷却阶梯（秒）：逐次加倍并封顶，避免反复为同一失败路径付费
TIMEOUT_COOLDOWN_LADDER = (60, 300, 900)

# 连续超载达到该次数后中止，而非持续回退到确定性摘要
CONSECUTIVE_OVERLOAD_ABORT_ESCALATION = 3

# 保护头部在首次压缩后失效：否则早期轮次会被反复保护而固化成永久开销
PROTECT_FIRST_DECAY_AFTER_COMPRESSIONS = 1


@dataclass(frozen=True)
class CompactionSettings:
    """一次压缩行为的全部可调参数。"""

    enabled: bool = True
    threshold_percent: float = DEFAULT_THRESHOLD_PERCENT
    threshold_tokens: Optional[int] = None
    # 尾部原文预算占阈值的比例（legacy 模式）
    target_ratio: float = DEFAULT_TARGET_RATIO
    protect_first_n: int = DEFAULT_PROTECT_FIRST_N
    protect_last_n: int = DEFAULT_PROTECT_LAST_N
    tail_mode: str = "lean"
    min_tail_user_messages: int = 1
    # 摘要重试轮数：部分会话因工具 schema 不可压缩而需要多轮
    max_attempts: int = 3
    # 主动瘦身触发（token）：0 表示关闭
    proactive_prune_tokens: int = 0
    proactive_prune_min_result_chars: int = 8_000
    proactive_prune_min_reclaim_tokens: int = 4_096
    summary_max_chars: int = 8_000
    summary_max_tokens: int = 2_000
    summary_input_max_chars: int = 160_000
    message_threshold: int = DEFAULT_MESSAGE_THRESHOLD
    abort_on_summary_failure: bool = False
    # 按模型名子串覆盖阈值比例（最长匹配优先）
    model_thresholds: Mapping[str, float] = field(default_factory=dict)

    def context_length_default(self) -> int:
        """未解析到窗口时使用的兜底值。"""
        from backend.modules.compression.model_meta import DEFAULT_CONTEXT_LENGTH

        return DEFAULT_CONTEXT_LENGTH

    def threshold(self, context_length: int, model: str = "") -> int:
        """压缩触发阈值：比例值与绝对上限取较小者，并受窗口上限约束。"""
        percent = self.threshold_percent
        overridden = self.model_threshold_percent(model)
        if overridden is not None:
            percent = overridden
        ratio_value = int(context_length * percent)
        value = ratio_value
        if self.threshold_tokens and self.threshold_tokens > 0:
            value = min(ratio_value, int(self.threshold_tokens))
        if context_length > 0:
            # 阈值不可达或超出窗口时回退到窗口内的安全值
            trigger_cap = int(context_length * MIN_CTX_TRIGGER_RATIO)
            if value >= context_length:
                value = max(1, min(trigger_cap, context_length - 1))
        return max(1, value)

    def model_threshold_percent(self, model: str) -> Optional[float]:
        """按模型名子串覆盖阈值比例，最长匹配优先。"""
        name = (model or "").strip().lower()
        if not name or not self.model_thresholds:
            return None
        matches = [
            (str(key), float(value))
            for key, value in self.model_thresholds.items()
            if str(key).lower() in name
        ]
        if not matches:
            return None
        matches.sort(key=lambda item: len(item[0]), reverse=True)
        return matches[0][1]

    def tail_budget(self, threshold: int, context_length: int) -> int:
        """尾部原文的 token 预算。"""
        if self.tail_mode == "lean":
            window_value = int(context_length * TAIL_WINDOW_RATIO)
            return max(TAIL_WINDOW_FLOOR, min(window_value, TAIL_WINDOW_CEILING))
        ratio = min(max(self.target_ratio, TARGET_RATIO_MIN), TARGET_RATIO_MAX)
        return max(1, int(threshold * ratio))

    def summary_budget(self, threshold: int) -> int:
        """摘要正文的 token 预算：按阈值比例计算并设下限与上限。"""
        from backend.modules.compression.engine_prompt import (
            MIN_SUMMARY_TOKENS,
            SUMMARY_RATIO,
            SUMMARY_TOKENS_CEILING,
        )

        budget = max(MIN_SUMMARY_TOKENS, int(threshold * SUMMARY_RATIO))
        return min(budget, SUMMARY_TOKENS_CEILING)

    def cooldown_for_attempt(self, consecutive_failures: int) -> float:
        """按连续失败次数取冷却时长。"""
        index = min(max(0, consecutive_failures - 1), len(TIMEOUT_COOLDOWN_LADDER) - 1)
        return float(TIMEOUT_COOLDOWN_LADDER[index])

    @classmethod
    def from_config(cls, config: Any) -> "CompactionSettings":
        """从应用配置构造，缺失或非法项用默认值。

        压缩参数错误不应阻塞会话处理，因此整体回退而非抛错。
        """
        raw = getattr(config, "compaction", None)
        if raw is None:
            return cls()

        def pick(name: str, default: Any, cast) -> Any:
            value = getattr(raw, name, None)
            if value is None:
                return default
            try:
                return cast(value)
            except (TypeError, ValueError):
                return default

        return cls(
            enabled=pick("enabled", True, bool),
            threshold_percent=pick("threshold_percent", DEFAULT_THRESHOLD_PERCENT, float),
            threshold_tokens=pick("threshold_tokens", None, int),
            target_ratio=pick("target_ratio", DEFAULT_TARGET_RATIO, float),
            protect_first_n=pick("protect_first_n", DEFAULT_PROTECT_FIRST_N, int),
            protect_last_n=pick("protect_last_n", DEFAULT_PROTECT_LAST_N, int),
            tail_mode=pick("tail_mode", "lean", str),
            min_tail_user_messages=pick("min_tail_user_messages", 1, int),
            max_attempts=pick("max_attempts", 3, int),
            proactive_prune_tokens=pick("proactive_prune_tokens", 0, int),
            proactive_prune_min_result_chars=pick("proactive_prune_min_result_chars", 8_000, int),
            proactive_prune_min_reclaim_tokens=pick("proactive_prune_min_reclaim_tokens", 4_096, int),
            summary_max_chars=pick("summary_max_chars", 8_000, int),
            summary_max_tokens=pick("summary_max_tokens", 2_000, int),
            summary_input_max_chars=pick("summary_input_max_chars", 160_000, int),
            message_threshold=pick("message_threshold", DEFAULT_MESSAGE_THRESHOLD, int),
            abort_on_summary_failure=pick("abort_on_summary_failure", False, bool),
            model_thresholds=pick("model_thresholds", {}, dict),
        )
