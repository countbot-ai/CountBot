<template>
  <div
    class="message"
    :class="`message-${message.role}`"
  >
    <div class="message-avatar">
      <component
        :is="avatarIcon"
        :size="16"
      />
    </div>
    <div class="message-body">
      <!-- 推理内容显示（思考模型） -->
      <ReasoningBlock
        v-if="message.reasoningContent && message.role === 'assistant'"
        :content="message.reasoningContent"
        :is-thinking="false"
        :default-expanded="false"
      />
      
      <!-- 工具调用显示 -->
      <!-- 工具调用 Task List 样式 -->
      <div
        v-if="message.toolCalls && message.toolCalls.length > 0 && (!isReplaying || replayToolIndex > 0)"
        class="tool-calls-container"
      >
        <div class="tool-calls-header" @click="toggleToolCalls">
          <component :is="WrenchIcon" :size="14" class="tool-calls-icon" />
          <span class="tool-calls-title">{{ $t('tools.toolCalls') || 'Tool Calls' }}</span>
          <span class="tool-calls-count">{{ visibleToolCalls.length }}</span>
          <component :is="ChevronDownIcon" :size="14" class="tool-calls-chevron" :class="{ expanded: toolCallsExpanded }" />
        </div>
        <transition name="slide-list">
          <div v-show="toolCallsExpanded" class="tool-calls-list">
            <ToolCallCard
              v-for="(toolCall, index) in visibleToolCalls"
              :key="toolCall.id || index"
              :tool-name="toolCall.name"
              :arguments="toolCall.arguments"
              :status="toolCall.status || 'success'"
              :result="toolCall.result"
              :error="toolCall.error"
              :duration="toolCall.duration"
              :timestamp="message.timestamp"
              :default-collapsed="true"
            />
          </div>
        </transition>
      </div>

      <!-- 思考中状态 -->
      <div v-if="message.isThinking" class="message-content thinking-indicator">
        <span class="thinking-dots">
          <span class="dot" />
          <span class="dot" />
          <span class="dot" />
        </span>
      </div>

      <!-- 消息内容 -->
      <!-- eslint-disable-next-line vue/no-v-html -->
      <div 
        v-else-if="message.role === 'assistant' && message.content && (!isReplaying || replayContent !== null)"
        class="message-content markdown-content"
        :class="{ 'typewriter-active': isReplaying }"
        v-html="replayContent !== null ? replayContent : renderedContent"
      />
      <div 
        v-else-if="message.role !== 'assistant' && message.content"
        class="message-content user-message-content"
      >
        {{ message.content }}
      </div>
      <div class="message-footer">
        <div class="message-time">
          {{ formattedTime }}
        </div>
        <div
          class="message-actions"
        >
          <button
            v-if="message.role === 'assistant'"
            class="action-btn"
            :title="$t('chat.replay') || '重放'"
            @click="handleReplay"
          >
            <component
              :is="isReplaying ? SquareIcon : PlayIcon"
              :size="14"
            />
          </button>
          <button
            v-if="message.role === 'assistant'"
            class="action-btn"
            :title="$t('chat.regenerate')"
            @click="handleRegenerate"
          >
            <component
              :is="RefreshIcon"
              :size="14"
            />
          </button>
          <button
            v-if="message.role === 'assistant'"
            class="action-btn"
            :title="$t('chat.copy')"
            @click="handleCopy"
          >
            <component
              :is="copied ? CheckIcon : CopyIcon"
              :size="14"
            />
          </button>
          <button
            class="action-btn action-btn-delete"
            :title="$t('chat.deleteMessage') || '删除消息'"
            @click="handleDelete"
          >
            <component
              :is="TrashIcon"
              :size="14"
            />
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onBeforeUnmount } from 'vue'
import {
  User as UserIcon,
  Bot as BotIcon,
  RefreshCw as RefreshIcon,
  Copy as CopyIcon,
  Check as CheckIcon,
  Wrench as WrenchIcon,
  ChevronDown as ChevronDownIcon,
  Play as PlayIcon,
  Square as SquareIcon,
  Trash2 as TrashIcon
} from 'lucide-vue-next'
import { useMarkdown } from '@/composables/useMarkdown'
import { useI18n } from 'vue-i18n'
import { useToast } from '@/composables/useToast'
import ToolCallCard from '@/components/chat/ToolCallCard.vue'
import ReasoningBlock from '@/components/chat/ReasoningBlock.vue'

interface ToolCall {
  id: string
  name: string
  arguments?: any
  result?: string
  status?: 'pending' | 'running' | 'success' | 'error'
  duration?: number
}

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  toolCalls?: ToolCall[]
  reasoningContent?: string
  isThinking?: boolean
}

interface Props {
  message: Message
}

interface Emits {
  (e: 'regenerate', messageId: string): void
  (e: 'replay-start', messageId: string): void
  (e: 'delete', messageId: string): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const { renderMarkdown } = useMarkdown()
const { locale, t } = useI18n()
const toast = useToast()

const copied = ref(false)
const toolCallsExpanded = ref(true)
const isReplaying = ref(false)
const replayContent = ref<string | null>(null)
const replayToolIndex = ref(0)
let replayTimer: number | null = null

const toggleToolCalls = () => {
  toolCallsExpanded.value = !toolCallsExpanded.value
}

const avatarIcon = computed(() => (props.message.role === 'user' ? UserIcon : BotIcon))

const renderedContent = computed(() => {
  if (props.message.role === 'assistant') {
    return renderMarkdown(props.message.content)
  }
  return props.message.content
})

const visibleToolCalls = computed(() => {
  const all = props.message.toolCalls || []
  if (!isReplaying.value) return all
  return all.slice(0, replayToolIndex.value)
})

import { formatTime } from '@/utils/time'

const formattedTime = computed(() => {
  return formatTime(props.message.timestamp)
})

const handleRegenerate = () => {
  emit('regenerate', props.message.id)
}

const handleDelete = () => {
  if (confirm(t('chat.confirmDeleteMessage') || '确定要删除这条消息吗？')) {
    emit('delete', props.message.id)
  }
}

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

const handleReplay = () => {
  if (isReplaying.value) {
    stopReplay()
    return
  }
  
  const hasContent = props.message.content
  const hasToolCalls = props.message.toolCalls && props.message.toolCalls.length > 0
  if (!hasContent && !hasToolCalls) return
  
  // 先清空所有内容（blank slate）
  isReplaying.value = true
  replayContent.value = null  // null = 隐藏文字区域
  replayToolIndex.value = 0   // 0 = 隐藏所有工具调用
  toolCallsExpanded.value = true
  
  // 通知父组件滚动到此消息
  emit('replay-start', props.message.id)
  
  // 延迟后开始重放，让用户看到清空效果
  replayTimer = window.setTimeout(() => {
    if (hasToolCalls) {
      showToolCallsSequentially()
    } else {
      startTextReplay()
    }
  }, 300)
}

const showToolCallsSequentially = () => {
  if (!isReplaying.value) return
  
  const toolCalls = props.message.toolCalls || []
  if (replayToolIndex.value < toolCalls.length) {
    replayToolIndex.value++
    replayTimer = window.setTimeout(showToolCallsSequentially, 400)
  } else {
    // 工具调用全部展示完毕，进入文字阶段
    if (props.message.content) {
      replayTimer = window.setTimeout(startTextReplay, 300)
    } else {
      stopReplay()
    }
  }
}

const startTextReplay = () => {
  if (!isReplaying.value || !props.message.content) return
  
  // 设置为空字符串，使内容区域可见（null = 隐藏）
  replayContent.value = ''
  const rawText = props.message.content
  let charIndex = 0
  const speed = 15
  
  const tick = () => {
    if (!isReplaying.value) return
    
    const step = Math.min(3, rawText.length - charIndex)
    charIndex += step
    
    const partial = rawText.slice(0, charIndex)
    replayContent.value = renderMarkdown(partial)
    
    if (charIndex >= rawText.length) {
      stopReplay()
      return
    }
    
    replayTimer = window.setTimeout(tick, speed)
  }
  
  replayTimer = window.setTimeout(tick, speed)
}

const stopReplay = () => {
  isReplaying.value = false
  replayContent.value = null
  replayToolIndex.value = 0
  if (replayTimer) {
    clearTimeout(replayTimer)
    replayTimer = null
  }
}

const formatArgs = (args: any) => {
  if (typeof args === 'string') {
    try {
      return JSON.stringify(JSON.parse(args), null, 2)
    } catch {
      return args
    }
  }
  return JSON.stringify(args, null, 2)
}

// Global function for code block copy buttons
const setupCodeCopyHandler = () => {
  (window as any).copyCode = async (button: HTMLButtonElement, code: string) => {
    try {
      // Decode HTML entities
      const decodedCode = code
        .replace(/&quot;/g, '"')
        .replace(/&#39;/g, "'")
        .replace(/&lt;/g, '<')
        .replace(/&gt;/g, '>')
        .replace(/&amp;/g, '&')
      
      await navigator.clipboard.writeText(decodedCode)
      
      // Visual feedback
      const originalHTML = button.innerHTML
      button.innerHTML = `
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="20 6 9 17 4 12"></polyline>
        </svg>
      `
      button.classList.add('copied')
      
      setTimeout(() => {
        button.innerHTML = originalHTML
        button.classList.remove('copied')
      }, 2000)
    } catch (error) {
      console.error('Failed to copy code:', error)
    }
  }
}

onMounted(() => {
  setupCodeCopyHandler()
})

onBeforeUnmount(() => {
  delete (window as any).copyCode
  stopReplay()
})
</script>

<style scoped>
.message {
  display: flex;
  gap: var(--spacing-md);
}

.message-avatar {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-full);
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  transition: all 0.2s ease;
}

.message-assistant .message-avatar {
  background: #f1f5f9;
  color: #64748b;
  border: 1px solid #e2e8f0;
}

.message-user .message-avatar {
  background: #64748b;
  color: #ffffff;
}

.message-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

/* ===== Task List 样式 ===== */
.tool-calls-container {
  margin-bottom: var(--spacing-sm);
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 8px;
  overflow: hidden;
  background: var(--bg-primary, #ffffff);
}

.tool-calls-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--bg-secondary, #f8fafc);
  cursor: pointer;
  user-select: none;
  transition: background 0.1s ease;
}
.tool-calls-header:hover {
  background: var(--hover-bg, #f1f5f9);
}

.tool-calls-icon {
  color: var(--text-tertiary, #94a3b8);
}

.tool-calls-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary, #475569);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.tool-calls-count {
  font-size: 11px;
  font-weight: 500;
  color: var(--text-tertiary, #94a3b8);
  background: var(--bg-tertiary, #f1f5f9);
  padding: 1px 6px;
  border-radius: 10px;
  min-width: 18px;
  text-align: center;
}

.tool-calls-chevron {
  margin-left: auto;
  color: var(--text-tertiary, #94a3b8);
  transition: transform 0.15s ease;
}
.tool-calls-chevron.expanded {
  transform: rotate(180deg);
}

.tool-calls-list {
  display: flex;
  flex-direction: column;
}
.tool-calls-list > * {
  border-radius: 0;
  border-left: none;
  border-right: none;
  border-bottom: none;
}
.tool-calls-list > *:last-child {
  border-bottom: none;
}

/* slide-list transition */
.slide-list-enter-active,
.slide-list-leave-active {
  transition: all 0.2s ease;
  overflow: hidden;
}
.slide-list-enter-from,
.slide-list-leave-to {
  opacity: 0;
  max-height: 0;
}
.slide-list-enter-to,
.slide-list-leave-from {
  opacity: 1;
  max-height: 2000px;
}

.message-content {
  padding: 12px 16px;
  background: transparent;
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 14px;
  line-height: 1.6;
  word-wrap: break-word;
  overflow-wrap: break-word;
  word-break: break-word;
  max-width: 100%;
  overflow-x: auto;
}

.message-assistant .message-content {
  background: #f8fafc;
  border: 1px solid #f1f5f9;
}

.message-user .message-content {
  background: #ffffff;
  border: 1px solid #e2e8f0;
}

.user-message-content {
  white-space: pre-wrap;
}

.message-time {
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
  padding: 0 var(--spacing-xs);
}

.message-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-sm);
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

/* Markdown content styles */
.markdown-content {
  overflow: hidden;
  max-width: 100%;
}

.markdown-content * {
  max-width: 100%;
}

/* Code block wrapper */
.markdown-content :deep(.code-block-wrapper) {
  margin: var(--spacing-md) 0;
  border-radius: var(--radius-md);
  overflow: hidden;
  background: var(--bg-tertiary);
}

.markdown-content :deep(.code-block-header) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-sm) var(--spacing-md);
  background: rgba(0, 0, 0, 0.1);
  border-bottom: 1px solid var(--border-color);
}

.markdown-content :deep(.code-block-language) {
  font-size: var(--font-size-xs);
  font-family: var(--font-mono);
  color: var(--text-secondary);
  text-transform: uppercase;
  font-weight: var(--font-weight-medium);
}

.markdown-content :deep(.code-copy-btn) {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 4px 8px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-tertiary);
  cursor: pointer;
  transition: all var(--transition-base);
  font-size: var(--font-size-xs);
}

.markdown-content :deep(.code-copy-btn:hover) {
  background: rgba(0, 0, 0, 0.1);
  color: var(--text-primary);
}

.markdown-content :deep(.code-copy-btn.copied) {
  color: var(--color-success);
}

.markdown-content :deep(.code-block-wrapper pre) {
  margin: 0;
  border-radius: 0;
}

.markdown-content :deep(h1),
.markdown-content :deep(h2),
.markdown-content :deep(h3),
.markdown-content :deep(h4),
.markdown-content :deep(h5),
.markdown-content :deep(h6) {
  margin: var(--spacing-md) 0 var(--spacing-sm) 0;
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.markdown-content :deep(h1) { font-size: var(--font-size-2xl); }
.markdown-content :deep(h2) { font-size: var(--font-size-xl); }
.markdown-content :deep(h3) { font-size: var(--font-size-lg); }

.markdown-content :deep(p) {
  margin: var(--spacing-sm) 0;
}

.markdown-content :deep(p:first-child) {
  margin-top: 0;
}

.markdown-content :deep(p:last-child) {
  margin-bottom: 0;
}

.markdown-content :deep(ul),
.markdown-content :deep(ol) {
  margin: var(--spacing-sm) 0;
  padding-left: var(--spacing-xl);
}

.markdown-content :deep(li) {
  margin: var(--spacing-xs) 0;
}

.markdown-content :deep(a) {
  color: var(--color-primary);
  text-decoration: underline;
}

.markdown-content :deep(a:hover) {
  opacity: 0.8;
}

.markdown-content :deep(blockquote) {
  margin: var(--spacing-md) 0;
  padding-left: var(--spacing-md);
  border-left: 3px solid var(--border-color);
  color: var(--text-secondary);
  font-style: italic;
}

.markdown-content :deep(code.inline-code) {
  padding: 2px 6px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-sm);
  font-family: var(--font-mono);
  font-size: 0.9em;
  color: var(--text-primary);
}

.markdown-content :deep(pre) {
  margin: var(--spacing-md) 0;
  padding: var(--spacing-md);
  background: var(--bg-tertiary);
  border-radius: var(--radius-md);
  overflow-x: auto;
  white-space: pre-wrap;
  word-wrap: break-word;
  word-break: break-word;
}

.markdown-content :deep(pre code) {
  font-family: var(--font-mono);
  font-size: var(--font-size-sm);
  line-height: 1.5;
  color: var(--text-primary);
  white-space: pre-wrap;
  word-wrap: break-word;
  word-break: break-word;
  tab-size: 4;
  -moz-tab-size: 4;
}

.markdown-content :deep(table) {
  width: 100%;
  margin: var(--spacing-md) 0;
  border-collapse: collapse;
}

.markdown-content :deep(th),
.markdown-content :deep(td) {
  padding: var(--spacing-sm);
  border: 1px solid var(--border-color);
  text-align: left;
}

.markdown-content :deep(th) {
  background: var(--bg-secondary);
  font-weight: var(--font-weight-semibold);
}

.markdown-content :deep(hr) {
  margin: var(--spacing-lg) 0;
  border: none;
  border-top: 1px solid var(--border-color);
}

.markdown-content :deep(img) {
  max-width: 100%;
  height: auto;
  border-radius: var(--radius-md);
  margin: var(--spacing-md) 0;
}

/* Syntax highlighting styles */
.markdown-content :deep(.hljs) {
  background: transparent;
  padding: 0;
}

/* ===== 深色主题适配 - 赛博朋克 ===== */
[data-theme='dark'] .message-assistant .message-avatar {
  background: #0e1422;
  color: #00f0ff;
  border: 1px solid #152035;
}

[data-theme='dark'] .message-user .message-avatar {
  background: #131b2c;
  color: #d0e8f0;
}

[data-theme='dark'] .message-assistant .message-content {
  background: #0e1422;
  border: 1px solid #152035;
}

[data-theme='dark'] .message-user .message-content {
  background: #0a0e1a;
  border: 1px solid #152035;
  color: #d0e8f0;
}

/* Responsive */
@media (max-width: 768px) {
  .message {
    gap: var(--spacing-sm);
  }

  .message-avatar {
    width: 32px;
    height: 32px;
  }
}

/* 工具调用样式 */

/* 思考中指示器 */
.thinking-indicator {
  display: flex;
  align-items: center;
  min-height: 40px;
}

.thinking-dots {
  display: flex;
  gap: 4px;
  align-items: center;
}

.thinking-dots .dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-tertiary, #94a3b8);
  animation: thinking-bounce 1.4s ease-in-out infinite;
}

.thinking-dots .dot:nth-child(2) {
  animation-delay: 0.16s;
}

.thinking-dots .dot:nth-child(3) {
  animation-delay: 0.32s;
}

@keyframes thinking-bounce {
  0%, 80%, 100% {
    transform: scale(0.6);
    opacity: 0.4;
  }
  40% {
    transform: scale(1);
    opacity: 1;
  }
}

/* 打字机光标 */
.typewriter-active :deep(*:last-child)::after {
  content: '|';
  animation: blink-cursor 0.7s step-end infinite;
  color: var(--text-tertiary, #94a3b8);
  font-weight: 100;
}

@keyframes blink-cursor {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}
</style>
