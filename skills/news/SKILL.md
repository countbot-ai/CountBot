---
name: news
description: 新闻与资讯查询。获取中文新闻和全球 AI 技术资讯，支持按分类查询（时政、财经、科技、社会、国际、体育、娱乐、AI 技术、AI 社区）。当用户询问最新新闻、AI 动态、行业资讯时使用。
homepage: https://github.com/countbot-ai/CountBot
---

# 新闻与资讯查询

通过 RSS 源和网页抓取获取中文新闻和全球 AI 资讯，支持多分类、关键词过滤。

## 无需配置

此技能开箱即用，无需 API Key。

## 命令行调用

```bash
# 获取热点新闻（默认）
python3 skills/news/scripts/news.py hot

# AI新闻资讯查询
python3 skills/news/scripts/news.py category --cat ai --limit 20

# 按分类查询
python3 skills/news/scripts/news.py category --cat tech
python3 skills/news/scripts/news.py category --cat finance
python3 skills/news/scripts/news.py category --cat ai
python3 skills/news/scripts/news.py category --cat ai-community

# 关键词搜索
python3 skills/news/scripts/news.py hot --keyword AI
python3 skills/news/scripts/news.py category --cat ai --keyword GPT

# 控制摘要长度（默认 100 字符）
python3 skills/news/scripts/news.py category --cat ai --detail 500    # 显示 500 字符摘要
python3 skills/news/scripts/news.py category --cat ai --detail -1     # 显示全文
python3 skills/news/scripts/news.py category --cat ai --detail 0      # 不显示摘要

# 指定返回条数
python3 skills/news/scripts/news.py hot --limit 20

# JSON 格式输出（包含完整正文，不截断）
python3 skills/news/scripts/news.py hot --json

# 查看所有支持的分类和来源
python3 skills/news/scripts/news.py sources
```

## 支持的新闻分类

### 中文新闻

| 分类 | 参数值 | 来源 |
|------|--------|------|
| 热点要闻 | `hot` | 人民网、新华网、澎湃新闻 |
| 时政 | `politics` | 人民网时政、新华网政务 |
| 财经 | `finance` | 新浪财经、东方财富 |
| 科技 | `tech` | 36氪、IT之家 |
| 社会 | `society` | 中国新闻网、澎湃新闻 |
| 国际 | `world` | 环球网、参考消息 |
| 体育 | `sports` | 新浪体育、虎扑 |
| 娱乐 | `entertainment` | 新浪娱乐 |

### AI 技术与资讯

| 分类 | 参数值 | 来源 |
|------|--------|------|
| AI 技术 | `ai` | MIT Tech Review、OpenAI Blog、Google AI Blog、DeepMind Blog、Latent Space、Interconnects、One Useful Thing、KDnuggets |
| AI 社区 | `ai-community` | AI News Daily、Sebastian Raschka、Hacker News、Product Hunt |

AI 源说明：

- MIT Technology Review — MIT 科技评论，AI 与前沿技术深度报道
- OpenAI Blog — OpenAI 官方博客，模型发布与研究动态
- Google AI Blog — Google AI 研究与产品更新
- DeepMind Blog — DeepMind 研究进展
- Latent Space — AI 工程师社区播客与文章
- Interconnects — Nathan Lambert 的 AI 技术深度分析
- One Useful Thing — Ethan Mollick 的 AI 实践应用分享
- KDnuggets — AI/ML 技术文章聚合
- AI News Daily — AI 行业每日新闻汇总
- Sebastian Raschka — 机器学习深度技术博客
- Hacker News — 科技新闻与讨论社区
- Product Hunt — 新产品发现平台（含 AI 产品）

## AI 调用场景

用户说"今天有什么新闻"：

```bash
python3 skills/news/scripts/news.py hot --limit 10
```

用户说"最近 AI 有什么新动态"：

```bash
python3 skills/news/scripts/news.py category --cat ai --limit 10
```

用户说"有什么新的 AI 产品"：

```bash
python3 skills/news/scripts/news.py category --cat ai-community --limit 10
```

用户说"搜一下关于 GPT 的新闻"：

```bash
python3 skills/news/scripts/news.py category --cat ai --keyword GPT --limit 15
```

用户想深入阅读某篇文章：

```bash
# 使用 --detail -1 获取 RSS 全文内容
python3 skills/news/scripts/news.py category --cat ai --keyword "关键词" --detail -1 --limit 5

# 或使用 --json 获取完整 JSON（含全文）
python3 skills/news/scripts/news.py category --cat ai --keyword "关键词" --json --limit 5
```

获取新闻后，整理为简洁的列表返回给用户，包含标题、来源和链接。英文内容可适当翻译摘要。

### 深入阅读策略

当用户想详细了解某篇新闻时，按以下优先级获取全文：

1. **首选：`--detail -1` 或 `--json`** — 直接从 RSS 源获取全文内容，无需额外网络请求
2. **备选：`web_fetch`（仅限中文新闻源）** — 人民网、新华网、澎湃新闻、36氪等中文站点通常允许抓取
3. **不要对 AI 类源使用 `web_fetch`** — OpenAI Blog、MIT Tech Review、Google AI Blog、DeepMind Blog 等网站会返回 403/404，无法抓取

## 注意事项

- 纯 Python 标准库实现，无需额外依赖
- RSS 源可能因网站调整而失效，脚本会自动跳过失败的源
- AI 类源为英文内容，返回给用户时可适当翻译
- 多数 AI 博客网站（OpenAI、Google AI、DeepMind、MIT Tech Review 等）会阻止 `web_fetch` 直接访问（返回 403/404），因此深入阅读 AI 文章应使用 `--detail -1` 从 RSS 获取全文，而非尝试抓取原始链接
- 中文新闻源（人民网、澎湃、36氪等）通常允许 `web_fetch` 抓取详情页
