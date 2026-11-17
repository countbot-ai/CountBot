#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""百度 AI 搜索命令行工具"""
import argparse
import sys
import json
import io
import os

# 将当前目录加入路径
sys.path.insert(0, os.path.dirname(__file__))

from baidu_search_manager import BaiduSearchManager

# 修复 Windows 控制台编码
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


def format_result(result, index=None):
    """格式化单条搜索结果"""
    lines = []
    
    if index is not None:
        lines.append(f"[{index}] {result.get('title', 'N/A')}")
    else:
        lines.append(result.get('title', 'N/A'))
    
    lines.append(f"    URL: {result.get('url', 'N/A')}")
    
    if result.get('snippet'):
        snippet = result['snippet']
        if len(snippet) > 150:
            snippet = snippet[:150] + '...'
        lines.append(f"    摘要: {snippet}")
    
    if result.get('date'):
        lines.append(f"    日期: {result['date']}")
    
    if result.get('website'):
        lines.append(f"    来源: {result['website']}")
    
    return '\n'.join(lines)


def cmd_search(args):
    """执行搜索命令"""
    try:
        # 初始化管理器
        if args.api_key:
            manager = BaiduSearchManager(api_key=args.api_key)
        else:
            config_path = os.path.join(os.path.dirname(__file__), 'config.json')
            manager = BaiduSearchManager(config_file=config_path)
        
        # 准备资源类型
        resource_types = None
        if args.resource_type:
            resource_types = [{"type": args.resource_type, "top_k": args.limit}]
        
        # 执行搜索
        result = manager.search(
            query=args.query,
            api_type=args.api_type,
            max_results=args.limit,
            resource_types=resource_types,
            sites=args.sites,
            recency_filter=args.recency,
            safe_search=args.safe_search,
            include_date=not args.no_date
        )
        
        # JSON 输出
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return
        
        # 文本输出
        results = result.get('results', result) if not args.no_date else result
        date_ctx = result.get('date_context', {}) if not args.no_date else {}
        api_type = result.get('api_type', args.api_type) if not args.no_date else args.api_type
        
        # 处理不同 API 类型
        if api_type == "baike":
            # 百科词条结果
            entry = result.get('entry', {})
            print(f"搜索引擎: 百度百科")
            print(f"搜索关键词: {args.query}")
            if date_ctx:
                print(f"搜索日期: {date_ctx.get('date')} ({date_ctx.get('weekday')})")
            print(f"\n词条信息:\n")
            print(f"标题: {entry.get('title', 'N/A')}")
            print(f"URL: {entry.get('url', 'N/A')}")
            if entry.get('summary'):
                print(f"摘要: {entry['summary']}")
            if entry.get('content'):
                content = entry['content'][:500] + "..." if len(entry.get('content', '')) > 500 else entry.get('content', '')
                print(f"内容: {content}")
            return
        
        elif api_type == "miaodong_baike":
            # 秒懂百科视频结果
            video = result.get('video', {})
            print(f"搜索引擎: 秒懂百科")
            print(f"搜索关键词: {args.query}")
            if date_ctx:
                print(f"搜索日期: {date_ctx.get('date')} ({date_ctx.get('weekday')})")
            print(f"\n视频信息:\n")
            print(f"标题: {video.get('title', 'N/A')}")
            print(f"URL: {video.get('url', 'N/A')}")
            print(f"视频URL: {video.get('video_url', 'N/A')}")
            if video.get('duration'):
                print(f"时长: {video['duration']}秒")
            if video.get('description'):
                print(f"描述: {video['description']}")
            return
        
        elif api_type == "ai_chat":
            # AI 生成结果
            ai_result = result.get('result', {})
            print(f"搜索引擎: AI 智能搜索")
            print(f"搜索关键词: {args.query}")
            if date_ctx:
                print(f"搜索日期: {date_ctx.get('date')} ({date_ctx.get('weekday')})")
            print(f"\nAI 生成回答:\n")
            if ai_result.get('answer'):
                print(f"{ai_result['answer']}\n")
            if ai_result.get('sources'):
                print(f"\n参考来源 ({len(ai_result['sources'])} 条):")
                for i, source in enumerate(ai_result['sources'][:5], 1):
                    print(f"  [{i}] {source.get('title', 'N/A')}")
                    print(f"      {source.get('url', 'N/A')}")
            if ai_result.get('usage'):
                usage = ai_result['usage']
                print(f"\n模型使用: {usage.get('total_tokens', 0)} tokens")
            return
        
        # 默认：列表结果
        if not results:
            print("未找到结果")
            return
        
        api_name = {
            "web_search": "百度搜索",
            "baike": "百度百科",
            "miaodong_baike": "秒懂百科",
            "ai_chat": "AI 智能搜索"
        }.get(api_type, "百度搜索")
        
        print(f"搜索引擎: {api_name}")
        print(f"搜索关键词: {args.query}")
        if date_ctx:
            print(f"搜索日期: {date_ctx.get('date')} ({date_ctx.get('weekday')})")
        print(f"找到 {len(results)} 条结果:\n")
        
        for i, item in enumerate(results, 1):
            print(format_result(item, i))
            print()
        
    except Exception as e:
        print(f"搜索失败: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    """主入口"""
    parser = argparse.ArgumentParser(
        description='百度 AI 搜索工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s "百度千帆平台"
  %(prog)s "人工智能" --api-type baike
  %(prog)s "深度学习" --api-type miaodong_baike
  %(prog)s "什么是人工智能" --api-type ai_chat
  %(prog)s "人工智能" --json
  %(prog)s "Python教程" --limit 5
  %(prog)s "天气预报" --sites weather.com.cn
  %(prog)s "AI新闻" --recency week

API 类型:
  web_search     - 百度搜索（默认）
  baike          - 百度百科
  miaodong_baike - 秒懂百科（视频）
  ai_chat        - AI 智能搜索生成
"""
    )
    
    parser.add_argument('query', help='搜索关键词')
    
    parser.add_argument(
        '--api-type',
        choices=['web_search', 'baike', 'miaodong_baike', 'ai_chat'],
        default='web_search',
        help='API 类型（默认: web_search）'
    )
    
    parser.add_argument('--api-key', help='API 密钥（覆盖 config.json）')
    
    parser.add_argument('--limit', type=int, default=10, help='最大结果数（默认: 10）')
    
    parser.add_argument(
        '--type',
        dest='resource_type',
        choices=['web', 'video', 'image', 'aladdin'],
        help='资源类型'
    )
    
    parser.add_argument('--sites', nargs='+', help='指定站点')
    
    parser.add_argument(
        '--recency',
        choices=['week', 'month', 'semiyear', 'year'],
        help='时间过滤'
    )
    
    parser.add_argument('--safe-search', action='store_true', help='启用安全搜索')
    
    parser.add_argument('--json', action='store_true', help='JSON 格式输出')
    
    parser.add_argument('--no-date', action='store_true', help='禁用日期上下文')
    
    args = parser.parse_args()
    cmd_search(args)


if __name__ == '__main__':
    main()
