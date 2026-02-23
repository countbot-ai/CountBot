# 三-1、Agent 主循环

Agent 主循环是 CountBot 的核心处理引擎，负责接收用户消息、调用 LLM、执行工具，并将结果返回给用户。

核心文件：`backend/modules/agent/loop.py`

## 1、AgentLoop 类设计

### （1）构造参数

```python
class AgentLoop:
    def __init__(self,
        provider,          # LLM 提供商
        workspace,         # 工作区路径
        tools,             # 工具注册表
        context_builder,   # 上下文构建器
        subagent_manager,  # 子代理管理器
        model,             # 模型名称
        max_iterations=25, # 最大迭代次数
        max_retries=3,     # 工具重试次数
        retry_delay=1.0,   # 重试间隔
        temperature=0.7,   # 生成温度
        max_tokens=4096,   # 最大 token 数
    ):
```

`AgentLoop` 是一个**无状态的处理器**，每次调用 `process_message()` 都是独立的处理流程。它不保存历史消息，也不维护会话状态——这些由外部的会话管理和消息数据库负责。

### （2）关键参数说明

| 参数 | 作用 | 说明 |
|------|------|------|
| `max_iterations` | 防止无限循环 | 最多进行 25 轮 LLM 调用 |
| `max_retries` | 工具执行容错 | 单个工具失败时最多重试 3 次 |
| `retry_delay` | 重试等待 | 两次重试间等待 1 秒 |
| `temperature` | 生成随机性 | 0.7 是比较平衡的值 |

## 2、ReAct 循环核心逻辑

ReAct（Reasoning + Acting）是 Agent 的核心运行模式。代码位于 `loop.py:50-361`。

### （1）整体流程

```
process_message() 入口
    │
    ├── 1. 设置会话上下文
    │   ├── 设置工具注册表的 session_id
    │   └── 设置 spawn 工具的上下文
    │
    ├── 2. 构建消息列表
    │   └── context_builder.build_messages(history, current_message, media, channel)
    │
    └── 3. 进入迭代循环（最多 max_iterations 次）
        │
        ├── 检查取消令牌 → 已取消则退出
        │
        ├── 获取工具定义列表
        │
        ├── 调用 LLM（流式）
        │   ├── provider.chat_stream(messages, tools, model, temperature, max_tokens)
        │   │
        │   ├── 解析流式响应：
        │   │   ├── chunk.is_content    → 追加到 content_buffer，yield 给调用者
        │   │   ├── chunk.is_tool_call  → 追加到 tool_calls_buffer
        │   │   ├── chunk.is_reasoning  → 追加到 reasoning_buffer
        │   │   ├── chunk.is_done       → 记录 finish_reason
        │   │   └── chunk.is_error      → yield 错误信息，return
        │
        ├── 如果有文本内容 → 记录完整响应
        │
        ├── 如果有工具调用 → 进入工具执行流程
        │   │
        │   ├── 将 assistant 消息（含 tool_calls）加入消息列表
        │   │
        │   └── 遍历每个工具调用：
        │       ├── 检查是否超过最大调用次数
        │       ├── 检查取消令牌
        │       ├── 发送工具调用通知（WebSocket）
        │       ├── 记录开始时间
        │       │
        │       ├── 重试循环（最多 max_retries 次）：
        │       │   ├── 执行工具 execute_tool(name, args)
        │       │   ├── 成功 → break
        │       │   └── 失败 → 等待 retry_delay 后重试
        │       │
        │       ├── 记录工具对话历史
        │       ├── 发送工具执行通知（WebSocket）
        │       └── 将工具结果加入消息列表（role: "tool"）
        │
        └── 如果没有工具调用 → 结束循环
```

### （2）循环终止条件

循环在以下三种情况下会终止：
- **LLM 不再调用工具**：正常结束，意味着 LLM 认为已经完成任务
- **达到最大迭代次数**：安全保护，防止 AI 陷入无限调用循环
- **用户取消**：通过取消令牌机制，用户可以随时中断处理

## 3、流式响应处理

### （1）async for + yield 模式

```python
# loop.py:112-135
async for chunk in self.provider.chat_stream(
    messages=messages,
    tools=tool_definitions,
    model=self.model,
    temperature=self.temperature,
    max_tokens=self.max_tokens,
):
    if chunk.is_content and chunk.content:
        content_buffer += chunk.content
        yield chunk.content              # ★ 实时流式返回文本给用户

    if chunk.is_tool_call and chunk.tool_call:
        tool_calls_buffer.append(chunk.tool_call)  # 收集工具调用

    if chunk.is_reasoning and chunk.reasoning_content:
        reasoning_buffer += chunk.reasoning_content  # 收集推理内容（DeepSeek 等）

    if chunk.is_error:
        yield chunk.error                # 错误也流式返回
        return
```

`process_message` 本身是一个**异步生成器**，使用了 `async for` + `yield` 模式。调用者可以逐块接收 LLM 的响应文本，实现打字机效果。

### （2）四种 chunk 类型

| 类型 | 说明 | 处理方式 |
|------|------|----------|
| `is_content` | 文本内容 | 追加到 buffer + yield 给调用者 |
| `is_tool_call` | 工具调用 | 收集到列表，等流式结束后统一执行 |
| `is_reasoning` | 推理内容 | 追加到 buffer（部分模型如 DeepSeek 支持） |
| `is_error` | 错误信息 | yield 后立即 return |

### （3）流式的好处

- 用户不需要等整个回复生成完毕，就能看到开头部分
- WebSocket 可以逐块推送给前端，渠道也可以逐段发送
- 如果中途出错，已经发送的内容不会丢失

## 4、工具执行与重试

### （1）重试机制

```python
# loop.py:213-229
for attempt in range(self.max_retries):
    try:
        result = await self.execute_tool(tool_name, tool_args)
        break
    except Exception as e:
        last_error = e
        if attempt < self.max_retries - 1:
            await asyncio.sleep(self.retry_delay)  # 等待后重试
```

工具执行失败时自动重试，但**不改变参数**（假设是临时性错误如网络超时）。如果是参数错误，重试也不会成功，但这种情况下工具的 `execute()` 方法通常返回错误字符串而非抛出异常。

### （2）工具调用通知

每次工具执行前后都会通过 WebSocket 发送通知：

```python
# 工具调用开始通知
await notify_tool_execution(session_id, tool_name, tool_args)

# 工具执行完成通知（含结果或错误）
await notify_tool_execution(session_id, tool_name, tool_args, result=result)
```

前端可以据此展示工具调用的实时状态（"正在读取文件..."、"正在执行命令..."）。

### （3）工具结果进入消息列表

工具执行完成后，结果以 `role: "tool"` 的格式加入消息列表，供 LLM 在下一轮迭代中参考：

```python
messages.append({
    "role": "tool",
    "tool_call_id": tool_call_id,
    "name": tool_name,
    "content": result
})
```

## 5、消息列表管理

Agent 循环中最重要的数据结构是 `messages` 列表，它维护了完整的对话上下文：

```python
messages = [
    {"role": "system", "content": "系统提示词..."},
    {"role": "user", "content": "历史消息1"},
    {"role": "assistant", "content": "历史回复1"},
    ...
    {"role": "user", "content": "当前用户消息"},
    # --- Agent 循环中动态添加 ---
    {"role": "assistant", "content": "...", "tool_calls": [...]},
    {"role": "tool", "tool_call_id": "...", "name": "read_file", "content": "文件内容..."},
    {"role": "assistant", "content": "最终回复"},
]
```

注意这个列表在循环过程中会不断增长：每次 LLM 的工具调用和工具的执行结果都会追加进去。这样 LLM 在下一轮迭代中就能看到之前的所有操作和结果。

## 6、process_direct 方法

```python
# loop.py:395-424
async def process_direct(self, content, session_id="cli:direct", ...):
    """直接处理消息（用于 CLI 或 cron 使用）"""
    response_parts = []
    async for chunk in self.process_message(message=content, session_id=session_id, ...):
        response_parts.append(chunk)
    return "".join(response_parts)
```

这是一个**便捷方法**，将流式生成器转换为完整字符串。适用于不需要流式输出的场景：
- 定时任务执行（cron）
- CLI 命令行调用
- 子代理处理

## 7、取消令牌机制

取消令牌（Cancel Token）允许用户中断正在进行的处理。在 Agent 循环中的多个检查点都会检查取消状态：

- 循环开始前
- 每轮迭代开始时
- 每个工具执行前

这确保了取消操作能及时生效，不会让用户等待一个不需要的长时间操作。

## 8、子代理系统

核心文件：`backend/modules/agent/subagent.py`

子代理是 Agent 主循环的扩展，用于处理耗时或复杂的后台任务。

### （1）触发方式

子代理由 `spawn` 工具触发：

```
主 Agent
    │
    ├── spawn(task="搜索新闻并生成摘要")
    │   └── SubagentManager.create()
    │       └── 创建独立的 AgentLoop
    │           └── 在后台异步执行
    │
    └── 继续处理其他请求
```

### （2）与主 Agent 的关系

- **共享**：provider（LLM 提供商）和 workspace（工作区）
- **独立**：工具注册表和消息上下文

这意味着子代理可以使用相同的 LLM 和工作区文件，但不会干扰主 Agent 的工具状态和对话上下文。

## 9、对应代码阅读指引

| 阅读顺序 | 文件 | 重点关注 |
|----------|------|----------|
| 1 | `agent/loop.py` 全文 | `process_message()` 的 ReAct 循环流程 |
| 2 | `agent/loop.py:112-135` | 流式响应处理的 async for + yield |
| 3 | `agent/loop.py:213-229` | 工具执行重试逻辑 |
| 4 | `agent/loop.py:395-424` | `process_direct()` 便捷方法 |
| 5 | `agent/subagent.py` | 子代理创建和管理 |
| 6 | `agent/task_manager.py` | 取消令牌管理 |
