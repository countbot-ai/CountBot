---
name: cron-manager
description: 定时任务管理。创建、查看、修改、删除定时任务，管理任务会话数据。当用户需要设置提醒、定时执行任务、管理调度计划时使用。
version: 1.0.0
always: false
---

# 定时任务管理

通过命令行管理 CountBot 的定时任务系统，支持完整的 CRUD 操作和会话数据管理。

## 使用场景

- 用户说"每天早上9点提醒我开会" -> 创建定时任务
- 用户说"帮我设置一个每小时查天气的任务" -> 创建定时任务
- 用户说"看看我有哪些定时任务" -> 列出任务
- 用户说"把那个天气任务改成每2小时执行" -> 修改任务
- 用户说"删掉那个新闻任务" -> 删除任务
- 用户说"暂停/恢复某个任务" -> 禁用/启用任务
- 用户说"立即执行一次那个任务" -> 手动触发
- 用户说"看看天气任务的历史消息" -> 查看会话消息
- 用户说"清理一下定时任务的历史记录" -> 清理会话

## 命令行调用

所有操作通过 `exec` 工具执行脚本：

```bash
python3 skills/cron-manager/scripts/cron_manager.py <command> [args]
```

### 创建任务

```bash
# 基本创建（仅在系统内执行，不推送到渠道）
python3 skills/cron-manager/scripts/cron_manager.py create --name "每日天气" --schedule "0 9 * * *" --message "查询今天的天气并生成播报"

# 创建并推送到当前渠道（需要指定 channel 和 chat_id）
python3 skills/cron-manager/scripts/cron_manager.py create --name "每日天气" --schedule "0 9 * * *" --message "查询今天的天气并生成播报" --channel feishu --chat-id ou_xxxx --deliver
```

### 列出任务

```bash
python3 skills/cron-manager/scripts/cron_manager.py list
```

### 查看任务详情

```bash
python3 skills/cron-manager/scripts/cron_manager.py info <job_id>
```

### 修改任务

```bash
# 修改调度时间
python3 skills/cron-manager/scripts/cron_manager.py update <job_id> --schedule "0 */2 * * *"

# 修改名称
python3 skills/cron-manager/scripts/cron_manager.py update <job_id> --name "新名称"

# 修改执行消息
python3 skills/cron-manager/scripts/cron_manager.py update <job_id> --message "新的执行指令"

# 修改渠道投递
python3 skills/cron-manager/scripts/cron_manager.py update <job_id> --channel telegram --chat-id 123456 --deliver true
```

### 删除任务

```bash
python3 skills/cron-manager/scripts/cron_manager.py delete <job_id>
```

### 启用/禁用任务

```bash
python3 skills/cron-manager/scripts/cron_manager.py enable <job_id>
python3 skills/cron-manager/scripts/cron_manager.py disable <job_id>
```

### 手动触发执行

```bash
python3 skills/cron-manager/scripts/cron_manager.py run <job_id>
```

### 验证 Cron 表达式

```bash
python3 skills/cron-manager/scripts/cron_manager.py validate "0 9 * * *"
```

### 查看任务会话消息

```bash
python3 skills/cron-manager/scripts/cron_manager.py messages <job_id> --limit 20
```

### 清理任务会话消息

```bash
# 保留最近10条
python3 skills/cron-manager/scripts/cron_manager.py clean <job_id> --keep 10

# 清空所有消息
python3 skills/cron-manager/scripts/cron_manager.py clean <job_id> --keep 0
```

### 重置任务会话

```bash
python3 skills/cron-manager/scripts/cron_manager.py reset <job_id>
```

## Cron 表达式参考

格式: `分钟 小时 日 月 星期`

| 表达式 | 含义 |
|--------|------|
| `0 9 * * *` | 每天 9:00 |
| `*/30 * * * *` | 每 30 分钟 |
| `0 9 * * 1-5` | 工作日 9:00 |
| `0 0 1 * *` | 每月 1 日 0:00 |
| `0 */2 * * *` | 每 2 小时整点 |
| `0 8,12,18 * * *` | 每天 8:00、12:00、18:00 |

## 注意事项

- job_id 支持前缀匹配，输入前几位即可
- 内置系统任务完全隐藏，不可见也不可操作
- message 字段是任务执行时发送给 AI 的指令，应该写清楚要做什么
- 创建任务时如果需要推送结果到渠道，必须同时指定 --channel、--chat-id 和 --deliver
- clean 操作不可撤销，清理前建议先用 messages 查看内容
- reset 会删除整个会话，任务下次执行时会自动创建新会话

## 渠道自动识别

当用户通过飞书、钉钉、QQ、Telegram 等渠道与 AI 对话时，系统提示词中会自动包含当前渠道信息：

```
Channel: feishu
Chat ID: ou_xxxx
```

创建定时任务时，应主动利用这些信息：
- 如果用户说"每天提醒我"，自动使用当前渠道和 chat_id 作为投递目标
- 如果用户说"推送到这个群"，从上下文获取 channel 和 chat_id
- 如果是网页端对话（无渠道信息），创建任务时不设置投递，仅在系统内执行

示例：用户在飞书群中说"每天9点提醒我看天气"

```bash
python3 skills/cron-manager/scripts/cron_manager.py create --name "每日天气提醒" --schedule "0 9 * * *" --message "查询今天的天气并生成播报" --channel feishu --chat-id ou_xxxx --deliver
```
