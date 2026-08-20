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
    onMessage: (message) => {
      if (message.type === 'error') {
        console.error('[ChatWindow] Error:', message.message)
        options.toast.error(message.message || '发生错误')
        return
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
