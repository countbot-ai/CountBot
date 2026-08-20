<template>
  <div class="message-footer">
    <div class="message-time">
      {{ formattedTime }}
    </div>
    <div class="message-actions">
      <button
        v-if="message.role === 'assistant'"
        class="action-btn"
        :title="$t('chat.replay') || '重放'"
        @click="$emit('replay')"
      >
        <component :is="isReplaying ? SquareIcon : PlayIcon" :size="14" />
      </button>
      <button
        v-if="message.role === 'assistant'"
        class="action-btn"
        :title="$t('chat.regenerate')"
        @click="$emit('regenerate')"
      >
        <component :is="RefreshIcon" :size="14" />
      </button>
      <button
        v-if="message.role === 'assistant'"
        class="action-btn"
        :title="$t('chat.copy')"
        @click="handleCopy"
      >
        <component :is="copied ? CheckIcon : CopyIcon" :size="14" />
      </button>
      <button
        class="action-btn action-btn-delete"
        :title="$t('chat.deleteMessage') || '删除消息'"
        @click="$emit('delete')"
      >
        <component :is="TrashIcon" :size="14" />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import {
  RefreshCw as RefreshIcon,
  Copy as CopyIcon,
  Check as CheckIcon,
  Play as PlayIcon,
  Square as SquareIcon,
  Trash2 as TrashIcon
} from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { useToast } from '@/composables/useToast'
import { formatTime } from '@/utils/time'
import type { ChatMessage } from '@/types/chat'

interface Props {
  message: ChatMessage
  isReplaying: boolean
}

const props = defineProps<Props>()

interface Emits {
  (e: 'replay'): void
  (e: 'regenerate'): void
  (e: 'delete'): void
}

defineEmits<Emits>()

const { t } = useI18n()
const toast = useToast()

const copied = ref(false)

const formattedTime = computed(() => {
  return formatTime(props.message.timestamp)
})

const handleCopy = async () => {
  try {
    await navigator.clipboard.writeText(props.message.content)
    copied.value = true
    toast.success(t('chat.copied'))
    
    setTimeout(() => {
      copied.value = false
    }, 2000)
  } catch (error) {
    console.error('Failed to copy:', error)
    toast.error(t('chat.copyFailed'))
  }
}
</script>

<style scoped>
.message-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-sm);
}

.message-time {
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
  padding: 0 var(--spacing-xs);
}

.message-actions {
  display: flex;
  gap: var(--spacing-xs);
  opacity: 0;
  transition: opacity var(--transition-base);
}

.message:hover .message-actions {
  opacity: 1;
}

.action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-tertiary);
  cursor: pointer;
  transition: all var(--transition-base);
}

.action-btn:hover {
  background: var(--hover-bg);
  color: var(--text-primary);
}

.action-btn:active {
  transform: scale(0.95);
}

.action-btn-delete {
  color: var(--text-tertiary);
}

.action-btn-delete:hover {
  color: var(--color-error, #ef4444);
  background: var(--color-error-bg, #fee2e2);
}

:root[data-theme="dark"] .action-btn-delete:hover {
  color: #ff6b8a;
  background: rgba(239, 68, 68, 0.1);
}
</style>
