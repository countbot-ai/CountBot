<template>
  <div ref="rootEl" class="interleaved-message" :class="{ 'is-shell-mode': shellMode }">
    <!-- 完整消息内容 -->
    <!-- eslint-disable-next-line vue/no-v-html -->
    <div 
      v-if="content"
      class="message-content markdown-content"
      v-html="content"
    />
    
    <!-- 工具调用列表 -->
    <div v-if="visibleToolCalls.length > 0" class="tools-section">
      <div class="tools-header" @click="toggleToolsExpanded">
        <component :is="WrenchIcon" :size="14" class="tools-icon" />
        <div class="tools-copy">
          <span class="tools-label">{{ $t('tools.executedActions') }}</span>
          <span class="tools-subtitle">Primary agent execution trail</span>
        </div>
        <span class="tools-count">{{ visibleToolCalls.length }}</span>
        <component :is="ChevronDownIcon" :size="14" class="tools-chevron" :class="{ expanded: toolsExpanded }" />
      </div>
      <transition name="slide-tools">
        <div v-show="toolsExpanded" class="tools-list">
          <ToolCallCard
            v-for="(toolCall, index) in visibleToolCalls"
            :key="toolCall.id || index"
            :tool-name="toolCall.name"
            :arguments="toolCall.arguments"
            :status="toolCall.status || 'success'"
            :result="toolCall.result"
            :error="toolCall.error"
            :duration="toolCall.duration"
            :progress="toolCall.progress"
            :progress-message="toolCall.progressMessage"
            :progress-details="toolCall.progressDetails"
            :default-collapsed="true"
            :is-replaying="isReplaying"
            :show-result="shouldShowResult(index)"
            context-kind="main"
          />
        </div>
      </transition>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Wrench as WrenchIcon, ChevronDown as ChevronDownIcon } from 'lucide-vue-next'
import { useMermaid } from '@/composables/useMermaid'
import ToolCallCard from './ToolCallCard.vue'
import type { ChatToolCall } from '@/types/chat'

interface Props {
  content: string
  toolCalls: ChatToolCall[]
  isReplaying?: boolean
  replaySegmentCount?: number
  shellMode?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  isReplaying: false,
  replaySegmentCount: undefined,
  shellMode: false
})

const rootEl = ref<HTMLElement | null>(null)
const toolsExpanded = ref(true)

useMermaid(rootEl, [() => props.content, () => props.isReplaying, () => props.replaySegmentCount])

const toggleToolsExpanded = () => {
  toolsExpanded.value = !toolsExpanded.value
}

const visibleToolCalls = computed(() => {
  if (!props.isReplaying) return props.toolCalls
  return props.toolCalls.slice(0, props.replaySegmentCount || 0)
})

const shouldShowResult = (index: number): boolean => {
  if (!props.isReplaying) return true
  return index < (props.replaySegmentCount || 0)
}
</script>

<style scoped>
.interleaved-message {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.interleaved-message.is-shell-mode {
  gap: 14px;
}

/* 消息内容 */
.message-content {
  padding: 12px 16px;
  background: #f8fafc;
  border: 1px solid #f1f5f9;
  border-radius: 8px;
  font-size: 14px;
  line-height: 1.7;
  color: var(--text-primary, #1e293b);
  word-wrap: break-word;
  overflow-wrap: break-word;
  word-break: break-word;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}

.interleaved-message.is-shell-mode .message-content {
  padding: 0;
  background: transparent;
  border: none;
  border-radius: 0;
  box-shadow: none;
}

/* 工具调用区域 */
.tools-section {
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 16px;
  overflow: hidden;
  background:
    radial-gradient(circle at top left, rgba(79, 131, 204, 0.05), transparent 18%),
    linear-gradient(180deg, rgba(252, 253, 255, 0.985), rgba(246, 249, 252, 0.98));
  box-shadow:
    0 8px 20px rgba(15, 23, 42, 0.04),
    inset 0 1px 0 rgba(255, 255, 255, 0.82);
  transition: all 0.2s ease;
}

.interleaved-message.is-shell-mode .tools-section {
  position: relative;
  border-color: rgba(148, 163, 184, 0.12);
  border-radius: 20px;
  background: linear-gradient(180deg, rgba(252, 254, 255, 0.99), rgba(247, 250, 252, 0.98));
  box-shadow:
    0 10px 26px rgba(15, 23, 42, 0.05),
    inset 0 1px 0 rgba(255, 255, 255, 0.82);
}

.interleaved-message.is-shell-mode .tools-section::after {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  background:
    linear-gradient(rgba(148, 163, 184, 0.018) 1px, transparent 1px),
    linear-gradient(90deg, rgba(148, 163, 184, 0.018) 1px, transparent 1px);
  background-size: 100% 26px, 26px 100%;
  mask-image: linear-gradient(180deg, rgba(255, 255, 255, 0.32), transparent 76%);
}

.tools-section:hover {
  border-color: rgba(100, 116, 139, 0.18);
}

.tools-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px 10px 14px;
  background: linear-gradient(90deg, rgba(240, 245, 251, 0.82), rgba(255, 255, 255, 0.62) 58%, transparent);
  cursor: pointer;
  user-select: none;
  transition: background 0.15s ease;
}

.interleaved-message.is-shell-mode .tools-header {
  position: relative;
  gap: 8px;
  padding: 12px 16px;
  background: linear-gradient(90deg, rgba(241, 245, 249, 0.88), rgba(255, 255, 255, 0.56) 54%, transparent);
}

.tools-header:hover {
  background: linear-gradient(90deg, rgba(236, 242, 249, 0.9), rgba(255, 255, 255, 0.66) 58%, transparent);
}

.interleaved-message.is-shell-mode .tools-header:hover {
  background: linear-gradient(90deg, rgba(236, 242, 249, 0.92), rgba(255, 255, 255, 0.62) 54%, transparent);
}

.tools-icon {
  color: #7086a6;
  flex-shrink: 0;
  transition: color 0.2s ease;
}

.interleaved-message.is-shell-mode .tools-icon {
  color: #64748b;
}

.tools-copy {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.tools-label {
  font-size: 10px;
  font-weight: 700;
  color: #334155;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.interleaved-message.is-shell-mode .tools-label {
  font-size: 11px;
  letter-spacing: 0.08em;
}

.tools-subtitle {
  color: #718195;
  font-size: 11px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.interleaved-message.is-shell-mode .tools-subtitle {
  color: #64748b;
}

.tools-count {
  margin-left: auto;
  font-size: 9px;
  font-weight: 700;
  color: #526173;
  background: rgba(255, 255, 255, 0.8);
  padding: 3px 7px;
  border-radius: 999px;
  border: 1px solid rgba(148, 163, 184, 0.12);
  min-width: 20px;
  text-align: center;
}

.interleaved-message.is-shell-mode .tools-count {
  font-size: 10px;
  color: #475569;
  background: rgba(255, 255, 255, 0.84);
  padding: 4px 8px;
  min-width: 18px;
}

.tools-chevron {
  color: #94a3b8;
  transition: transform 0.2s ease;
  flex-shrink: 0;
}

.interleaved-message.is-shell-mode .tools-chevron {
  margin-left: 0;
}

.tools-chevron.expanded {
  transform: rotate(180deg);
}

.tools-list {
  display: flex;
  flex-direction: column;
  padding: 0 8px 8px;
  background: transparent;
}

.interleaved-message.is-shell-mode .tools-list {
  padding: 0;
}

.tools-list > * {
  margin-top: 8px;
}

.interleaved-message.is-shell-mode .tools-list > * {
  margin-top: 0;
  border-radius: 0;
  border-left: none;
  border-right: none;
  border-bottom: none;
}

/* slide-tools transition */
.slide-tools-enter-active,
.slide-tools-leave-active {
  transition: all 0.2s ease;
  overflow: hidden;
}

.slide-tools-enter-from,
.slide-tools-leave-to {
  opacity: 0;
  max-height: 0;
}

.slide-tools-enter-to,
.slide-tools-leave-from {
  opacity: 1;
  max-height: 2000px;
}

/* 深色主题 */
:root[data-theme="dark"] .message-content {
  color: #e2e8f0;
  background: #0e1422;
  border: 1px solid #152035;
}

:root[data-theme="dark"] .interleaved-message.is-shell-mode .message-content {
  color: #d6dee8;
  background: transparent;
  border: none;
}

:root[data-theme="dark"] .tools-section {
  border-color: rgba(51, 65, 85, 0.56);
  background:
    radial-gradient(circle at top left, rgba(79, 131, 204, 0.06), transparent 20%),
    linear-gradient(180deg, rgba(12, 19, 32, 0.99), rgba(8, 13, 24, 0.99));
}

:root[data-theme="dark"] .interleaved-message.is-shell-mode .tools-section {
  background: linear-gradient(180deg, rgba(12, 19, 32, 0.99), rgba(8, 13, 24, 0.99));
  box-shadow:
    0 18px 40px rgba(2, 6, 23, 0.42),
    inset 0 1px 0 rgba(148, 163, 184, 0.05);
}

:root[data-theme="dark"] .interleaved-message.is-shell-mode .tools-section::after {
  background:
    linear-gradient(rgba(148, 163, 184, 0.016) 1px, transparent 1px),
    linear-gradient(90deg, rgba(148, 163, 184, 0.016) 1px, transparent 1px);
}

:root[data-theme="dark"] .tools-section:hover {
  border-color: rgba(71, 85, 105, 0.76);
}

:root[data-theme="dark"] .tools-header {
  background: linear-gradient(90deg, rgba(20, 31, 50, 0.9), rgba(18, 27, 44, 0.74) 58%, transparent);
}

:root[data-theme="dark"] .interleaved-message.is-shell-mode .tools-header {
  background: linear-gradient(90deg, rgba(15, 23, 42, 0.95), rgba(22, 33, 52, 0.72) 56%, transparent);
}

:root[data-theme="dark"] .tools-header:hover {
  background: linear-gradient(90deg, rgba(24, 39, 62, 0.94), rgba(18, 27, 44, 0.8) 58%, transparent);
}

:root[data-theme="dark"] .interleaved-message.is-shell-mode .tools-header:hover {
  background: linear-gradient(90deg, rgba(18, 28, 45, 0.94), rgba(22, 33, 52, 0.78) 56%, transparent);
}

:root[data-theme="dark"] .tools-icon {
  color: #8ea4c2;
}

:root[data-theme="dark"] .interleaved-message.is-shell-mode .tools-icon,
:root[data-theme="dark"] .interleaved-message.is-shell-mode .tools-label,
:root[data-theme="dark"] .interleaved-message.is-shell-mode .tools-subtitle,
:root[data-theme="dark"] .interleaved-message.is-shell-mode .tools-count {
  color: #bcc7d6;
}

:root[data-theme="dark"] .tools-label {
  color: #d7e3f3;
}

:root[data-theme="dark"] .tools-subtitle {
  color: #8b9db6;
}

:root[data-theme="dark"] .interleaved-message.is-shell-mode .tools-count {
  background: rgba(9, 15, 28, 0.82);
  border-color: rgba(71, 85, 105, 0.3);
}

:root[data-theme="dark"] .tools-count {
  color: #c9d4e4;
  background: rgba(9, 15, 28, 0.82);
  border-color: rgba(71, 85, 105, 0.32);
}

:root[data-theme="dark"] .tools-chevron {
  color: #64748b;
}

:root[data-theme="dark"] .tools-list {
  background: transparent;
}
</style>
