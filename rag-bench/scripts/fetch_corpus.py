#!/usr/bin/env python3
"""抓取 countbot.cn 官方文档站全量页面，转为 Markdown 语料。

用途：RAG 基线测试（G0）的 C1/C2 语料构建。
来源全部为官方公开页面，保证可复现。

输出：
  rag-bench/corpus/<slug>.md   —— 每页一份 Markdown（首行为 H1 标题）
  rag-bench/corpus/manifest.json —— 抓取清单（slug/title/url/chars/est_tokens）

用法：
  python fetch_corpus.py [--out ../corpus]
"""

import json
import re
import sys
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

BASE = "https://countbot.cn"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# 额外页面（llms.txt 列出但 sitemap 缺失：scenarios / 新版 releases / update-guide）
EXTRA_PATHS = [
    "/docs/scenarios/一句话清空收件箱：AI邮件分拣的场景拆解与提示词技巧/",
    "/docs/scenarios/帮我做个网页然后上线：从需求描述到生产部署的完整话术/",
    "/docs/scenarios/帮我搜一下最近AI有什么新动态：多源信息聚合的场景与检索技巧/",
    "/docs/scenarios/帮我盯着这件事：定时监控与主动提醒的场景设计与自动化技巧/",
    "/docs/scenarios/帮我规划一趟旅行：多技能联动的复合任务拆解与编排技巧/",
    "/docs/scenarios/每天早上一条消息搞定全天：AI早报自动生成的场景与调度技巧/",
    "/docs/releases/v0.7.0/",
    "/docs/releases/v0.8.0/",
    "/docs/releases/v0.9.0/",
    "/docs/getting-started/update-guide/",
]


class ArticleToMarkdown(HTMLParser):
    """把 <article> 内的 HTML 转为 Markdown 文本（容忍不完整标签）。

    保留结构：h1-h6 标题、列表项、代码块（围栏）、表格（管道行）、引用。
    行内标签只保留文本。script/style/svg/nav 忽略。
    """

    BLOCK_TAGS = {"p", "div", "section", "header", "footer", "br", "hr",
                  "ul", "ol", "table", "thead", "tbody", "blockquote", "details", "summary"}
    SKIP_TAGS = {"script", "style", "svg", "nav", "img", "button", "input"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines: list[str] = []
        self._buf: list[str] = []
        self._skip_depth = 0
        self._pre_depth = 0
        self._pre_buf: list[str] = []
        self._in_cell = False
        self._cell_buf: list[str] = []
        self._row_cells: list[str] | None = None
        self._is_header_row = False
        self._list_depth = 0
        self._li_open = False
        self._quote = False

    # ---------- 基础 ----------
    def _text(self, s: str):
        if self._skip_depth > 0:
            return
        if self._pre_depth > 0:
            self._pre_buf.append(s)
        elif self._in_cell:
            self._cell_buf.append(s)
        else:
            self._buf.append(s)
            if self._li_open:
                self._li_open = False

    def _flush_para(self):
        text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
        self._buf = []
        if not text:
            return
        prefix = "> " if self._quote else ""
        indent = "  " * max(self._list_depth - 1, 0)
        bullet = "- " if self._list_depth > 0 else ""
        self.lines.append(prefix + indent + bullet + text)

    def _flush_cell(self):
        text = re.sub(r"\s+", " ", "".join(self._cell_buf)).strip()
        self._cell_buf = []
        if self._row_cells is not None:
            self._row_cells.append(text)

    # ---------- 标签处理 ----------
    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth > 0:
            return
        if tag == "pre":
            self._flush_para()
            self._pre_depth += 1
            if self._pre_depth == 1:
                self._pre_buf = []
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._flush_para()
            self._buf.append("\x00H%d\x00" % int(tag[1]))  # 标记，flush 时替换
        elif tag in ("p", "div", "section", "header", "footer", "blockquote",
                     "details", "summary", "ul", "ol", "table", "thead", "tbody"):
            self._flush_para()
            if tag == "blockquote":
                self._quote = True
            elif tag in ("ul", "ol"):
                self._list_depth += 1
        elif tag == "li":
            self._flush_para()
            self._li_open = True
        elif tag == "tr":
            self._row_cells = []
        elif tag in ("td", "th"):
            self._in_cell = True
            if tag == "th":
                self._is_header_row = True
        elif tag == "br":
            self._text(" ")
        elif tag == "hr":
            self._flush_para()
            self.lines.append("---")

    def handle_endtag(self, tag):
        if tag in self.SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth > 0:
            return
        if tag == "pre":
            self._pre_depth -= 1
            if self._pre_depth == 0:
                code = "".join(self._pre_buf).rstrip("\n")
                self.lines.append("```\n" + code + "\n```")
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(tag[1])
            raw = "".join(self._buf)
            self._buf = []
            text = re.sub(r"\s+", " ", raw.replace("\x00H%d\x00" % level, "")).strip()
            prefix = "> " if self._quote else ""
            self.lines.append(prefix + "#" * level + " " + text)
        elif tag in ("p", "div", "section", "header", "footer", "details", "summary"):
            self._flush_para()
        elif tag == "blockquote":
            self._quote = False
            self._flush_para()
        elif tag in ("ul", "ol"):
            self._list_depth = max(0, self._list_depth - 1)
            self._flush_para()
        elif tag in ("td", "th"):
            self._in_cell = False
            self._flush_cell()
        elif tag == "tr":
            if self._row_cells is not None:
                cells = self._row_cells
                self._row_cells = None
                if cells:
                    self.lines.append("| " + " | ".join(cells) + " |")
                    if self._is_header_row:
                        self.lines.append("|" + "---|" * len(cells))
                        self._is_header_row = False
        elif tag == "table":
            self._flush_para()

    def handle_data(self, data):
        self._text(data)

    def result(self) -> str:
        self._flush_para()
        out = []
        prev_blank = True
        for ln in self.lines:
            if ln.strip():
                out.append(ln)
                prev_blank = False
            else:
                if not prev_blank:
                    out.append("")
                prev_blank = True
        return "\n".join(out).strip() + "\n"


def extract_article(html: str) -> tuple[str, str]:
    """返回 (title, markdown)。title 取 <h1> 或 <title>。"""
    m = re.search(r"<article[^>]*>(.*?)</article>", html, re.S | re.I)
    body_html = m.group(1) if m else html
    parser = ArticleToMarkdown()
    parser.feed(body_html)
    md = parser.result()
    h1 = re.search(r"^#\s+(.+)$", md, re.M)
    title = h1.group(1).strip() if h1 else ""
    if not title:
        t = re.search(r"<title>(.*?)</title>", html, re.S)
        title = t.group(1).strip() if t else ""
    return title, md


def slug_of(path: str) -> str:
    p = path[len("/docs/"):] if path.startswith("/docs/") else path
    p = p.strip("/")
    if not p:
        p = "index"
    return p


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def main():
    out_dir = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv \
        else Path(__file__).resolve().parent.parent / "corpus"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1) URL 全集 = sitemap + EXTRA（按 unquote 后路径去重，中文与百分号编码视为同页）
    sitemap_url = BASE + "/sitemap.xml"
    xml = fetch(sitemap_url)
    paths = [urlparse(u).path for u in re.findall(r"<loc>(.*?)</loc>", xml)
             if "/docs/" in u]
    paths += EXTRA_PATHS
    # 归一化：unquote 去重，再统一以 / 结尾
    norm = {}
    for p in paths:
        key = unquote(p).rstrip("/")
        norm[key] = p if p.endswith("/") else p + "/"
    paths = sorted(norm.values())
    # sitemap 中的 articles/* 在 cn 站已 404（死链，指向另一域名的 SPA 兜底页），跳过
    paths = [p for p in paths if "/docs/articles/" not in unquote(p)]

    manifest = []
    failed = []
    for i, path in enumerate(paths, 1):
        slug = slug_of(unquote(path))
        # 统一 URL 编码（中文路径必须 quote，否则 ascii 编码错误）
        url = BASE + quote(unquote(path), safe="/:")
        try:
            html = fetch(url)
            title, md = extract_article(html)
            if len(md.strip()) < 100:
                raise ValueError(f"content too short: {len(md)} chars")
            out_file = out_dir / f"{slug}.md"
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_text(md, encoding="utf-8")
            chars = len(md)
            manifest.append({
                "slug": slug, "title": title, "url": url,
                "chars": chars, "est_tokens": int(chars / 1.5),
                "section": slug.split("/")[0] if "/" in slug else slug,
            })
            print(f"[{i}/{len(paths)}] {slug} ({chars} chars)")
        except Exception as e:
            failed.append({"slug": slug, "url": url, "error": str(e)})
            print(f"[{i}/{len(paths)}] FAIL {slug}: {e}")
        time.sleep(0.25)

    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    total_chars = sum(m["chars"] for m in manifest)
    print(f"\nOK: {len(manifest)} pages, {total_chars} chars "
          f"(~{total_chars // 1500}K est tokens); failed: {len(failed)}")
    if failed:
        (out_dir / "failed.json").write_text(
            json.dumps(failed, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
