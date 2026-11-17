"""HeadingChunker - 按 Markdown 标题切分文档为块

设计目标（M1）：
- 以"标题节"为自然边界，保持语义完整（不破坏代码块/表格）；
- 超长节按段落二次切分（代码围栏视为不可分割单元）；
- 每块携带 [slug#section] 溯源标识；
- 零第三方依赖（纯标准库）。

token 口径：est_tokens = chars / 1.5（CJK 近似），与 rag-bench 基线一致。
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


@dataclass
class Chunk:
    """一个可检索的内容块"""

    chunk_id: str          # 溯源标识: {slug}#{section-anchor}
    slug: str              # 所属文档 slug
    doc_title: str         # 所属文档标题
    section: str           # 节标题（首个标题前的内容为 ""）
    heading_path: str      # 层级路径，如 "安装 > Linux"
    content: str           # 块正文（不含节标题行）
    tags: List[str] = field(default_factory=list)
    mtime: float = 0.0

    @property
    def est_tokens(self) -> int:
        return int(len(self.content) / 1.5)

    @property
    def index_title(self) -> str:
        """用于 BM25 标题加权（×3）的复合标题：文档标题 + 节路径"""
        parts = [self.doc_title]
        if self.heading_path:
            parts.append(self.heading_path)
        return " · ".join(p for p in parts if p)


def _slugify_anchor(text: str) -> str:
    """标题 -> 稳定的 anchor（保留 CJK 与字母数字）"""
    anchor = re.sub(r"[^\w\u4e00-\u9fff]+", "-", text.strip().lower())
    anchor = anchor.strip("-")
    return anchor or "section"


class HeadingChunker:
    """按标题切块 + 超长节按段落二次切分

    Args:
        max_chars: 单块正文上限（字符）。默认 1200 ≈ 800 est tokens。
        min_chars: 低于此长度的独立段落并入前块，避免碎片。
        overlap_chars: 二次切分时块尾重叠量，保证跨块语义连续。
    """

    def __init__(self, max_chars: int = 1200, min_chars: int = 80, overlap_chars: int = 120):
        self.max_chars = max_chars
        self.min_chars = min_chars
        self.overlap_chars = overlap_chars

    # ---------- 主入口 ----------

    def chunk(
        self,
        slug: str,
        title: str,
        content: str,
        tags: Optional[List[str]] = None,
        mtime: float = 0.0,
    ) -> List[Chunk]:
        sections = self._split_by_headings(content)
        chunks: List[Chunk] = []
        anchor_counts = {}  # anchor 去重

        for section, text in sections:
            pieces = self._split_long_section(text)
            for i, piece in enumerate(pieces):
                anchor = _slugify_anchor(section) if section else "intro"
                anchor_counts[anchor] = anchor_counts.get(anchor, 0) + 1
                n = anchor_counts[anchor]
                chunk_id = f"{slug}#{anchor}" if n == 1 else f"{slug}#{anchor}-{n}"
                chunks.append(Chunk(
                    chunk_id=chunk_id,
                    slug=slug,
                    doc_title=title,
                    section=section or "概述",
                    heading_path=section or "",
                    content=piece,
                    tags=list(tags or []),
                    mtime=mtime,
                ))
        return chunks

    # ---------- 一级切分：按标题 ----------

    def _split_by_headings(self, content: str) -> List[tuple]:
        """返回 [(节标题路径, 节正文), ...]

        节标题路径 = 父级标题链，如 "部署 > Docker"。
        标题本身保留在正文开头（索引时可加权，注入时提供上下文）。
        """
        lines = (content or "").splitlines()
        sections: List[tuple] = []
        heading_stack: List[str] = []   # [(level, text)] 用元组拆开存
        heading_levels: List[int] = []
        current_lines: List[str] = []
        current_heading = ""

        in_fence = False
        fence_marker = ""

        def flush():
            text = "\n".join(current_lines).strip()
            if text or current_heading:
                sections.append((current_heading, text))

        for line in lines:
            stripped = line.strip()

            # 代码围栏内的 # 不是标题
            if stripped.startswith("```") or stripped.startswith("~~~"):
                if not in_fence:
                    in_fence, fence_marker = True, stripped[:3]
                    current_lines.append(line)
                    continue
                if stripped.startswith(fence_marker):
                    in_fence, fence_marker = False, ""
                current_lines.append(line)
                continue

            m = HEADING_RE.match(line) if not in_fence else None
            if m:
                flush()
                current_lines = []
                level = len(m.group(1))
                text = m.group(2).strip()
                # 弹出更深或同级的标题
                while heading_levels and heading_levels[-1] >= level:
                    heading_stack.pop()
                    heading_levels.pop()
                heading_stack.append(text)
                heading_levels.append(level)
                current_heading = " > ".join(heading_stack)
                current_lines.append(line)  # 标题行保留在块内
            else:
                current_lines.append(line)

        flush()
        return sections

    # ---------- 二级切分：超长节按段落 ----------

    def _split_long_section(self, text: str) -> List[str]:
        if len(text) <= self.max_chars:
            return [text]

        paragraphs = self._split_paragraphs(text)
        pieces: List[str] = []
        buf: List[str] = []
        buf_len = 0

        for para in paragraphs:
            # 单段超限：硬切（保留 overlap）
            if len(para) > self.max_chars:
                if buf:
                    pieces.append("\n\n".join(buf))
                    buf, buf_len = [], 0
                step = self.max_chars - self.overlap_chars
                for start in range(0, len(para), step):
                    piece = para[start:start + self.max_chars]
                    if len(piece) > self.min_chars:
                        pieces.append(piece)
                continue

            if buf_len + len(para) + 2 > self.max_chars and buf:
                pieces.append("\n\n".join(buf))
                # 携带尾部 overlap（保留最后一个不超过 overlap 的段落）
                tail = ""
                for prev in reversed(buf):
                    if len(tail) + len(prev) + 2 > self.overlap_chars:
                        break
                    tail = (prev + "\n\n" + tail) if tail else prev
                buf = [tail] if tail else []
                buf_len = len(tail)
            buf.append(para)
            buf_len += len(para) + 2

        if buf:
            last = "\n\n".join(buf)
            # 尾块太小则并入前块
            if pieces and len(last) < self.min_chars:
                pieces[-1] = pieces[-1] + "\n\n" + last
            else:
                pieces.append(last)
        return pieces

    def _split_paragraphs(self, text: str) -> List[str]:
        """按空行分段；代码围栏、表格行保持为不可分割单元"""
        paragraphs: List[str] = []
        buf: List[str] = []
        in_fence = False
        fence_marker = ""

        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("```") or stripped.startswith("~~~"):
                if not in_fence:
                    in_fence, fence_marker = True, stripped[:3]
                    buf.append(line)
                    continue
                if stripped.startswith(fence_marker):
                    in_fence, fence_marker = False, ""
                buf.append(line)
                continue
            if not in_fence and not stripped and buf:
                paragraphs.append("\n".join(buf))
                buf = []
            else:
                buf.append(line)
        if buf:
            paragraphs.append("\n".join(buf))
        return [p for p in paragraphs if p.strip()]
