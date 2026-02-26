<template>
  <div
    ref="containerRef"
    class="message-list-container"
    @scroll="handleScroll"
  >
    <div class="message-list-wrapper">
      <MessageItem
        v-for="message in safeMessages"
        :key="message.id"
        :ref="el => setMessageRef(message.id, el)"
        :message="message"
        @regenerate="handleRegenerate"
        @replay-start="handleReplayStart"
        @delete="handleDelete"
      />
    </div>
    
    <!-- 滚动到底部按钮 -->
    <transition name="fade">
      <button
        v-if="showScrollButton"
        class="scroll-to-bottom"
        :title="$t('chat.scrollToBottom')"
        @click="scrollToBottom(true)"
      >
        <component
          :is="ChevronDownIcon"
          :size="20"
        />
      </button>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import { ChevronDown as ChevronDownIcon } from 'lucide-vue-next'
import MessageItem from './MessageItem.vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
}

interface Props {
  messages: Message[]
  autoScroll?: boolean
}

interface Emits {
  (e: 'regenerate', messageId: string): void
  (e: 'replay-start', messageId: string): void
  (e: 'delete', messageId: string): void
}

const props = withDefaults(defineProps<Props>(), {
  autoScroll: true
})

const emit = defineEmits<Emits>()

const containerRef = ref<HTMLElement>()
const showScrollButton = ref(false)
const isUserScrolling = ref(false)
const scrollTimeout = ref<number>()

// 使用 computed 确保响应式
const safeMessages = computed(() => {
  const msgs = props.messages
  if (!Array.isArray(msgs)) {
    console.error('[MessageList] messages is not an array:', msgs)
    return []
  }
  return msgs
})

// 检测用户是否在底部
const isAtBottom = () => {
  if (!containerRef.value) return true
  const { scrollTop, scrollHeight, clientHeight } = containerRef.value
  return scrollHeight - scrollTop - clientHeight < 100
}

// 处理滚动事件
const handleScroll = () => {
  showScrollButton.value = !isAtBottom()
  
  // 标记用户正在滚动
  isUserScrolling.value = true
  
  // 清除之前的定时器
  if (scrollTimeout.value) {
    clearTimeout(scrollTimeout.value)
  }
  
  // 1秒后认为用户停止滚动
  scrollTimeout.value = window.setTimeout(() => {
    isUserScrolling.value = false
  }, 1000)
}

// 滚动到底部
const scrollToBottom = (smooth = true) => {
  if (!containerRef.value) return
  
  containerRef.value.scrollTo({
    top: containerRef.value.scrollHeight,
    behavior: smooth ? 'smooth' : 'auto'
  })
  
  showScrollButton.value = false
}

// 监听消息数量变化
watch(
  () => props.messages.length,
  async (newLength, oldLength) => {
    if (newLength > oldLength) {
      await nextTick()
      
      // 只有在用户没有手动滚动且开启自动滚动时才滚动到底部
      if (props.autoScroll && !isUserScrolling.value) {
        scrollToBottom(true)
      }
    }
  }
)

// 监听最后一条消息的内容变化（流式更新）
watch(
  () => props.messages[props.messages.length - 1]?.content,
  async () => {
    await nextTick()
    
    // 流式更新时，如果用户在底部则保持在底部
    if (props.autoScroll && isAtBottom() && !isUserScrolling.value) {
      scrollToBottom(false) // 不使用平滑滚动，避免卡顿
    }
  }
)

// Handle regenerate event
const handleRegenerate = (messageId: string) => {
  emit('regenerate', messageId)
}

// Handle delete event
const handleDelete = (messageId: string) => {
  emit('delete', messageId)
}

// Handle replay-start event - scroll message to top of viewport
const handleReplayStart = (messageId: string) => {
  emit('replay-start', messageId)
  scrollToMessage(messageId)
}

// 消息元素引用映射
const messageRefs = new Map<string, any>()

const setMessageRef = (id: string, el: any) => {
  if (el) {
    messageRefs.set(id, el)
  } else {
    messageRefs.delete(id)
  }
}

// 滚动到指定消息（定位到视口顶部）
const scrollToMessage = (messageId: string) => {
  nextTick(() => {
    const ref = messageRefs.get(messageId)
    if (!ref?.$el || !containerRef.value) return
    
    const el = ref.$el as HTMLElement
    const containerRect = containerRef.value.getBoundingClientRect()
    const elRect = el.getBoundingClientRect()
    const offset = elRect.top - containerRect.top + containerRef.value.scrollTop
    
    containerRef.value.scrollTo({
      top: offset - 16,  // 留 16px 上边距
      behavior: 'smooth'
    })
  })
}

onMounted(() => {
  scrollToBottom(false)
})

// Expose methods for parent component
defineExpose({
  scrollToBottom,
  scrollToMessage,
  isAtBottom
})
</script>

<style scoped>
.message-list-container {
  position: relative;
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: var(--spacing-xl);
  background: var(--bg-secondary, #f9fafb);
  /* 使用 GPU 加速 */
  transform: translateZ(0);
  will-change: scroll-position;
}

.message-list-wrapper {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
  max-width: 800px;
  margin: 0 auto;
  width: 100%;
  /* 最小高度确保内容不足时也能滚动 */
  min-height: 100%;
  padding-bottom: var(--spacing-xl);
}

/* 滚动到底部按钮 */
.scroll-to-bottom {
  position: absolute;
  bottom: var(--spacing-xl);
  right: var(--spacing-xl);
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: var(--radius-full);
  background: var(--bg-primary);
  color: var(--text-primary);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  cursor: pointer;
  transition: all var(--transition-base);
  z-index: 10;
}

.scroll-to-bottom:hover {
  background: var(--color-primary);
  color: #ffffff;
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.2);
}

.scroll-to-bottom:active {
  transform: translateY(0);
}

/* 淡入淡出动画 */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease, transform 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: translateY(10px);
}

/* 平滑滚动 */
.message-list-container {
  scroll-behavior: smooth;
}

/* 优化的滚动条样式 */
.message-list-container::-webkit-scrollbar {
  width: 6px;
}

.message-list-container::-webkit-scrollbar-track {
  background: transparent;
  margin: var(--spacing-md) 0;
}

.message-list-container::-webkit-scrollbar-thumb {
  background: var(--border-color, #e5e7eb);
  border-radius: 3px;
  transition: background var(--transition-base);
}

.message-list-container::-webkit-scrollbar-thumb:hover {
  background: var(--text-tertiary, #9ca3af);
}

/* 深色模式 */
:root[data-theme="dark"] .message-list-container {
  background: var(--bg-secondary, #111827);
}

:root[data-theme="dark"] .scroll-to-bottom {
  background: var(--bg-tertiary);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}

:root[data-theme="dark"] .message-list-container::-webkit-scrollbar-thumb {
  background: var(--border-color, #374151);
}

:root[data-theme="dark"] .message-list-container::-webkit-scrollbar-thumb:hover {
  background: var(--text-tertiary, #6b7280);
}

/* 移动端优化 */
@media (max-width: 768px) {
  .message-list-container {
    padding: var(--spacing-md);
  }
  
  .message-list-wrapper {
    gap: var(--spacing-md);
    padding-bottom: var(--spacing-md);
  }
  
  .scroll-to-bottom {
    bottom: var(--spacing-md);
    right: var(--spacing-md);
    width: 40px;
    height: 40px;
  }
}
</style>
