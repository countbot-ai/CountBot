#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""中文新闻聚合工具 - 基于 RSS 源和网页抓取，纯标准库实现"""
import argparse
import sys
import json
import os
import re
import io
import html
import time
import urllib.request
import urllib.error
from xml.etree import ElementTree as ET
from datetime import datetime

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7) AppleWebKit/537.36 Chrome/131.0 Safari/537.36"
TIMEOUT = 10  # 增加超时时间，提高稳定性

# ── 新闻源定义 ──────────────────────────────────────────────
SOURCES = {
    "hot": [
        {"name": "人民网",   "type": "rss", "url": "http://www.people.com.cn/rss/politics.xml"},
        {"name": "新华网",   "type": "web", "url": "http://www.news.cn/politics/"},
        {"name": "澎湃新闻", "type": "rss", "url": "https://www.thepaper.cn/rss_newslist_all.xml"},
    ],
    "politics": [
        {"name": "人民网时政", "type": "rss", "url": "http://www.people.com.cn/rss/politics.xml"},
        {"name": "新华网政务", "type": "web", "url": "http://www.news.cn/politics/"},
    ],
    "finance": [
        {"name": "新浪财经",  "type": "rss", "url": "https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2516&k=&num=20&page=1&r=0.1&callback="},
        {"name": "东方财富",  "type": "web", "url": "https://www.eastmoney.com/"},
    ],
    "tech": [
        {"name": "36氪",     "type": "rss", "url": "https://36kr.com/feed"},
        {"name": "IT之家",   "type": "rss", "url": "https://www.ithome.com/rss/"},
    ],
    "society": [
        {"name": "中国新闻网", "type": "rss", "url": "https://www.chinanews.com/rss/scroll-news.xml"},
        {"name": "澎湃新闻",  "type": "rss", "url": "https://www.thepaper.cn/rss_newslist_all.xml"},
    ],
    "world": [
        {"name": "环球网",   "type": "rss", "url": "https://world.huanqiu.com/rss/world.xml"},
        {"name": "参考消息",  "type": "rss", "url": "http://www.cankaoxiaoxi.com/rss/roll.xml"},
        {"name": "中国新闻网国际", "type": "rss", "url": "https://www.chinanews.com/rss/world.xml"},
    ],
    "sports": [
        {"name": "新浪体育", "type": "web", "url": "https://sports.sina.com.cn/"},
        {"name": "虎扑",     "type": "web", "url": "https://www.hupu.com/"},
    ],
    "entertainment": [
        {"name": "新浪娱乐", "type": "web", "url": "https://ent.sina.com.cn/"},
    ],
    "ai": [
        {"name": "MIT Tech Review",  "type": "rss", "url": "https://www.technologyreview.com/feed/"},
        {"name": "OpenAI Blog",      "type": "rss", "url": "https://openai.com/blog/rss.xml"},
        {"name": "Google AI Blog",   "type": "rss", "url": "https://blog.google/technology/ai/rss/"},
        {"name": "DeepMind Blog",    "type": "rss", "url": "https://deepmind.google/blog/rss.xml"},
        {"name": "Latent Space",     "type": "rss", "url": "https://www.latent.space/feed"},
        {"name": "Interconnects",    "type": "rss", "url": "https://www.interconnects.ai/feed"},
        {"name": "One Useful Thing", "type": "rss", "url": "https://www.oneusefulthing.org/feed"},
        {"name": "KDnuggets",       "type": "rss", "url": "https://www.kdnuggets.com/feed"},
    ],
    "ai-community": [
        {"name": "AI News Daily",    "type": "rss", "url": "https://buttondown.com/ainews/rss"},
        {"name": "Sebastian Raschka","type": "rss", "url": "https://magazine.sebastianraschka.com/feed"},
        {"name": "Hacker News",      "type": "rss", "url": "https://hnrss.org/frontpage"},
        {"name": "Product Hunt",     "type": "rss", "url": "https://www.producthunt.com/feed"},
    ],
}

CAT_NAMES = {
    "hot": "热点要闻", "politics": "时政", "finance": "财经",
    "tech": "科技", "society": "社会", "world": "国际",
    "sports": "体育", "entertainment": "娱乐",
    "ai": "AI 技术与资讯", "ai-community": "AI 社区与聚合",
}


# ── 网络请求 ─────────────────────────────────────────────────
def fetch(url, timeout=TIMEOUT, retry=2):
    """获取 URL 内容，返回文本，支持重试"""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    
    for attempt in range(retry):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
                # 尝试多种编码
                for enc in ('utf-8', 'gbk', 'gb2312', 'latin-1'):
                    try:
                        return data.decode(enc)
                    except (UnicodeDecodeError, LookupError):
                        continue
                return data.decode('utf-8', errors='replace')
        except urllib.error.HTTPError as e:
            if attempt < retry - 1:
                time.sleep(1)
                continue
            print(f"  ⚠️  HTTP错误 {e.code}: {url}", file=sys.stderr)
            return None
        except urllib.error.URLError as e:
            if attempt < retry - 1:
                time.sleep(1)
                continue
            print(f"  ⚠️  网络错误: {url} - {e.reason}", file=sys.stderr)
            return None
        except Exception as e:
            if attempt < retry - 1:
                time.sleep(1)
                continue
            print(f"  ⚠️  获取失败: {url} - {type(e).__name__}: {e}", file=sys.stderr)
            return None
    return None


# ── RSS 解析 ─────────────────────────────────────────────────
def parse_rss(xml_text, source_name):
    """解析 RSS/Atom XML，返回新闻列表"""
    items = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items

    # RSS 2.0
    for item in root.iter('item'):
        title = _text(item, 'title')
        link = _text(item, 'link')
        pub = _text(item, 'pubDate')
        desc = _text(item, 'description')
        # 优先取 content:encoded（完整正文），其次 description
        content = None
        for tag in ('{http://purl.org/rss/1.0/modules/content/}encoded', 'content:encoded'):
            content = _text(item, tag)
            if content:
                break
        body = _clean(content) if content else (_clean(desc) if desc else "")
        if title and link:
            items.append({
                "title": _clean(title),
                "link": link.strip(),
                "source": source_name,
                "time": _parse_time(pub),
                "summary": body,
            })

    # Atom
    if not items:
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        for entry in root.iter('{http://www.w3.org/2005/Atom}entry'):
            title = _text(entry, '{http://www.w3.org/2005/Atom}title')
            link_el = entry.find('{http://www.w3.org/2005/Atom}link')
            link = link_el.get('href', '') if link_el is not None else ''
            pub = _text(entry, '{http://www.w3.org/2005/Atom}published') or _text(entry, '{http://www.w3.org/2005/Atom}updated')
            content = _text(entry, '{http://www.w3.org/2005/Atom}content') or _text(entry, '{http://www.w3.org/2005/Atom}summary') or ""
            if title and link:
                items.append({
                    "title": _clean(title),
                    "link": link.strip(),
                    "source": source_name,
                    "time": _parse_time(pub),
                    "summary": _clean(content),
                })
    return items


def _text(el, tag):
    """安全获取子元素文本"""
    child = el.find(tag)
    return child.text if child is not None and child.text else None


def _clean(text):
    """清理 HTML 标签和多余空白"""
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _parse_time(time_str):
    """尝试解析时间字符串"""
    if not time_str:
        return ""
    # 常见 RSS 时间格式
    for fmt in ('%a, %d %b %Y %H:%M:%S %z', '%a, %d %b %Y %H:%M:%S GMT',
                '%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%dT%H:%M:%SZ',
                '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
        try:
            dt = datetime.strptime(time_str.strip(), fmt)
            return dt.strftime('%m-%d %H:%M')
        except ValueError:
            continue
    return time_str[:16]


# ── 网页标题提取 ──────────────────────────────────────────────
def parse_web_titles(html_text, source_name, base_url):
    """从网页 HTML 中提取新闻标题和链接"""
    items = []
    # 匹配 <a> 标签中的标题链接
    pattern = r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>([^<]{8,80})</a>'
    seen = set()
    for match in re.finditer(pattern, html_text):
        link, title = match.group(1), match.group(2)
        title = _clean(title)
        # 过滤非新闻链接
        if not title or len(title) < 8:
            continue
        if any(skip in title for skip in ('首页', '登录', '注册', '关于我们', '联系', '广告', '下载', '客户端', '反馈')):
            continue
        # 补全相对链接
        if link.startswith('//'):
            link = 'https:' + link
        elif link.startswith('/'):
            from urllib.parse import urljoin
            link = urljoin(base_url, link)
        elif not link.startswith('http'):
            continue
        if title in seen:
            continue
        seen.add(title)
        items.append({
            "title": title,
            "link": link,
            "source": source_name,
            "time": "",
            "summary": "",
        })
    return items


# ── 新浪 API 解析 ────────────────────────────────────────────
def parse_sina_api(text, source_name):
    """解析新浪滚动新闻 API 返回"""
    items = []
    try:
        # 去掉 JSONP callback
        text = re.sub(r'^[^{]*', '', text)
        text = re.sub(r'[^}]*$', '', text)
        data = json.loads(text)
        for item in data.get('result', {}).get('data', []):
            title = item.get('title', '')
            link = item.get('url', '')
            ctime = item.get('ctime', '')
            if title and link:
                items.append({
                    "title": _clean(title),
                    "link": link,
                    "source": source_name,
                    "time": ctime,
                    "summary": _clean(item.get('intro', ''))[:200],
                })
    except (json.JSONDecodeError, KeyError):
        pass
    return items


# ── 核心逻辑 ─────────────────────────────────────────────────
def _fetch_one_source(src):
    """获取并解析单个新闻源（用于并发）"""
    try:
        print(f"  📡 正在获取 {src['name']}...", file=sys.stderr)
        text = fetch(src["url"])
        if not text:
            print(f"  ❌ {src['name']} 获取失败", file=sys.stderr)
            return []
        
        if src["type"] == "rss":
            if 'feed.mix.sina.com.cn' in src["url"]:
                items = parse_sina_api(text, src["name"])
            else:
                items = parse_rss(text, src["name"])
        else:
            items = parse_web_titles(text, src["name"], src["url"])
        
        print(f"  ✅ {src['name']} 获取成功 ({len(items)} 条)", file=sys.stderr)
        return items
    except Exception as e:
        print(f"  ❌ {src['name']} 解析异常: {type(e).__name__}: {e}", file=sys.stderr)
        return []


def fetch_news(category="hot", keyword=None, limit=10):
    """获取指定分类的新闻（并发请求所有源）"""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    sources = SOURCES.get(category, SOURCES["hot"])
    all_items = []
    
    print(f"\n🔍 开始获取 {CAT_NAMES.get(category, category)} 新闻...", file=sys.stderr)

    with ThreadPoolExecutor(max_workers=min(len(sources), 6)) as pool:
        futures = {pool.submit(_fetch_one_source, src): src for src in sources}
        for future in as_completed(futures):
            try:
                result = future.result(timeout=15)  # 单个源最多等待15秒
                all_items.extend(result)
            except Exception as e:
                src = futures[future]
                print(f"  ❌ {src['name']} 处理异常: {type(e).__name__}: {e}", file=sys.stderr)

    # 去重（按标题）
    seen = set()
    unique = []
    for item in all_items:
        if item["title"] not in seen:
            seen.add(item["title"])
            unique.append(item)

    # 按时间排序（最新的在前），没有时间的放在后面
    def sort_key(item):
        time_str = item.get("time", "")
        if not time_str:
            return "99-99 99:99"  # 没有时间的排在最后
        return time_str
    
    unique.sort(key=sort_key, reverse=True)

    # 关键词过滤
    if keyword:
        keyword_lower = keyword.lower()
        unique = [i for i in unique if keyword_lower in i["title"].lower() or keyword_lower in i.get("summary", "").lower()]

    # 多样性优化：交错展示不同来源，避免单一来源占据前排
    if len(unique) > limit:
        diversified = []
        source_indices = {}  # 记录每个来源的当前索引
        
        # 按来源分组
        by_source = {}
        for item in unique:
            source = item.get("source", "Unknown")
            if source not in by_source:
                by_source[source] = []
            by_source[source].append(item)
        
        # 轮流从各个来源取新闻，实现多样性
        while len(diversified) < limit and by_source:
            for source in list(by_source.keys()):
                if by_source[source]:
                    diversified.append(by_source[source].pop(0))
                    if len(diversified) >= limit:
                        break
                else:
                    del by_source[source]
        
        return diversified
    
    return unique[:limit]


def format_news(items, category="hot", summary_len=100):
    """格式化新闻输出，summary_len 控制摘要显示长度"""
    cat_name = CAT_NAMES.get(category, category)
    lines = [f"📰 {cat_name}新闻 (共 {len(items)} 条)\n"]
    for i, item in enumerate(items, 1):
        time_str = f" | {item['time']}" if item.get('time') else ""
        lines.append(f"  {i}. {item['title']}")
        lines.append(f"     📌 {item['source']}{time_str}")
        lines.append(f"     🔗 {item['link']}")
        if item.get('summary') and summary_len != 0:
            text = item['summary']
            if summary_len > 0 and len(text) > summary_len:
                text = text[:summary_len] + "..."
            lines.append(f"     📝 {text}")
        lines.append("")
    return "\n".join(lines)


# ── 命令处理 ─────────────────────────────────────────────────
def cmd_hot(args):
    """获取热点新闻"""
    items = fetch_news("hot", keyword=args.keyword, limit=args.limit)
    if not items:
        if args.keyword:
            print(f'未找到包含关键词 "{args.keyword}" 的新闻')
            print(f"\n💡 提示：")
            print(f"  - RSS源只包含最新热点新闻，可能不包含特定关键词")
            print(f'  - 建议使用百度搜索查找 "{args.keyword}" 相关新闻')
            print(f"  - 或者去掉关键词查看所有热点新闻")
        else:
            print("暂无新闻数据，请稍后重试")
        return
    if args.json:
        print(json.dumps(items, ensure_ascii=False, indent=2))
    else:
        print(format_news(items, "hot", summary_len=args.detail))


def cmd_category(args):
    """按分类获取新闻"""
    cat = args.cat
    if cat not in SOURCES:
        print(f"不支持的分类: {cat}", file=sys.stderr)
        print(f"支持的分类: {', '.join(SOURCES.keys())}", file=sys.stderr)
        sys.exit(1)
    items = fetch_news(cat, keyword=args.keyword, limit=args.limit)
    if not items:
        cat_name = CAT_NAMES.get(cat, cat)
        if args.keyword:
            print(f'未找到包含关键词 "{args.keyword}" 的{cat_name}新闻')
            print(f"\n💡 提示：")
            print(f"  - RSS源只包含最新新闻，可能不包含特定关键词")
            print(f'  - 建议使用百度搜索查找 "{args.keyword}" 相关新闻')
            print(f"  - 或者去掉关键词查看所有{cat_name}新闻")
        else:
            print(f"暂无 {cat_name} 新闻数据，请稍后重试")
        return
    if args.json:
        print(json.dumps(items, ensure_ascii=False, indent=2))
    else:
        print(format_news(items, cat, summary_len=args.detail))


def cmd_sources(args):
    """列出所有新闻源"""
    print("📡 支持的新闻分类和来源:\n")
    for cat, sources in SOURCES.items():
        cat_name = CAT_NAMES.get(cat, cat)
        names = ", ".join(s["name"] for s in sources)
        print(f"  {cat_name} ({cat}): {names}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description='中文新闻聚合工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s hot                          获取热点新闻
  %(prog)s hot --keyword AI             搜索 AI 相关新闻
  %(prog)s category --cat tech          获取科技新闻
  %(prog)s category --cat finance       获取财经新闻
  %(prog)s sources                      查看所有新闻源
""")
    subparsers = parser.add_subparsers(dest='command', help='命令')

    hp = subparsers.add_parser('hot', help='获取热点新闻')
    hp.add_argument('--keyword', '-k', help='关键词过滤')
    hp.add_argument('--limit', '-n', type=int, default=10, help='返回条数（默认 10）')
    hp.add_argument('--detail', '-d', type=int, default=100, help='摘要长度（默认 100，0=不显示，-1=全文）')
    hp.add_argument('--json', action='store_true', help='JSON 格式输出')

    cp = subparsers.add_parser('category', help='按分类获取新闻')
    cp.add_argument('--cat', '-c', required=True, choices=list(SOURCES.keys()), help='新闻分类')
    cp.add_argument('--keyword', '-k', help='关键词过滤')
    cp.add_argument('--limit', '-n', type=int, default=10, help='返回条数（默认 10）')
    cp.add_argument('--detail', '-d', type=int, default=100, help='摘要长度（默认 100，0=不显示，-1=全文）')
    cp.add_argument('--json', action='store_true', help='JSON 格式输出')

    subparsers.add_parser('sources', help='查看所有新闻源')

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    {'hot': cmd_hot, 'category': cmd_category, 'sources': cmd_sources}[args.command](args)


if __name__ == '__main__':
    main()
