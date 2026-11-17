<template>
  <div
    ref="rootRef"
    class="chat-mode-toggle"
    role="group"
    :aria-label="$t('chat.mode.label')"
    @mouseleave="hovered = null"
  >
    <button
      v-for="option in options"
      :key="option.value"
      type="button"
      class="chat-mode-option"
      :class="{ 'is-active': option.value === mode }"
      :aria-pressed="option.value === mode"
      :aria-label="`${option.label}：${option.description}`"
      @click="select(option.value)"
      @mouseenter="hovered = option.value"
      @focus="hovered = option.value"
      @blur="hovered = null"
    >
      <component :is="option.icon" :size="12" />
      <span>{{ option.label }}</span>
    </button>

    <div v-if="hoveredOption" class="chat-mode-tooltip" role="tooltip">
      <div class="chat-mode-tooltip-title">{{ hoveredOption.label }}</div>
      <p class="chat-mode-tooltip-desc">{{ hoveredOption.description }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Bot as BotIcon, MessageSquare as MessageSquareIcon } from 'lucide-vue-next'
import type { ChatMode } from '@/api'

interface Props {
  mode?: ChatMode
  allowedModes?: ChatMode[]
}

const props = withDefaults(defineProps<Props>(), {
  mode: 'agent',
  allowedModes: () => ['agent', 'chat'],
})

const emit = defineEmits<{
  (e: 'change', mode: ChatMode): void
}>()

const { t } = useI18n()

const hovered = ref<ChatMode | null>(null)
const rootRef = ref<HTMLElement>()

const options = computed(() =>
  [
    {
      value: 'agent' as ChatMode,
      icon: BotIcon,
      label: t('chat.mode.agent'),
      description: t('chat.mode.agentTitle'),
    },
    {
      value: 'chat' as ChatMode,
      icon: MessageSquareIcon,
      label: t('chat.mode.chat'),
      description: t('chat.mode.chatTitle'),
    },
  ].filter(option => props.allowedModes.includes(option.value)),
)

const hoveredOption = computed(
  () => options.value.find(option => option.value === hovered.value) || null,
)

function select(mode: ChatMode): void {
  if (mode !== props.mode) {
    emit('change', mode)
  }
}
</script>

<style scoped>
/* 紧跟「思考强度」的模式切换：Agent 可调用工具，对话只保留性格与上下文 */
.chat-mode-toggle {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 1px;
  flex-shrink: 0;
  padding: 2px;
  border-radius: 8px;
  background: var(--color-bg-tertiary);
}

.chat-mode-option {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  min-width: 58px;
  padding: 1px 6px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--color-text-tertiary);
  font-size: 11px;
  line-height: 1.6;
  white-space: nowrap;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease, box-shadow 0.15s ease;
}

.chat-mode-option:hover {
  color: var(--color-text-secondary);
}

.chat-mode-option.is-active {
  background: var(--color-bg-elevated);
  color: var(--color-text-primary);
  box-shadow: var(--shadow-sm);
}

/* ---------- 悬停说明 ---------- */

.chat-mode-tooltip {
  position: absolute;
  bottom: calc(100% + 8px);
  left: 0;
  z-index: 40;
  width: max-content;
  max-width: 240px;
  padding: 7px 9px;
  border: 1px solid var(--color-border-secondary);
  border-radius: 8px;
  background: var(--color-bg-elevated);
  box-shadow: var(--shadow-md);
  color: var(--color-text-secondary);
  font-size: 11px;
  line-height: 1.55;
  text-align: left;
  pointer-events: none;
}

.chat-mode-tooltip-title {
  margin-bottom: 2px;
  color: var(--color-text-primary);
  font-size: 11px;
  font-weight: 600;
}

.chat-mode-tooltip-desc {
  margin: 0;
}
</style>
