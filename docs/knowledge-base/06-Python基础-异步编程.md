# Python 异步编程

CountBot 全栈使用异步编程（FastAPI、SQLAlchemy Async、asyncio）。本文梳理异步编程的核心概念，作为阅读项目代码的前置知识。

## 1、进程、线程与协程的关系

### （1）三者的层级

从大到小：**进程 > 线程 > 事件循环 > 协程**

```
┌─────────────── 进程 ───────────────┐
│                                     │
│  ┌─────────── 主线程 ───────────┐  │
│  │                               │  │
│  │  ┌─────── 事件循环 ───────┐  │  │
│  │  │                         │  │  │
│  │  │  协程A ──await──→ 挂起  │  │  │
│  │  │  协程B ← 获得执行权     │  │  │
│  │  │  协程B ──await──→ 挂起  │  │  │
│  │  │  协程A ← I/O完成，恢复  │  │  │
│  │  │  ...                    │  │  │
│  │  │                         │  │  │
│  │  └─────────────────────────┘  │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
```

### （2）各概念说明

**进程（Process）**：操作系统分配资源的最小单位。一个 Python 程序启动就是一个进程，拥有独立的内存空间。

```
CountBot 启动 → 1 个进程
├── 拥有独立的内存空间
├── 包含 1 个主线程
└── 主线程中运行 1 个事件循环
```

**线程（Thread）**：进程内的执行单元，共享进程的内存。Python 受 GIL（全局解释器锁）限制，多线程无法真正并行执行 CPU 密集型任务。

**事件循环（Event Loop）**：运行在线程里的一个调度器，负责决定"现在该执行哪个协程"。整个 CountBot 只有一个事件循环，由 `uvicorn` 启动时创建。

**协程（Coroutine）**：用 `async def` 定义的函数，是事件循环调度的最小单位。协程不是线程，它们在同一个线程里交替执行。

### （3）关键区别

| | 切换方式 | 开销 | 并行性 |
|---|---|---|---|
| **进程** | 操作系统强制切换 | 重（独立内存） | 真并行 |
| **线程** | 操作系统强制切换 | 中（共享内存） | Python 受 GIL 限制 |
| **协程** | `await` 时主动让出 | 极轻（函数调用级别） | 非并行，是并发 |

**并行 vs 并发**：
- 并行：两件事同一时刻都在执行（需要多核 CPU）
- 并发：两件事交替执行，看起来像同时进行（单核即可）

协程实现的是**并发**——在一个线程内，多个任务交替推进。

## 2、为什么需要异步

### （1）同步的问题

```python
# 同步写法 — 等待数据库时，整个进程卡住，什么都干不了
def handle_request():
    data = db.query("SELECT ...")   # 等待 50ms，进程阻塞
    result = call_llm(data)          # 等待 2000ms，进程阻塞
    return result                    # 总共阻塞 2050ms
```

在这 2050ms 内，如果有其他用户发来请求，只能排队等待。

### （2）异步的优势

```python
# 异步写法 — 等待时释放控制权，事件循环去处理其他任务
async def handle_request():
    data = await db.query("SELECT ...")   # 等待期间去处理其他请求
    result = await call_llm(data)          # 等待期间去处理其他请求
    return result
```

当用户 A 的请求在等待 LLM 响应时，事件循环可以去处理用户 B 的 WebSocket 消息。这就是 FastAPI 能用单线程处理大量并发请求的原因。

### （3）适合异步的场景

异步适合 **I/O 密集型** 任务，即大量时间花在等待外部响应上：

| 操作 | 等待时间 | 适合异步？ |
|------|----------|-----------|
| 调用 LLM API | 数百ms~数秒 | 非常适合 |
| 数据库查询 | 数ms~数十ms | 适合 |
| 网络请求（HTTP） | 数十ms~数秒 | 非常适合 |
| 读写文件 | 数ms | 适合 |
| 数学计算 | 取决于复杂度 | 不适合（CPU 密集型） |

CountBot 的核心操作（调 LLM、查数据库、WebSocket 通信）几乎全是 I/O，所以异步架构非常合适。

## 3、async/await 基础语法

### （1）定义协程

```python
# 普通函数
def hello():
    return "hello"

# 协程函数 — 加 async 关键字
async def hello():
    return "hello"
```

调用协程函数不会立即执行，而是返回一个协程对象，需要 `await` 或交给事件循环才会真正执行。

### （2）await 关键字

`await` 做两件事：
1. 等待一个协程执行完成，获取返回值
2. 在等待期间，将控制权交还给事件循环

```python
async def main():
    result = await some_async_function()  # 等待并获取结果
    print(result)
```

**重要规则**：`await` 只能在 `async def` 函数内部使用。

### （3）async for — 异步迭代

```python
# 普通 for 循环 — 数据已在内存中，取下一个元素是瞬间完成的
for item in some_list:
    process(item)

# 异步 for 循环 — 每次取下一个元素可能需要等待 I/O
async for chunk in provider.chat_stream(...):
    yield chunk.content  # 逐块接收 LLM 的流式响应
```

关键区别在于**数据的来源**：

| | 数据来源 | 取下一个元素时 |
|---|---|---|
| `for` | 内存中已有的列表/生成器 | 立即返回 |
| `async for` | 网络流、数据库游标等 | 可能要 `await` 等待 |

#### chat_stream 内部：async for 的数据是怎么来的

以 CountBot 的 `chat_stream` 方法为例（`providers/litellm_provider.py:87-253`），看看 `async for` 迭代的数据是如何产生的：

```python
async def chat_stream(self, messages, tools=None, model=None, ...):
    # 1. 发起一个异步 HTTP 请求给 LLM API，开启流式连接
    response = await litellm.acompletion(
        model=model,
        messages=messages,
        stream=True,       # ★ 关键：开启流式模式
        ...
    )

    # 2. response 是一个异步迭代器，LLM 每吐出一小块数据就产生一个 chunk
    async for chunk in response:
        choice = chunk.choices[0]
        delta = choice.delta

        # 3. 如果这一块包含文本内容 → yield 出去
        if delta.content:
            yield StreamChunk(content=delta.content)

        # 4. 如果这一块包含推理内容（DeepSeek 等思考模型）
        if delta.reasoning_content:
            yield StreamChunk(reasoning_content=delta.reasoning_content)

        # 5. 如果这一块包含工具调用信息 → 累积到缓冲区
        if delta.tool_calls:
            # ... 累积工具名和参数片段 ...

        # 6. 如果 LLM 说"我说完了" → 发送累积的工具调用 + 完成信号
        if choice.finish_reason:
            # 发送完整的工具调用
            yield StreamChunk(tool_call=ToolCall(...))
            # 发送完成信号
            yield StreamChunk(finish_reason=choice.finish_reason)
```

整个数据流是这样的：

```
LLM 服务器                    chat_stream()                   Agent Loop
    │                              │                              │
    ├─ 吐出 "你"  ──网络──→  yield StreamChunk("你")  ──→  yield "你" → 用户
    │   (等 100ms)                 │                              │
    ├─ 吐出 "好，" ──网络──→  yield StreamChunk("好，") ──→  yield "好，" → 用户
    │   (等 80ms)                  │                              │
    ├─ 吐出 "我是" ──网络──→  yield StreamChunk("我是") ──→  yield "我是" → 用户
    │   ...                        │                              │
    └─ finish    ──网络──→  yield StreamChunk(done)   ──→  循环结束
```

每两个 chunk 之间的等待时间里，`async for` 会把控制权还给事件循环，事件循环就可以去处理其他用户的请求。这就是 `async for` 的核心价值——**等待下一块数据时不阻塞**。

CountBot 的 Agent 主循环就大量使用 `async for` 来处理 LLM 的流式响应。

### （4）async with — 异步上下文管理器

先回忆普通 `with` 做了什么：

```python
with open("file.txt") as f:
    data = f.read()
# 离开 with 块时，自动调用 f.close()
```

`with` 的本质是**自动清理**——不管中间代码是否出错，离开时都保证执行清理操作（如关闭文件、释放连接）。

`async with` 也是一样，只不过**进入和退出时的操作可能涉及异步 I/O**：

```python
# 进入时：建立网络连接（需要 await）
# 退出时：关闭网络连接（需要 await）
async with aiohttp.ClientSession() as session:
    response = await session.get(url)
# 离开时，自动 await session.close()
```

如果用普通 `with`，建立和关闭连接时就没法 `await`，会阻塞事件循环。

简单记忆：**只要"打开"和"关闭"的动作涉及 I/O，就用 `async with` 代替 `with`**。

#### CountBot 中的 lifespan 示例

FastAPI 的 `lifespan` 就是一个异步上下文管理器：

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # "进入"时：启动资源（都是异步操作）
    await init_db()
    await channel_manager.start_all()

    yield  # ← 应用在这里运行

    # "退出"时：清理资源（也是异步操作）
    await channel_manager.stop_all()
    await scheduler.stop()
```

FastAPI 内部大致是这样使用它的：

```python
async with lifespan(app):
    # async with 进入 → 执行 yield 之前的代码（启动）
    await serve_forever()   # 应用运行，处理请求
# async with 退出 → 执行 yield 之后的代码（关闭）
```

如果 `init_db()` 和 `stop_all()` 不需要 `await`（比如纯内存操作），用普通 `with` 就够了。但它们都涉及数据库连接、网络通信，必须用 `async with` 才能在等待时不阻塞事件循环。

## 4、异步生成器（async generator）

### （1）普通生成器 vs 异步生成器

```python
# 普通生成器 — 用 yield 逐个产出值
def count():
    yield 1
    yield 2
    yield 3

# 异步生成器 — async def + yield，可以在产出值之间做异步操作
async def stream_response():
    async for chunk in llm.chat_stream(...):
        yield chunk.content  # 每收到一块就产出
```

### （2）在 CountBot 中的应用

Agent 主循环的 `process_message()` 就是一个异步生成器：

```python
# agent/loop.py
async def process_message(self, message, ...):
    # ... 构建消息列表 ...
    async for chunk in self.provider.chat_stream(messages, ...):
        if chunk.is_content:
            yield chunk.content  # 实时流式返回给调用者
```

调用者这样使用：

```python
async for text in agent_loop.process_message(message):
    await websocket.send(text)  # 逐块发送给前端
```

这个模式实现了 LLM 响应的"打字机效果"——不需要等整个回复生成完毕，边生成边发送。

## 5、asyncio 常用工具

### （1）asyncio.create_task — 并发执行

```python
# 顺序执行 — 总耗时 = A + B
await task_a()
await task_b()

# 并发执行 — 总耗时 = max(A, B)
task1 = asyncio.create_task(task_a())
task2 = asyncio.create_task(task_b())
await task1
await task2
```

CountBot 的消息处理器用 `create_task` 并发处理多条消息：

```python
# channels/handler.py
async def start_processing(self):
    while True:
        msg = await self.bus.consume_inbound()
        asyncio.create_task(self.handle_message(msg))  # 不等待，立即处理下一条
```

### （2）asyncio.gather — 等待多个协程

```python
# 并发执行多个协程，等待全部完成
results = await asyncio.gather(
    fetch_weather(),
    fetch_news(),
    fetch_email(),
)
```

### （3）asyncio.sleep — 异步等待

```python
# 同步等待 — 阻塞整个线程
import time
time.sleep(5)  # 5 秒内什么都干不了

# 异步等待 — 释放控制权，不阻塞
await asyncio.sleep(5)  # 5 秒内事件循环可以处理其他协程
```

CountBot 的定时调度器就用 `asyncio.sleep` 精确等待到下次任务时间：

```python
# cron/scheduler.py
await asyncio.sleep(seconds_until_next_job)  # 等待期间不占资源
```

### （4）asyncio.Semaphore — 并发限制

```python
sem = asyncio.Semaphore(3)  # 最多 3 个并发

async def limited_task():
    async with sem:          # 超过 3 个时，后续任务等待
        await do_work()
```

CountBot 的定时任务执行器用信号量限制最多 3 个任务同时运行。

### （5）asyncio.wait — 等待任意一个完成

```python
tasks = [asyncio.create_task(queue.get()) for queue in queues]
done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
# done 中包含最先完成的任务
for task in pending:
    task.cancel()  # 取消其余任务
```

CountBot 的优先级队列用这个模式监听多个队列，哪个先有消息就处理哪个。

## 6、在 CountBot 中的异步全景

```
uvicorn 启动
    │
    └── 创建事件循环
        │
        ├── lifespan（启动阶段）
        │   ├── await init_db()
        │   ├── await channel_manager.start_all()
        │   └── await scheduler.start()
        │
        ├── WebSocket 连接处理（每个连接一个协程）
        │   └── async for message in websocket:
        │       └── async for chunk in agent_loop.process_message():
        │           └── await websocket.send(chunk)
        │
        ├── 渠道消息处理（每条消息一个 task）
        │   └── asyncio.create_task(handle_message(msg))
        │
        ├── 定时调度器（一个长期运行的协程）
        │   └── while True:
        │       └── await asyncio.sleep(seconds_until_next)
        │
        └── lifespan（关闭阶段）
            ├── await channel_manager.stop_all()
            └── await scheduler.stop()
```

所有这些协程都在同一个线程的同一个事件循环中交替运行。当某个协程在 `await` 等待 I/O 时，事件循环会去执行其他就绪的协程，实现高效的并发处理。

## 7、常见误区

### （1）async 不等于快

异步不会让单个操作变快。调用一次 LLM 同步需要 2 秒，异步也需要 2 秒。异步的优势是在这 2 秒内可以**同时处理其他请求**。

### （2）await 不等于并发

两个 `await` 顺序执行不会并发：

```python
await task_a()  # 先执行完 A
await task_b()  # 再执行 B
# 总耗时 = A + B
```

要并发，需要用 `create_task` 或 `gather`：

```python
await asyncio.gather(task_a(), task_b())
# 总耗时 = max(A, B)
```

### （3）不要在 async 函数中使用阻塞调用

```python
# 错误 — time.sleep 会阻塞整个事件循环
async def bad():
    time.sleep(5)  # 5 秒内所有协程都无法运行

# 正确 — asyncio.sleep 会释放控制权
async def good():
    await asyncio.sleep(5)
```

同理，`requests.get()` 是阻塞的，应该用 `aiohttp` 或 `httpx` 的异步版本。

## 8、对应代码阅读指引

理解了异步编程基础后，在阅读 CountBot 代码时重点关注：

| 模式 | 在项目中的位置 | 说明 |
|------|---------------|------|
| `async for` + `yield` | `agent/loop.py` | Agent 主循环的流式响应 |
| `asynccontextmanager` | `app.py:lifespan` | 应用生命周期管理 |
| `asyncio.create_task` | `channels/handler.py` | 并发处理多条消息 |
| `asyncio.sleep` | `cron/scheduler.py` | 精确定时等待 |
| `asyncio.Semaphore` | `cron/scheduler.py` | 定时任务并发限制 |
| `asyncio.wait` | `messaging/enterprise_queue.py` | 优先级队列监听 |
