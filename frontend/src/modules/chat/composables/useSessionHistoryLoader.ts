import { ref } from 'vue'
import type { SpawnTaskState } from '@/api/endpoints'
import type { ChatMessage } from '@/types/chat'
import type { Message as ChatHistoryMessage } from '@/store/chat'
import { normalizeHistoryMessages } from '@/modules/chat/utils/historyMessages'

const HISTORY_PAGE_SIZE = 50
interface UseSessionHistoryLoaderOptions {
  loadMessages: (
    sessionId: string,
    params?: {
      limit?: number
      offset?: number
      tool_mode?: 'full' | 'summary' | 'none'
      tool_preview_limit?: number
    }
  ) => Promise<ChatHistoryMessage[]>
  connectWebSocket: (sessionId: string) => void
  replaceMessages: (messages: ChatMessage[]) => void
  clearMessages: () => void
  restoreSessionMessages: (sessionId: string) => boolean
  clearSessionCache: (sessionId: string) => void
  cacheSessionMessages: (sessionId: string) => void
  getCachedSpawnTask: (taskId: string) => SpawnTaskState | null
}

export function useSessionHistoryLoader(options: UseSessionHistoryLoaderOptions) {
  const isLoadingMessages = ref(false)
  const isLoadingOlderMessages = ref(false)
  const hasMoreHistory = ref(false)
  const lastInitializedSessionId = ref<string | null>(null)
  const loadedMessageCountBySession = ref<Record<string, number>>({})

  async function fetchHistoryMessages(sessionId: string, messageCount: number): Promise<ChatMessage[]> {
    const historyMessages = await options.loadMessages(sessionId, {
      limit: messageCount,
      tool_mode: 'none',
    })

    if (!Array.isArray(historyMessages)) {
      hasMoreHistory.value = false
      return []
    }

    const normalizedMessages = normalizeHistoryMessages(
      historyMessages,
      options.getCachedSpawnTask
    )
    loadedMessageCountBySession.value = {
      ...loadedMessageCountBySession.value,
      [sessionId]: historyMessages.length,
    }
    hasMoreHistory.value = historyMessages.length >= messageCount
    return normalizedMessages
  }

  async function loadSessionMessages(sessionId: string, messageCount?: number) {
    try {
      isLoadingMessages.value = true
      const requestedCount =
        messageCount
        ?? loadedMessageCountBySession.value[sessionId]
        ?? HISTORY_PAGE_SIZE

      options.replaceMessages(await fetchHistoryMessages(sessionId, requestedCount))
      options.cacheSessionMessages(sessionId)
    } catch (error) {
      console.error('[useSessionHistoryLoader] 加载消息失败:', error)
      options.replaceMessages([])
    } finally {
      isLoadingMessages.value = false
    }
  }

  async function loadOlderMessages(sessionId: string) {
    if (!sessionId || isLoadingOlderMessages.value || !hasMoreHistory.value) {
      return
    }

    try {
      isLoadingOlderMessages.value = true
      const currentCount = loadedMessageCountBySession.value[sessionId] || HISTORY_PAGE_SIZE
      const nextCount = currentCount + HISTORY_PAGE_SIZE
      options.replaceMessages(await fetchHistoryMessages(sessionId, nextCount))
      options.cacheSessionMessages(sessionId)
    } catch (error) {
      console.error('[useSessionHistoryLoader] 加载更早消息失败:', error)
    } finally {
      isLoadingOlderMessages.value = false
    }
  }

  function initializeChat(sessionId: string, shouldClearMessages = false) {
    if (sessionId === lastInitializedSessionId.value) return

    lastInitializedSessionId.value = sessionId

    const restored = options.restoreSessionMessages(sessionId)
    if (restored) {
      options.connectWebSocket(sessionId)
      // Cached messages are only a fast-start snapshot. Always backfill from
      // the server so channel-originated updates are not hidden by sessionStorage.
      void loadSessionMessages(sessionId)
      return
    }

    if (shouldClearMessages) {
      options.clearMessages()
      options.clearSessionCache(sessionId)
    }

    options.connectWebSocket(sessionId)
    void loadSessionMessages(sessionId)
  }

  function resetInitializedSession() {
    lastInitializedSessionId.value = null
  }

  function cacheCurrentSession(sessionId: string | null, hasMessages: boolean) {
    if (!sessionId || !hasMessages) return
    options.cacheSessionMessages(sessionId)
  }

  return {
    isLoadingMessages,
    isLoadingOlderMessages,
    hasMoreHistory,
    initializeChat,
    loadSessionMessages,
    loadOlderMessages,
    resetInitializedSession,
    cacheCurrentSession,
  }
}
