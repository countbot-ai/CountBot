<div align="center">
  <img src="https://github.com/user-attachments/assets/d42ee929-a9a9-4017-a07b-9eb66670bcc3" alt="CountBot Logo" width="180">
  <p>Lightweight, Extensible AI Agent Framework | Optimized for Chinese Users & Domestic LLMs</p>

  <p>
    <a href="https://github.com/countbot-ai/countbot/stargazers"><img src="https://img.shields.io/github/stars/countbot-ai/countbot?style=social" alt="GitHub stars"></a>
    <a href="https://github.com/countbot-ai/countbot"><img src="https://img.shields.io/badge/Python-3.11+-blue.svg" alt="Python"></a>
    <a href="https://github.com/countbot-ai/countbot"><img src="https://img.shields.io/badge/Lines-~21K-brightgreen.svg" alt="Lines of Code"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License"></a>
  </p>

  <p>
    <a href="README.md">中文</a> | English
  </p>
</div>

---

## What's New

- Feb 21, 2026 — CountBot officially open-sourced with standardized codebase
- Feb 19, 2026 — CountBot project launched

---

## What is CountBot?

CountBot is a lightweight, extensible AI Agent framework optimized for Chinese users and domestic LLMs. With only ~21,000 lines of Python, it delivers production-grade intelligent assistant infrastructure featuring:

- Smart Memory — Auto-summarizes conversations, never forgets important info
- Proactive Greeting — Like a real assistant, reaches out when you're idle
- Zero-Config Security — Frictionless local access, auto-protected remote access
- Multi-Channel Unified — One codebase serving Web, Lark, DingTalk, QQ, Telegram, WeChat
- Personalization — 12 personality presets + custom nicknames and location
- Message Queue — Priority scheduling, deduplication, dead-letter handling
- Domestic LLM Optimized — Deep support for Zhipu, Qwen, Kimi, MiniMax, DeepSeek, etc.

Core philosophy: Make AI Agents into digital companions with memory, emotion, initiative, and collaboration.

---

## Why CountBot?

### Top 10 Highlights

| Highlight | Description | Advantage |
|-----------|-------------|-----------|
| Chinese-Friendly | 21K lines with full Chinese comments, comprehensive docs, deep domestic LLM integration | Low learning curve |
| Dual Deployment | B/S browser + C/S desktop client, one codebase | Fits personal & team use |
| Domestic Ecosystem | 10 built-in skill plugins: search, maps, email, file transfer, web publishing, etc. | Works out of the box |
| GUI Configuration | Full web-based management, zero config file editing | Fewer config errors |
| Deep Personalization | 12 personality system + custom nicknames & location | Warm interaction |
| High Performance | Smart context compression, significantly reduced token usage | Cost-effective |
| Progressive Security | Local access fully open, remote access auto-protected | Security meets convenience |
| Lightweight | 21K lines vs 50K–400K in other frameworks, modular design | Easy to read & extend |
| Smart Memory | Auto-summarize, keyword search, never forget | Long-term companion |
| Message Queue | 4-level priority, deduplication, dead-letter handling | Production-grade reliability |

---

## Use Cases

CountBot combines built-in tools and skill plugins to handle a variety of daily tasks:

### Information Retrieval & Search

"Search for today's AI news"
- Uses Baidu Search skill to fetch and summarize the latest information

"Find Western restaurants in Dongguan, I plan to leave at 6 PM"
- Calls Amap (Gaode) skill to search restaurants and plan routes

"What's the weather like today?"
- Queries the weather skill for real-time and forecast data

### Email & File Management

"Check if I have any new emails today"
- Connects to QQ/163 mailbox via email skill, auto-checks new mail

"Compress the images on my desktop and send them to my email"
- Uses file tools to package files, sends via email skill

### Image Processing & Creation

"Generate a picture of a cat celebrating New Year and send it to me"
- Calls image generation skill for AI art, delivers via channel

"Take a screenshot of my computer and send it to me"
- Uses screenshot tool to capture screen, sends via Lark/DingTalk

"What's in this image?"
- Image analysis skill identifies content with detailed descriptions

### Web Design & Publishing

"Design a personal resume webpage and publish it online"
- Uses web design skill to generate HTML, auto-deploys to Cloudflare Pages

### Browser Automation

"Open Bing in the browser, search for AI, open the third result, then screenshot it for me"
- Browser automation skill handles complex web operation workflows

### Scheduled Tasks

"Check the weather for me every morning at 8 AM"
- Sets up a Cron task that auto-executes and pushes results

### Multi-Channel Collaboration

CountBot runs simultaneously on Web, Lark, DingTalk, QQ, and more. All channels share the same smart memory system — no matter where you chat, the AI remembers your preferences and history.

---

## Core Features

### Smart Memory System

CountBot's memory system includes:

- **Auto Conversation Summary** — LLM decides when to summarize, extracting key information
- **Rolling Context Compression** — Auto-compresses when conversation exceeds window, no info lost
- **Keyword Search** — Fast retrieval of historical memories by keyword
- **Line-Based Storage** — Simple, reliable file storage, easy to backup and migrate

```python
# Memory system works automatically
User: "My name is John, I live in Beijing"
AI: "Got it, I'll remember that"

# Days later...
User: "Where do I live again?"
AI: "You live in Beijing"  # Auto-retrieved from memory
```

### Heartbeat Proactive Greeting

CountBot has **proactive care capabilities**:

- **Smart Idle Detection** — Monitors user's last active time
- **Do Not Disturb** — Supports DND time windows (e.g., 22:00–08:00 Beijing time)
- **Daily Limit** — Prevents over-disturbance (default: max 2 per day)
- **Natural Randomness** — Not mechanical timed greetings, but natural care

```python
# User inactive for 4 hours, within active hours
AI: "Long time no see! What have you been up to? Need any help?"
```

### Zero-Config Security Model

An innovative **progressive security** design:

- **Local Access (127.0.0.1)** → Zero friction, direct use
- **Remote Access (192.168.x.x)** → Guided password setup on first visit
- **Password Requirements** → Min 8 chars, upper/lowercase + digits
- **Session Management** → 24-hour validity

```bash
# Local use — no configuration needed
http://localhost:8000  ✅ Direct access

# Remote use — auto-protected
http://192.168.1.100:8000  🔐 First-time password setup
```

### Personalization

In the Settings page under "User Management", you can configure:

12 Personality Presets

CountBot offers 12 distinct personality settings: Hot-Tempered Bro, Roast Master, Gentle Sister, Straight Shooter, Sharp-Tongued Boss, Chatterbox, Philosopher, Soft & Cute Assistant, Comedian, Energetic, Chuunibyou, Zen Master. You can also fully customize the personality description to match your usage habits.

Custom Nicknames & Location

- AI Name — Give your assistant a name (default: CountBot)
- User Nickname — How the AI addresses you
- User Location — Your location info (e.g., Dongguan), used for weather, maps, trip planning

### Precision On-Demand Cron Scheduler

Not polling, not a simple timer, but a **smart scheduling system**:

- **Precision Wake** — Calculates next task time, accurate to the second
- **Concurrency Control** — Semaphore-based max concurrency
- **Timeout Protection** — Max execution time per task (default: 300s)
- **Independent Sessions** — Each task uses its own database session
- **SQLite Lock Retry** — Auto-handles concurrent write conflicts

```python
# Not polling every second, but precisely calculating next wake time
next_wake = min([job.next_run for job in enabled_jobs])
await asyncio.sleep((next_wake - now).total_seconds())
```

---

## Quick Start

### One-Click Launch

```bash
# Clone the repository
git clone https://github.com/countbot-ai/countbot.git
cd countbot

# Install dependencies
pip install -r requirements.txt

# Start (auto-opens browser)
python start_app.py
```

Visit `http://localhost:8000`, configure an LLM provider in the settings page, and you're ready to go.

### Download Desktop Version

```
https://github.com/countbot-ai/CountBot/releases
Supports Windows / macOS / Linux
```

### Recommended Configuration

Notable Chinese AI models: GLM-5, MiniMax-M2.5, Kimi K2.5, Qwen3.5-Plus, DeepSeek Chat, etc.

Zero-cost start: Use Zhipu AI's free GLM-4.7-Flash model

1. Visit [Zhipu AI Open Platform](https://open.bigmodel.cn/)
2. Register and obtain an API Key
3. Select "Zhipu AI" in CountBot settings, enter the API Key
4. Start using!

---

## Architecture

### Project Structure

```
countbot/
├── backend/                   # Backend (~21K lines)
│   ├── modules/
│   │   ├── agent/             # Agent Core
│   │   │   ├── loop.py        # ReAct Loop
│   │   │   ├── memory.py      # Smart Memory
│   │   │   ├── heartbeat.py   # Proactive Greeting
│   │   │   ├── personalities.py # 12 Personalities
│   │   │   └── context.py     # Context Builder
│   │   ├── messaging/         # Message Queue
│   │   │   ├── enterprise_queue.py # Message Queue
│   │   │   └── rate_limiter.py     # Token Bucket
│   │   ├── cron/              # Cron Scheduler
│   │   │   └── scheduler.py   # Precision Wake
│   │   ├── auth/              # Authentication
│   │   │   └── middleware.py  # Zero-Config Security
│   │   ├── channels/          # Channel Management
│   │   ├── providers/         # LLM Providers
│   │   └── tools/             # Tool System (13)
├── frontend/                  # Frontend (Vue 3 + TypeScript)
├── skills/                    # Skill Plugins (10)
└── docs/                      # Documentation
```

---

## Tech Stack

### Backend

- **FastAPI** — Modern web framework with native async & WebSocket support
- **SQLAlchemy 2.0** — Async ORM with complex query support
- **aiosqlite** — SQLite async driver, zero-config database
- **LiteLLM** — Unified LLM interface, supports all major models
- **Pydantic v2** — Data validation and config management
- **Loguru** — Structured logging, easy debugging
- **cryptography** — Fernet encryption for API key protection

### Frontend

- **Vue 3** — Progressive framework, Composition API
- **TypeScript** — Type safety, fewer runtime errors
- **Pinia** — Lightweight state management
- **Vue I18n** — Internationalization (Chinese/English)
- **Axios** — HTTP client with auto-retry
- **Lucide Icons** — Modern icon library

> **Note:** Frontend source code is currently undergoing final optimization and will be fully uploaded upon completion. The `frontend/dist/` directory contains pre-built HTML files that are fully functional.

---

## Documentation

| Document | Description |
|----------|-------------|
| [Quick Start Guide](docs/quick-start-guide.md) | Feature setup, API key acquisition |
| [Deployment](docs/deployment.md) | Installation, startup, production deployment |
| [Agent Loop](docs/agent-loop.md) | ReAct loop principles |
| [Memory System](docs/memory.md) | Auto-summary, context compression |
| [Cron Scheduler](docs/cron.md) | Precision wake, concurrency control |
| [Channel System](docs/channels.md) | Multi-channel configuration |
| [Tool System](docs/tools.md) | 13 built-in tools |
| [Skill System](docs/skills.md) | 10 plugin development |
| [Remote Auth](docs/auth.md) | Zero-config security model |
| [Configuration Manual](docs/configuration-manual.md) | Complete config reference |
| [API Reference](docs/api-reference.md) | REST API + WebSocket |

---

## Supported LLMs (via LiteLLM Unified Interface)

CountBot uses LiteLLM as a unified interface layer, compatible with OpenAI / Anthropic / Gemini protocols, supporting all major LLMs:

### Recommended Chinese LLMs

| Provider | Model Examples | Access |
|----------|---------------|--------|
| Zhipu AI | glm-4.7-flash (free), GLM-5 | [open.bigmodel.cn](https://open.bigmodel.cn) |
| Qwen | Qwen3.5-Plus | [dashscope.aliyun.com](https://dashscope.aliyun.com) |
| Moonshot | Kimi K2.5 | [platform.moonshot.cn](https://platform.moonshot.cn) |
| MiniMax | MiniMax-M2.5 | [platform.minimax.io](https://platform.minimax.io) |
| DeepSeek | DeepSeek Chat | [platform.deepseek.com](https://platform.deepseek.com) |
| Doubao | Doubao-Pro-32K | [volcengine.com](https://volcengine.com) |
| Baidu ERNIE | ERNIE-4.0-8K | [qianfan.baidubce.com](https://qianfan.baidubce.com) |
| Tencent Hunyuan | Hunyuan-Lite | [hunyuan.tencentcloudapi.com](https://hunyuan.tencentcloudapi.com) |
| Yi | Yi-Large | [platform.lingyiwanwu.com](https://platform.lingyiwanwu.com) |
| Baichuan | Baichuan4 | [platform.baichuan-ai.com](https://platform.baichuan-ai.com) |

### International LLMs

| Provider | Model Examples | Access |
|----------|---------------|--------|
| OpenAI | gpt-5.3 | [platform.openai.com](https://platform.openai.com) |
| Anthropic | Claude Sonnet 4 | [console.anthropic.com](https://console.anthropic.com) |
| Gemini | Gemini 2.0 Flash | [aistudio.google.com](https://aistudio.google.com) |
| Groq | Llama 3.3 70B | [console.groq.com](https://console.groq.com) |
| Mistral | Mistral Large | [console.mistral.ai](https://console.mistral.ai) |
| Cohere | Command R+ | [dashboard.cohere.com](https://dashboard.cohere.com) |
| Together AI | Llama 3.3 70B Turbo | [api.together.xyz](https://api.together.xyz) |
| OpenRouter | Multi-model aggregation | [openrouter.ai](https://openrouter.ai) |

### Local Deployment

| Method | Description |
|--------|-------------|
| Ollama | Local open-source model deployment |
| vLLM | High-performance inference engine |
| LM Studio | GUI-based local deployment |

### Custom Compatible APIs

| Protocol | Description |
|----------|-------------|
| OpenAI Compatible | Any OpenAI-protocol compatible API |
| Anthropic Compatible | Any Anthropic-protocol compatible API |
| Gemini Compatible | Any Gemini-protocol compatible API |

---

## Supported Channels

| Channel | Connection | Configuration |
|---------|-----------|---------------|
| Web UI | Built-in | No config needed |
| Lark (Feishu) | WebSocket | App ID + App Secret |
| DingTalk | Stream Mode | Client ID + Client Secret |
| QQ | Official SDK | App ID + Secret |
| WeChat (Coming Soon) | Official Account API | App ID + App Secret + Token |
| Telegram | Long Polling | Bot Token (proxy supported) |
| Discord (Coming Soon) | Gateway | Bot Token |

All channels support `allow_from` whitelist for access control.

---

## Built-in Tools (13)

| Tool | Function |
|------|----------|
| `read_file` | Read file content |
| `write_file` | Write file content |
| `edit_file` | Edit file (replace/insert/delete) |
| `list_dir` | List directory contents |
| `exec` | Execute shell commands (sandboxed) |
| `web_fetch` | Fetch web page content |
| `memory_read` | Read long-term memory |
| `memory_write` | Write long-term memory |
| `memory_search` | Search memory |
| `screenshot` | Capture screen |
| `file_search` | Search files |
| `spawn` | Create sub-agent |
| `send_media` | Send media files |

---

## Built-in Skill Plugins (10)

| Skill | Description | Config |
|-------|-------------|--------|
| Baidu Search | Baidu AI search with web, encyclopedia, AI generation | API Key |
| Cron Manager | Create/manage scheduled tasks via chat | No config |
| Email | QQ/163 mailbox send/receive with attachments | Email auth code |
| Image Analysis | Zhipu/Qwen vision models, OCR, object recognition | API Key |
| Image Generation | ModelScope text-to-image with LoRA style stacking | API Token |
| Map Navigation | Amap route planning & POI search | API Key |
| News Aggregation | Chinese news + global AI news, multi-category RSS | No config |
| Weather | wttr.in weather service, global city support | No config |
| Web Design | HTML generation + Cloudflare Pages one-click deploy | API Token |
| Browser Automation | agent-browser CLI, web ops, screenshots, data extraction | Manual install |

---

## Security Features

### Progressive Security Model

```
Local Access (127.0.0.1)
    ↓
  Zero Friction
    ↓
  Direct Use

Remote Access (192.168.x.x)
    ↓
  First Visit
    ↓
  Guided Password Setup
    ↓
  Login Required
```

### Command Sandbox

- Workspace isolation (`restrict_to_workspace`)
- Path traversal detection
- Null byte injection blocking
- Command whitelist/blacklist
- Audit logging

### API Key Encryption

- Fernet symmetric encryption
- Encrypted storage in SQLite
- Runtime auto-decryption

### Rate Limiting

- Token bucket algorithm
- Per-user rate limiting
- Configurable rate and burst size

---

## Contributing

We welcome all forms of contribution!

### Development Environment

```bash
# Backend development (hot reload)
uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000

# Frontend development
cd frontend
npm install
npm run dev
```

### Adding New Components

- New LLM Provider → `backend/modules/providers/`
- New Channel → `backend/modules/channels/`
- New Tool → `backend/modules/tools/`
- New Skill → `skills/<skill-name>/`

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

---

## License

[MIT License](LICENSE)

---

## Acknowledgments

CountBot's creation was inspired and supported by the open-source community.

### Project Inspiration

- [PicoClaw](https://github.com/sipeed/picoclaw) — Thanks to the PicoClaw team for demonstrating the possibility of ultra-lightweight AI Agents. CountBot's tool system and core architecture were deeply inspired by it.

- [NanoBot](https://github.com/HKUDS/nanobot) — Thanks to the NanoBot team for showcasing clean code organization and modular design.

- [ZeroClaw](https://github.com/zeroclaw-labs/zeroclaw) — Thanks to the ZeroClaw team for their exploration in security and performance. CountBot's security architecture references their security-first design philosophy.

### Tech Stack

Thanks to the following open-source projects and communities:

- [FastAPI](https://fastapi.tiangolo.com/) — Modern Python web framework
- [Vue.js](https://vuejs.org/) — Progressive JavaScript framework
- [LiteLLM](https://github.com/BerriAI/litellm) — Unified LLM API interface
- [SQLAlchemy](https://www.sqlalchemy.org/) — Python SQL toolkit and ORM
- [Pydantic](https://docs.pydantic.dev/) — Data validation and settings management

### Community

Special thanks to all developers and users who provided feedback, suggestions, and contributions to CountBot. You make AI technology more accessible and user-friendly.

### Open Source Spirit

CountBot embraces the open-source spirit, committed to making AI Agent technology more transparent, controllable, and easy to use. We believe that through open-source collaboration, more people can benefit from the advancement of AI technology.

---

<div align="center">
  <p>Lightweight, Extensible AI Agent Framework | Optimized for Chinese Users & Domestic LLMs</p>
  <br>
  <p>
    <a href="https://654321.ai">Website</a> ·
    <a href="https://github.com/countbot-ai/countbot">GitHub</a> ·
    <a href="docs/README.md">Docs</a> ·
    <a href="https://github.com/countbot-ai/countbot/issues">Issues</a>
  </p>
  <br>
  <p><sub>CountBot is for educational, research, and technical exchange purposes only</sub></p>
</div>
