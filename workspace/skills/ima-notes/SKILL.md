---
name: ima-notes
description: 通过 IMA OpenAPI 处理笔记任务。支持搜索笔记、读取笔记、列出笔记、新建笔记、追加笔记。用户提到笔记、备忘录、记一下、追加到某篇笔记时使用。
---

# IMA Notes

入口：

```bash
python skills/ima-notes/scripts/ima_notes_tool.py <command> ...
```

## 执行规则

- 用户说“搜笔记、找笔记、看看有没有笔记”时，先 `search-notes`
- 看正文用 `read-note`
- 明确说新建时用 `create-note`
- 明确说追加到某一篇时才用 `append-note`
- 目标不明确时，不要猜；先搜索或先确认
- 默认直接返回命中的标题和摘要；只有需要结构化结果时才加 `--json`

## 常用命令

```bash
python skills/ima-notes/scripts/ima_notes_tool.py search-notes --keyword "周报"
python skills/ima-notes/scripts/ima_notes_tool.py search-notes --search-field content --keyword "复盘"
python skills/ima-notes/scripts/ima_notes_tool.py read-note --title "会议纪要"
python skills/ima-notes/scripts/ima_notes_tool.py list-notes --limit 20
python skills/ima-notes/scripts/ima_notes_tool.py create-note --title "新笔记" --content "正文"
python skills/ima-notes/scripts/ima_notes_tool.py append-note --title "会议纪要" --content "补充内容"
```

## 写入安全

- `append-note` 会真实修改已有笔记，目标不唯一时不要直接执行
- 需要配置时查看 `scripts/config.json` 和 `config.help.md`

## 如何配置 

下载最新的IMA客户端（比如Android），登陆后点击 “我” --> Claw配置  --> 复制  client_id和api_key参数，提供给CountBot后会自动调用文件编辑工具修改config.json。