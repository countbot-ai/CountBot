"""Memory Store - 记忆存储管理

记忆格式: 每行一条，格式为
  日期|来源|内容事项1；事项2；事项3

示例:
  2026-02-15|web-chat|用户询问天气API方案；决定使用OpenWeatherMap；缓存策略选Redis TTL=3600s
  2026-02-15|telegram|用户要求每天早上9点发送日报；已创建cron任务

支持功能:
- 写入记忆（追加一行）
- 关键词搜索（单词/多词，返回匹配行号和内容）
- 按行号读取（支持单行和范围）
- 对话自动总结写入
"""

from datetime import datetime
from pathlib import Path

from loguru import logger


class MemoryStore:
    """记忆存储 - 基于单文件的行式记忆管理"""

    def __init__(self, memory_dir: Path):
        self.memory_dir = memory_dir
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.memory_file = self.memory_dir / "MEMORY.md"
        logger.debug(f"MemoryStore initialized: {self.memory_file}")

    def _read_lines(self) -> list[str]:
        """读取所有记忆行"""
        if not self.memory_file.exists():
            return []
        content = self.memory_file.read_text(encoding="utf-8")
        if not content.strip():
            return []
        return content.strip().split("\n")

    def _write_lines(self, lines: list[str]) -> None:
        """写入所有记忆行"""
        self.memory_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def read_all(self) -> str:
        """读取全部记忆内容"""
        if not self.memory_file.exists():
            return ""
        return self.memory_file.read_text(encoding="utf-8")

    def write_all(self, content: str) -> None:
        """覆盖写入全部记忆"""
        self.memory_file.write_text(content, encoding="utf-8")

    def get_line_count(self) -> int:
        """获取记忆总行数"""
        return len(self._read_lines())

    def append_entry(self, source: str, content: str) -> int:
        """追加一条记忆

        Args:
            source: 来源（web-chat, telegram, dingtalk, feishu, cron 等）
            content: 记忆内容（多个事项用；分隔）

        Returns:
            int: 写入后的行号（1-based）
        """
        date_str = datetime.now().strftime("%Y-%m-%d")
        
        # 清理内容：移除换行符，避免破坏行式存储格式
        content = content.replace('\n', ' ').replace('\r', ' ')
        # 压缩多个空格为一个
        content = ' '.join(content.split())
        
        entry = f"{date_str}|{source}|{content}"

        lines = self._read_lines()
        lines.append(entry)
        self._write_lines(lines)

        line_num = len(lines)
        logger.info(f"Memory appended at line {line_num}: {entry[:80]}...")
        return line_num

    def read_lines(self, start: int, end: int | None = None) -> str:
        """按行号读取记忆

        Args:
            start: 起始行号（1-based）
            end: 结束行号（1-based，包含），None 表示只读 start 那一行

        Returns:
            str: 格式化的行内容，每行带行号前缀
        """
        lines = self._read_lines()
        total = len(lines)

        if total == 0:
            return "记忆为空"

        if end is None:
            end = start

        # 边界检查
        start = max(1, min(start, total))
        end = max(start, min(end, total))

        result = []
        for i in range(start - 1, end):
            result.append(f"[{i + 1}] {lines[i]}")

        return "\n".join(result)

    def search(self, keywords: list[str], max_results: int = 15, match_mode: str = "or") -> str:
        """关键词搜索记忆

        支持单词和多词搜索，可选择AND或OR逻辑。
        搜索不区分大小写。

        Args:
            keywords: 关键词列表
            max_results: 最大返回条数
            match_mode: 匹配模式，"or"（任意匹配）或"and"（全部匹配），默认"or"

        Returns:
            str: 格式化的搜索结果，每行带行号前缀
        """
        lines = self._read_lines()
        if not lines:
            return "记忆为空，无搜索结果"

        if not keywords:
            return "请提供搜索关键词"

        # 清理关键词
        keywords = [kw.strip().lower() for kw in keywords if kw.strip()]
        if not keywords:
            return "请提供有效的搜索关键词"

        results = []
        for i, line in enumerate(lines):
            line_lower = line.lower()
            
            # 根据匹配模式选择逻辑
            if match_mode == "and":
                # AND 逻辑：所有关键词都必须匹配
                if all(kw in line_lower for kw in keywords):
                    results.append(f"[{i + 1}] {line}")
            else:
                # OR 逻辑：任意关键词匹配即可
                if any(kw in line_lower for kw in keywords):
                    results.append(f"[{i + 1}] {line}")

        if not results:
            mode_text = "任意" if match_mode == "or" else "全部"
            return f"未找到包含 {mode_text} 关键词 {', '.join(keywords)} 的记忆"

        # 限制结果数
        if len(results) > max_results:
            total_found = len(results)
            results = results[:max_results]
            results.append(f"... 共 {total_found} 条匹配，仅显示前 {max_results} 条")

        return "\n".join(results)

    def delete_lines(self, line_numbers: list[int]) -> int:
        """删除指定行号的记忆

        Args:
            line_numbers: 要删除的行号列表（1-based）

        Returns:
            int: 实际删除的行数
        """
        lines = self._read_lines()
        if not lines:
            return 0

        to_delete = set(line_numbers)
        new_lines = [
            line for i, line in enumerate(lines)
            if (i + 1) not in to_delete
        ]

        deleted = len(lines) - len(new_lines)
        if deleted > 0:
            self._write_lines(new_lines)
            logger.info(f"Deleted {deleted} memory lines: {line_numbers}")

        return deleted

    def get_recent(self, count: int = 10) -> str:
        """获取最近 N 条记忆

        Args:
            count: 返回条数

        Returns:
            str: 格式化的最近记忆
        """
        lines = self._read_lines()
        if not lines:
            return "记忆为空"

        start = max(0, len(lines) - count)
        result = []
        for i in range(start, len(lines)):
            result.append(f"[{i + 1}] {lines[i]}")

        return "\n".join(result)

    def get_stats(self) -> dict:
        """获取记忆统计信息"""
        lines = self._read_lines()
        total = len(lines)

        if total == 0:
            return {"total": 0, "sources": {}, "date_range": ""}

        # 统计来源分布
        sources: dict[str, int] = {}
        dates: list[str] = []
        for line in lines:
            parts = line.split("|", 2)
            if len(parts) >= 2:
                dates.append(parts[0])
                src = parts[1]
                sources[src] = sources.get(src, 0) + 1

        date_range = ""
        if dates:
            date_range = f"{dates[0]} ~ {dates[-1]}"

        return {
            "total": total,
            "sources": sources,
            "date_range": date_range,
        }


class ConversationSummarizer:
    """对话总结器 - 使用 LLM 直接总结对话"""

    def __init__(self, provider, char_limit: int = 2000):
        self.provider = provider
        self.char_limit = char_limit

    async def summarize_conversation(
        self,
        messages: list[dict],
        previous_summary: str = "",
    ) -> str:
        """总结对话历史

        Args:
            messages: 要总结的消息列表
            previous_summary: 之前的总结

        Returns:
            str: 生成的总结文本
        """
        from backend.modules.agent.prompts import (
            CONVERSATION_TO_MEMORY_PROMPT,
            RECURSIVE_SUMMARY_PROMPT,
        )
        from backend.modules.agent.analyzer import MessageAnalyzer

        try:
            analyzer = MessageAnalyzer()
            formatted = analyzer.format_messages_for_summary(messages, max_chars=self.char_limit * 2)

            if previous_summary:
                prompt = RECURSIVE_SUMMARY_PROMPT.format(
                    previous_summary=previous_summary,
                    past_messages=formatted,
                    char_limit=self.char_limit,
                )
            else:
                prompt = CONVERSATION_TO_MEMORY_PROMPT.format(messages=formatted)

            # 使用 chat_stream 收集完整响应
            result_parts = []
            async for chunk in self.provider.chat_stream(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            ):
                if chunk.is_content and chunk.content:
                    result_parts.append(chunk.content)

            return "".join(result_parts).strip()

        except Exception as e:
            logger.error(f"Failed to summarize conversation: {e}")
            return f"[对话 {len(messages)} 条消息]"

    def should_summarize(
        self,
        messages: list[dict],
        message_threshold: int = 20,
        char_threshold: int = 10000,
    ) -> bool:
        """判断是否需要总结（委托给 MessageAnalyzer）"""
        from backend.modules.agent.analyzer import MessageAnalyzer
        return MessageAnalyzer().should_summarize(messages, message_threshold, char_threshold)

    def get_messages_to_keep(
        self,
        messages: list[dict],
        keep_recent: int = 10,
    ) -> tuple[list[dict], list[dict]]:
        """分割消息（委托给 MessageAnalyzer）"""
        from backend.modules.agent.analyzer import MessageAnalyzer
        return MessageAnalyzer().split_messages(messages, keep_recent)
