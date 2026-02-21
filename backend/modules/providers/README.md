# LLM Providers 模块 - 流式优先设计

## 🚀 概述

LLM Providers 模块提供了**流式优先**的统一接口来访问多个大语言模型提供商。相比传统的非流式设计，我们的实现提供了更好的用户体验和更现代化的 API。

### ✨ 核心优势

1. **真正的流式响应** - 逐字输出，实时反馈
2. **现代化数据类** - 使用 `@dataclass`，代码简洁
3. **10+ 提供商支持** - 统一接口访问所有主流 LLM
4. **智能模型规范化** - 自动添加正确的提供商前缀
5. **工具调用增量处理** - 正确处理流式工具调用
6. **完善的错误处理** - 错误信息包含在流中
7. **类型安全** - 完整的类型注解
8. **清晰的 API** - `chat_stream()` 方法名明确表达意图

## 📦 模块结构

```
providers/
├── __init__.py              # 模块导出
├── base.py                  # LLMProvider 抽象基类 + 数据类
├── litellm_provider.py      # LiteLLM Provider 实现
├── transcription.py         # 语音转录服务
└── README.md               # 本文档
```

## 🎯 核心组件

### 1. 数据类 (base.py)

#### ToolCall

表示 LLM 请求调用的工具：

```python
from backend.modules.providers import ToolCall

tool = ToolCall(
    id="call_abc123",
    name="get_weather",
    arguments={"city": "北京", "unit": "celsius"}
)
```

#### StreamChunk

流式响应块，支持多种类型的数据：

```python
from backend.modules.providers import StreamChunk

# 内容块
content_chunk = StreamChunk(content="你好")
assert content_chunk.is_content == True

# 工具调用块
tool_chunk = StreamChunk(tool_call=tool)
assert tool_chunk.is_tool_call == True

# 完成块
done_chunk = StreamChunk(
    finish_reason="stop",
    usage={"total_tokens": 100}
)
assert done_chunk.is_done == True

# 错误块
error_chunk = StreamChunk(error="API 错误")
assert error_chunk.is_error == True
```

**StreamChunk 属性:**
- `content`: 文本内容增量（逐字输出）
- `tool_call`: 完整的工具调用信息
- `finish_reason`: 完成原因 ("stop", "length", "tool_calls" 等)
- `usage`: Token 使用统计
- `error`: 错误信息

**StreamChunk 方法:**
- `is_content`: 是否为内容块
- `is_tool_call`: 是否为工具调用块
- `is_done`: 是否为完成块
- `is_error`: 是否为错误块

### 2. LLMProvider 抽象基类 (base.py)

所有 Provider 必须实现的接口：

```python
from backend.modules.providers import LLMProvider
from typing import AsyncIterator

class MyProvider(LLMProvider):
    async def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs
    ) -> AsyncIterator[StreamChunk]:
        # 实现流式聊天
        yield StreamChunk(content="响应内容")
        yield StreamChunk(finish_reason="stop")
    
    def get_default_model(self) -> str:
        return "my-model"
```

### 3. LiteLLMProvider (litellm_provider.py)

使用 litellm 库的 Provider 实现，支持 10+ 个主流提供商。

#### 支持的提供商

| 提供商 | 模型示例 | 前缀 |
|--------|---------|------|
| **OpenRouter** | 所有模型 | `openrouter/` |
| **Anthropic** | claude-4.5 | `anthropic/` |
| **OpenAI** | gpt-4, gpt-3.5-turbo | `openai/` |
| **DeepSeek** | deepseek-chat, deepseek-coder | `deepseek/` |
| **Google Gemini** | gemini-pro, gemini-1.5-pro | `gemini/` |
| **Moonshot/Kimi** | moonshot-k2.5, kimi-k2.5 | `moonshot/` |
| **Zhipu GLM** | glm-4, glm-3-turbo | `zai/` |
| **DashScope Qwen** | qwen-turbo, qwen-plus | `dashscope/` |
| **Groq** | llama3-70b, mixtral-8x7b | `groq/` |
| **vLLM** | 自托管模型 | `hosted_vllm/` |

#### 基本使用

```python
from backend.modules.providers import LiteLLMProvider

# 初始化
provider = LiteLLMProvider(
    api_key="your_api_key",
    default_model="anthropic/claude-4.5",
    timeout=120.0,
    max_retries=3
)

# 流式聊天
messages = [
    {"role": "system", "content": "你是一个有帮助的助手"},
    {"role": "user", "content": "介绍一下 Python"}
]

async for chunk in provider.chat_stream(messages):
    if chunk.is_content:
        print(chunk.content, end='', flush=True)
    elif chunk.is_tool_call:
        print(f"\n调用工具: {chunk.tool_call.name}")
        print(f"参数: {chunk.tool_call.arguments}")
    elif chunk.is_done:
        print(f"\n完成: {chunk.finish_reason}")
        if chunk.usage:
            print(f"Token 使用: {chunk.usage}")
    elif chunk.is_error:
        print(f"\n错误: {chunk.error}")
```

#### 带工具调用的示例

```python
# 定义工具
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "获取指定城市的天气信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "城市名称"
                    },
                    "unit": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                        "description": "温度单位"
                    }
                },
                "required": ["city"]
            }
        }
    }
]

messages = [
    {"role": "user", "content": "北京今天天气怎么样？"}
]

async for chunk in provider.chat_stream(messages, tools=tools):
    if chunk.is_tool_call:
        tool = chunk.tool_call
        print(f"工具: {tool.name}")
        print(f"参数: {tool.arguments}")
        
        # 执行工具
        if tool.name == "get_weather":
            result = get_weather(**tool.arguments)
            # 将结果添加到消息历史...
```

#### 多提供商配置

```python
# OpenRouter
provider_or = LiteLLMProvider(
    api_key="sk-or-v1-...",
    default_model="anthropic/claude-4.5"
)

# Anthropic 直连
provider_anthropic = LiteLLMProvider(
    api_key="sk-ant-...",
    default_model="claude-4.5"
)

# OpenAI
provider_openai = LiteLLMProvider(
    api_key="sk-...",
    default_model="gpt-4"
)

# DeepSeek
provider_deepseek = LiteLLMProvider(
    api_key="sk-...",
    default_model="deepseek-chat"
)

# Moonshot/Kimi
provider_moonshot = LiteLLMProvider(
    api_key="sk-...",
    default_model="moonshot-k2.5"
)

# vLLM 自托管
provider_vllm = LiteLLMProvider(
    api_key="your_key",
    api_base="http://localhost:8000",
    default_model="my-model"
)
```

#### 智能模型名称规范化

Provider 会自动为模型名称添加正确的前缀：

```python
provider = LiteLLMProvider(api_key="sk-or-test")

# 自动添加 openrouter/ 前缀
provider._normalize_model_name("gpt-4")
# 返回: "openrouter/gpt-4"

provider2 = LiteLLMProvider(api_key="test")

# 自动添加 zai/ 前缀
provider2._normalize_model_name("glm-4")
# 返回: "zai/glm-4"

# 自动添加 dashscope/ 前缀
provider2._normalize_model_name("qwen-turbo")
# 返回: "dashscope/qwen-turbo"
```

### 4. TranscriptionService (transcription.py)

语音转录服务，支持 Groq 和 OpenAI 的 Whisper API。

#### 基本使用

```python
from backend.modules.providers import TranscriptionService

# 使用 Groq Whisper
service = TranscriptionService(
    provider="groq",
    api_key="your_groq_api_key",
    model="whisper-large-v3"
)

# 读取音频文件
with open("recording.mp3", "rb") as f:
    audio_bytes = f.read()

# 转录
result = await service.transcribe(
    audio_file=audio_bytes,
    language="zh",  # 可选：指定语言
    prompt="这是一段关于..."  # 可选：提示文本
)

print(result["text"])      # 转录文本
print(result["language"])  # 检测到的语言
print(result["duration"])  # 音频时长（秒）
```

#### 支持的音频格式

- MP3 (.mp3)
- MP4 (.mp4)
- MPEG (.mpeg, .mpga)
- M4A (.m4a)
- WAV (.wav)
- WebM (.webm)

#### 音频格式验证

```python
from pathlib import Path

service = TranscriptionService(provider="groq", api_key="key")

# 验证格式
assert service.validate_audio_format(Path("audio.mp3")) == True
assert service.validate_audio_format(Path("audio.txt")) == False
```

## 🔥 完整示例

### 示例 1: 基本流式聊天

```python
from backend.modules.providers import LiteLLMProvider

async def basic_chat():
    provider = LiteLLMProvider(
        api_key="your_key",
        default_model="gpt-3.5-turbo"
    )
    
    messages = [
        {"role": "user", "content": "写一首关于编程的诗"}
    ]
    
    print("AI: ", end='', flush=True)
    
    async for chunk in provider.chat_stream(messages):
        if chunk.is_content:
            print(chunk.content, end='', flush=True)
        elif chunk.is_done:
            print(f"\n\n[完成: {chunk.finish_reason}]")
            if chunk.usage:
                tokens = chunk.usage.get('total_tokens', 0)
                print(f"[使用 {tokens} tokens]")
        elif chunk.is_error:
            print(f"\n[错误: {chunk.error}]")
            break

# 运行
import asyncio
asyncio.run(basic_chat())
```

### 示例 2: 带工具调用的智能助手

```python
from backend.modules.providers import LiteLLMProvider
import json

async def smart_assistant():
    provider = LiteLLMProvider(api_key="your_key")
    
    # 定义工具
    tools = [
        {
            "type": "function",
            "function": {
                "name": "search_web",
                "description": "搜索网络获取信息",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "搜索查询"}
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "calculate",
                "description": "执行数学计算",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "expression": {"type": "string", "description": "数学表达式"}
                    },
                    "required": ["expression"]
                }
            }
        }
    ]
    
    messages = [
        {"role": "user", "content": "搜索一下 Python 3.12 的新特性，然后计算 123 * 456"}
    ]
    
    async for chunk in provider.chat_stream(messages, tools=tools):
        if chunk.is_content:
            print(chunk.content, end='', flush=True)
        
        elif chunk.is_tool_call:
            tool = chunk.tool_call
            print(f"\n\n[调用工具: {tool.name}]")
            print(f"[参数: {json.dumps(tool.arguments, ensure_ascii=False)}]")
            
            # 执行工具
            if tool.name == "search_web":
                result = f"搜索结果: Python 3.12 引入了..."
            elif tool.name == "calculate":
                result = str(eval(tool.arguments["expression"]))
            
            print(f"[结果: {result}]")
            
            # 将工具结果添加到消息历史
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": tool.id,
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "arguments": json.dumps(tool.arguments)
                    }
                }]
            })
            messages.append({
                "role": "tool",
                "tool_call_id": tool.id,
                "content": result
            })
        
        elif chunk.is_done:
            print(f"\n\n[完成: {chunk.finish_reason}]")

asyncio.run(smart_assistant())
```

### 示例 3: 多轮对话

```python
from backend.modules.providers import LiteLLMProvider

async def multi_turn_chat():
    provider = LiteLLMProvider(api_key="your_key")
    
    messages = []
    
    while True:
        # 用户输入
        user_input = input("\n你: ")
        if user_input.lower() in ['退出', 'quit', 'exit']:
            break
        
        messages.append({"role": "user", "content": user_input})
        
        # AI 响应
        print("AI: ", end='', flush=True)
        assistant_message = ""
        
        async for chunk in provider.chat_stream(messages):
            if chunk.is_content:
                print(chunk.content, end='', flush=True)
                assistant_message += chunk.content
            elif chunk.is_done:
                print()
                break
            elif chunk.is_error:
                print(f"\n错误: {chunk.error}")
                break
        
        # 添加到历史
        if assistant_message:
            messages.append({"role": "assistant", "content": assistant_message})

asyncio.run(multi_turn_chat())
```

### 示例 4: 语音转录

```python
from backend.modules.providers import TranscriptionService

async def transcribe_audio():
    service = TranscriptionService(
        provider="groq",
        api_key="your_groq_key",
        model="whisper-large-v3"
    )
    
    # 读取音频
    with open("meeting_recording.mp3", "rb") as f:
        audio_bytes = f.read()
    
    print("正在转录...")
    
    # 转录
    result = await service.transcribe(
        audio_file=audio_bytes,
        language="zh",
        prompt="这是一段会议录音"
    )
    
    print(f"\n转录结果:\n{result['text']}")
    print(f"\n语言: {result['language']}")
    print(f"时长: {result['duration']} 秒")

asyncio.run(transcribe_audio())
```

## ⚙️ 配置选项

### LiteLLMProvider 配置

```python
provider = LiteLLMProvider(
    api_key="your_key",              # API 密钥
    api_base="https://...",          # 自定义 API 端点（可选）
    default_model="gpt-4",           # 默认模型
    timeout=120.0,                   # 请求超时（秒）
    max_retries=3,                   # 最大重试次数
)
```

### TranscriptionService 配置

```python
service = TranscriptionService(
    provider="groq",                 # 提供商: groq, openai
    api_key="your_key",              # API 密钥
    model="whisper-large-v3",        # 模型名称
)
```

## 🔧 错误处理

所有错误都通过 `StreamChunk` 的 `error` 字段返回：

```python
async for chunk in provider.chat_stream(messages):
    if chunk.is_error:
        print(f"错误: {chunk.error}")
        # 处理错误
        break
    # 正常处理...
```

## 📊 依赖项

```txt
litellm>=1.0.0
groq>=0.4.0
openai>=1.0.0
pydub>=0.25.0  # 可选，用于音频时长检测
```

## 🧪 测试

运行测试：

```bash
python3 -m pytest tests/backend/test_providers.py -v
```

## 💡 最佳实践

1. **API 密钥安全**: 使用环境变量或配置文件，不要硬编码
2. **速率限制**: 实现适当的重试逻辑和退避策略
3. **成本控制**: 监控 token 使用量，设置合理的 `max_tokens`
4. **错误处理**: 始终检查 `chunk.is_error`，实现优雅降级
5. **流式体验**: 使用 `flush=True` 确保实时输出
6. **工具调用**: 正确处理工具调用结果，添加到消息历史

## 🚀 扩展

要添加新的 Provider：

```python
from backend.modules.providers import LLMProvider, StreamChunk
from typing import AsyncIterator

class MyCustomProvider(LLMProvider):
    async def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs
    ) -> AsyncIterator[StreamChunk]:
        # 实现你的流式逻辑
        yield StreamChunk(content="响应内容")
        yield StreamChunk(finish_reason="stop")
    
    def get_default_model(self) -> str:
        return "my-default-model"
```

## 📄 许可证

MIT License
