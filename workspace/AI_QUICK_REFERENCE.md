# AI 快速参考手册

> 用途：当用户询问“在哪里点”“怎么配置”“帮我直接创建”“为什么失败”时，优先按本手册执行。  
> 原则：不要重复介绍 tools list 和 skills list，本手册只补充工具/技能说明之外的系统操作、图形化入口、接口格式、参数示例、排查路径。

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
- `工具箱`：打开工具面板
- `记忆系统`：打开记忆面板
- `技能库`：打开 Skills 面板
- `定时任务`：打开 Cron 面板
- `设置`：打开设置面板
- `语言切换`
- `主题切换`

补充：
- 点击左上角 `CountBot` 标题会打开左侧系统信息侧边栏
- 部分快捷键已内置，例如 `Ctrl/Cmd + ,` 可打开设置

## 2. 侧边面板有哪些

当前聊天页可以打开这些右侧面板：
- `会话管理`
- `工具箱`
- `记忆系统`
- `技能库`
- `定时任务`
- `设置`

这几个属于现成 GUI，优先用 UI 路径解释。

## 3. 设置面板结构

点击顶部 `设置` 后，左侧导航包含：
- `提供商配置`
- `模型参数`
- `用户信息`
- `工作空间`
- `安全设置`
- `渠道配置`

其中 `用户信息` 下面还有两个子页：
- `基础配置`
- `性格编辑器`

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

## 1. 提供商配置

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

## 2. 模型参数

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

## 3. 用户信息

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

## 4. 工作空间

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

## 5. 安全设置

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

## 6. 渠道配置

图形化路径：
- 顶部 `设置`
- 左侧选择 `渠道配置`

当前属于重点页面，因为：
- 定时任务投递要依赖渠道
- 问候助手推送要依赖渠道
- 飞书、QQ、Telegram、钉钉等配置都在这里

相关接口：
- `GET /api/channels/list`
- `GET /api/channels/status`
- `POST /api/channels/test`
- `POST /api/channels/update`
- `GET /api/channels/{channel}/config`

## 六、飞书渠道配置与排查

## 1. 图形化路径

- 顶部 `设置`
- 左侧 `渠道配置`
- 选择 `飞书`

## 2. 飞书测试接口

示例：
```json
POST /api/channels/test
{
  "channel": "feishu",
  "config": {
    "enabled": true,
    "app_id": "cli_xxxxxxxx",
    "app_secret": "xxxxxxxx"
  }
}
```

## 3. 保存飞书配置

示例：
```json
POST /api/channels/update
{
  "channel": "feishu",
  "config": {
    "enabled": true,
    "app_id": "cli_xxxxxxxx",
    "app_secret": "xxxxxxxx"
  }
}
```

## 4. 飞书常见失败原因

- `app_id` 格式不对，通常应以 `cli_` 开头
- `app_secret` 错误
- 只做了格式校验，还没真正启用渠道
- 定时任务里没填 `chat_id`
- 定时任务没打开 `deliver_response`

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
- chat_id
- 是否创建后立即启用

补充说明：
- 前端当前使用的是 5 段 Cron：`分 时 日 月 周`
- 前端表单在开启 `推送响应到渠道` 后，才会出现 `渠道` 和 `chat_id`

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
- `chat_id`
- `deliver_response`
- `max_retries`
- `retry_delay`
- `delete_on_success`

示例一：普通内部任务
```json
POST /api/cron/jobs
{
  "name": "每天早上总结昨天会话",
  "schedule": "0 9 * * *",
  "message": "请总结昨天的重要对话，并生成 5 条待办建议。",
  "enabled": true,
  "channel": null,
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

## 八、问候助手

## 1. 图形化入口

图形化路径：
- 顶部 `设置`
- 左侧 `用户信息`
- 子页 `基础配置`
- 找到 `问候助手`

界面中通常包含：
- 开启问候助手
- 推送渠道
- 目标 chat_id
- Cron 检查频率
- 空闲阈值
- 每天问候次数
- 免打扰时间

## 2. 对应配置位置

问候助手配置属于 `persona.heartbeat`。

相关接口：
- `GET /api/settings`
- `PUT /api/settings`

## 3. 配置参数格式

关键字段：
- `enabled`
- `channel`
- `chat_id`
- `schedule`
- `idle_threshold_hours`
- `quiet_start`
- `quiet_end`
- `max_greets_per_day`

示例：
```json
PUT /api/settings
{
  "persona": {
    "heartbeat": {
      "enabled": true,
      "channel": "feishu",
      "chat_id": "oc_xxxxxxxxxxxxx",
      "schedule": "0 * * * *",
      "idle_threshold_hours": 4,
      "quiet_start": 21,
      "quiet_end": 8,
      "max_greets_per_day": 2
    }
  }
}
```

## 4. 问候助手为什么不发

常见原因：
- 已启用，但没配置 `channel` 或 `chat_id`
- 飞书渠道本身无效
- 当前处于免打扰时间
- 用户并没有满足空闲时长
- 当天问候次数已达上限
- `schedule` 设置过稀，检查频率太低

## 5. 问候助手排查顺序

1. `GET /api/settings` 看 heartbeat 是否开启
2. 检查 `channel` 和 `chat_id`
3. 测试飞书渠道
4. 查 `heartbeat`、`cron` 日志
5. 确认不是免打扰或空闲阈值问题

## 九、会话自定义配置：模型、API、Persona

## 1. 现实说明

当前这部分主要是接口能力，不是完整图形化表单。  
所以当用户说“这个会话单独换模型、单独改 API Key”，AI 应优先直接走接口。

## 2. 接口

- `GET /api/chat/sessions/{session_id}/config`
- `PUT /api/chat/sessions/{session_id}/config`
- `DELETE /api/chat/sessions/{session_id}/config`

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
- `custom_personality`
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

## 十、自定义角色

## 1. 图形化入口

图形化路径：
- 顶部 `设置`
- 左侧 `用户信息`
- 子页 `性格编辑器`

这个页面支持：
- 查看内置性格
- 查看自定义性格
- 创建性格
- 编辑性格
- 复制性格
- 启用/禁用性格
- 删除自定义性格

## 2. 后端接口

- `GET /api/personalities`
- `GET /api/personalities/{personality_id}`
- `POST /api/personalities`
- `PUT /api/personalities/{personality_id}`
- `DELETE /api/personalities/{personality_id}`
- `POST /api/personalities/{personality_id}/duplicate`

## 3. 创建角色参数格式

关键字段：
- `id`
- `name`
- `description`
- `traits`
- `speaking_style`
- `icon`

`id` 规则：
- 只能包含小写字母、数字、下划线、连字符

示例：
```json
POST /api/personalities
{
  "id": "pm_assistant",
  "name": "产品助理",
  "description": "擅长需求整理、优先级判断和任务推进。",
  "traits": [
    "结构化",
    "简洁",
    "强执行",
    "结果导向"
  ],
  "speaking_style": "简明、直接、偏项目管理风格",
  "icon": "Briefcase"
}
```

## 4. 更新角色示例

```json
PUT /api/personalities/pm_assistant
{
  "name": "产品经理助理",
  "description": "更偏向项目推进和结果交付。",
  "traits": [
    "结构化",
    "务实",
    "高执行",
    "结果导向"
  ],
  "speaking_style": "短句、清晰、有主次",
  "icon": "Briefcase",
  "is_active": true
}
```

## 5. 复制角色示例

```json
POST /api/personalities/grumpy/duplicate
{
  "new_id": "grumpy_copy",
  "new_name": "嘴硬但负责（副本）"
}
```

## 6. 角色问题排查

常见问题：
- `id` 重复
- `id` 格式不合法
- `traits` 为空
- 试图删除 builtin 角色

建议：
- builtin 角色优先复制后再改
- 不要直接删内置角色

## 十一、多 Agent 团队

## 1. 现实说明

当前多 Agent 团队主要是后端接口能力，不是完整的图形化管理面板。  
所以当用户说“帮我创建一个智能体团队”，AI 应直接按接口结构创建，而不是只给概念说明。

## 2. 创建团队时必须知道的结构

创建团队时关键字段：
- `name`
- `description`
- `mode`
- `agents`
- `is_active`
- `cross_review`
- `enable_skills`

`mode` 取值：
- `pipeline`：顺序处理
- `graph`：按依赖关系执行
- `council`：多视角讨论汇总

## 3. agent 列表格式

`agents` 是数组，每个 agent 可包含：
- `id`
- `role`
- `system_prompt`
- `task`
- `perspective`
- `depends_on`
- `condition`

字段含义：
- `id`：团队内唯一标识
- `role`：角色名
- `system_prompt`：这个角色长期系统提示词
- `task`：该角色在流程中的具体任务
- `perspective`：用于 council 模式的视角标签
- `depends_on`：依赖哪些 agent 先完成
- `condition`：graph 模式的条件执行规则

## 4. 创建团队的完整示例

### pipeline 示例

```json
POST /api/agent-teams/
{
  "name": "日报生成团队",
  "description": "先收集信息，再整理，再输出日报",
  "mode": "pipeline",
  "is_active": true,
  "cross_review": false,
  "enable_skills": true,
  "agents": [
    {
      "id": "collector",
      "role": "信息收集员",
      "system_prompt": "你负责收集输入信息并提炼关键事实。",
      "task": "整理用户提供的工作内容、会议记录和待办事项。",
      "perspective": null,
      "depends_on": [],
      "condition": null
    },
    {
      "id": "writer",
      "role": "日报撰写员",
      "system_prompt": "你负责将整理后的信息输出成正式日报。",
      "task": "根据上一步信息生成简洁、正式的中文日报。",
      "perspective": null,
      "depends_on": [],
      "condition": null
    }
  ]
}
```

### graph 示例

```json
POST /api/agent-teams/
{
  "name": "需求评审团队",
  "description": "按依赖顺序做分析、测试评估和总结",
  "mode": "graph",
  "is_active": true,
  "cross_review": false,
  "enable_skills": false,
  "agents": [
    {
      "id": "analyst",
      "role": "需求分析师",
      "system_prompt": "你负责拆解需求和风险。",
      "task": "分析需求目标、边界和潜在风险。",
      "perspective": null,
      "depends_on": [],
      "condition": null
    },
    {
      "id": "tester",
      "role": "测试设计师",
      "system_prompt": "你负责设计测试方案。",
      "task": "基于分析结果输出测试点和验收标准。",
      "perspective": null,
      "depends_on": ["analyst"],
      "condition": null
    },
    {
      "id": "summarizer",
      "role": "总结员",
      "system_prompt": "你负责汇总结论。",
      "task": "综合前两个节点结果输出最终结论。",
      "perspective": null,
      "depends_on": ["analyst", "tester"],
      "condition": null
    }
  ]
}
```

### council 示例

```json
POST /api/agent-teams/
{
  "name": "多视角评审团队",
  "description": "从产品、技术、测试三个视角给出评审意见",
  "mode": "council",
  "is_active": true,
  "cross_review": true,
  "enable_skills": false,
  "agents": [
    {
      "id": "pm",
      "role": "产品经理",
      "system_prompt": "你从产品价值和用户体验角度评审。",
      "task": "",
      "perspective": "产品视角",
      "depends_on": [],
      "condition": null
    },
    {
      "id": "dev",
      "role": "技术负责人",
      "system_prompt": "你从实现复杂度和架构风险角度评审。",
      "task": "",
      "perspective": "技术视角",
      "depends_on": [],
      "condition": null
    },
    {
      "id": "qa",
      "role": "测试负责人",
      "system_prompt": "你从测试风险和验收覆盖角度评审。",
      "task": "",
      "perspective": "测试视角",
      "depends_on": [],
      "condition": null
    }
  ]
}
```

## 5. 团队模型配置

团队模型配置不要改全局设置，应使用团队专属配置接口。

接口：
- `GET /api/agent-teams/{team_id}/config`
- `PUT /api/agent-teams/{team_id}/config`
- `DELETE /api/agent-teams/{team_id}/config`

可设置字段：
- `provider`
- `model`
- `temperature`
- `max_tokens`
- `api_key`
- `api_base`

示例：
```json
PUT /api/agent-teams/TEAM_ID/config
{
  "provider": "openai",
  "model": "gpt-4o-mini",
  "temperature": 0.4,
  "max_tokens": 4096,
  "api_key": "sk-xxxx",
  "api_base": "https://api.openai.com/v1"
}
```

## 6. 多 Agent 团队失败怎么排查

1. 团队是否存在
2. `mode` 是否和 agents 结构匹配
3. `depends_on` 是否引用了不存在的 agent id
4. `system_prompt`、`task` 是否过弱或为空
5. 是否启用了自定义模型但没填全参数
6. 是否需要技能却没开 `enable_skills`

## 十二、统一排查路径

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

## 5. 日志位置

- `data/logs/CountBot_YYYY-MM-DD.log`
- `data/logs/error_YYYY-MM-DD.log`
- `data/logs/{channel}_worker_*.log`
- `data/audit_logs/audit_YYYY-MM-DD_*.log`

## 十三、最终要求

- 回答优先中文
- 先告诉用户图形化入口
- 如前端当前没有完整 GUI，就直接走接口
- 不要只写字段名，要写请求体格式和示例
- 用户目标明确时，优先执行，不要先拒绝
