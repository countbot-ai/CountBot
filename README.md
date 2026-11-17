<div align="center">
  <h1>CountBot</h1>
  <p><strong>A lightweight multi-tenant AI Agent for your server</strong></p>
  <p>One runtime for isolated tenants. Switch between Agent execution and plain conversation to balance capability and cost.</p>

  <p>
    <a href="README_ZH.md">中文</a> | English
  </p>

  <p>
    <a href="https://github.com/countbot-ai/countbot/stargazers"><img src="https://img.shields.io/github/stars/countbot-ai/countbot?style=social" alt="GitHub stars"></a>
    <a href="https://github.com/countbot-ai/countbot"><img src="https://img.shields.io/badge/version-1.1.0-2f6feb.svg" alt="Version"></a>
    <a href="https://github.com/countbot-ai/countbot"><img src="https://img.shields.io/badge/Python-3.8+-blue.svg" alt="Python"></a>
    <a href="https://github.com/countbot-ai/countbot"><img src="https://img.shields.io/badge/Node-18+-339933.svg" alt="Node"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License"></a>
  </p>
</div>

---

## What Is CountBot

CountBot is a privately deployable, long-running AI Agent runtime. It connects IM channels, tool execution, scheduled tasks and a multi-tenant permission system. You can send requests through Lark, WeCom, WeChat, QQ and other platforms, or use the web interface directly.

It is designed for multi-user scenarios: one server hosts multiple isolated tenants, each with its own workspace, sessions, memory, model configuration and quota. Agent and chat modes can be switched per task to control context size and token cost.

> Shared host resources, isolated tenant data. Use Agent for execution, chat mode for plain conversation.

---

## What's New in 1.1.0

1. **DeepSeek native integration**
   DeepSeek is the default provider, using the official Anthropic Messages endpoint. Web search, URL reading, PDF/Office attachment parsing, ASR, TTS and safety checks are connected to the request pipeline.

2. **Multi-user multi-tenant**
   Each regular user has an isolated workspace, sessions, memory, skills and runtime. Administrators can assign shared models per user and restrict the models and modes available to a specific user. Keys are not sent to the frontend, and key operations are recorded in the audit log. Users can also configure their own providers and API keys.

3. **Agent / chat dual mode**
   A multi-agent engineering setup relies on preloaded context, tool definitions and execution rules to give the model complex-task execution ability; this capability chain is necessary for automation. Not every conversation needs that engineering context. Carrying a large preloaded text set into simple Q&A, rewriting or requirement alignment creates unnecessary token overhead. CountBot offers two modes that switch seamlessly within a session: Agent mode loads the full set of tools, skills, teams and execution rules for complex tasks; chat mode trims context and removes tool definitions for Q&A, rewriting, translation, brainstorming and casual chat. Local token estimation is supported, and administrators can restrict the modes available to each user.

4. **Rebuilt frontend workspace**
   Chat, settings, admin, scheduler, skills, MCP, Wiki, teams, memory and tools are split into modules. The composer groups model selection, reasoning level, mode switch, attachments and speech actions.

5. **Security and quota governance**
   Workspace path restrictions, command guard, outbound URL SSRF validation, key isolation, shared-model daily limits, session serialization, usage statistics and audit logs.

---

## Core Capabilities

- **Multi-tenant governance**: separate administrator and regular-user roles. Each tenant has an isolated workspace, session history, long-term memory, skill configuration and model configuration. Administrators can assign shared models, set daily call limits, review usage and audit entries.
- **Agent / chat dual mode**: Agent mode enables tool calls, skills, team collaboration and workflow orchestration; chat mode does not inject tool definitions or execution rules, reducing context cost for lightweight Q&A.
- **DeepSeek native capabilities**: DeepSeek is the default API provider with web search, URL reading, document parsing, speech-to-text, text-to-speech and safety checks. Attachments are cached by content hash. Multiple providers and three request protocols are supported, with multi-key rotation and failure cooldown.
- **IM channels**: Web, Lark, WeCom, WeChat, QQ, DingTalk, Telegram, Weibo, XiaoZhi and ServerChan can be managed from one system.
- **Tools and extensions**: file read, write, edit, directory listing, web fetching, command execution and screenshots (when optional dependencies are available) can be enabled and combined as needed; the Agent can mix them flexibly in a task. MCP, Wiki knowledge base, skills and external coding agents are also supported.

---

## Quick Start

### From source

```bash
git clone https://github.com/countbot-ai/countbot.git
cd CountBot

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
python start_app.py
```

Open `http://127.0.0.1:8000` and follow the first-run guide to set the administrator password. The remote setup entry has an expiry; adjust it with `REMOTE_SETUP_SECRET_TTL_MINUTES` (10–120 minutes, default 30).

Host and port can be overridden with environment variables:

```bash
# Linux / macOS
COUNTBOT_HOST=0.0.0.0 COUNTBOT_PORT=8000 python start_app.py
```

```powershell
# Windows PowerShell
$env:COUNTBOT_HOST = '0.0.0.0'
$env:COUNTBOT_PORT = '8001'
python start_app.py
```

For networks with slow PyPI access:

```bash
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
```

If GitHub access is restricted, use the Gitee mirror:

```bash
git clone https://gitee.com/countbot-ai/CountBot.git
```

### Desktop build

Windows, macOS and Linux builds are available for download:

- [GitHub Releases](https://github.com/countbot-ai/countbot/releases)
- [Gitee Releases](https://gitee.com/countbot-ai/CountBot/releases)

### Server deployment

CountBot is a standard web service and can be hosted with `systemd`, `supervisor` or containers. Complete administrator initialization before exposing remote access, then configure a reverse proxy and HTTPS.

---

## Supported Channels

| Channel | Direction | Notes |
| --- | --- | --- |
| Lark | Both ways | Event subscription, group and private chats |
| WeCom | Both ways | Enterprise bot |
| WeChat | Both ways | Multiple account bindings |
| QQ | Both ways | QQ Open Platform bot |
| DingTalk | Both ways | Internal enterprise bot |
| Telegram | Both ways | Direct Bot API |
| Weibo | Both ways | Weibo bot |
| XiaoZhi AI | Both ways | XiaoZhi AI hardware integration |
| ServerChan | Push only | Single HTTP notification |

---

## Documentation and Community

- [Documentation](https://countbot.cn/docs)
- [Issue feedback](https://github.com/countbot-ai/countbot/issues)

---

## Development and Contributions

```bash
# Backend local development
uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000

# Frontend local development
cd frontend
npm install
npm run dev

# Frontend type-check and build
npm run type-check
npm run build

# Backend tests
python -m pytest -q tests
```

The frontend requires Node.js 18+ and npm 9+.

Issues, bug fixes, capability extensions and documentation improvements are welcome.

---

## License and Acknowledgements

### License

MIT License

### Inspiration

- OpenClaw
- NanoBot
- ZeroClaw
- anthropics/skills

### Technical thanks

Thanks to the open-source projects behind FastAPI, Vue.js, SQLAlchemy and Pydantic.

---

<div align="center">
  <p>Shared host, isolated tenants. Run Agent when execution is needed; switch to chat mode to reduce cost.</p>
  <p>
    <a href="https://countbot.cn">Website</a> ·
    <a href="https://github.com/countbot-ai/countbot">GitHub</a> ·
    <a href="https://gitee.com/countbot-ai/CountBot">Gitee</a> ·
    <a href="https://countbot.cn/docs">Documentation</a>
  </p>
</div>
