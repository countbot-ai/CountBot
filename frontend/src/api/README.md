# API 模块

完整的前后端 API 对接实现。

## 文件结构

```
api/
├── client.ts       # Axios 客户端（带重试、拦截器）
├── endpoints.ts    # 所有 API 端点定义和类型
├── websocket.ts    # WebSocket 客户端（带重连）
├── index.ts        # 统一导出
└── README.md       # 本文件
```

## 功能特性

### client.ts
- ✅ 自动重试失败的请求（指数退避）
- ✅ 请求/响应拦截器
- ✅ 错误处理和转换
- ✅ 请求超时控制
- ✅ 性能监控（开发环境）
- ✅ 请求 ID 追踪

### endpoints.ts
- ✅ 完整的 TypeScript 类型定义
- ✅ 所有后端 API 端点
- ✅ Chat API（会话、消息）
- ✅ Settings API（配置管理）
- ✅ Tools API（工具执行）
- ✅ Memory API（记忆管理）
- ✅ Skills API（技能管理）
- ✅ Cron API（定时任务）
- ✅ Tasks API（后台任务）

### websocket.ts
- ✅ 自动重连机制
- ✅ 消息队列（断线时）
- ✅ 心跳检测
- ✅ 事件处理器
- ✅ TypeScript 类型安全

## 使用示例

### 基本 API 调用

```typescript
import { chatAPI, settingsAPI } from '@/api'

// 获取会话列表
const sessions = await chatAPI.getSessions()

// 创建新会话
const newSession = await chatAPI.createSession('My Chat')

// 获取设置
const settings = await settingsAPI.get()

// 更新设置
await settingsAPI.update({
  model: {
    temperature: 0.8
  }
})
```

### WebSocket 使用

```typescript
import { getWebSocketClient } from '@/api'

const ws = getWebSocketClient()

// 连接
await ws.connect()

// 监听消息
ws.on('message_chunk', (message) => {
  console.log('Received:', message.content)
})

// 发送消息
ws.sendMessage('session-id', 'Hello!')

// 断开连接
ws.disconnect()
```

### 错误处理

```typescript
import { chatAPI, type ApiError } from '@/api'

try {
  await chatAPI.createSession('Test')
} catch (error) {
  const apiError = error as ApiError
  console.error('Error:', apiError.message)
  console.error('Status:', apiError.status)
  console.error('Details:', apiError.details)
}
```

### 请求取消

```typescript
import { apiClient, CancelToken } from '@/api'

const source = CancelToken.source()

// 发起请求
apiClient.get('/some-endpoint', {
  cancelToken: source.token
})

// 取消请求
source.cancel('Operation canceled by user')
```

## 与 Store 集成

所有 Pinia stores 已经集成了新的 API 客户端：

- `useChatStore` - 使用 `chatAPI`
- `useSettingsStore` - 使用 `settingsAPI`
- `useToolsStore` - 使用 `toolsAPI`
- `useMemoryStore` - 使用 `memoryAPI`
- `useSkillsStore` - 使用 `skillsAPI`
- `useCronStore` - 使用 `cronAPI`
- `useTasksStore` - 使用 `tasksAPI`

## 配置

### 超时时间

默认超时：30 秒

```typescript
import { createApiClient } from '@/api'

const customClient = createApiClient({
  timeout: 60000 // 60 秒
})
```

### 重试配置

默认重试：3 次，指数退避（1s, 2s, 4s）

可重试的状态码：408, 429, 500, 502, 503, 504
可重试的错误：ECONNABORTED, ETIMEDOUT, ENOTFOUND, ENETUNREACH

### WebSocket 配置

默认重连：最多 5 次，指数退避
心跳间隔：30 秒

## 开发调试

开发环境下，所有 API 请求和响应都会在控制台输出：

```
[API Request] POST /api/chat/send { ... }
[API Response] POST /api/chat/send (234ms) { ... }
[API Performance] Slow request detected: /api/chat/send (3456ms)
```

## 类型安全

所有 API 调用都有完整的 TypeScript 类型定义：

```typescript
// ✅ 类型安全
const session: Session = await chatAPI.createSession('Test')

// ❌ 类型错误
const session: string = await chatAPI.createSession('Test')
```

## 测试

运行类型检查：

```bash
npm run type-check
```

## 后端对接状态

| API 模块 | 端点数 | 状态 |
|---------|-------|------|
| Chat    | 6     | ✅   |
| Settings| 3     | ✅   |
| Tools   | 2     | ✅   |
| Memory  | 6     | ✅   |
| Skills  | 3     | ✅   |
| Cron    | 5     | ✅   |
| Tasks   | 3     | ✅   |
| WebSocket| 1    | ✅   |

**总计：29 个 API 端点，全部对接完成！**
