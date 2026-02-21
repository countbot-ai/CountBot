# Tools Module - 工具模块

## 概述

工具模块为 CountBot Desktop 提供了完整的工具系统，允许 AI Agent 执行各种操作，包括文件操作、Shell 命令执行和 Web 搜索。

## 架构

```
tools/
├── base.py           # Tool 抽象基类
├── registry.py       # 工具注册表
├── filesystem.py     # 文件系统工具
├── shell.py          # Shell 执行工具
├── web.py            # Web 工具
└── example_tool.py   # 示例工具
```

## 核心组件

### 1. Tool 基类 (base.py)

所有工具必须继承的抽象基类。

```python
from backend.modules.tools import Tool

class MyTool(Tool):
    @property
    def name(self) -> str:
        return "my_tool"
    
    @property
    def description(self) -> str:
        return "My custom tool"
    
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "param": {"type": "string"}
            },
            "required": ["param"]
        }
    
    async def execute(self, **kwargs) -> str:
        return f"Result: {kwargs['param']}"
```

### 2. ToolRegistry (registry.py)

管理所有工具的注册和执行。

```python
from backend.modules.tools import ToolRegistry

registry = ToolRegistry()
registry.register(my_tool)

# 执行工具
result = await registry.execute("my_tool", {"param": "value"})

# 获取工具定义（用于 LLM）
definitions = registry.get_definitions()
```

### 3. 文件系统工具 (filesystem.py)

#### WorkspaceValidator
确保所有文件操作在工作空间内进行。

#### ReadFileTool
读取文件内容。

```python
tool = ReadFileTool(workspace)
content = await tool.execute(path="file.txt")
```

#### WriteFileTool
写入文件内容。

```python
tool = WriteFileTool(workspace)
result = await tool.execute(path="file.txt", content="Hello")
```

#### EditFileTool
使用搜索替换编辑文件。

```python
tool = EditFileTool(workspace)
result = await tool.execute(
    path="file.txt",
    old_text="old",
    new_text="new"
)
```

#### ListDirTool
列出目录内容。

```python
tool = ListDirTool(workspace)
result = await tool.execute(path=".")
```

### 4. Shell 工具 (shell.py)

#### ExecTool
执行 Shell 命令，包含安全检查。

```python
tool = ExecTool(workspace, timeout=30)
result = await tool.execute(command="ls -la")
```

#### 危险命令检测
自动阻止危险命令：
- `rm -rf`
- `format`
- `dd`
- `shutdown`
- `chmod -R 777 /`
- 等等

### 5. Web 工具 (web.py)

#### WebSearchTool
使用 Brave Search API 搜索网络。

```python
tool = WebSearchTool(api_key="your_key")
result = await tool.execute(query="Python", count=5)
```

#### WebFetchTool
获取网页内容。

```python
tool = WebFetchTool()
content = await tool.execute(url="https://example.com")
```

#### WebSearchToolMock
用于测试的模拟搜索工具。

```python
tool = WebSearchToolMock()
result = await tool.execute(query="test")
```

## 使用示例

### 完整工作流

```python
from pathlib import Path
from backend.modules.tools import *

# 创建工作空间
workspace = Path("/path/to/workspace")

# 创建注册表
registry = ToolRegistry()

# 注册工具
registry.register(ReadFileTool(workspace))
registry.register(WriteFileTool(workspace))
registry.register(EditFileTool(workspace))
registry.register(ListDirTool(workspace))
registry.register(ExecTool(workspace))
registry.register(WebSearchTool(api_key="key"))

# 使用工具
await registry.execute("write_file", {
    "path": "test.txt",
    "content": "Hello World"
})

content = await registry.execute("read_file", {
    "path": "test.txt"
})

await registry.execute("edit_file", {
    "path": "test.txt",
    "old_text": "World",
    "new_text": "Python"
})

result = await registry.execute("exec", {
    "command": "cat test.txt"
})

search_results = await registry.execute("web_search", {
    "query": "Python programming",
    "count": 5
})
```

### 为 LLM 生成工具定义

```python
registry = ToolRegistry()
# ... 注册工具 ...

# 获取所有工具定义
definitions = registry.get_definitions()

# 传递给 LLM
response = llm.chat(
    messages=[...],
    tools=definitions
)
```

## 安全特性

### 1. 工作空间隔离
所有文件操作都限制在指定的工作空间内，防止路径遍历攻击。

### 2. 危险命令检测
Shell 工具自动检测并阻止危险命令。

### 3. 超时控制
Shell 命令执行有超时限制，防止长时间运行。

### 4. 输出截断
长输出会被自动截断，防止内存溢出。

## 测试

```bash
# 运行所有工具测试
pytest tests/backend/test_tools.py
pytest tests/backend/test_filesystem_tools.py
pytest tests/backend/test_shell_tools.py
pytest tests/backend/test_web_tools.py
pytest tests/backend/test_tools_integration.py
```

## 扩展

### 创建自定义工具

1. 继承 `Tool` 基类
2. 实现所有抽象方法
3. 注册到 `ToolRegistry`

```python
from backend.modules.tools import Tool

class CustomTool(Tool):
    @property
    def name(self) -> str:
        return "custom_tool"
    
    @property
    def description(self) -> str:
        return "A custom tool"
    
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "input": {"type": "string"}
            },
            "required": ["input"]
        }
    
    async def execute(self, **kwargs) -> str:
        # 实现工具逻辑
        return "Result"
```

## 性能考虑

- 所有工具都是异步的，支持并发执行
- 文件操作使用缓冲 I/O
- Shell 命令有超时保护
- Web 请求有连接池和超时控制

## 日志

所有工具操作都会记录日志：
- INFO: 正常操作
- WARNING: 潜在问题（如输出截断）
- ERROR: 错误情况

查看日志：
```bash
tail -f data/logs/CountBot_*.log
```

## 依赖

- `loguru`: 日志记录
- `httpx`: HTTP 客户端（Web 工具）
- Python 3.11+

## 许可

MIT License
