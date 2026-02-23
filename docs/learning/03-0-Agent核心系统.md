# 三、Agent 核心系统

Agent 系统是 CountBot 的大脑，位于 `backend/modules/agent/` 目录。本章分为三个子文档，分别详解 Agent 的主循环、上下文构建和记忆管理。

## 1、模块概览

```
backend/modules/agent/
├── loop.py            # ★ Agent 主循环（ReAct 模式）
├── context.py         # ★ 上下文构建器（系统提示词）
├── memory.py          # ★ 记忆存储管理
├── heartbeat.py       # 主动问候服务
├── personalities.py   # 12 种性格预设
├── skills.py          # 技能加载器
├── subagent.py        # 子代理管理
├── analyzer.py        # 消息分析与总结触发
├── prompts.py         # 提示词模板
└── task_manager.py    # 取消令牌管理
```

## 2、子文档导航

| 子文档 | 内容 | 核心文件 |
|--------|------|----------|
| [03-1 Agent 主循环](03-1-Agent主循环.md) | AgentLoop 类、ReAct 循环、流式响应、工具执行重试、取消令牌、子代理 | `loop.py`, `subagent.py`, `task_manager.py` |
| [03-2 上下文构建器](03-2-上下文构建器.md) | ContextBuilder、系统提示词构建、核心身份、性格加载、消息列表、多模态支持 | `context.py`, `personalities.py` |
| [03-3 记忆系统](03-3-记忆系统.md) | MemoryStore、行式存储格式、搜索、ConversationSummarizer | `memory.py`, `analyzer.py`, `prompts.py` |

## 3、建议阅读顺序

1. 先读 **03-1 Agent 主循环**，理解 Agent 的整体运行流程
2. 再读 **03-2 上下文构建器**，理解 LLM 接收到的提示词是如何构建的
3. 最后读 **03-3 记忆系统**，理解跨会话记忆和对话总结的实现

## 4、关键设计要点

（1）Agent Loop 的流式生成器设计使得文本可以实时推送给用户，无需等待完整响应
（2）工具调用的重试机制提高了可靠性，但不会无限重试（最多 3 次）
（3）取消令牌在循环的多个检查点被检查，确保取消操作能及时生效
（4）ContextBuilder 的降级策略保证了即使数据库异常也不会影响基本功能
（5）记忆系统采用文本文件而非数据库，是一个有意的简化决策
