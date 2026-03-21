<div align="center">
  <img src="https://github.com/user-attachments/assets/d42ee929-a9a9-4017-a07b-9eb66670bcc3" alt="CountBot Logo" width="180">
  <p>轻量级、可扩展的 AI Agent 框架 | 专为中文用户和国内大模型优化</p>

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

## 最新动态

- **2026-03-19 v0.5.0**
  - 实现真正的AI团队协作：支持多角色分工、上下文衔接、条件流转与团队级编排，可在企业微信、飞书等群聊添加多个机器人实现多团队协作
  - 会话级配置升级为角色级与团队级配置：一个工作区即可管理多个角色、多个模型、多个机器人
  - 渠道系统全面增强：支持自定义渠道扩展，并新增微博、企业微信、小智 AI 等接入能力
  - 多机器人运行能力进一步完善：不同渠道、不同角色、不同配置可独立服务不同场景
  - 前端全面重构与优化：聊天、配置、技能、团队、工具面板和国际化体验整体升级
  - 工具调用、消息流、媒体发送与渠道管理链路全面增强，复杂任务更稳定

- **2026-03-14 v0.4.0**
  - 会话级配置（独立 API/模型/提示词）
  - 新增微博、企业微信、小智 AI 渠道（语音），实现企业微信、飞书流式输出
  - 优化多智能体协作，新增 /help 命令
  - 集成 Mermaid 图表，兼容 OpenClaw Skills
  - 重构 Heartbeat 主动问候系统，支持自定义对话头像

- **2026-03-04 v0.3.0**
  - 多智能体协作（Pipeline/Graph/Council）
  - 定时任务增强、技能系统可视化配置
  - UI/UX 优化，修复大量已知问题

- 2026-02-25 v0.2.0：问题修复与体验优化
- 2026-02-21：CountBot 正式开源

### 未来计划
- 自建频道加密连接（小程序/APP/WEB）
- 实现集中管理功能，支持控制多个CountBot
- 性能持续优化

---

## CountBot 是什么？
轻量级、可扩展的 AI Agent 框架，专为中文用户和国内大模型优化，更适合中文用户上手使用：

- 智能记忆：自动总结对话，长期留存关键信息
- 主动问候：空闲时自然关心，贴近真人交互
- 零配置安全：本地免配置，远程自动保护
- 多渠道统一：一套代码支持 Web/企业微信/微博/飞书/钉钉/QQ/Telegram/小智AI语音控制等
- 深度个性化：12 种性格 + 自定义称呼/地址/输出语言
- 生产级可靠性：消息队列、优先级调度、死信处理
- 国产大模型适配：智谱/千问/Kimi/MiniMax/DeepSeek及各大厂商Coding plan套餐等

核心理念：让 AI Agent 成为有记忆、有情感、会主动、能协作的数字伙伴。

---

## 核心亮点

| 亮点 | 说明 | 优势 |
|------|------|------|
| 中文友好 | 全中文界面，深度适配国产大模型 | 学习门槛低，上手快 |
| 易于拓展 | 使用anthropics/skills规范，兼容OpenClaw技能生态 | 可拓展性强 |
| 双模式部署 | B/S 浏览器 + C/S 桌面端，一套代码切换 | 个人/团队场景通吃 |
| 国内生态 | 内置10种技能插件（搜索/地图/邮件等） | 开箱即用，无需折腾 |
| 图形化配置 | 全 Web 管理，无需编辑配置文件 | 降低配置错误率 |
| 深度个性化 | 12种性格 + 自定义称呼/地址 | 有温度的交互体验 |
| 极致性能 | 智能上下文压缩，减少 Token 消耗 | 省钱又高效 |
| 渐进式安全 | 本地开放，远程自动保护 | 安全与便捷兼得 |

---

## 使用场景

### 信息获取与搜索
- "帮我搜今天的 AI 新闻" → 百度搜索+智能总结
- "找东莞18点能去的西餐厅" → 高德地图+路线规划
- "今天天气怎么样？" → 实时天气+预报

### 邮件与文件管理
- "查今天的新邮件" → 自动检查 QQ/163 邮箱
- "打包桌面图片并发送到我邮箱" → 文件处理+邮件发送

### 图像处理与创作
- "生成小猫拜年图片" → AI 绘画+渠道发送
- "截图屏幕并发给我" → 截图+飞书/钉钉发送
- "分析这张图片内容" → OCR+场景理解

### 其他核心场景
网页设计+一键发布、浏览器自动化、定时任务、多渠道协作

---

## 核心特性
- 智能记忆系统
- 零配置安全模型
- 个性化用户管理
- 精确 Cron 调度器

---

## 快速开始

### 一键启动（推荐）
```bash
# 1. 克隆仓库
git clone https://github.com/countbot-ai/countbot.git
cd countbot

# 2. 安装依赖（国内镜像避免网络问题）
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/

# 3. 启动项目（自动打开浏览器）
python start_app.py
```

✅ 验证步骤：程序完全启动后访问 http://localhost:8000，配置 LLM 提供商即可使用。

### 桌面版下载（测试版）
地址：https://github.com/countbot-ai/CountBot/releases
支持：Windows/macOS/Linux（测试版，仅供体验，稳定性待优化）

### 零成本配置（智谱 AI 免费模型）
1. 访问 智谱 AI 开放平台
2. 注册并获取 API Key
3. 在 CountBot 设置页选择「智谱 AI」，填入 API Key 和 GLM-4.7-Flash 模型
4. 立即使用 GLM-4.7-Flash 免费模型

---

## 创新性的安全设计
### 渐进式安全模型
- 本地访问（127.0.0.1）→ 零摩擦 → 直接使用
- 远程访问（192.168.x.x）→ 首次访问 → 设密码 → 后续登录

### 命令沙箱
- 工作空间隔离（默认关闭）
- 路径穿越检测、空字节注入阻断
- 命令黑白名单、审计日志记录

---

## 文档参考
| 文档类型 | 说明 | 链接 |
|----------|------|------|
| 快速开始 | 安装/配置/启动 | docs/quick-start-guide.md |
| 部署运维 | 生产环境部署 | docs/deployment.md |
| 配置手册 | 完整配置参考 | docs/configuration-manual.md |
| API 参考 | REST API + WebSocket | docs/api-reference.md |
| 系统设计 | 记忆/调度/安全等原理 | docs/agent-loop.md |

---

## 贡献指南
### 开发环境搭建
```bash
# 后端热重载
uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000
```

### 社群交流
QQ 交流群：1028356423
群内主要讨论：CountBot 使用、交流、二次开发等

---

## 开源协议与致谢
### 开源协议
MIT License

### 项目灵感
- OpenClaw - 感谢 OpenClaw 团队开创性的 AI Agent 框架设计。CountBot 的 Agent Loop、工具系统等核心架构深受其启发。
- NanoBot - 感谢 NanoBot 团队展示了简洁的代码组织和模块化思想。
- ZeroClaw - 感谢 ZeroClaw 团队在安全性和性能方面的探索。CountBot 的安全体系设计参考了其安全优先的架构理念。
- anthropics/skills - 感谢 anthropics 提供 Skills 规范。CountBot 的 Skills 复用了其先进的设计理念。

### 技术致谢
感谢 FastAPI、Vue.js、SQLAlchemy、Pydantic 等开源项目。

### 社区支持
感谢所有反馈、建议和贡献的开发者与用户！

---

<div align="center">
  <p>轻量级、可扩展的 AI Agent 框架 | 专为中文用户和国内大模型优化</p>
  <br>
  <p>
    <a href="https://654321.ai">官方网站</a> ·
    <a href="https://github.com/countbot-ai/countbot">GitHub</a> ·
    <a href="docs/README.md">完整文档</a> ·
    <a href="https://github.com/countbot-ai/countbot/issues">问题反馈</a>
  </p>
</div>
