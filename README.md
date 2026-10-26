<div align="center">
 <h1>CountBot</h1>
  <p>An AI work assistant that runs on your server</p>
  <p>Bind the chat tools you already use, and let it push digests and run tasks on schedule</p>

  <p>
    <a href="README_ZH.md">中文</a> | English
  </p>

  <p>
    <a href="https://github.com/countbot-ai/countbot/stargazers"><img src="https://img.shields.io/github/stars/countbot-ai/countbot?style=social" alt="GitHub stars"></a>
    <a href="https://github.com/countbot-ai/countbot"><img src="https://img.shields.io/badge/Python-3.8+-blue.svg" alt="Python"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License"></a>
  </p>
</div>


---

## What Is CountBot

CountBot is a lightweight, low-footprint AI assistant that runs on your server and stays up. A modest machine is enough to host it. Once it is bound to the chat tools you already use, you can call it directly from Lark, WeCom, WeChat or QQ, or work with it through the web interface.

Unlike a plain chat bot, CountBot can actually execute work. It reads and writes files, runs commands, searches the web, takes screenshots and sends media. Beyond that, you can wrap your recurring routines into skills, let it run on a schedule, and have the results delivered to the channel you choose.

Key points below.

- Entry points are the IM tools you already use, including Lark, WeCom, WeChat, QQ, DingTalk, Telegram and Weibo, plus ServerChan for push-only delivery
- Recurring routines can be wrapped into skills, triggered by a single instruction or run automatically by the scheduler
- Scheduled tasks combine with proactive greetings to push digests, reminders and summaries on plan
- Long-term memory keeps context across sessions, so earlier instructions do not have to be repeated
- 22 model providers are built in, and models can be assigned per session or per task

---

## Skills

The skill system is the core mechanism of CountBot.

A lot of daily work follows fixed procedures. Compiling a competitive digest every week, summarizing new content from a few sites every day, cleaning spreadsheets by a fixed rule. You have done these many times and know the steps by heart, yet still run them by hand each time.

Skills fix that. Write the procedure once, and afterwards a single instruction triggers it, or the scheduler runs it automatically.

Writing one is not hard. Describe when to use it and how it works, and that is enough. If you are not sure where to start, the built-in `skill-creator` walks you through the whole process, from clarifying the goal to validating the result. Finished skills can be enabled, disabled and configured from the panel, or installed from the SkillsHub.

---

## Multi-Agent Teams

For more complex work, a single agent tends to lose track of things. Agent Teams let you group several roles, each owning one part, working in stages or in parallel.

Three orchestration modes are available.

`pipeline` runs stages in sequence, where the output of one stage becomes the input of the next. It suits tasks with a clear order of steps.

`graph` lets you declare dependencies between roles first, then runs everything without unmet dependencies in parallel. It suits tasks with branches and a final merge. If the dependencies form a cycle, the system reports an error instead of looping.

`council` has each member produce an independent result from their own perspective, then review each other, and finally consolidate. It suits judgment calls that need several angles weighed.

Once a team exists, send `/team <team name> <task>` in a session to invoke it, or mention the team name with @.

A team can carry its own model configuration. When configured, execution inside the team uses the team configuration; otherwise it inherits the model of the current session.

---

## Session-Level Model Configuration

Changing models used to mean editing the global default, which affected every session. Now it can be switched inside a session.

A model picker sits next to the chat input. The selection applies only to the current session and leaves the global default untouched. Right beside it, the reasoning effort for that session can be adjusted, with the available levels determined by the model.

Switching the level on the same model is enough to cover different scenarios. Long tasks get a higher level, quick questions drop back to a lower one, without repeated trips to the settings page.

Order of precedence is as follows. The model selected in a session applies to that session; if a team has its own model configured, execution inside the team follows the team configuration; when neither is configured, the global default applies.

---

## What It Can Do For You

| Scenario | Description |
|------|------|
| Daily digest delivery | Scheduled tasks fetch and summarize the topics you specify by cron, then push to Lark, WeChat, QQ, ServerChan and other channels |
| In-group assistant | Mention the bot in a group to ask questions, look up material, draft content and call tools |
| Scheduled tasks and reminders | Run arbitrary instructions on a schedule, with a selectable delivery target and bot account, and a selectable model per task |
| Proactive greetings | A heartbeat mechanism starts conversations or reminders at the frequency you set, suited to schedule reminders and shift handover briefings |
| Material handling | Web scraping, document parsing, knowledge base retrieval, file read/write and batch processing |
| Multi-role collaboration | Split complex work across an Agent Team, run it in parts and consolidate |
| External coding tools | Connect Claude Code, Codex, OpenCode and dsh (DeepSeek Harness), either as callable tools or as agents bound to a channel |

---

## Supported Channels

| Channel | Direction | Notes |
|------|------|------|
| Lark | Two-way | Event subscription, supports groups and direct messages |
| WeCom | Two-way | Enterprise internal bot |
| WeChat | Two-way | Multiple account binding supported |
| QQ | Two-way | QQ Open Platform bot |
| DingTalk | Two-way | Enterprise internal bot |
| Telegram | Two-way | Direct Bot API |
| Weibo | Two-way | Weibo bot |
| Xiaozhi | Two-way | Xiaozhi AI hardware integration |
| ServerChan | Push only | A single HTTP request delivers a notification to WeChat, with no persistent connection, suited to pure broadcasting |

All two-way channels share the same session model. A session processes one turn at a time, so concurrent messages from multiple entry points do not interfere with each other.

---

## Supported Models

22 providers are built in, covering mainstream Chinese and international models, along with OpenAI-compatible custom endpoints and local inference.

```
openrouter   anthropic   openai      deepseek   moonshot   zhipu
groq         mistral     cohere      together   qwen       hunyuan
ernie        doubao      yi          baichuan   minimax    vllm
ollama       lm_studio   custom_openai          custom_anthropic
```

The request protocol is determined by the provider setting or by user selection.

| Protocol | Endpoint |
|------|------|
| OpenAI Chat Completions | `/chat/completions` |
| OpenAI Responses | `/responses` |
| Anthropic Messages | `/v1/messages` |

A single provider can hold multiple models, fetched from the upstream `/models` endpoint or entered manually. Each model records its context window, image input capability, reasoning levels and related metadata. The global default, session level and scheduled task level can each designate which model to use.

---

## Core Capabilities

| Module | Description |
|------|------|
| Skill system | Turn recurring routines into skills that load automatically as callable capability. Supports enable/disable, parameter configuration and SkillsHub installs, with `skill-creator` built in for guided creation |
| Multi-agent teams | Three orchestration modes, `pipeline`, `graph` and `council`, invoked through `/team` or @, with optional team-level model configuration |
| Agent Loop | ReAct reasoning, tool invocation, result feedback and iteration control |
| Layered configuration | Team, session and global layers fall back in order, and each layer can designate its own model |
| Channel matrix | A single workspace serves multiple channels, bot accounts and business entry points |
| Providers and models | Multiple model lists, three protocols, and context window and image capability metadata |
| Reasoning levels | Levels declared per model, adjustable at session and task level, with support for custom values |
| Context compaction | A four-stage pipeline of pruning, boundary, summarization and assembly, triggered automatically by water level or manually from the session list |
| Memory | One fact per record, where a new value under the same key replaces the old one, across `pinned`, `recent` and `archived` tiers |
| Built-in tools | Files, Shell, web, screenshots, memory, workflows, media delivery, file search, external coding tools |
| External execution tools | Claude Code, Codex, OpenCode and dsh (DeepSeek Harness) connected to a unified runtime |
| Knowledge base | Wiki module with BM25 full-text retrieval, which can layer a vector channel on top once an embedding endpoint is configured |
| MCP | Multi-server connections, health checks and tool discovery, disabled by default |
| Scheduling and heartbeat | Cron tasks, proactive greetings and long-running background operation, with selectable model and delivery target |
| Security and workspace | Path restrictions, audit logs, timeout control, remote authentication boundary and a one-time initialization entry |

---

## Latest Updates

- **v1.0.0 · 2026-10-24**
  - Reworked the provider system: model lists per provider, the OpenAI Responses protocol and explicit protocol selection, with existing configuration migrated automatically
  - Added reasoning levels: available levels declared per model, customizable, and assignable per session or scheduled task
  - Added model switching in the chat input: per-session model and level without touching the global default
  - Split context compaction into a standalone module (pruning, boundary, summarization, assembly) with a manual compaction entry in the session list
  - Reworked memory into an assertion store: three lifecycle tiers, inferred content kept in cold storage only, plus a migration script
  - Added the ServerChan push channel, with the session target field omitted for push-only channels on the scheduled task page
  - Scheduled tasks now support a per-task model and reasoning level
  - Enabled SQLite WAL and busy_timeout to reduce write lock waits under long-lived connections
  - Completed usage accounting with cache hits and reasoning tokens, and filtered invisible upstream output to avoid rendering empty reasoning blocks
  - Added a queued state for subagents, making cancellation propagation and terminal state convergence more reliable
  - Messages now render interleaved in the order text and tool calls actually occur
  - Front-end interface reworked and optimized for a better overall experience

- **v0.9.0**
  - Added MCP client module with multi-server connections, health checks, and tool discovery. Disabled by default, designed for advanced users with personalized needs
  - Added Wiki knowledge base module with BM25 full-text search, batch retrieval, relevance filtering, and LRU cache
  - New MCP and Wiki management panels with component modularization and i18n support
  - New WebSocket status broadcast module for real-time MCP connection state sync to frontend
  - Improved context management and heartbeat mechanism, simplified greeting logic to reduce LLM calls
  - Refined tool registration and initialization flow for better startup consistency
  - Added API Key rotation with automatic failover and multi-key support
  - Improved send_media tool compatibility for web mode, supports image preview and file download in Web UI
  - Optimized model preset interface and updated build artifacts
  - Release notes: [https://countbot.cn/docs/releases/v0.9.0](https://countbot.cn/docs/releases/v0.9.0)

- **v0.8.0**
  - Fixed a batch of issues reported by users and known bugs in high-frequency scenarios
  - Overall improvements to the frontend interface and interaction experience
  - Continued optimization of the response path for accuracy, timeliness and stability
  - Reworked session context maintenance with short-term summary cache, overflow history summarization and whole-session memory persistence
  - Strengthened multi-channel stability for WeChat, WeCom and Lark message handling, deduplication and streaming delivery
  - Improved proactive greeting and scheduled execution logic, avoiding premature counting on failed delivery and refreshing the daily plan after configuration changes
  - Refined reasoning switches and runtime configuration resolution, adding reasoning field mappings for different providers and persona merge strategy
  - Unified host and port environment variables at startup, documented `COUNTBOT_HOST` / `COUNTBOT_PORT`
  - Release notes: [https://countbot.cn/docs/releases/v0.8.0](https://countbot.cn/docs/releases/v0.8.0)

- **v0.7.0**
  - Resolved multiple issues and fixed a batch of known bugs for better overall stability
  - Added file upload and processing logic to the Web UI, improved Mermaid chart rendering
  - Refined the frontend interface and interaction flow for skills, configuration and tools
  - Optimized the tool invocation path and context organization, significantly reducing token consumption
  - Added a model reasoning switch to adjust effort per scenario for faster responses
  - Added `find-skills`, fully integrated with Tencent Cloud SkillsHub for searching, installing, enabling, disabling and deleting skills through conversation
  - Added `ima-knowledge-base` and `ima-notes`, integrating IMA knowledge base and note capabilities, including knowledge base search, upload and web import, plus note search, read, create and append
  - Release notes: [https://countbot.cn/docs/releases/v0.7.0](https://countbot.cn/docs/releases/v0.7.0)

- **v0.6.0**
  - Added WeChat ClawBot integration with multiple account binding
  - Added external coding tool integration (Claude/Codex/OpenCode), usable either as a tool for LLM invocation or as an agent bound to IM channels
  - Added a remote first-time initialization entry at `/setup/<random>`
  - Added `REMOTE_SETUP_SECRET_TTL_MINUTES` to control the validity window of the remote initialization entry
  - Strengthened the remote authentication boundary, covering `/api/*` and `/ws/chat`
  - Release notes: [https://countbot.cn/docs/releases/v0.6.0](https://countbot.cn/docs/releases/v0.6.0)

- **v0.5.0**
  - Agent Team took shape, with multi-role division, context handoff and team-level orchestration
  - Configuration evolved from session level to role level, team level and multi-bot coordination
  - The channel system gained further enterprise and social entry points
  - The frontend chat, configuration, skills, teams and tools panels were upgraded overall
  - Release notes: [https://countbot.cn/docs/releases/v0.5.0](https://countbot.cn/docs/releases/v0.5.0)

- **v0.4.0**
  - Introduced session-level configuration, allowing different models and prompts per session
  - Extended channel support for Lark, WeCom, Weibo and Xiaozhi AI
  - Improved multi-agent collaboration and added the `/help` entry
  - Release notes: [https://countbot.cn/docs/releases/v0.4.0](https://countbot.cn/docs/releases/v0.4.0)

- **v0.3.0**
  - Multi-agent collaboration (`pipeline` / `graph` / `council`) landed as a systematic capability
  - Scheduled tasks, skill configuration and workspace management were significantly enhanced
  - Release notes: [https://countbot.cn/docs/releases/v0.3.0](https://countbot.cn/docs/releases/v0.3.0)

- **v0.2.0 · 2026-02-26**
  - Focused on bug fixes, interaction improvements and build process cleanup
  - Moved CountBot from "runnable" toward "stably iterable"

- **First open source release · 2026-02-21**
  - CountBot was open sourced for the first time, covering the base framework, startup scripts, agent core, channel system, tool system, skill system and base frontend
  - Public iteration has continued since that day

---

## Why CountBot

The way software is used keeps changing. Commands had to be memorized and configuration learned; today more and more operations take a single natural-language sentence.

The real difficulty is never the model itself, but how to bring models, tools, channels, permission boundaries and long-running operation into one system that can be deployed and maintained. Building a demo is not hard; running stably for months is a different order of requirement.

OpenClaw proved the direction viable for local execution and autonomous agents. CountBot fills in what it does not cover, including Chinese-language scenarios, server-resident operation, a lower barrier to entry, security control and governance.

---

## Quick Start

### Option 1: Run From Source

```bash
git clone https://github.com/countbot-ai/CountBot.git
cd CountBot

# default install
pip install -r requirements.txt

# Aliyun mirror for networks in China
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

python start_app.py
```

Once started, `http://127.0.0.1:8000` opens by default.

The listen address and port can be overridden with environment variables, where `COUNTBOT_HOST` / `COUNTBOT_PORT` take precedence over the defaults.

```bash
# Linux / macOS, bind 0.0.0.0 for server-resident use and put a reverse proxy in front
COUNTBOT_HOST=0.0.0.0 COUNTBOT_PORT=8000 python start_app.py
```

```powershell
$env:COUNTBOT_HOST = '0.0.0.0'
$env:COUNTBOT_PORT = '8001'
python start_app.py
```

```cmd
set COUNTBOT_HOST=0.0.0.0
set COUNTBOT_PORT=8001
python start_app.py
```

If GitHub is hard to reach from China, switch to Gitee.

```bash
git clone https://gitee.com/countbot-ai/CountBot.git
```

### Option 2: Desktop Build

- Gitee Releases: https://gitee.com/countbot-ai/CountBot/releases
- GitHub Releases: https://github.com/countbot-ai/CountBot/releases
- Platforms: Windows / macOS / Linux

### Deploying To A Server

CountBot is an ordinary web service and can be hosted persistently with `systemd`, `supervisor` or a container. Before opening remote access, set the initialization password first, then open the port as needed and configure a reverse proxy. The initialization entry is one-time, and its validity window is controlled by `REMOTE_SETUP_SECRET_TTL_MINUTES`.

---

## Project Status

CountBot is still under active iteration. Since the early base framework, the provider and model system, context compaction, memory storage and channel matrix have all undergone substantial rework, so the directory structure may look different if you come back after a while.

Questions and bug reports are welcome through Issues, and pull requests for fixes, new capabilities and documentation are accepted.

---

## Development And Contributing

### Local Development

```bash
# backend
uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000

# frontend
cd frontend && npm install && npm run dev
```

### Reporting Issues

- GitHub Issues: https://github.com/countbot-ai/CountBot/issues

---

## License And Credits

### License

MIT License

### Contributors

Thanks to the following contributors for the code and documentation they have submitted.

<p>
<a href="https://github.com/ddggkkcc" title="ddggkkcc"><img src="https://github.com/ddggkkcc.png?size=96" width="48" height="48" alt="ddggkkcc"></a>
<a href="https://github.com/23821" title="23821"><img src="https://github.com/23821.png?size=96" width="48" height="48" alt="23821"></a>
<a href="https://github.com/ct-jaryn" title="ct-jaryn"><img src="https://github.com/ct-jaryn.png?size=96" width="48" height="48" alt="ct-jaryn"></a>
<a href="https://github.com/hhzscreate" title="hhzscreate"><img src="https://github.com/hhzscreate.png?size=96" width="48" height="48" alt="hhzscreate"></a>
<a href="https://github.com/Liears" title="Liears"><img src="https://github.com/Liears.png?size=96" width="48" height="48" alt="Liears"></a>
<a href="https://github.com/mozhuanzuojing" title="mozhuanzuojing"><img src="https://github.com/mozhuanzuojing.png?size=96" width="48" height="48" alt="mozhuanzuojing"></a>
<a href="https://github.com/ranpis02" title="ranpis02"><img src="https://github.com/ranpis02.png?size=96" width="48" height="48" alt="ranpis02"></a>
</p>

### Inspiration

- OpenClaw
- NanoBot
- ZeroClaw
- anthropics/skills

### Technical Credits

Thanks to the open-source projects FastAPI, Vue.js, SQLAlchemy and Pydantic.

---

<div align="center">
  <p>An AI work assistant that runs on your server, for the long haul</p>
  <p>
    <a href="https://countbot.cn">Website</a> ·
    <a href="https://github.com/countbot-ai/countbot">GitHub</a> ·
    <a href="https://gitee.com/countbot-ai/CountBot">Gitee</a> ·
    <a href="https://countbot.cn/docs">Documentation</a>
  </p>
</div>
