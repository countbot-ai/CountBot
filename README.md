<div align="center">
  <img src="https://github.com/user-attachments/assets/d42ee929-a9a9-4017-a07b-9eb66670bcc3" alt="CountBot Logo" width="180">
  <h1>CountBot</h1>
  <p>面向中文用户的开源 AI Agent 框架与运行中枢</p>
  <p>连接大模型、IM 渠道、工作流与外部工具，帮助 AI 真正进入执行链路</p>

  <p>
    中文 | <a href="README_EN.md">English</a>
  </p>

  <p>
    <a href="https://github.com/countbot-ai/countbot/stargazers"><img src="https://img.shields.io/github/stars/countbot-ai/countbot?style=social" alt="GitHub stars"></a>
    <a href="https://github.com/countbot-ai/countbot"><img src="https://img.shields.io/badge/Python-3.11+-blue.svg" alt="Python"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License"></a>
  </p>
</div>

---

## CountBot 是什么

CountBot 是一个更加符合中文用户习惯的轻量级 AI Agent 框架，也是一个面向本地部署与长期运行的 AI Agent 中枢。

它把角色、团队、工作流、工具调用、记忆、大模型、IM 渠道和本地工作空间连接起来，让 AI 具备长期运行、跨入口协作与任务执行能力。

你可以把 CountBot 理解为一个框架和中枢：

- 向上连接 100+ LLM 提供商与不同模型策略
- 向外连接 Web、微信、飞书、钉钉、Telegram、Discord、QQ、微博等入口
- 向内组织角色、团队、工作流、记忆与安全边界
- 向执行层连接文件、Shell、Web、屏幕、文件传输，以及 Claude Code、Codex、OpenCode 一类外部行业工具

一句话概括：**CountBot 是连接模型、渠道、团队和工具的 AI Agent 框架与运行中枢。**

---

## 最新动态

- **v0.6.0**
  - 新增微信ClawBot接入，支持多个账号绑定
  - 新增外部编程工具接入（Claude/Codex/OpenCode）,可以作为工具提供LLM调用，亦可成为代理连接IM渠道
  - 新增远程首次初始化安全入口 `/setup/<random>`
  - 新增 `REMOTE_SETUP_SECRET_TTL_MINUTES`，远程初始化入口有效期可控
  - 强化远程认证边界，覆盖 `/api/*` 与 `/ws/chat`
  - 发布说明：[https://654321.ai/docs/releases/v0.6.0](https://654321.ai/docs/releases/v0.6.0)

- **v0.5.0**
  - Agent Team 正式成型，支持多角色分工、上下文衔接与团队级编排
  - 配置体系从会话级演进到角色级、团队级与多机器人协同
  - 渠道系统进一步增强，支持更多企业与社交入口
  - 前端聊天、配置、技能、团队与工具面板整体升级
  - 发布说明：[https://654321.ai/docs/releases/v0.5.0](https://654321.ai/docs/releases/v0.5.0)

- **v0.4.0**
  - 引入会话级配置，支持不同会话使用不同模型与提示词
  - 扩展飞书、企业微信、微博、小智 AI 等渠道能力
  - 优化多智能体协作，新增 `/help` 等使用入口
  - 发布说明：[https://654321.ai/docs/releases/v0.4.0](https://654321.ai/docs/releases/v0.4.0)

- **v0.3.0**
  - 多智能体协作（`pipeline` / `graph` / `council`）首次体系化落地
  - 定时任务、技能配置、工作空间管理能力显著增强
  - 发布说明：[https://654321.ai/docs/releases/v0.3.0](https://654321.ai/docs/releases/v0.3.0)

---

## 为什么做 CountBot

我们相信两件事：

1. 编程从硅而生，终将回归语言。
2. 软件会从“少数人面向多数人的共识产品”，走向“更多人创造更多个性化工具”的时代。

过去一百年，软件系统不断从底层指令走向更高层抽象。今天，AI Agent 的关键问题已经从单纯追求更强模型，转向如何把模型、渠道、工具、权限边界和长期运行能力组织成一个可落地系统。

CountBot 就是在这个方向上，提供一套真正可部署、可扩展、可治理的开源基础设施。

---

## 核心能力

| 模块 | 说明 |
|------|------|
| Agent Loop | ReAct 推理、工具调用、结果反馈与迭代控制 |
| Agent Teams | `pipeline`、`graph`、`council` 三种协作模式 |
| 多机器人渠道矩阵 | 一个工作区可服务多个渠道、多个机器人、多个业务入口 |
| 配置分层 | 全局默认、角色、团队、会话运行时配置分层协同 |
| 工具与技能 | 文件、Shell、Web、截图、记忆、工作流、媒体发送与技能扩展 |
| 外部执行工具接入 | 将 Claude Code、Codex、OpenCode 等外部行业工具接入统一运行时 |
| 记忆与会话 | 长期记忆、摘要、上下文注入、会话隔离 |
| Cron 与 Heartbeat | 定时任务、主动提醒、后台长期运行 |
| 安全与工作空间 | 本地可控、路径限制、审计日志、超时与远程认证边界 |
| 多模型接入 | 兼容国产与国际主流模型接入，支持团队级模型覆盖 |

---

## 适用场景

- 希望把自然语言需求拆成多个角色协同完成的复杂任务
- 希望在本地或私有环境中运行自己的 AI 助手、AI 团队或自动化流程
- 需要同时服务 Web、企业微信、飞书、钉钉、Telegram、Discord 等多个入口
- 希望将工具调用、文件操作、消息通知、定时任务整合进同一运行环境
- 希望把大模型、消息渠道、工具调用和团队协作整合到一个统一中枢
- 希望在 AI 助手之外，进一步构建可持续运行的 Agent 系统

---

## 快速开始

### 方式一：源码启动

```bash
git clone https://github.com/countbot-ai/CountBot.git
cd CountBot
pip install -r requirements.txt
python start_app.py
```

启动完成后默认打开 `http://127.0.0.1:8000`。

如果国内网络访问 GitHub 受限，可切换到 Gitee：

```bash
git clone https://gitee.com/countbot-ai/CountBot.git
```

### 方式二：桌面版体验

- Gitee Releases: https://gitee.com/countbot-ai/CountBot/releases
- GitHub Releases: https://github.com/countbot-ai/CountBot/releases
- 适用平台：Windows / macOS / Linux

---

## v0.6.0 重点变化

### 1. 远程首次初始化更加安全

当实例尚未设置密码时，远程访问不再直接暴露固定初始化入口，而是生成一次性的随机入口：

```text
/setup/<random>
```

入口有效期可通过 `REMOTE_SETUP_SECRET_TTL_MINUTES` 控制，范围为 `10` 到 `120` 分钟。

### 2. 外部编程代理进入正式能力层

CountBot 不再只依赖内建工具，也可以把 Claude Code、Codex、OpenCode 一类外部行业工具纳入统一调度体系，形成更清晰的执行层边界。

### 3. 远程认证边界继续收紧

- 远程未登录情况下保护 `/api/*`
- 将 `/ws/chat` 纳入认证边界
- 健康检查与初始化入口按白名单与合法 secret 分流

---

## 文档入口

| 文档 | 说明 | 链接 |
|------|------|------|
| 快速开始 | 安装、配置、启动 | [https://654321.ai/docs/getting-started/quick-start-guide](https://654321.ai/docs/getting-started/quick-start-guide) |
| 配置手册 | 完整配置说明 | [https://654321.ai/docs/getting-started/configuration-manual](https://654321.ai/docs/getting-started/configuration-manual) |
| 部署与运维 | 启动、部署、排障 | [https://654321.ai/docs/advanced/deployment](https://654321.ai/docs/advanced/deployment) |
| 远程访问指南 | 远程初始化、认证、排障 | [https://654321.ai/docs/advanced/remote-access](https://654321.ai/docs/advanced/remote-access) |
| 认证说明 | 密码初始化与访问边界 | [https://654321.ai/docs/advanced/auth](https://654321.ai/docs/advanced/auth) |
| API 参考 | REST API 与 WebSocket | [https://654321.ai/docs/api-reference](https://654321.ai/docs/api-reference) |
| 发布说明 | 版本演进记录 | [https://654321.ai/docs/releases/v0.6.0](https://654321.ai/docs/releases/v0.6.0) |

完整站点文档请查看：[https://654321.ai/docs](https://654321.ai/docs)

---

## 开发与贡献

### 本地开发

```bash
uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000
```

### 社区交流

- QQ 交流群：`1028356423`
- 讨论方向：CountBot 使用、问题反馈、二次开发、场景共创

### 问题反馈

- GitHub Issues: https://github.com/countbot-ai/CountBot/issues

---

## 开源协议与致谢

### 开源协议

MIT License

### 项目灵感

- OpenClaw
- NanoBot
- ZeroClaw
- anthropics/skills

### 技术致谢

感谢 FastAPI、Vue.js、SQLAlchemy、Pydantic、LiteLLM 等开源项目。

---

<div align="center">
  <p>连接模型、渠道、团队与工具的 AI Agent 中枢</p>
  <p>
    <a href="https://654321.ai">官方网站</a> ·
    <a href="https://github.com/countbot-ai/countbot">GitHub</a> ·
    <a href="https://gitee.com/countbot-ai/CountBot">Gitee</a> ·
    <a href="https://654321.ai/docs">完整文档</a>
  </p>
</div>
