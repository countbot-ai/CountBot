<div align="center">
  <img src="https://github.com/user-attachments/assets/d42ee929-a9a9-4017-a07b-9eb66670bcc3" alt="CountBot Logo" width="180">
  <h1>CountBot</h1>
  <p>Open-source AI agent framework and runtime hub for Chinese users</p>
  <p>Connects LLMs, IM channels, workflows, and external tools so AI can actually execute work</p>

  <p>
    <a href="README.md">中文</a> | English
  </p>

  <p>
    <a href="https://github.com/countbot-ai/countbot/stargazers"><img src="https://img.shields.io/github/stars/countbot-ai/countbot?style=social" alt="GitHub stars"></a>
    <a href="https://github.com/countbot-ai/countbot"><img src="https://img.shields.io/badge/Python-3.11+-blue.svg" alt="Python"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License"></a>
  </p>
</div>

---

## What Is CountBot

CountBot is a lightweight AI agent framework that better fits Chinese users' habits, and also a runtime hub built for local deployment and long-running operation.

It connects roles, teams, workflows, tool invocation, memory, LLMs, IM channels, and local workspaces so AI can run continuously, collaborate across entry points, and execute real tasks.

You can think of CountBot as both a framework and a hub:

- Upward, it connects to 100+ LLM providers and different model strategies
- Outward, it connects to Web, WeChat, Lark, DingTalk, Telegram, Discord, QQ, Weibo, and more
- Inward, it organizes roles, teams, workflows, memory, and security boundaries
- At the execution layer, it connects files, Shell, Web, screenshots, file transfer, and external professional tools such as Claude Code, Codex, and OpenCode

In one sentence: **CountBot is an AI agent framework and runtime hub that connects models, channels, teams, and tools.**

CountBot was born from natural language. Its vision is not to require more people to learn complex configuration and programming before they can use AI, but to let ordinary users interact with AI directly through natural language to retrieve information, generate content, break down tasks, call tools, orchestrate workflows, and even build their own assistants, team collaboration flows, and automation systems.

---

## Latest Updates

- **v0.7.0**
  - Addressed multiple issue reports, fixed a batch of known bugs, and improved overall stability
  - Added file upload and processing flows to the WEBUI, improved Mermaid rendering, and made chart presentation more user-friendly
  - Optimized frontend pages and interaction flows so everyday operations around skills, configuration, and tools feel smoother
  - Optimized the tool invocation chain and context organization, significantly reducing token usage compared with previous versions
  - Added a model thinking control switch so you can adjust reasoning intensity by scenario and get faster perceived responses
  - Added `find-skills` with full Tencent Cloud SkillsHub integration, enabling conversational search, install, enable, disable, and delete for skills
  - Added `ima-knowledge-base` and `ima-notes` with full IMA knowledge-base and note capabilities, including search, upload, web import, reading, creation, and append
  - Release notes: [https://654321.ai/docs/releases/v0.7.0](https://654321.ai/docs/releases/v0.7.0)

- **v0.6.0**
  - Added WeChat ClawBot integration with support for binding multiple accounts
  - Added external coding tool integration for Claude, Codex, and OpenCode, which can either be called by the LLM as tools or act as agents connected to IM channels
  - Added the secure first-time remote initialization entry `/setup/<random>`
  - Added `REMOTE_SETUP_SECRET_TTL_MINUTES` so the validity period of the remote setup entry can be controlled
  - Strengthened remote authentication boundaries, covering `/api/*` and `/ws/chat`
  - Release notes: [https://654321.ai/docs/releases/v0.6.0](https://654321.ai/docs/releases/v0.6.0)

- **v0.5.0**
  - Agent Teams became a first-class capability, supporting multi-role collaboration, context handoff, and team-level orchestration
  - The configuration system evolved from session-level configuration to role-level, team-level, and multi-bot coordination
  - The channel system was further strengthened to support more enterprise and social entry points
  - Frontend panels for chat, configuration, skills, teams, and tools were upgraded as a whole
  - Release notes: [https://654321.ai/docs/releases/v0.5.0](https://654321.ai/docs/releases/v0.5.0)

- **v0.4.0**
  - Introduced session-level configuration so different sessions can use different models and prompts
  - Expanded channel support for Lark, WeCom, Weibo, Xiaozhi AI, and more
  - Improved multi-agent collaboration and added usage entry points such as `/help`
  - Release notes: [https://654321.ai/docs/releases/v0.4.0](https://654321.ai/docs/releases/v0.4.0)

- **v0.3.0**
  - Multi-agent collaboration modes (`pipeline` / `graph` / `council`) were first systematized
  - Scheduled tasks, skill configuration, and workspace management were significantly enhanced
  - Release notes: [https://654321.ai/docs/releases/v0.3.0](https://654321.ai/docs/releases/v0.3.0)

- **v0.2.0 · 2026-02-26**
  - Focused on bug fixes, interaction improvements, and cleanup of the build workflow
  - Pushed CountBot from "basically runnable" toward "stable and ready to iterate"

- **Official Open Source Release · 2026-02-21**
  - CountBot was open-sourced for the first time, including the base framework, startup scripts, agent core, channel system, tool system, skill system, and foundational frontend capabilities
  - Public iteration has continued from that day onward

---

## Why CountBot

CountBot starts from the broader trend of software being driven by natural language, and aims to let AI truly land in real tasks and everyday work.

Software development and software usage are changing:
1. Interaction between people and software is moving from complex commands and code toward natural language.
2. Tools and systems are moving from standardized products toward a future where more people can define and create personalized tools.

The core challenge for AI agents is no longer just model capability alone. It is how to combine LLMs, tool invocation, multi-channel access, permission boundaries, and long-running operation into a system that can actually be deployed and maintained.

OpenClaw has already validated a viable path for local execution and autonomous agents. On top of that, CountBot focuses on filling key gaps in **Chinese scenario adaptation, lightweight deployment, usability expansion, security control, and governance**.

CountBot is not merely a conversational AI application. It is open infrastructure for real tasks: deployable, extensible, and governable, so ordinary users can use natural language to drive AI, organize tools, connect channels, and actually land business and daily workflows.

---

## Core Capabilities

| Module | Description |
|------|------|
| Agent Loop | ReAct reasoning, tool invocation, result feedback, and iterative control |
| Agent Teams | Three collaboration modes: `pipeline`, `graph`, and `council` |
| Multi-bot channel matrix | One workspace can serve multiple channels, multiple bots, and multiple business entry points |
| Configuration layers | Global defaults, roles, teams, and runtime session configuration working together |
| Tools and skills | Files, Shell, Web, screenshots, memory, workflows, media delivery, and skill extensions |
| External execution tool integration | Connect external professional tools such as Claude Code, Codex, and OpenCode into one unified runtime |
| Memory and sessions | Long-term memory, summaries, context injection, and session isolation |
| Cron and Heartbeat | Scheduled tasks, proactive reminders, and long-running background operation |
| Security and workspace | Local control, path restrictions, audit logs, timeouts, and remote authentication boundaries |
| Multi-model access | Compatible with major domestic and international models, with team-level model override support |

---

## Use Cases

- Breaking down complex tasks into multiple roles that collaborate through natural-language instructions
- Running your own AI assistant, AI team, or automation workflow locally or in a private environment
- Serving multiple entry points at the same time, including Web, WeCom, Lark, DingTalk, Telegram, and Discord
- Unifying tool invocation, file operations, message delivery, and scheduled tasks in one runtime
- Bringing LLMs, message channels, tool usage, and team collaboration into a single operating hub
- Going beyond a simple AI assistant to build a sustainable, long-running agent system

---

## Quick Start

### Option 1: Start From Source

```bash
git clone https://github.com/countbot-ai/CountBot.git
cd CountBot

# Default installation
pip install -r requirements.txt

# If you are in mainland China, you can use the Aliyun mirror
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

python start_app.py
```

After startup, CountBot opens at `http://127.0.0.1:8000` by default.

If GitHub access is limited, you can switch to Gitee:

```bash
git clone https://gitee.com/countbot-ai/CountBot.git
```

### Option 2: Use the Desktop Build

- Gitee Releases: https://gitee.com/countbot-ai/CountBot/releases
- GitHub Releases: https://github.com/countbot-ai/CountBot/releases
- Supported platforms: Windows / macOS / Linux

---

## Key Changes in v0.7.0

### 1. Focused on bug fixes and stability improvements

This release first tackles known issues coming from GitHub issues and daily usage feedback, covering tool invocation, configuration flows, skill integration, and interaction details, making CountBot more stable and predictable in complex scenarios.

### 2. Frontend interaction keeps getting tighter and faster

The frontend continues to be optimized around common operation paths, reducing the cognitive load of configuration and skill management so daily use feels more direct.

### 3. The tool invocation chain is now leaner

The tool flow, context assembly, and execution chain were reworked again. Without sacrificing capability coverage, token usage dropped significantly. 

### 4. Model thinking control is more precise

A new thinking control switch lets you decide whether to enable or reduce reasoning intensity based on task complexity, which improves perceived response speed in many high-frequency scenarios.

### 5. SkillsHub is now part of the conversational management flow

The new `find-skills` skill integrates Tencent Cloud SkillsHub into the conversation flow. You can now search, install, enable, disable, and remove skills directly through natural language without manually handling underlying files.

### 6. IMA knowledge base and notes are now built in

CountBot adds two new skills:

- `ima-knowledge-base`: search knowledge bases, inspect hit details, browse entries, upload files, and import web pages
- `ima-notes`: search notes, read notes, create new notes, and append content

This allows CountBot to write material directly into the IMA knowledge base or persist content into the IMA notes system, further strengthening the idea of "conversation as management".

---

## Documentation

| Document | Description | Link |
|------|------|------|
| Quick Start | Installation, configuration, and startup | [https://654321.ai/docs/getting-started/quick-start-guide](https://654321.ai/docs/getting-started/quick-start-guide) |
| Configuration Manual | Full configuration reference | [https://654321.ai/docs/getting-started/configuration-manual](https://654321.ai/docs/getting-started/configuration-manual) |
| Deployment and Operations | Startup, deployment, and troubleshooting | [https://654321.ai/docs/advanced/deployment](https://654321.ai/docs/advanced/deployment) |
| Remote Access Guide | Remote initialization, authentication, and troubleshooting | [https://654321.ai/docs/advanced/remote-access](https://654321.ai/docs/advanced/remote-access) |
| Authentication | Password setup and access boundaries | [https://654321.ai/docs/advanced/auth](https://654321.ai/docs/advanced/auth) |
| API Reference | REST API and WebSocket | [https://654321.ai/docs/api-reference](https://654321.ai/docs/api-reference) |
| Release Notes | Version history and release changes | [https://654321.ai/docs/releases/v0.7.0](https://654321.ai/docs/releases/v0.7.0) |

For the full documentation site, see: [https://654321.ai/docs](https://654321.ai/docs)

---

## Development and Contribution

### Local Development

```bash
uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000
```

### Community

- QQ group: `1028356423`
- Discussion topics: CountBot usage, issue feedback, secondary development, and scenario co-creation

### Issue Reporting

- GitHub Issues: https://github.com/countbot-ai/CountBot/issues

---

## License and Acknowledgements

### License

MIT License

### Project Inspiration

- OpenClaw
- NanoBot
- ZeroClaw
- anthropics/skills

### Technical Thanks

Thanks to FastAPI, Vue.js, SQLAlchemy, Pydantic, LiteLLM, and other open-source projects.

---

<div align="center">
  <p>An AI agent runtime hub that connects models, channels, teams, and tools</p>
  <p>
    <a href="https://654321.ai">Official Website</a> ·
    <a href="https://github.com/countbot-ai/countbot">GitHub</a> ·
    <a href="https://gitee.com/countbot-ai/CountBot">Gitee</a> ·
    <a href="https://654321.ai/docs">Full Documentation</a>
  </p>
</div>
