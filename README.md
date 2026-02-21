<div align="center">
  <img src="https://github.com/user-attachments/assets/d42ee929-a9a9-4017-a07b-9eb66670bcc3" alt="CountBot Logo" width="180">
  <p>轻量级、可扩展的 AI Agent 框架 | 专为中文用户和国内大模型优化</p>

  <p>
    <a href="https://github.com/countbot-ai/countbot/stargazers"><img src="https://img.shields.io/github/stars/countbot-ai/countbot?style=social" alt="GitHub stars"></a>
    <a href="https://github.com/countbot-ai/countbot"><img src="https://img.shields.io/badge/Python-3.11+-blue.svg" alt="Python"></a>
    <a href="https://github.com/countbot-ai/countbot"><img src="https://img.shields.io/badge/代码量-~21K行-brightgreen.svg" alt="代码量"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License"></a>
  </p>
</div>

---

## 最新动态

- 2026年2月21日 - CountBot 正式开源，代码规范化重构
- 2026年2月19日 - CountBot 项目正式上线

---

## CountBot 是什么？

CountBot 是一个轻量级、可扩展的 AI Agent 框架，专为中文用户和国内大模型优化。仅用约 21,000 行 Python 代码，就实现了生产级的智能助手基础设施，具备：

- 智能记忆系统 - 自动总结对话，永不遗忘重要信息
- 主动问候机制 - 像真人助手一样，在你空闲时主动关心
- 零配置安全 - 本地访问零摩擦，远程访问自动保护
- 多渠道统一 - 一套代码，同时服务 Web、飞书、钉钉、QQ、Telegram、微信
- 个性化设置 - 12 种性格 + 自定义称呼和地址
- 消息队列 - 优先级调度、消息去重、死信处理
- 国内优化 - 深度支持智谱、千问、Kimi、MiniMax、Deepseek等国产大模型

核心理念：让 AI Agent 成为有记忆、有情感、会主动、能协作的数字伙伴。

---

## 为什么选择 CountBot？

### 十大核心亮点

| 亮点 | 说明 | 优势 |
|------|------|------|
| 中文友好 | 21K 行代码全中文注释，完善文档体系，深度适配国产大模型 | 学习门槛低，上手快 |
| 双模式部署 | B/S 浏览器访问 + C/S 桌面客户端，一套代码灵活切换 | 个人/团队场景通吃 |
| 国内生态 | 内置搜索、地图、邮箱、文件收发、网页发布等 10 种技能插件 | 开箱即用，无需折腾 |
| 图形化配置 | 全 Web 界面管理，零配置文件编辑 | 降低配置错误率 |
| 深度个性化 | 12 种性格系统 + 自定义称呼地址 | 有温度的交互体验 |
| 极致性能 | 智能上下文压缩，Token 使用量大幅降低 | 省钱又高效 |
| 渐进式安全 | 本地访问全开放，远程访问自动保护 | 安全与便捷兼得 |
| 轻量架构 | 21K 行 vs 其他框架 50K-400K 行，模块化设计 | 易读易扩展 |
| 智能记忆 | 自动总结对话，关键词检索，永不遗忘 | 长期陪伴助手 |
| 消息队列 | 四级优先级、消息去重、死信处理 | 生产级可靠性 |

---

## 使用场景

CountBot 结合内置工具和技能插件，可以轻松应对各种日常任务：

### 信息获取与搜索

"帮我搜索一下今天的 AI 新闻"
- 使用百度搜索技能，获取最新资讯并智能总结

"帮我找找东莞的西餐厅，我准备 18 点出发"
- 调用高德地图技能，搜索餐厅并规划路线

"今天天气怎么样？"
- 查询天气技能，获取实时天气和未来预报

### 邮件与文件管理

"帮我看看今天有什么新的邮件"
- 通过邮件技能连接 QQ/163 邮箱，自动检查新邮件

"帮我把桌面的图片文件打包压缩，然后发送到我的邮箱"
- 使用文件工具打包文件，通过邮件技能发送附件

### 图像处理与创作

"帮我生成一个小猫拜年的图片，发送给我"
- 调用图像生成技能创作 AI 绘画，通过渠道发送

"帮我把电脑的屏幕做个截图，然后发送给我"
- 使用截图工具捕获屏幕，通过飞书/钉钉渠道发送

"这张图片里有什么内容？"
- 图像分析技能识别图片内容并给出详细描述

### 网页设计与发布

"帮我设计一个个人简历网页，然后发布到互联网上"
- 使用网页设计技能生成 HTML，自动部署到 Cloudflare Pages

### 浏览器自动化

"帮我用浏览器打开必应，搜索人工智能，打开第三个网站，然后截图给我"
- 通过浏览器自动化技能完成复杂的网页操作流程

### 定时任务

"每天早上 8 点帮我查看天气情况"
- 设置 Cron 定时任务，自动执行并推送结果

### 多渠道协作

CountBot 支持在 Web、飞书、钉钉、QQ 等多个渠道同时运行，所有渠道共享同一个智能记忆系统，无论在哪里对话，AI 都能记住你的偏好和历史信息。

---
## 核心特性

### 智能记忆系统

CountBot 的记忆系统具备：

- **自动对话总结** - LLM 自动判断何时总结，提取关键信息
- **上下文滚动压缩** - 对话超出窗口时自动压缩，信息不丢失
- **关键词搜索** - 基于关键词快速检索历史记忆
- **行式存储** - 简单可靠的文件存储，易于备份和迁移

```python
# 记忆系统自动工作，无需手动调用
用户: "我叫张三，住在北京"
AI: "好的，我记住了"

# 几天后...
用户: "我住哪儿来着？"
AI: "你住在北京" # 自动从记忆中检索
```

### Heartbeat 主动问候

CountBot 具备**主动关心能力**：

- **智能空闲检测** - 监测用户最后活跃时间
- **免打扰时段** - 支持北京时间的免打扰设置（如 22:00-08:00）
- **每日限额** - 防止过度打扰（默认每天最多 2 次）
- **自然随机** - 不是机械的定时问候，而是自然的关心

```python
# 用户 4 小时未活跃，且在活跃时段
AI: "好久不见！最近忙什么呢？需要我帮忙吗？"
```

### 零配置安全模型

独创的**渐进式安全**设计：

- **本地访问（127.0.0.1）** → 零摩擦，直接使用
- **远程访问（192.168.x.x）** → 首次引导设置密码
- **密码要求** → 至少 8 位，大小写+数字
- **Session 管理** → 24 小时有效期

```bash
# 本地使用 - 无需任何配置
http://localhost:8000  ✅ 直接访问

# 远程使用 - 自动保护
http://192.168.1.100:8000  🔐 首次设置密码
```


### 个性化用户管理

在设置页面的「用户管理」中，可以配置：

12 种性格系统

CountBot 提供 12 种不同的性格设定：暴躁老哥、吐槽达人、温柔姐姐、直球选手、毒舌大佬、话痨本痨、哲学家、软萌助手、段子手、元气满满、中二之魂、佛系大师。从贴吧暴躁老哥到佛系大师，从软萌可爱到中二之魂，满足不同场景下的交互需求。你还可以完全自定义性格描述，让 AI 助手更贴合你的使用习惯。

自定义称呼和地址

- AI 名称 - 给你的助手起个名字（默认：CountBot）
- 用户称呼 - AI 如何称呼你（如：老张、小明）
- 用户地址 - 你的位置信息（如：东莞市），用于天气、地图、行程规划等场景

### 精确按需唤醒的 Cron 调度器

不是轮询，不是简单定时器，而是**智能调度系统**：

- **精确唤醒** - 计算最近任务时间，精确到秒
- **并发控制** - 信号量控制最大并发数
- **超时保护** - 单任务最大执行时间（默认 300 秒）
- **独立 Session** - 每个任务使用独立数据库会话
- **SQLite 锁重试** - 自动处理并发写入冲突

```python
# 不是每秒轮询，而是精确计算下次唤醒时间
next_wake = min([job.next_run for job in enabled_jobs])
await asyncio.sleep((next_wake - now).total_seconds())
```

---

## 快速开始

### 一键启动

```bash
# 克隆仓库
git clone https://github.com/countbot-ai/countbot.git
cd countbot

# 安装依赖
pip install -r requirements.txt （建议使用国内镜像 pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/ ）

# 启动（自动打开浏览器）
python start_app.py
```

访问 `http://localhost:8000`，在设置页面配置 LLM 提供商即可使用。

### 下载桌面版

```
https://github.com/countbot-ai/CountBot/releases
支持 Windows/macOS/Linux
```

### 一下载

### 推荐配置

部分国内优秀 AI 模型：GLM-5、MiniMax-M2.5、Kimi K2.5、Qwen3.5-Plus、DeepSeek Chat 等

零成本上手：使用智谱 AI 的免费 GLM-4.7-Flash 模型

1. 访问 [智谱 AI 开放平台](https://open.bigmodel.cn/)
2. 注册并获取 API Key
3. 在 CountBot 设置页面选择「智谱 AI」，填入 API Key
4. 开始使用！

---

## 架构设计

### 项目结构

```
countbot/
├── backend/                   # 后端代码（~21K 行）
│   ├── modules/
│   │   ├── agent/             # Agent 核心
│   │   │   ├── loop.py        # ReAct 循环
│   │   │   ├── memory.py      # 智能记忆系统
│   │   │   ├── heartbeat.py   # 主动问候
│   │   │   ├── personalities.py # 12 种性格
│   │   │   └── context.py     # 上下文构建
│   │   ├── messaging/         # 消息队列
│   │   │   ├── enterprise_queue.py # 消息队列
│   │   │   └── rate_limiter.py     # 令牌桶限流
│   │   ├── cron/              # Cron 调度
│   │   │   └── scheduler.py   # 精确按需唤醒
│   │   ├── auth/              # 安全认证
│   │   │   └── middleware.py  # 零配置安全
│   │   ├── channels/          # 渠道管理
│   │   ├── providers/         # LLM 提供商
│   │   └── tools/             # 工具系统（13 个）
├── frontend/                  # 前端（Vue 3 + TypeScript）
├── skills/                    # 技能插件（10 种）
└── docs/                      # 文档
```

---
## 技术栈

### 后端

- **FastAPI** - 现代化 Web 框架，原生支持异步和 WebSocket
- **SQLAlchemy 2.0** - 异步 ORM，支持复杂查询
- **aiosqlite** - SQLite 异步驱动，零配置数据库
- **LiteLLM** - 统一 LLM 接口，支持主流大模型
- **Pydantic v2** - 数据验证和配置管理
- **Loguru** - 结构化日志，易于调试
- **cryptography** - Fernet 加密，保护 API 密钥

### 前端

- **Vue 3** - 渐进式框架，Composition API
- **TypeScript** - 类型安全，减少运行时错误
- **Pinia** - 轻量级状态管理
- **Vue I18n** - 国际化支持（中文/英文）
- **Axios** - HTTP 客户端，自动重试
- **Lucide Icons** - 现代化图标库

---

## 文档

| 文档 | 说明 |
|------|------|
| [快速开始指南](docs/quick-start-guide.md) | 功能开通、API 密钥获取 |
| [部署与运维](docs/deployment.md) | 安装、启动、生产部署 |
| [Agent Loop](docs/agent-loop.md) | ReAct 循环原理 |
| [记忆系统](docs/memory.md) | 自动总结、上下文压缩 |
| [Cron 调度器](docs/cron.md) | 精确唤醒、并发控制 |
| [渠道系统](docs/channels.md) | 多渠道配置 |
| [工具系统](docs/tools.md) | 13 个内置工具 |
| [技能系统](docs/skills.md) | 10 种插件开发 |
| [远程认证](docs/auth.md) | 零配置安全模型 |
| [配置手册](docs/configuration-manual.md) | 完整配置参考 |
| [API 参考](docs/api-reference.md) | REST API + WebSocket |

---

## 支持主流 LLM（基于 LiteLLM 统一接口）

CountBot 使用 LiteLLM 作为统一接口层，兼容 OpenAI / Anthropic / Gemini 协议，支持所有主流大模型：

### 国产大模型推荐

| 提供商 | 模型示例 | 获取方式 |
|--------|----------|----------|
| 智谱 AI | glm-4.7-flash（免费）, GLM-5 | [open.bigmodel.cn](https://open.bigmodel.cn) |
| 千问 | Qwen3.5-Plus | [dashscope.aliyun.com](https://dashscope.aliyun.com) |
| Moonshot | Kimi K2.5 | [platform.moonshot.cn](https://platform.moonshot.cn) |
| MiniMax | MiniMax-M2.5 | [platform.minimax.io](https://platform.minimax.io) |
| DeepSeek | DeepSeek Chat | [platform.deepseek.com](https://platform.deepseek.com) |
| 豆包 | Doubao-Pro-32K | [volcengine.com](https://volcengine.com) |
| 百度文心 | ERNIE-4.0-8K | [qianfan.baidubce.com](https://qianfan.baidubce.com) |
| 腾讯混元 | Hunyuan-Lite | [hunyuan.tencentcloudapi.com](https://hunyuan.tencentcloudapi.com) |
| 零一万物 | Yi-Large | [platform.lingyiwanwu.com](https://platform.lingyiwanwu.com) |
| 百川 | Baichuan4 | [platform.baichuan-ai.com](https://platform.baichuan-ai.com) |

### 国际大模型

| 提供商 | 模型示例 | 获取方式 |
|--------|----------|----------|
| OpenAI | gpt-5.3 | [platform.openai.com](https://platform.openai.com) |
| Anthropic | Claude Sonnet 4 | [console.anthropic.com](https://console.anthropic.com) |
| Gemini | Gemini 2.0 Flash | [aistudio.google.com](https://aistudio.google.com) |
| Groq | Llama 3.3 70B | [console.groq.com](https://console.groq.com) |
| Mistral | Mistral Large | [console.mistral.ai](https://console.mistral.ai) |
| Cohere | Command R+ | [dashboard.cohere.com](https://dashboard.cohere.com) |
| Together AI | Llama 3.3 70B Turbo | [api.together.xyz](https://api.together.xyz) |
| OpenRouter | 多模型聚合 | [openrouter.ai](https://openrouter.ai) |


### 本地部署

| 方式 | 说明 |
|------|------|
| Ollama | 本地部署开源模型 |
| vLLM | 高性能推理引擎 |
| LM Studio | 图形化本地部署 |

### 自定义兼容 API

| 协议 | 说明 |
|------|------|
| OpenAI 兼容 | 任意 OpenAI 协议兼容的 API |
| Anthropic 兼容 | 任意 Anthropic 协议兼容的 API |
| Gemini 兼容 | 任意 Gemini 协议兼容的 API |

---

## 支持的消息渠道

| 渠道 | 连接方式 | 所需配置 |
|------|----------|----------|
| Web UI | 内置 | 无需配置 |
| 飞书 | WebSocket 长连接 | App ID + App Secret |
| 钉钉 | Stream 模式 | Client ID + Client Secret |
| QQ | 官方 SDK | App ID + Secret |
| 微信(即将上线) | 公众号 API | App ID + App Secret + Token |
| Telegram | Long Polling | Bot Token（支持代理） |
| Discord(即将上线) | Gateway | Bot Token |

所有渠道支持 `allow_from` 白名单进行访问控制。

---

## 内置工具（13 个）

| 工具 | 功能 |
|------|------|
| `read_file` | 读取文件内容 |
| `write_file` | 写入文件内容 |
| `edit_file` | 编辑文件（替换/插入/删除） |
| `list_dir` | 列出目录内容 |
| `exec` | 执行 Shell 命令（沙箱保护） |
| `web_fetch` | 抓取网页内容 |
| `memory_read` | 读取长期记忆 |
| `memory_write` | 写入长期记忆 |
| `memory_search` | 搜索记忆 |
| `screenshot` | 截取屏幕 |
| `file_search` | 搜索文件 |
| `spawn` | 创建子代理 |
| `send_media` | 发送媒体文件 |

---

## 内置技能插件（10 种）

| 技能 | 说明 | 配置 |
|------|------|------|
| 百度搜索 | 百度 AI 搜索，支持网页搜索、百科、AI 智能生成 | API Key |
| 定时任务管理 | 通过聊天创建/管理定时任务和会话 | 无需配置 |
| 邮件管理 | QQ/163 邮箱收发，支持附件 | 邮箱授权码 |
| 图片分析 | 智谱/千问视觉模型，OCR、物体识别、场景理解 | API Key |
| 图片生成 | ModelScope 文生图，支持 LoRA 风格叠加 | API Token |
| 地图导航 | 高德地图路线规划与 POI 搜索 | API Key |
| 新闻聚合 | 中文新闻 + 全球 AI 资讯，多分类 RSS 源 | 无需配置 |
| 天气查询 | wttr.in 天气服务，支持全球城市 | 无需配置 |
| 网页设计 | HTML 生成 + Cloudflare Pages 一键部署 | API Token |
| 浏览器自动化 | agent-browser CLI，网页操作、截图、数据提取 | 手动安装 |

---

## 安全特性

### 渐进式安全模型

```
本地访问（127.0.0.1）
    ↓
  零摩擦
    ↓
  直接使用

远程访问（192.168.x.x）
    ↓
  首次访问
    ↓
  引导设置密码
    ↓
  后续需要登录
```

### 命令沙箱

- 工作空间隔离（`restrict_to_workspace`）
- 路径穿越检测
- 空字节注入阻断
- 命令白名单/黑名单
- 审计日志记录

### API 密钥加密

- Fernet 对称加密
- 加密存储在 SQLite
- 运行时自动解密

### 流量控制

- 令牌桶算法
- 按用户维度限流
- 可配置速率和突发大小

---

## 贡献指南

我们欢迎所有形式的贡献！

### 开发环境

```bash
# 后端开发（热重载）
uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000

# 前端开发
cd frontend
npm install
npm run dev

```

### 添加新组件

- 新 LLM 提供商 → `backend/modules/providers/`
- 新消息渠道 → `backend/modules/channels/`
- 新工具 → `backend/modules/tools/`
- 新技能 → `skills/<skill-name>/`

详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

---

## 开源协议

[MIT License](LICENSE)

---

## 致谢

CountBot 的诞生离不开开源社区的启发和支持。

### 项目灵感

- [PicoClaw](https://github.com/sipeed/picoclaw) - 感谢 PicoClaw 团队展示了超轻量级 AI Agent 的可能性。CountBot 的工具系统等核心架构深受其启发。

- [NanoBot](https://github.com/HKUDS/nanobot) - 感谢 NanoBot 团队展示了简洁的代码组织和模块化思想。

- [ZeroClaw](https://github.com/zeroclaw-labs/zeroclaw) - 感谢 ZeroClaw 团队在安全性和性能方面的探索。CountBot 的安全体系设计参考了其安全优先的架构理念。


### 技术栈

感谢以下开源项目和技术社区：

- [FastAPI](https://fastapi.tiangolo.com/) - 现代化的 Python Web 框架
- [Vue.js](https://vuejs.org/) - 渐进式 JavaScript 框架
- [LiteLLM](https://github.com/BerriAI/litellm) - 统一的 LLM API 接口
- [SQLAlchemy](https://www.sqlalchemy.org/) - Python SQL 工具包和 ORM
- [Pydantic](https://docs.pydantic.dev/) - 数据验证和设置管理

### 社区支持

特别感谢所有为 CountBot 提供反馈、建议和贡献的开发者和用户。是你们让 AI 技术变得更加普惠和易用。

### 开源精神

CountBot 秉承开源精神，致力于让 AI Agent 技术更加透明、可控和易于使用。我们相信，通过开源协作，可以让更多人受益于 AI 技术的进步。

---

<div align="center">
  <p>轻量级、可扩展的 AI Agent 框架 | 专为中文用户和国内大模型优化</p>
  <br>
  <p>
    <a href="https://654321.ai">官方网站</a> ·
    <a href="https://github.com/countbot-ai/countbot">GitHub</a> ·
    <a href="docs/README.md">文档</a> ·
    <a href="https://github.com/countbot-ai/countbot/issues">问题反馈</a>
  </p>
  <br>
  <p><sub>CountBot 仅供教育、研究和技术交流使用</sub></p>
</div>
