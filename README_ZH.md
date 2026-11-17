![GitHub stars](https://img.shields.io/github/stars/countbot-ai/countbot?style=social)



![CountBot Logo](https://github.com/user-attachments/assets/5a848b1f-04bf-40ff-8249-8a453294f444)



***

## CountBot 是什么

CountBot 是一套可私有化部署、长期运行的 AI Agent 运行时。它统一接入 IM 渠道、工具执行、任务调度和多租户权限体系；你可以在飞书、企业微信、微信、QQ 等平台下发指令，也可以直接通过 Web 界面交互。

它面向多用户场景设计：一台服务器承载多个独立租户，每位用户拥有独立的工作区、会话、记忆、模型配置和配额；同时提供 Agent / 对话双模式，按任务复杂度控制上下文和 token 成本。

> 共享主机资源，隔离租户数据；执行任务用 Agent，纯对话用聊天模式。



***

## 1.1.0 核心升级



1. **DeepSeek 官方原生接入**

   DeepSeek 设为默认供应商，使用官方 Anthropic Messages 端点；接通联网搜索、链接读取、PDF/Office 附件解析、语音转写、语音朗读和内容安全校验。

2. **多用户多租户**

   每个普通用户拥有独立工作区、会话、记忆、技能和运行环境；管理员可按用户分配共享模型、限制特定用户使用的模型、模式。Key 不下发前端，关键操作进入审计日志；用户也可以配置自己的供应商和 API Key。

3. **Agent / 对话双模式**

   多 Agent 工程方案依靠预置大量上下文、工具定义与执行规则，来赋予模型复杂任务执行能力，这套能力链在自动化任务中必不可少。但并非每一次对话都需要这套工程化上下文：简单问答、改写、需求对齐，依然无条件携带庞大的预置文本，会产生大量无效 Token 开销。CountBot 提供会话内无缝切换的双模式：Agent 模式加载完整工具、技能、团队与执行规则，应对复杂任务；对话模式精简上下文，剥离工具定义，适配问答、改写、翻译、头脑风暴与闲聊。本地支持 Token 预估，管理员也可以为用户限定可用模式。

4. **前端工作台重构**

   会话、设置、管理后台、调度、技能、MCP、Wiki、团队、记忆和工具按模块拆分；输入区集中模型选择、思考档位、模式切换、附件和语音操作。

5. **安全与配额治理**

   工作区路径限制、危险命令守卫、出站 URL SSRF 校验、Key 隔离、共享模型每日上限、会话串行执行、用量统计和审计日志。



***

## 核心能力



* **多租户治理**：管理员与普通用户分级；每个租户独立拥有工作区、会话历史、长期记忆、技能配置和模型配置。管理员可分配共享模型、设置每日调用上限、查看用量统计和审计日志。

* **Agent / 对话双模式**：Agent 模式启用工具调用、技能、团队协作和工作流编排；对话模式不注入工具定义和执行规则，降低轻量问答的上下文成本。

* **DeepSeek 原生能力**：默认接入 DeepSeek 官方 API，支持联网搜索、链接读取、文档解析、语音输入、语音朗读和内容安全；附件按内容哈希缓存复用。同时兼容多家供应商和三种请求协议，支持多 Key 轮换与失败冷却。

* **IM 渠道接入**：统一接入 Web、飞书、企业微信、微信、QQ、钉钉、Telegram、微博、小智和 Server 酱，可在一套系统内管理多个机器人入口。

* **工具与扩展生态**：文件读取、文件写入、文件编辑、目录浏览、网页抓取、命令执行、截图（可选依赖可用时）等工具可按需求启用和组合，Agent 可在任务中灵活搭配调用；同时支持 MCP、Wiki 知识库、技能系统和外部编程代理接入。



***

## 快速开始

### 源码启动



```
git clone https://github.com/countbot-ai/countbot.git
cd CountBot

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
python start_app.py
```

启动后访问 `http://127.0.0.1:8000`，首次打开按引导设置管理员密码。远程初始化入口有时效，可通过 `REMOTE_SETUP_SECRET_TTL_MINUTES` 调整（10–120 分钟，默认 30 分钟）。

监听地址与端口可用环境变量覆盖：



```
# Linux / macOS
COUNTBOT_HOST=0.0.0.0 COUNTBOT_PORT=8000 python start_app.py
```



```
# Windows PowerShell
$env:COUNTBOT_HOST = '0.0.0.0'
$env:COUNTBOT_PORT = '8001'
python start_app.py
```

国内网络可使用阿里云镜像安装依赖：



```
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
```

GitHub 访问受限时，也可以使用 Gitee 镜像：



```
git clone https://gitee.com/countbot-ai/CountBot.git
```

### 桌面版

支持 Windows /macOS/ Linux，可直接下载使用：



* [GitHub Releases](https://github.com/countbot-ai/countbot/releases)

* [Gitee Releases](https://gitee.com/countbot-ai/CountBot/releases)

### 部署到服务器

CountBot 是标准 Web 服务，支持 `systemd`、`supervisor` 或容器长期托管。开放远程访问前，先完成管理员初始化，再配置反向代理与 HTTPS。



***

## 支持的渠道



| 渠道       | 方向  | 说明             |
| -------- | --- | -------------- |
| 飞书       | 双向  | 事件订阅，支持群聊与私聊   |
| 企业微信     | 双向  | 企业内机器人         |
| 微信       | 双向  | 支持多账号绑定        |
| QQ       | 双向  | QQ 开放平台机器人     |
| 钉钉       | 双向  | 企业内部机器人        |
| Telegram | 双向  | 直连 Bot API     |
| 微博       | 双向  | 微博机器人          |
| 小智 AI    | 双向  | 小智 AI 硬件接入     |
| Server 酱 | 仅推送 | 单次 HTTP 请求推送通知 |



***

## 文档与社区



* [完整文档](https://countbot.cn/docs)

* [问题反馈](https://github.com/countbot-ai/countbot/issues)



***

## 开发与贡献



```
# 后端本地开发
uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000

# 前端本地开发
cd frontend
npm install
npm run dev

# 前端类型检查与构建
npm run type-check
npm run build

# 后端测试
python -m pytest -q tests
```

前端开发要求 Node.js 18+、npm 9+。

欢迎提交 Issue 反馈问题，也接受功能修复、能力扩展与文档改进的 PR。



***

## 开源协议与致谢

### 开源协议

MIT License

### 项目灵感



* OpenClaw

* NanoBot

* ZeroClaw

* anthropics/skills

### 技术致谢

感谢 FastAPI、Vue.js、SQLAlchemy、Pydantic 等开源项目。



***