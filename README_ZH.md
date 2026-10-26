<div align="center">
 <h1>CountBot</h1>
  <p>部署在服务器上的 AI 工作助手</p>
  <p>绑定日常使用的聊天工具，按计划推送资讯、执行任务</p>

  <p>
    中文 | <a href="README.md">English</a>
  </p>

  <p>
    <a href="https://github.com/countbot-ai/countbot/stargazers"><img src="https://img.shields.io/github/stars/countbot-ai/countbot?style=social" alt="GitHub stars"></a>
    <a href="https://github.com/countbot-ai/countbot"><img src="https://img.shields.io/badge/Python-3.8+-blue.svg" alt="Python"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License"></a>
  </p>
  <img src="https://github.com/user-attachments/assets/5a848b1f-04bf-40ff-8249-8a453294f444" alt="CountBot Logo" width="680">
</div>


---

## CountBot 是什么

CountBot 是一套部署在服务器上长期运行的 AI 助手，轻量、低资源占用，一台小机器就能跑起来。绑定常用的聊天工具之后，它常驻在后台，你可以在飞书、企业微信、微信、QQ 中直接呼叫它，也可以使用 Web 界面。

与常见的对话机器人不同，CountBot 具备实际执行能力，可以读写文件、执行命令、检索网页、截图、发送媒体。在此基础上，还可以把日常重复的流程封装成技能交给它，按计划自动执行，并将结果推送到指定渠道。

主要特点如下。

- 入口为日常使用的 IM，飞书、企业微信、微信、QQ、钉钉、Telegram、微博，以及仅做推送的 Server酱
- 重复流程可封装为技能，一句指令即可触发，也可交由定时任务自动运行
- 定时任务与主动问候结合，支持按计划推送资讯、提醒与汇总
- 具备长期记忆，跨会话保留此前交代的事项
- 内置 22 家模型供应商，支持会话级与任务级独立指定模型

---

## 技能

技能系统是 CountBot 的核心机制。

日常工作里有大量流程其实是固定的，比如每周整理一次竞品动态，每天汇总几个站点的新内容，或按固定规则清洗表格。这些事你做过很多遍，步骤心里有数，但每次还是得亲手来一遍。

技能就是把这类流程固化下来。写一次，之后一句指令就能触发，也可以交给定时任务按计划自动执行。

写技能本身不复杂，说清楚「什么时候用它、具体怎么做」就够了。不确定从哪下手的，内置的 `skill-creator` 会带着走完整个流程，从明确目标到验证效果逐步调整。做好的技能可以在面板里启停、配置参数，也能从 SkillsHub 安装别人做好的。

---

## 多智能体团队

面对较复杂的任务，单个 Agent 容易顾此失彼。Agent Team 允许把多个角色组成团队，各自负责一部分，分阶段或并行完成。

团队支持三种编排模式。

`pipeline` 为流水线模式，各阶段顺序执行，上一阶段的产出作为下一阶段的输入，适合步骤顺序明确的任务。

`graph` 为依赖图模式，先声明角色之间的依赖关系，无依赖的部分并行执行，适合存在分支与汇总的任务。若依赖关系构成环，系统会直接报错。

`council` 为议会模式，各成员先按各自视角独立给出一版结果，再相互评审，最后汇总，适合需要多角度权衡的判断类问题。

团队创建完成后，在会话中发送 `/team 团队名 任务描述` 即可调用，也可以在消息中 @ 团队名。

团队可单独配置模型。已配置时，团队内部的执行使用团队配置；未配置时继承当前会话的模型。

---

## 会话级模型配置

以往更换模型需要修改全局默认，所有会话随之变化。现在可以直接在会话内切换。

对话输入框旁提供模型选择器，选择结果仅作用于当前会话，不影响全局默认。旁边可以同时调整该会话的思考强度，可选档位由具体模型决定。

同一个模型切换档位即可应对不同场景，长任务使用更高档位，简单问答调回低档位，无需反复修改设置。

配置生效顺序为，会话内选定的模型作用于该会话；团队若配置了独立模型，团队内部的执行以团队配置为准；两者均未配置时使用全局默认。

---

## 它能帮你做什么

| 场景 | 说明 |
|------|------|
| 每日资讯推送 | 定时任务按 cron 抓取并汇总指定话题，推送到飞书、微信、QQ、Server酱 等渠道 |
| 群内助手 | 在群聊中 @ 机器人即可问答、检索资料、撰写内容、调用工具 |
| 定时任务与提醒 | 按计划执行任意指令，可指定投递目标与机器人账号，也可指定该任务使用的模型 |
| 主动问候 | 通过心跳机制按设定频率主动发起会话或提醒，适用于日程提醒、值班播报等场景 |
| 资料整理与检索 | 网页抓取、文档解析、知识库检索、文件读写与批量处理 |
| 多角色协作 | 通过 Agent Team 拆分复杂任务，分头执行后汇总 |
| 外部编程工具协作 | 接入 Claude Code、Codex、OpenCode、dsh（DeepSeek Harness），既可作为工具调用，也可挂载到渠道作为代理 |

---

## 支持的渠道

| 渠道 | 方向 | 说明 |
|------|------|------|
| 飞书 | 双向 | 事件订阅接入，支持群聊与私聊 |
| 企业微信 | 双向 | 企业内机器人 |
| 微信 | 双向 | 支持多账号绑定 |
| QQ | 双向 | QQ 开放平台机器人 |
| 钉钉 | 双向 | 企业内部机器人 |
| Telegram | 双向 | 直连 Bot API |
| 微博 | 双向 | 微博机器人 |
| 小智 | 双向 | 小智 AI 硬件接入 |
| Server酱 | 仅推送 | 单次 HTTP 请求即可推送通知到微信，无需常驻连接，适合纯播报场景 |

所有双向渠道共用同一套会话模型，同一会话同一时刻只处理一轮，多入口并发不会相互干扰。

---

## 支持的模型

内置 22 家供应商，覆盖国产与国外主流模型，同时支持 OpenAI 兼容的自定义端点与本地推理。

```
openrouter   anthropic   openai      deepseek   moonshot   zhipu
groq         mistral     cohere      together   qwen       hunyuan
ernie        doubao      yi          baichuan   minimax    vllm
ollama       lm_studio   custom_openai          custom_anthropic
```

请求协议取决于供应商设定或用户选择。

| 协议 | 端点 |
|------|------|
| OpenAI Chat Completions | `/chat/completions` |
| OpenAI Responses | `/responses` |
| Anthropic Messages | `/v1/messages` |

单个供应商下可以维护多个模型，支持从上游 `/models` 拉取或手工录入。每个模型记录上下文窗口、图片输入能力与思考档位等信息。全局默认、会话级、定时任务级均可各自指定使用哪个模型。

---

## 核心能力

| 模块 | 说明 |
|------|------|
| 技能系统 | 将日常重复流程固化为技能，放入工作区后自动加载为可调用能力。支持启停、参数配置、SkillsHub 安装，内置 `skill-creator` 引导创建 |
| 多智能体团队 | `pipeline`、`graph`、`council` 三种编排模式，通过 `/team` 或 @ 调用，团队可自带模型配置 |
| Agent Loop | ReAct 推理、工具调用、结果反馈与迭代控制 |
| 配置分层 | 团队、会话、全局逐层兜底，各层均可单独指定模型 |
| 渠道矩阵 | 单一工作区可服务多个渠道、多个机器人账号与多个业务入口 |
| 供应商与模型 | 多模型清单、三种协议、上下文窗口与图片能力元数据 |
| 思考档位 | 按模型声明可选档位，支持会话级与任务级调整，也支持自定义 |
| 上下文压缩 | 瘦身、边界、摘要、组装四阶段流水线，按水位自动触发，也可在会话列表手动压缩 |
| 记忆 | 一条事实一条记录，同 key 新值取代旧值，分 `pinned`、`recent`、`archived` 三层 |
| 内置工具 | 文件、Shell、网页、截图、记忆、工作流、媒体发送、文件检索、外部编程工具 |
| 外部执行工具 | 接入 Claude Code、Codex、OpenCode、dsh（DeepSeek Harness）至统一运行时 |
| 知识库 | Wiki 模块，基于 BM25 全文检索，配置嵌入端点后可叠加向量通道 |
| MCP | 多服务器连接、健康检查与工具发现，默认关闭 |
| 定时与心跳 | Cron 任务、主动问候与后台长期运行，可指定模型与投递目标 |
| 安全与工作空间 | 路径限制、审计日志、超时控制、远程认证边界与一次性初始化入口 |

---

## 最新动态

- **v1.0.0 · 2026-10-24**
  - 供应商体系重构：供应商下可维护模型清单，新增 OpenAI Responses 协议与协议选择，存量配置自动迁移
  - 新增思考档位：按模型声明可用档位，支持自定义，可在会话与定时任务中单独指定
  - 对话输入框新增模型切换：按会话切换模型与档位，不改动全局默认
  - 上下文压缩拆分为独立模块（瘦身 / 边界 / 摘要 / 组装），会话列表新增手动压缩入口
  - 记忆改为断言式存储：三层生命周期、推断内容只入冷存档、新增格式迁移脚本
  - 新增 Server酱推送渠道，定时任务页对只推送渠道免填会话目标
  - 定时任务支持按任务指定模型与思考档位
  - SQLite 启用 WAL 与 busy_timeout，缓解长连接下的写锁等待
  - 用量统计补齐缓存命中与推理 token；上游返回可见性过滤，避免渲染空思考块
  - 子代理新增排队态，取消传播与终态收敛更可靠
  - 消息改为按「正文 / 工具调用」时间顺序交织渲染
  - 前端界面重构优化，提升整体使用体验

- **v0.9.0**
  - 新增 MCP 客户端模块，支持多服务器连接、健康检查与工具发现，扩展 AI 执行能力边界。默认关闭，为个性化用户而新增的功能
  - 新增 Wiki 知识库模块，基于 BM25 全文搜索，支持批量获取、相关性过滤与 LRU 缓存加速
  - 新增 MCP、Wiki 管理面板，组件模块化拆分与国际化支持
  - 新增 WebSocket 状态广播模块，实时同步 MCP 连接状态至前端会话
  - 改进上下文管理与心跳机制，简化问候逻辑，减少 LLM 调用成本
  - 完善工具注册与初始化流程，提升系统启动一致性与可维护性
  - 新增 API Key 轮换机制与故障转移能力，支持多 key 自动切换
  - 改进 send_media 工具网页版兼容性，支持在WEB UI 预览图片和下载附件
  - 优化模型预设界面并更新构建产物
  - 发布说明：[https://countbot.cn/docs/releases/v0.9.0](https://countbot.cn/docs/releases/v0.9.0)

- **v0.8.0**
  - 集中修复 issue 与用户反馈中的多项问题，修复一批高频使用场景下的已知 Bug
  - 全面优化前端界面与交互体验，提升整体易用性与操作流畅度
  - 持续优化系统响应链路，提升 AI 回复的准确性、及时性与整体稳定性
  - 重构会话上下文维护链路，新增短期摘要缓存、溢出历史总结与整会话自动记忆沉淀
  - 增强多渠道稳定性，补强微信、企微、飞书消息处理、去重与流式投递控制
  - 优化主动问候与定时执行逻辑，避免未成功投递时提前计次，并支持配置变更后刷新当日计划
  - 完善推理开关与运行时配置解析，补充不同提供商的思考字段映射与 persona 合并策略
  - 统一启动时的监听地址与端口环境变量，补充 `COUNTBOT_HOST` / `COUNTBOT_PORT` 文档说明
  - 发布说明：[https://countbot.cn/docs/releases/v0.8.0](https://countbot.cn/docs/releases/v0.8.0)

- **v0.7.0**
  - 集中解决多个 issue 反馈问题，修复一批已知 Bug，提升整体稳定性
  - WEBUI 新增了文件上传和处理相关逻辑，优化了 Mermaid，提供更加友好的图表展示
  - 优化前端界面与交互流程，技能、配置、工具等日常使用体验更顺手
  - 优化 tool 调用链路与上下文组织，相比此前版本显著降低 token 消耗
  - 新增模型思考控制开关，可按场景切换思考强度，在体感上获得更快的 AI 响应
  - 新增 `find-skills`，全面接入腾讯云 SkillsHub，可通过对话完成 skills 的搜索、安装、启用、禁用与删除
  - 新增 `ima-knowledge-base`、`ima-notes`，全面接入 IMA 知识库与笔记能力，支持知识库搜索、上传、网页导入，以及笔记搜索、读取、新建和追加
  - 发布说明：[https://countbot.cn/docs/releases/v0.7.0](https://countbot.cn/docs/releases/v0.7.0)

- **v0.6.0**
  - 新增微信ClawBot接入，支持多个账号绑定
  - 新增外部编程工具接入（Claude/Codex/OpenCode）,可以作为工具提供LLM调用，亦可成为代理连接IM渠道
  - 新增远程首次初始化安全入口 `/setup/<random>`
  - 新增 `REMOTE_SETUP_SECRET_TTL_MINUTES`，远程初始化入口有效期可控
  - 强化远程认证边界，覆盖 `/api/*` 与 `/ws/chat`
  - 发布说明：[https://countbot.cn/docs/releases/v0.6.0](https://countbot.cn/docs/releases/v0.6.0)

- **v0.5.0**
  - Agent Team 正式成型，支持多角色分工、上下文衔接与团队级编排
  - 配置体系从会话级演进到角色级、团队级与多机器人协同
  - 渠道系统进一步增强，支持更多企业与社交入口
  - 前端聊天、配置、技能、团队与工具面板整体升级
  - 发布说明：[https://countbot.cn/docs/releases/v0.5.0](https://countbot.cn/docs/releases/v0.5.0)

- **v0.4.0**
  - 引入会话级配置，支持不同会话使用不同模型与提示词
  - 扩展飞书、企业微信、微博、小智 AI 等渠道能力
  - 优化多智能体协作，新增 `/help` 等使用入口
  - 发布说明：[https://countbot.cn/docs/releases/v0.4.0](https://countbot.cn/docs/releases/v0.4.0)

- **v0.3.0**
  - 多智能体协作（`pipeline` / `graph` / `council`）首次体系化落地
  - 定时任务、技能配置、工作空间管理能力显著增强
  - 发布说明：[https://countbot.cn/docs/releases/v0.3.0](https://countbot.cn/docs/releases/v0.3.0)

- **v0.2.0 · 2026-02-26**
  - 聚焦 Bug 修复、交互体验优化与构建流程整理
  - 让 CountBot 从「基础可运行」进一步走向「稳定可迭代」

- **正式开源 · 2026-02-21**
  - CountBot 首次开源，开放基础框架、启动脚本、Agent 核心、渠道系统、工具系统、技能系统与前端基础能力
  - 项目从这一天开始持续公开迭代

---

## 为什么做 CountBot

软件的使用方式一直在变化。过去需要记忆命令、学习配置，如今越来越多的操作可以用一句自然语言完成。

真正的难点不在模型本身，而在于如何把模型、工具、渠道、权限边界与长期运行能力整合成一套可落地、可持续维护的系统。做出演示并不困难，长期稳定运行则完全是另一个量级的要求。

OpenClaw 已在本地执行与自主 Agent 方向验证了可行性。CountBot 补齐的是它未覆盖的部分，包括中文场景适配、服务器常驻运行、使用门槛、安全管控与治理能力。

---

## 快速开始

### 方式一：源码启动

```bash
git clone https://github.com/countbot-ai/CountBot.git
cd CountBot

# 默认安装
pip install -r requirements.txt

# 国内网络可使用阿里云镜像
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

python start_app.py
```

启动完成后默认打开 `http://127.0.0.1:8000`。

监听地址与端口可通过环境变量覆盖，优先级为 `COUNTBOT_HOST` / `COUNTBOT_PORT` 高于默认值。

```bash
# Linux / macOS，服务器常驻建议绑定 0.0.0.0，并在前方配置反向代理
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

若国内访问 GitHub 受限，可改用 Gitee。

```bash
git clone https://gitee.com/countbot-ai/CountBot.git
```

### 方式二：桌面版体验

- Gitee Releases: https://gitee.com/countbot-ai/CountBot/releases
- GitHub Releases: https://github.com/countbot-ai/CountBot/releases
- 适用平台：Windows / macOS / Linux

### 部署到服务器

CountBot 本身是一个常规 Web 服务，可使用 `systemd`、`supervisor` 或容器常驻托管。开放远程访问前，请先完成初始化密码设置，再按需开放端口并配置反向代理。初始化入口为一次性，有效期可通过 `REMOTE_SETUP_SECRET_TTL_MINUTES` 控制。

---

## 项目状态

CountBot 仍在持续迭代。从早期的基础框架至今，供应商与模型体系、上下文压缩、记忆存储、渠道矩阵等模块均经历过较大重构，因此隔一段时间再查看时，目录结构与之前可能有所不同。

欢迎通过 Issue 反馈问题，功能修复、新能力与文档改进均接受 PR。

---

## 开发与贡献

### 本地开发

```bash
# 后端
uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000

# 前端
cd frontend && npm install && npm run dev
```

### 问题反馈

- GitHub Issues: https://github.com/countbot-ai/CountBot/issues

---

## 开源协议与致谢

### 开源协议

MIT License

### 贡献者

感谢以下贡献者为 CountBot 提交的代码与文档。

<p>
<a href="https://github.com/ddggkkcc" title="ddggkkcc"><img src="https://github.com/ddggkkcc.png?size=96" width="48" height="48" alt="ddggkkcc"></a>
<a href="https://github.com/23821" title="23821"><img src="https://github.com/23821.png?size=96" width="48" height="48" alt="23821"></a>
<a href="https://github.com/ct-jaryn" title="ct-jaryn"><img src="https://github.com/ct-jaryn.png?size=96" width="48" height="48" alt="ct-jaryn"></a>
<a href="https://github.com/hhzscreate" title="hhzscreate"><img src="https://github.com/hhzscreate.png?size=96" width="48" height="48" alt="hhzscreate"></a>
<a href="https://github.com/Liears" title="Liears"><img src="https://github.com/Liears.png?size=96" width="48" height="48" alt="Liears"></a>
<a href="https://github.com/mozhuanzuojing" title="mozhuanzuojing"><img src="https://github.com/mozhuanzuojing.png?size=96" width="48" height="48" alt="mozhuanzuojing"></a>
<a href="https://github.com/ranpis02" title="ranpis02"><img src="https://github.com/ranpis02.png?size=96" width="48" height="48" alt="ranpis02"></a>
</p>

### 项目灵感

- OpenClaw
- NanoBot
- ZeroClaw
- anthropics/skills

### 技术致谢

感谢 FastAPI、Vue.js、SQLAlchemy、Pydantic 等开源项目。

---

<div align="center">
  <p>部署在服务器上、长期运行的 AI 工作助手</p>
  <p>
    <a href="https://countbot.cn">官方网站</a> ·
    <a href="https://github.com/countbot-ai/countbot">GitHub</a> ·
    <a href="https://gitee.com/countbot-ai/CountBot">Gitee</a> ·
    <a href="https://countbot.cn/docs">完整文档</a>
  </p>
</div>
