import { nextTick, ref, type Ref } from 'vue'
import type { ChatMessage } from '@/types/chat'
import type { AttachmentItem } from '@/api/endpoints'

interface ToastLike {
  info(message: string): void
}

interface UseQueuedMessagesOptions {
  messages: Ref<ChatMessage[]>
  isStreaming: Ref<boolean>
  getCurrentSessionId: () => string | null
  sendRealtimeMessage: (payload: { type: 'message'; sessionId: string; content: string; attachments?: string[] }) => boolean
  addThinkingMessage: () => void
  toast: ToastLike
  scrollToBottom?: () => void
}

export interface OutgoingChatPayload {
  content: string
  attachmentItems?: AttachmentItem[]
}

export function useQueuedMessages(options: UseQueuedMessagesOptions) {
  const pendingMessages = ref<OutgoingChatPayload[]>([])

  function attachmentSignature(attachmentItems?: AttachmentItem[]) {
    return JSON.stringify((attachmentItems || []).map((item) => item.path))
  }

  function scrollToBottomSoon() {
    if (!options.scrollToBottom) return
    nextTick(() => {
      options.scrollToBottom?.()
    })
  }

  function pushQueuedPlaceholder(payload: OutgoingChatPayload) {
    options.messages.value.push({
      id: `user-${Date.now()}`,
      role: 'user',
      content: payload.content,
      attachmentItems: payload.attachmentItems || [],
      timestamp: new Date(),
      queued: true,
    })
  }

  function sendImmediateMessage(payload: OutgoingChatPayload) {
    const sessionId = options.getCurrentSessionId()
    if (!sessionId) return false

    const existingQueued = options.messages.value.find(
      (item) =>
        item.role === 'user' &&
        item.content === payload.content &&
        attachmentSignature(item.attachmentItems) === attachmentSignature(payload.attachmentItems) &&
        item.queued
    )

    if (existingQueued) {
      delete existingQueued.queued
    } else {
      options.messages.value.push({
        id: `user-${Date.now()}`,
        role: 'user',
        content: payload.content,
        attachmentItems: payload.attachmentItems || [],
        timestamp: new Date(),
      })
    }

    const sent = options.sendRealtimeMessage({
      type: 'message',
      sessionId,
      content: payload.content,
      attachments: (payload.attachmentItems || []).map((item) => item.path),
    })

    if (!sent) return false

    options.addThinkingMessage()
    scrollToBottomSoon()
    return true
  }

  function sendOrQueueMessage(payload: OutgoingChatPayload) {
    if (options.isStreaming.value) {
      pendingMessages.value.push(payload)
      pushQueuedPlaceholder(payload)
      options.toast.info(`消息已排队 (${pendingMessages.value.length})`)
      scrollToBottomSoon()
      return 'queued' as const
    }

    return sendImmediateMessage(payload) ? ('sent' as const) : ('failed' as const)
  }

  function flushNextQueuedMessage(delay = 100) {
    if (pendingMessages.value.length === 0) return
    const nextMessage = pendingMessages.value.shift()
    if (!nextMessage) return

    window.setTimeout(() => {
      sendImmediateMessage(nextMessage)
    }, delay)
  }

  function clearPendingMessages() {
    pendingMessages.value = []
  }

  return {
    pendingMessages,
    sendOrQueueMessage,
    sendImmediateMessage,
    flushNextQueuedMessage,
    clearPendingMessages,
  }
}
