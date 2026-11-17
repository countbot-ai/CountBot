/** 当前用户的对话模式策略：用于隐藏模式切换与默认模式收敛。 */

import { computed } from 'vue'
import type { ChatMode, ChatModePolicy } from '@/api'
import { useUserStore } from '@/store/user'

export function normalizeChatModePolicy(value?: string | null): ChatModePolicy {
  const text = String(value || '').trim().toLowerCase()
  if (text === 'chat' || text === 'agent') {
    return text
  }
  return 'all'
}

export function useChatModePolicy() {
  const userStore = useUserStore()

  const policy = computed<ChatModePolicy>(() =>
    normalizeChatModePolicy(userStore.profile?.chat_mode_policy),
  )

  const allowedChatModes = computed<ChatMode[]>(() => {
    const explicit = userStore.profile?.allowed_chat_modes
    if (Array.isArray(explicit) && explicit.length > 0) {
      return explicit
    }
    if (policy.value === 'chat' || policy.value === 'agent') {
      return [policy.value]
    }
    return ['agent', 'chat']
  })

  const canSwitchChatMode = computed(() => allowedChatModes.value.length > 1)
  const defaultChatMode = computed<ChatMode>(() => allowedChatModes.value[0] || 'agent')

  function clampChatMode(mode?: string | null): ChatMode {
    const next: ChatMode = String(mode || '').trim().toLowerCase() === 'chat' ? 'chat' : 'agent'
    return allowedChatModes.value.includes(next) ? next : defaultChatMode.value
  }

  return {
    policy,
    allowedChatModes,
    canSwitchChatMode,
    defaultChatMode,
    clampChatMode,
  }
}
