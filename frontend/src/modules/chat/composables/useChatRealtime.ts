import type { WebSocketMessage, UseWebSocketOptions } from '@/composables/useWebSocket'

interface ToastLike {
  error(message: string): void
}

interface UseChatRealtimeOptions {
  setHandlers: (options: UseWebSocketOptions) => void
  dispatchStreamEvent: (message: WebSocketMessage) => void
  getCurrentSessionId: () => string | null
  refreshSessionMessages: (sessionId: string) => Promise<void> | void
  refreshSessions: () => Promise<void> | void
  cacheSessionMessages: (sessionId: string) => void
  flushNextQueuedMessage: (delay?: number) => void
  toast: ToastLike
  /** 是否有对话正在处理中，用于让心跳避免误判连接失活 */
  isBusy?: () => boolean
}

export function useChatRealtime(options: UseChatRealtimeOptions) {
  const cacheDebounceMs = 250
  const highFrequencyCacheEventTypes = new Set([
    'message_chunk',
    'reasoning_chunk',
    'workflow_agent_chunk',
    'tool_progress',
    'task_progress',
    'task_log',
  ])

  let cacheTimer: number | null = null
  let pendingCacheSessionId: string | null = null

  const flushCachedSession = () => {
    if (!pendingCacheSessionId) {
      return
    }

    options.cacheSessionMessages(pendingCacheSessionId)
    pendingCacheSessionId = null
  }

  const clearPendingCacheTimer = () => {
    if (cacheTimer !== null) {
      window.clearTimeout(cacheTimer)
      cacheTimer = null
    }
  }

  const scheduleSessionCache = (sessionId: string) => {
    pendingCacheSessionId = sessionId
    if (cacheTimer !== null) {
      return
    }

    cacheTimer = window.setTimeout(() => {
      cacheTimer = null
      flushCachedSession()
    }, cacheDebounceMs)
  }

  const persistSessionCache = (sessionId: string, immediate = false) => {
    if (immediate) {
      pendingCacheSessionId = sessionId
      clearPendingCacheTimer()
      flushCachedSession()
      return
    }

    scheduleSessionCache(sessionId)
  }

  options.setHandlers({
    isBusy: options.isBusy,
    onOpen: (isReconnect) => {
      if (!isReconnect) return
      const sessionId = options.getCurrentSessionId()
      if (!sessionId) return
      // 断线期间可能错过流式分片或完成事件：重连后以服务端历史为准收敛一次，
      // 同时也能结束可能残留的“执行中”状态。
      Promise.resolve(options.refreshSessionMessages(sessionId)).catch((error) => {
        console.warn('[ChatWindow] 重连后刷新消息失败:', error)
      })
    },
    onMessage: (message) => {
      if (message.type === 'error') {
        console.error('[ChatWindow] Error:', message.message)
        // 通用 error 表示本轮处理已终止：收敛仍在运行的卡片并退出流式态，
        // 否则界面会一直停在“执行中”。
        options.dispatchStreamEvent({ ...message, type: 'stream_error' })
        options.toast.error(message.message || '发生错误')
        const failedSessionId = options.getCurrentSessionId()
        if (failedSessionId) {
          persistSessionCache(failedSessionId, true)
        }
        return
      }

      if (message.type === 'tool_error') {
        // 单个工具失败不终止本轮对话，但要保留原有的错误提示。
        options.toast.error(message.error || message.message || '工具执行失败')
      }

      if (message.type === 'sessions_updated') {
        Promise.resolve(options.refreshSessions()).catch((error) => {
          console.warn('[ChatWindow] 刷新会话列表失败:', error)
        })
        return
      }

      if (message.type === 'history_updated') {
        const currentSessionId = options.getCurrentSessionId()
        const targetSessionId = String(message.sessionId || '')

        Promise.resolve(options.refreshSessions()).catch((error) => {
          console.warn('[ChatWindow] 刷新会话列表失败:', error)
        })

        if (currentSessionId && targetSessionId === currentSessionId) {
          Promise.resolve(options.refreshSessionMessages(currentSessionId)).catch((error) => {
            console.warn('[ChatWindow] 刷新当前会话消息失败:', error)
          })
        }
        return
      }

      options.dispatchStreamEvent(
        message.type === 'message_chunk'
          ? { ...message, sessionId: options.getCurrentSessionId() }
          : message
      )

      if (message.type === 'message_complete') {
        options.flushNextQueuedMessage(100)
      }

      const sessionId = options.getCurrentSessionId()
      if (sessionId) {
        persistSessionCache(
          sessionId,
          !highFrequencyCacheEventTypes.has(message.type) || message.type === 'message_complete'
        )
      }
    },
  })
}
