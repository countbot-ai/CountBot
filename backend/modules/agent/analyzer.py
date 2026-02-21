"""Message Analyzer - 对话分析工具

提供对话消息的基础分析能力:
- 格式化消息为文本（用于 LLM 总结）
- 判断是否需要总结
- 分割消息（要总结的 vs 要保留的）
"""

from loguru import logger


class MessageAnalyzer:
    """对话消息分析器"""

    # 短消息无意义词过滤前缀（长度 ≤ 8 且匹配时跳过）
    _SKIP_PREFIXES = (
        "好的", "知道了", "明白", "收到", "谢谢", "好", "行",
        "嗯", "哦", "ok", "OK", "Ok", "嗯嗯", "哦哦", "好好",
        "了解", "可以", "没问题", "对", "是的", "没错", "确实",
        "哈哈", "呵呵", "嘻嘻", "666", "👍", "🙏", "感谢",
        "thanks", "thx", "yes", "no", "yep", "nope", "sure",
        "got it", "noted", "fine", "cool", "nice",
    )

    def format_messages_for_summary(
        self,
        messages: list[dict],
        max_chars: int = 4000,
    ) -> str:
        """将消息列表格式化为文本，用于 LLM 总结

        Args:
            messages: 消息列表
            max_chars: 最大字符数

        Returns:
            str: 格式化的对话文本
        """
        lines = []
        total_chars = 0

        for msg in messages:
            role = msg.get("role", "unknown").upper()
            content = msg.get("content", "").strip()

            if not content:
                continue

            # 短消息且以寒暄词开头 → 跳过
            if len(content) <= 8 and any(content.startswith(p) for p in self._SKIP_PREFIXES):
                continue

            # 截断过长内容
            if len(content) > 300:
                content = content[:300] + "..."

            line = f"{role}: {content}"

            if total_chars + len(line) + 1 > max_chars:
                break

            lines.append(line)
            total_chars += len(line) + 1

        return "\n".join(lines)

    def should_summarize(
        self,
        messages: list[dict],
        message_threshold: int = 20,
        char_threshold: int = 10000,
    ) -> bool:
        """判断是否需要总结对话

        Args:
            messages: 消息列表
            message_threshold: 消息数量阈值
            char_threshold: 总字符数阈值

        Returns:
            bool: 是否需要总结
        """
        if len(messages) > message_threshold:
            return True

        total_chars = sum(len(msg.get("content", "")) for msg in messages)
        if total_chars > char_threshold:
            return True

        return False

    def split_messages(
        self,
        messages: list[dict],
        keep_recent: int = 10,
    ) -> tuple[list[dict], list[dict]]:
        """分割消息: 要总结的和要保留的

        Args:
            messages: 所有消息
            keep_recent: 保留最近 N 条消息

        Returns:
            tuple: (要总结的消息, 要保留的消息)
        """
        if len(messages) <= keep_recent:
            return [], messages

        to_summarize = messages[:-keep_recent]
        to_keep = messages[-keep_recent:]

        logger.debug(
            f"Split messages: {len(to_summarize)} to summarize, "
            f"{len(to_keep)} to keep"
        )

        return to_summarize, to_keep
