# Agent Loop 重构设计文档

## 1. 现状分析

当前的 `AgentLoop.process_message` 方法存在以下问题：

1.  **代码过长**：单个方法超过 300 行，难以阅读和维护。
2.  **职责混合**：混合了 LLM 交互、工具执行、错误处理、日志记录、会话管理等多种逻辑。
3.  **扩展性差**：新增逻辑（如添加新的中间件或钩子）需要修改核心循环，容易引入 Bug。
4.  **测试困难**：由于依赖过多且逻辑复杂，单元测试难以覆盖所有分支。

## 2. 重构目标

1.  **提高可读性**：将大方法拆分为多个语义清晰的小方法。
2.  **增强扩展性**：通过清晰的流程控制，便于后续添加新的功能（如插件系统、更复杂的重试策略）。
3.  **解耦职责**：将工具执行、上下文管理等逻辑分离。

## 3. 详细设计

我们将 `process_message` 的执行流程拆分为以下几个主要步骤：

1.  **初始化上下文 (`_initialize_context`)**
2.  **主循环 (`_run_agent_loop`)**
    *   LLM 交互与流式响应 (`_stream_llm_response`)
    *   工具调用处理 (`_process_tool_calls`)
    *   上下文更新 (`_update_context_with_tool_results`)
3.  **会话结束处理 (`_finalize_session`)**

### 3.1 方法拆分设计

#### `_initialize_context`
负责构建初始的消息列表，处理 `context_builder` 的逻辑。

#### `_stream_llm_response`
负责调用 LLM 的 `chat_stream` 接口，处理流式块（Chunk），收集内容和工具调用信息，并 yield 给调用方。

#### `_process_tool_calls`
负责遍历 `tool_calls`，执行工具，处理重试逻辑，发送 WebSocket 通知，记录审计日志。

#### `_execute_single_tool`
负责单个工具的执行，包括重试机制和错误捕获。

#### `_finalize_session`
负责在循环结束后，保存会话历史和记录最终的审计日志。

### 3.2 代码结构示例

```python
class AgentLoop:
    async def process_message(self, message, session_id, ...):
        # 1. 初始化
        messages = self._initialize_context(message, context, ...)
        
        # 2. 主循环
        async for chunk in self._run_agent_loop(messages, session_id, ...):
            yield chunk

    async def _run_agent_loop(self, messages, session_id, ...):
        while iteration < self.max_iterations:
            # LLM 交互
            response_data = await self._stream_llm_response(messages, ...)
            yield response_data.content_chunk
            
            # 如果没有工具调用，结束
            if not response_data.tool_calls:
                break
                
            # 处理工具调用
            tool_results = await self._process_tool_calls(response_data.tool_calls, session_id, ...)
            
            # 更新上下文
            messages = self._update_context(messages, response_data, tool_results)
            
        # 3. 结束处理
        self._finalize_session(session_id, messages)
```

## 4. 重构步骤

1.  **提取 `_initialize_context`**：将消息构建逻辑独立。
2.  **提取 `_execute_single_tool`**：将单个工具的执行、重试、异常处理逻辑独立。
3.  **提取 `_process_tool_calls`**：将工具调用的循环、通知发送、历史记录逻辑独立。
4.  **提取 `_stream_llm_response`**：将 LLM 流式处理逻辑独立。
5.  **重组 `process_message`**：使用上述新方法重写主逻辑。

## 5. 预期收益

*   **代码行数减少**：主方法行数预计减少至 50 行以内。
*   **逻辑清晰**：每个方法的职责单一，易于理解。
*   **易于测试**：可以针对 `_execute_single_tool` 等小方法单独编写测试用例。
