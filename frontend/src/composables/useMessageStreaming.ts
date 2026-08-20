import { computed, ref } from 'vue'
import { type SpawnTaskState } from '@/api/endpoints'
import type { ChatMessage, ChatToolCall } from '@/types/chat'
import {
  chatStreamReducer,
  createInitialChatStreamState,
  mapRealtimeMessageToAction,
  type StreamRealtimeMessage,
} from '@/modules/chat/runtime/chatStreamReducer'

export type Message = ChatMessage
export type ToolCall = ChatToolCall

export function useMessageStreaming() {
  const runtime = ref(createInitialChatStreamState())

  const messages = computed({
    get: () => runtime.value.messages,
    set: (value: ChatMessage[]) => {
      runtime.value = {
        ...runtime.value,
        messages: value,
      }
    },
  })

  const isStreaming = computed({
    get: () => runtime.value.isStreaming,
    set: (value: boolean) => {
      runtime.value = {
        ...runtime.value,
        isStreaming: value,
      }
    },
  })

  const SPAWN_CACHE_KEY = (taskId: string) => `spawn_task_v1_${taskId}`
  const SESSION_MESSAGES_CACHE_KEY = (sessionId: string) => `session_messages_${sessionId}`
  const SESSION_STREAMING_STATE_KEY = (sessionId: string) => `session_streaming_${sessionId}`

  function applyAction(action: Parameters<typeof chatStreamReducer>[1]) {
    const previousState = runtime.value
    runtime.value = chatStreamReducer(runtime.value, action)

    if (action.type === 'spawn_event') {
      const payload = action.payload
      if (
        (payload.type === 'task_complete' || payload.type === 'task_failed') &&
        previousState.spawnTaskMap[payload.task_id]
      ) {
        const spawnLink = previousState.spawnTaskMap[payload.task_id]
        const message = runtime.value.messages.find((item) => item.id === spawnLink.messageId)
        const toolCall = message?.toolCalls?.find((item) => item.id === spawnLink.toolCallId)
        if (toolCall?.spawn_task) {
          cacheSpawnTask(payload.task_id, toolCall.spawn_task as SpawnTaskState)
        }
      }
    }
  }

  function dispatchStreamEvent(message: StreamRealtimeMessage) {
    const action = mapRealtimeMessageToAction(message)
    if (!action) {
      return
    }
    applyAction(action)
  }

  function replaceMessages(nextMessages: ChatMessage[]) {
    applyAction({ type: 'replace_messages', messages: nextMessages })
  }

  function cacheSpawnTask(taskId: string, spawnTaskData: SpawnTaskState) {
    try {
      localStorage.setItem(SPAWN_CACHE_KEY(taskId), JSON.stringify(spawnTaskData))
    } catch {
      /* ignore storage failures */
    }
  }

  function getCachedSpawnTask(taskId: string): SpawnTaskState | null {
    try {
      const raw = localStorage.getItem(SPAWN_CACHE_KEY(taskId))
      return raw ? (JSON.parse(raw) as SpawnTaskState) : null
    } catch {
      return null
    }
  }

  function cacheSessionMessages(sessionId: string) {
    if (!sessionId || messages.value.length === 0) return

    try {
      sessionStorage.setItem(
        SESSION_MESSAGES_CACHE_KEY(sessionId),
        JSON.stringify({
          messages: messages.value,
          isStreaming: isStreaming.value,
          timestamp: Date.now(),
        })
      )

      if (isStreaming.value && runtime.value.currentStreamingMessageId) {
        sessionStorage.setItem(
          SESSION_STREAMING_STATE_KEY(sessionId),
          JSON.stringify({
            currentStreamingMessageId: runtime.value.currentStreamingMessageId,
            currentWorkflowToolCallId: runtime.value.currentWorkflowToolCallId,
            timestamp: Date.now(),
          })
        )
      }
    } catch (error) {
      console.warn('[useMessageStreaming] 缓存消息失败:', error)
    }
  }

  function restoreSessionMessages(sessionId: string): boolean {
    if (!sessionId) return false

    try {
      const cached = sessionStorage.getItem(SESSION_MESSAGES_CACHE_KEY(sessionId))
      if (!cached) return false

      const cacheData = JSON.parse(cached)
      const age = Date.now() - cacheData.timestamp
      if (age > 5 * 60 * 1000) {
        clearSessionCache(sessionId)
        return false
      }

      const restoredMessages: ChatMessage[] = cacheData.messages.map((message: any) => ({
        ...message,
        timestamp: new Date(message.timestamp),
      }))

      let currentStreamingMessageId: string | null = null
      let currentWorkflowToolCallId: string | null = null
      if (cacheData.isStreaming) {
        const streamingState = sessionStorage.getItem(SESSION_STREAMING_STATE_KEY(sessionId))
        if (streamingState) {
          const parsed = JSON.parse(streamingState)
          currentStreamingMessageId = parsed.currentStreamingMessageId
          currentWorkflowToolCallId = parsed.currentWorkflowToolCallId
        }
      }

      applyAction({
        type: 'hydrate_runtime',
        messages: restoredMessages,
        isStreaming: cacheData.isStreaming,
        currentStreamingMessageId,
        currentWorkflowToolCallId,
      })

      console.debug(`[useMessageStreaming] 从缓存恢复了 ${messages.value.length} 条消息`)
      return true
    } catch (error) {
      console.warn('[useMessageStreaming] 恢复消息失败:', error)
      return false
    }
  }

  function clearSessionCache(sessionId: string) {
    if (!sessionId) return
    try {
      sessionStorage.removeItem(SESSION_MESSAGES_CACHE_KEY(sessionId))
      sessionStorage.removeItem(SESSION_STREAMING_STATE_KEY(sessionId))
    } catch {
      /* ignore */
    }
  }

  function handleMessageChunk(message: StreamRealtimeMessage) {
    dispatchStreamEvent(message)
  }

  function handleToolCall(message: StreamRealtimeMessage) {
    dispatchStreamEvent(message)
  }

  function handleToolResult(message: StreamRealtimeMessage) {
    dispatchStreamEvent(message)
  }

  function handleWorkflowEvent(message: StreamRealtimeMessage) {
    dispatchStreamEvent(message)
  }

  function handleSpawnEvent(message: StreamRealtimeMessage) {
    dispatchStreamEvent(message)
  }

  function handleMessageComplete() {
    applyAction({ type: 'message_complete' })
  }

  function stopStreaming() {
    applyAction({ type: 'stop_streaming' })
  }

  function clearMessages() {
    applyAction({ type: 'clear_messages' })
  }

  function addThinkingMessage() {
    applyAction({ type: 'add_thinking_message', now: Date.now() })
  }

  return {
    messages,
    isStreaming,
    dispatchStreamEvent,
    replaceMessages,
    handleMessageChunk,
    handleToolCall,
    handleToolResult,
    handleWorkflowEvent,
    handleSpawnEvent,
    handleMessageComplete,
    stopStreaming,
    clearMessages,
    addThinkingMessage,
    cacheSpawnTask,
    getCachedSpawnTask,
    cacheSessionMessages,
    restoreSessionMessages,
    clearSessionCache,
  }
}
