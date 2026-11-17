---
name: ima-knowledge-base
description: 通过 IMA OpenAPI 处理知识库任务。支持知识库内容搜索、命中详情查看、条目浏览、列出知识库、上传文件、导入网页。用户提到知识库、资料库、上传到知识库、导入网页、搜知识库时使用。
---

# IMA Knowledge Base

入口：

```bash
python skills/ima-knowledge-base/scripts/ima_kb_tool.py <command> ...
```

## 执行规则

- 用户说“搜、查、找、看看有没有”时，先 `search-kb`
- 默认直接返回命中片段，不堆字段
- `search-kb` 搜的是内容，不是知识库列表
- 用户给了 `kb-id` 或 `kb-name` 时，加定向参数
- 默认优先 `--keyword`，只有明确要把多个词合成一次搜索串时才用 `--query`
- 宽搜建议加 `--show 5 --limit 10`；知识库很大再加 `--search-pages 2` 或更高

## 查看单条结果

- 默认先 `show-kb-hit`
- 只有命中像图片、截图、OCR 文档、菜单图，或 `show-kb-hit` 太短时，才用 `inspect-kb-hit`
- 一条 `--keyword "推荐 菜单 餐厅 美食"` 会拆成多次搜索，同一标题可能重复出现
- 宽搜后稳定定位优先级：更窄关键词 > `--title` > `--media-id` > `--pick`

## 常用命令

```bash
python skills/ima-knowledge-base/scripts/ima_kb_tool.py search-kb --keyword "orslow"
python skills/ima-knowledge-base/scripts/ima_kb_tool.py search-kb --keyword "推荐 菜单 餐厅 美食" --show 5 --limit 10
python skills/ima-knowledge-base/scripts/ima_kb_tool.py search-kb --kb-name "个人知识库" --keyword "菜单"
python skills/ima-knowledge-base/scripts/ima_kb_tool.py show-kb-hit --keyword "orslow" --pick 1
python skills/ima-knowledge-base/scripts/ima_kb_tool.py inspect-kb-hit --keyword "orslow" --pick 1
python skills/ima-knowledge-base/scripts/ima_kb_tool.py list-kb
python skills/ima-knowledge-base/scripts/ima_kb_tool.py list-kb-items --kb-name "个人知识库" --limit 20
python skills/ima-knowledge-base/scripts/ima_kb_tool.py upload-file --kb-name "个人知识库" --file "/path/to/report.pdf"
python skills/ima-knowledge-base/scripts/ima_kb_tool.py import-url --kb-name "个人知识库" --url "https://example.com"
```

## 推荐类问题

用户问“知识库里有什么推荐”时：

1. 先宽搜：`search-kb --keyword "推荐 菜单 餐厅 美食" --show 5 --limit 10`
2. 命中太杂就补对象词，例如 `search-kb --keyword "orslow 推荐"`
3. 锁定单条后先 `show-kb-hit`
4. 只有需要 OCR 扩展片段时才 `inspect-kb-hit`

## 写入安全

- `upload-file`、`import-url` 会真实写入知识库，执行前先确认目标知识库
- 需要配置时查看 `scripts/config.json` 和 `config.help.md`

## 如何配置 

下载最新的IMA客户端（比如Android），登陆后点击 “我” --> Claw配置  --> 复制  client_id和api_key参数，提供给CountBot后会自动调用文件编辑工具修改config.json。