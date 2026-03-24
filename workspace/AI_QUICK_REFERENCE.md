# AI 快速参考手册

> 用途：当用户询问“在哪里点”“怎么配置”“帮我直接创建”“为什么失败”时，优先按本手册执行。  
> 原则：本手册只补充工具/技能说明之外的系统操作、图形化入口、接口格式、参数示例、排查路径。

## 一、总原则

### 1. 默认先执行，不先拒绝

当用户目标明确时，不要先回复“不能操作”或“当前无法完成”。优先判断：
- 这个操作前端能不能指导
- 这个操作后端有没有接口
- 当前是否缺关键参数

只要接口存在、参数可补齐，就应该直接执行或给出最短补参问题。

### 2. 回答顺序

1. 识别用户目标属于哪个模块
2. 告诉用户图形化入口在哪里
3. 如需直接操作，调用对应接口
4. 返回结果
5. 如失败，给出明确错误点、缺失字段和排查顺序

### 3. 文档中的两类能力要区分

- `有图形化入口`：前端已有面板，应该告诉用户点击路径
- `主要走接口/API`：前端当前没有完整操作面板，AI 应直接走接口或说明当前是数据层能力

## 二、图形化入口总览

## 1. 顶部工具栏

聊天主界面顶部右侧工具栏包含这些入口：
- `清空当前聊天`：删除当前会话消息
- `会话管理`：打开会话侧边面板
- `多智能体`：直接切到设置中的多智能体页
- `工具箱`：打开工具面板
- `记忆系统`：打开记忆面板
- `技能库`：打开 Skills 面板
- `定时任务`：打开 Cron 面板
- `时间线`：展开或收起右侧时间线
- `设置`：打开设置面板，默认进入 `通用`
- `语言切换`
- `主题切换`

补充：
- 点击左上角 `CountBot` 标题会打开左侧系统信息侧边栏

## 2. 设置面板结构

点击顶部 `设置` 后，左侧导航当前包含：
- `通用`
- `提供商配置`
- `模型参数`
- `用户信息`
- `记忆系统`
- `工作空间`
- `安全设置`
- `渠道配置`
- `编程工具`
- `多智能体`
- `导入导出`

其中：
- `用户信息` 下面有两个子页：`基础配置`、`性格编辑器`
- `记忆系统` 既可从顶部工具栏进入，也可从设置页签进入
- `多智能体` 也可从顶部工具栏直接打开
- `导入导出` 支持按配置节选择导出和导入

## 三、会话列表功能

## 1. 图形化入口

点击顶部 `会话管理` 按钮，打开右侧 `会话管理` 面板。

## 2. 当前会话面板能做什么

每个会话项支持：
- 点击会话名：切换会话
- 右上角 `+`：创建新会话
- `总结到记忆`：自动总结当前会话并写入长期记忆
- `导出会话`：导出完整会话上下文
- `编辑`：重命名会话
- `删除`：删除会话

## 3. 相关接口

- `GET /api/chat/sessions`
- `POST /api/chat/sessions`
- `PUT /api/chat/sessions/{session_id}`
- `DELETE /api/chat/sessions/{session_id}`
- `GET /api/chat/sessions/{session_id}/messages`
- `POST /api/chat/sessions/{session_id}/summarize`
- `GET /api/chat/sessions/{session_id}/export`

## 4. 创建会话参数

创建会话时，AI 至少要知道会话名称。

示例请求：
```json
POST /api/chat/sessions
{
  "name": "飞书日报助手"
}
```

## 5. 会话问题排查

用户说“会话切不过去、会话没了、导出失败”时，优先排查：
1. `GET /api/chat/sessions` 看会话是否存在
2. `GET /api/chat/sessions/{session_id}` 看会话详情
3. `GET /api/chat/sessions/{session_id}/messages` 看消息是否存在
4. 查看 `data/logs/` 中 chat 相关错误

## 四、Skills 入口、功能、参数

## 1. 图形化入口

点击顶部 `技能库` 按钮，打开右侧 `技能库` 面板。

## 2. Skills 面板当前功能

技能库面板支持：
- `创建技能`
- `刷新技能列表`
- 按状态过滤：`全部 / 已启用 / 已禁用 / 自动加载`
- 查看技能详情
- 启用或禁用技能

在技能详情弹窗中，用户还能看到：
- 技能名称
- 来源
- 状态
- 自动加载状态
- 技能内容

## 3. Skills 后端接口

- `GET /api/skills`
- `GET /api/skills/{name}`
- `POST /api/skills`
- `PUT /api/skills/{name}`
- `DELETE /api/skills/{name}`
- `POST /api/skills/{name}/toggle`
- `GET /api/skills/{name}/config`
- `PUT /api/skills/{name}/config`
- `GET /api/skills/{name}/config/status`
- `POST /api/skills/{name}/config/fix`
- `GET /api/skills/{name}/config/help`
- `POST /api/skills/reload`

## 4. 创建 skill 请求格式

创建技能时，AI 不能只知道字段名，必须知道请求体结构。

请求体格式：
- `name`：技能名称，创建后通常不建议变更
- `description`：技能描述
- `content`：技能主体内容，通常是 Markdown
- `autoLoad`：是否自动加载
- `requirements`：依赖列表

示例：
```json
POST /api/skills
{
  "name": "feishu-cron-helper",
  "description": "帮助配置飞书定时推送的技能",
  "content": "# Feishu Cron Helper\n\n用于指导或执行飞书定时推送配置。",
  "autoLoad": true,
  "requirements": [
    "需要飞书渠道已配置",
    "需要有效 chat_id"
  ]
}
```

## 5. 更新 skill 请求格式

```json
PUT /api/skills/feishu-cron-helper
{
  "description": "更新后的描述",
  "content": "# Feishu Cron Helper\n\n更新后的内容。",
  "autoLoad": true,
  "requirements": [
    "飞书渠道",
    "Cron 任务"
  ]
}
```

## 6. 切换 skill 启用状态

```json
POST /api/skills/feishu-cron-helper/toggle
{
  "enabled": true
}
```

## 7. Skill 配置问题怎么排查

优先顺序：
1. `GET /api/skills/{name}` 看技能是否存在
2. `GET /api/skills/{name}/config/status` 看配置状态
3. `GET /api/skills/{name}/config/help` 看缺什么
4. 修改配置后执行 `POST /api/skills/reload`
5. 查看日志和工具调用历史

## 8. 重要限制

- 只有 `workspace` 来源的 skill 适合直接新增、编辑、删除
- builtin 或 openclaw 技能通常不应直接覆盖
- 改完 skill 内容或配置后，最好 reload 一次

## 五、设置入口与功能

## 1. 通用

图形化路径：
- 顶部 `设置`
- 左侧选择 `通用`

可配置：
- 主题
- 界面语言
- 默认输出语言

说明：
- 顶部的 `语言切换`、`主题切换` 是快捷入口
- 用户只是想改显示偏好时，优先指导走 GUI，不必先查接口

## 2. 提供商配置

图形化路径：
- 顶部 `设置`
- 左侧选择 `提供商配置`

这个页面主要用于配置：
- provider 启用状态
- API Key
- API Base
- 默认模型
- 测试连接

相关接口：
- `GET /api/settings/providers`
- `GET /api/settings`
- `PUT /api/settings`
- `POST /api/settings/test-connection`

测试连接示例：
```json
POST /api/settings/test-connection
{
  "provider": "openai",
  "api_key": "sk-xxxx",
  "api_base": "https://api.openai.com/v1",
  "model": "gpt-4o-mini"
}
```

## 3. 模型参数

图形化路径：
- 顶部 `设置`
- 左侧选择 `模型参数`

这里控制全局模型运行参数，例如：
- `provider`
- `model`
- `temperature`
- `max_tokens`
- `max_iterations`

全局更新示例：
```json
PUT /api/settings
{
  "model": {
    "provider": "openai",
    "model": "gpt-4o-mini",
    "temperature": 0.7,
    "max_tokens": 4096,
    "max_iterations": 25
  }
}
```

## 4. 用户信息

图形化路径：
- 顶部 `设置`
- 左侧选择 `用户信息`

### 基础配置子页

可配置：
- AI 名称
- 用户称呼
- 用户常用地址
- 默认输出语言
- AI 性格
- 自定义 personality 文本
- 最大历史消息数
- 问候助手

### 性格编辑器子页

可做操作：
- 浏览内置性格
- 浏览自定义性格
- 新建自定义性格
- 编辑已有性格
- 复制性格
- 启用/禁用
- 删除自定义性格

## 5. 记忆系统

图形化路径：
- 顶部 `记忆系统`
- 或 顶部 `设置` -> 左侧 `记忆系统`

当前 GUI 明确支持：
- 查看长期记忆
- 切换到编辑模式直接修改长期记忆

需要统计、最近记录、关键词搜索时，优先直接走接口。

相关接口：
- `GET /api/memory/long-term`
- `PUT /api/memory/long-term`
- `GET /api/memory/stats`
- `GET /api/memory/recent?count=10`
- `POST /api/memory/search`

搜索示例：
```json
POST /api/memory/search
{
  "keywords": "日报 飞书",
  "max_results": 5
}
```

## 6. 工作空间

图形化路径：
- 顶部 `设置`
- 左侧选择 `工作空间`

支持：
- 设置工作空间路径
- 浏览选择目录
- 清理临时文件

相关接口：
- `POST /api/settings/workspace/select-directory`
- `GET /api/settings/workspace/info`
- `POST /api/settings/workspace/clean-temp`
- `POST /api/settings/workspace/set-path`

## 7. 安全设置

图形化路径：
- 顶部 `设置`
- 左侧选择 `安全设置`

可配置：
- 是否阻止危险命令
- 自定义拒绝规则
- 命令白名单
- 是否启用审计日志
- 命令超时
- 子代理超时
- 最大输出长度
- 是否限制在工作空间内

## 8. 渠道配置

图形化路径：
- 顶部 `设置`
- 左侧选择 `渠道配置`

当前属于重点页面，因为：
- 定时任务投递要依赖渠道
- 问候助手推送要依赖渠道
- 飞书、企业微信、微信、QQ、Telegram、钉钉、微博、小智 AI 等都在这里
- 当前前端已经支持多机器人账号配置，不再只是单账号表单

渠道页重点字段：
- `account_id`：机器人账号 ID，默认通常是 `default`
- `routing_mode`：账号默认路由，当前主要是 `ai` 或 `direct`
- `external_coding_profile`：当 `routing_mode=direct` 时应指定默认外部编程工具

相关接口：
- `GET /api/channels/list`
- `GET /api/channels/status`
- `POST /api/channels/test`
- `POST /api/channels/update`
- `GET /api/channels/{channel}/config`

## 9. 编程工具

图形化路径：
- 顶部 `设置`
- 左侧选择 `编程工具`

当前 GUI 支持：
- 新建和删除外部编程工具 profile
- 配置 `name`、`command`、`args`、`working_dir`
- 配置 `session_mode`、`history_message_count`
- 配置 `env`、`inherit_env`、`timeout`
- 对单个 profile 执行可用性检查

相关接口：
- `GET /api/settings/external-coding-tools`
- `PUT /api/settings/external-coding-tools`
- `POST /api/settings/external-coding-tools/check`

检查示例：
```json
POST /api/settings/external-coding-tools/check
{
  "profile": {
    "name": "codex",
    "enabled": true,
    "type": "cli",
    "command": "codex",
    "args": [],
    "working_dir": "",
    "env": {},
    "inherit_env": [
      "OPENAI_API_KEY"
    ],
    "session_mode": "history",
    "history_message_count": 10,
    "timeout": 1200,
    "success_exit_codes": [
      0
    ]
  }
}
```

## 10. 导入导出

图形化路径：
- 顶部 `设置`
- 左侧选择 `导入导出`

当前 GUI 支持：
- 按配置节选择导出
- 选择是否包含 API Keys
- 从 JSON 文件导入
- 选择合并模式或覆盖模式
- 前端会额外处理 `multiagent`、`codingplan` 这类复合配置节

相关接口：
- `GET /api/settings/export`
- `POST /api/settings/import`

导出示例：
```text
GET /api/settings/export?include_api_keys=false&sections=providers,model,persona,channels
```

导入示例：
```json
POST /api/settings/import
{
  "version": "1.0.0",
  "merge": true,
  "sections": [
    "providers",
    "model"
  ],
  "config": {
    "providers": {},
    "model": {
      "provider": "openai",
      "model": "gpt-4o-mini"
    }
  }
}
```

## 六、渠道配置与排查

## 1. 图形化路径

- 顶部 `设置`
- 左侧 `渠道配置`
- 选择 `飞书 / 企业微信 / 微信 / QQ / Telegram / 钉钉 / 微博 / 小智AI / Discord`

## 2. 多账号与默认路由

当前渠道页不是单机器人配置，而是支持：
- 主账号 + 多个附加账号
- 每个账号单独启用/停用
- 每个账号单独设置 `account_id`
- 每个账号单独设置 `routing_mode`
- 每个账号单独设置 `external_coding_profile`

关键规则：
- `account_id` 不填时，实际通常落到 `default`
- `routing_mode=direct` 时，必须同时配置 `external_coding_profile`
- 测试某个账号时，应该显式传 `account_id`

## 3. 飞书测试与保存

测试指定机器人账号示例：
```json
POST /api/channels/test
{
  "channel": "feishu",
  "account_id": "default",
  "config": {
    "enabled": true,
    "account_id": "default",
    "app_id": "cli_xxxxxxxx",
    "app_secret": "xxxxxxxx",
    "routing_mode": "ai",
    "external_coding_profile": ""
  }
}
```

保存多账号飞书配置示例：
```json
POST /api/channels/update
{
  "channel": "feishu",
  "config": {
    "enabled": true,
    "account_id": "default",
    "app_id": "cli_primaryxxxx",
    "app_secret": "primary-secret",
    "routing_mode": "ai",
    "external_coding_profile": "",
    "accounts": {
      "bot-dev": {
        "account_id": "bot-dev",
        "enabled": true,
        "app_id": "cli_devxxxx",
        "app_secret": "dev-secret",
        "routing_mode": "direct",
        "external_coding_profile": "codex"
      }
    }
  }
}
```

## 4. 微信扫码登录流程

微信当前已有完整 GUI，不是只能手动改配置：
- `设置` -> `渠道配置` -> `微信`
- 进入目标机器人账号
- 点击扫码登录，完成后自动填写数据，保存即可

接口流程：
1. `POST /api/channels/wechat/login/start`，传 `account_id` 和可选 `config`
2. 返回 `qrcode_url`、`session_key`
3. `POST /api/channels/wechat/login/poll` 轮询 `session_key`
4. 当 `status=confirmed` 时，后端会把登录结果合并回渠道配置并返回最新 `config`

轮询示例：
```json
POST /api/channels/wechat/login/poll
{
  "session_key": "wechat-login-session-key"
}
```

## 5. 渠道常见失败原因

- `app_id` / `client_id` / `token` / `secret` 本身错误
- 只做了测试，没有真正保存并启用渠道
- `account_id` 写错，导致测的是另一个机器人账号
- 多个机器人账号用了重复配置，被后端判定为冲突
- `routing_mode=direct` 但没填 `external_coding_profile`
- 微信二维码已过期，或者轮询没有到 `confirmed`
- 定时任务或问候助手只填了 `channel`，没填 `account_id` / `chat_id`

## 七、定时任务

## 1. 图形化入口

点击顶部 `定时任务` 打开右侧面板。

## 2. 图形化面板当前支持的操作

在 Job 编辑器里，用户能填写：
- 任务名称
- Cron 表达式
- 任务消息
- 是否把结果推送到渠道
- 推送渠道
- `account_id`
- chat_id
- 是否创建后立即启用

补充说明：
- 前端当前使用的是 5 段 Cron：`分 时 日 月 周`
- 前端表单在开启 `推送响应到渠道` 后，才会出现 `渠道`、`account_id` 和 `chat_id`
- 如果是 IM 渠道推送，建议显式写上 `account_id`；常见值是 `default`

## 3. 核心接口

- `GET /api/cron/jobs`
- `GET /api/cron/jobs/{job_id}`
- `POST /api/cron/jobs`
- `PUT /api/cron/jobs/{job_id}`
- `DELETE /api/cron/jobs/{job_id}`
- `POST /api/cron/jobs/{job_id}/run`
- `POST /api/cron/validate`

## 4. 创建定时任务的参数格式

请求体：
- `name`
- `schedule`
- `message`
- `enabled`
- `channel`
- `account_id`
- `chat_id`
- `deliver_response`
- `max_retries`
- `retry_delay`
- `delete_on_success`

补充说明：
- 不推送到渠道时，`channel`、`account_id`、`chat_id` 可以为 `null`
- 推送到 IM 渠道时，最好同时带上 `channel`、`account_id`、`chat_id`

示例一：普通内部任务
```json
POST /api/cron/jobs
{
  "name": "每天早上总结昨天会话",
  "schedule": "0 9 * * *",
  "message": "请总结昨天的重要对话，并生成 5 条待办建议。",
  "enabled": true,
  "channel": null,
  "account_id": null,
  "chat_id": null,
  "deliver_response": false,
  "max_retries": 1,
  "retry_delay": 60,
  "delete_on_success": false
}
```

示例二：推送到飞书
```json
POST /api/cron/jobs
{
  "name": "每天 9 点飞书日报",
  "schedule": "0 9 * * *",
  "message": "生成今天的工作日报，并用简洁中文输出。",
  "enabled": true,
  "channel": "feishu",
  "account_id": "default",
  "chat_id": "oc_xxxxxxxxxxxxx",
  "deliver_response": true,
  "max_retries": 2,
  "retry_delay": 120,
  "delete_on_success": false
}
```

## 5. 先校验再创建

示例：
```json
POST /api/cron/validate
{
  "schedule": "0 9 * * *"
}
```

AI 在用户说“帮我设个定时任务”时，最好先 validate，再 create。

## 6. 定时任务失败怎么排查

优先看：
1. `GET /api/cron/jobs/{job_id}` 中的 `last_status`
2. `last_error`
3. `run_count`
4. `error_count`
5. `next_run`

再继续查：
1. `POST /api/cron/validate`
2. `GET /api/channels/status`
3. `POST /api/channels/test`
4. `data/logs/`
5. `data/audit_logs/`

## 八、会话自定义配置：模型、API、Persona

## 1. 现实说明

当前这部分已经有明确的图形化入口，不再是“只有接口”：
- 顶部 `会话管理`
- 面板上方 `为当前会话单独设置 API / 模型 / 角色`
- 打开后进入 `会话配置` 面板，可直接启用或关闭当前会话的独立配置

所以当用户说“这个会话单独换模型、单独改 API Key”时：
- 优先告诉用户 GUI 入口
- 如果用户明确让 AI 直接改、或需要批量化/静默操作，再直接走接口

## 2. 接口

- `GET /api/chat/sessions/{session_id}/config`
- `PUT /api/chat/sessions/{session_id}/config`
- `DELETE /api/chat/sessions/{session_id}/config`

`GET /api/chat/sessions/{session_id}/config` 返回重点：
- `use_custom_config`
- `model_config`
- `persona_config`
- `global_defaults`

## 3. 模型配置参数格式

会话级 `model_config` 常用字段：
- `provider`
- `model`
- `temperature`
- `max_tokens`
- `max_iterations`
- `api_key`
- `api_base`

示例：
```json
PUT /api/chat/sessions/SESSION_ID/config
{
  "model_config": {
    "provider": "openai",
    "model": "gpt-4o-mini",
    "temperature": 0.3,
    "max_tokens": 4096,
    "max_iterations": 15,
    "api_key": "sk-xxxx",
    "api_base": "https://api.openai.com/v1"
  }
}
```

## 4. Persona 配置参数格式

会话级 `persona_config` 常用字段：
- `ai_name`
- `user_name`
- `user_address`
- `output_language`
- `personality`
- `custom_personality`：前端当前把它作为“自定义系统提示词/自定义角色提示”
- `max_history_messages`

示例：
```json
PUT /api/chat/sessions/SESSION_ID/config
{
  "persona_config": {
    "ai_name": "日报助手",
    "user_name": "Waner",
    "output_language": "中文",
    "personality": "custom",
    "custom_personality": "你是一个简洁、务实、偏项目管理风格的助理。",
    "max_history_messages": 50
  }
}
```

## 5. 同时提交模型和 persona

```json
PUT /api/chat/sessions/SESSION_ID/config
{
  "model_config": {
    "provider": "openai",
    "model": "gpt-4o-mini",
    "temperature": 0.5,
    "max_tokens": 4096,
    "max_iterations": 20,
    "api_key": "sk-xxxx",
    "api_base": "https://api.openai.com/v1"
  },
  "persona_config": {
    "ai_name": "产品助理",
    "user_name": "Waner",
    "output_language": "中文",
    "personality": "custom",
    "custom_personality": "你要像一个负责、简洁、强执行的产品经理助理。",
    "max_history_messages": 80
  }
}
```

## 6. 重置会话自定义配置

```json
DELETE /api/chat/sessions/SESSION_ID/config
```

## 7. 会话配置失败怎么排查

1. 会话 ID 是否存在
2. `provider` 是否已启用
3. `api_key` 是否有效
4. `api_base` 是否错误
5. `model` 名称是否可用
6. 查看发送消息时的具体报错

## 8. 用户问“现在使用什么模型”时怎么回复

优先顺序：
1. 如果用户问的是“当前这个会话”，先查 `GET /api/chat/sessions/{session_id}/config`
2. 如果 `use_custom_config=true`，说明当前会话用了独立模型配置
3. 如果没有会话级覆盖，再查 `GET /api/settings`
4. 如果用户问的是团队模型，再查 `GET /api/agent-teams/{team_id}/config`

不要只回复一个模型名，也不要让用户自己去设置里找。


## 十、统一排查路径

## 1. 配置问题

先查：
- `GET /api/settings`
- `GET /api/chat/sessions/{session_id}/config`
- `GET /api/agent-teams/{team_id}/config`

## 2. 渠道问题

先查：
- `GET /api/channels/status`
- `POST /api/channels/test`
- `GET /api/channels/{channel}/config`

## 3. 定时任务问题

先查：
- `GET /api/cron/jobs`
- `GET /api/cron/jobs/{job_id}`
- `POST /api/cron/validate`

## 4. 技能问题

先查：
- `GET /api/skills`
- `GET /api/skills/{name}`
- `GET /api/skills/{name}/config/status`
- `GET /api/skills/{name}/config/help`

## 5. 记忆问题

先查：
- `GET /api/memory/long-term`
- `GET /api/memory/stats`
- `POST /api/memory/search`

## 6. 外部编程工具 / 直通路由问题

先查：
- `GET /api/settings/external-coding-tools`
- `POST /api/settings/external-coding-tools/check`
- `GET /api/channels/{channel}/config`

## 7. 多智能体问题

先查：
- `GET /api/agent-teams/`
- `GET /api/agent-teams/{team_id}`
- `GET /api/agent-teams/{team_id}/config`

## 8. 日志位置

- `data/logs/CountBot_YYYY-MM-DD.log`
- `data/logs/error_YYYY-MM-DD.log`
- `data/logs/{channel}_worker_*.log`
- `data/audit_logs/audit_YYYY-MM-DD_*.log`

## 十一、最终要求

- 回答优先中文
- 先告诉用户图形化入口
- 如前端当前没有完整 GUI，就直接走接口
- 不要只写字段名，要写请求体格式和示例
- 用户目标明确时，优先执行，不要先拒绝
