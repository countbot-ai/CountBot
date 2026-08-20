<template>
  <div
    ref="containerRef"
    class="message-list-container"
    @scroll="handleScroll"
  >
    <div class="message-list-wrapper">
      <div v-if="hasMoreHistory" class="history-load-more">
        <button
          class="history-load-more-btn"
          :disabled="isLoadingMore"
          @click="$emit('load-more')"
        >
          {{ isLoadingMore ? ($t('common.loading') || '加载中...') : ($t('chat.loadOlderMessages') || '加载更早消息') }}
        </button>
        <div class="history-load-more-note">
          {{ $t('chat.historyPreviewNotice') || '当前先展示最近消息，历史内容按需继续加载。' }}
        </div>
      </div>
      <MessageItem
        v-for="message in safeMessages"
        :key="message.id"
        :ref="el => setMessageRef(message.id, el)"
        :message="message"
        @regenerate="handleRegenerate"
        @replay-start="handleReplayStart"
        @delete="handleDelete"
      />
      <div ref="bottomAnchorRef" class="message-list-anchor" aria-hidden="true" />
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
import type { ChatMessage } from '@/types/chat'
import MessageItem from './MessageItem.vue'

interface Props {
  messages: ChatMessage[]
  autoScroll?: boolean
  hasMoreHistory?: boolean
  isLoadingMore?: boolean
}

interface Emits {
  (e: 'regenerate', messageId: string): void
  (e: 'replay-start', messageId: string): void
  (e: 'delete', messageId: string): void
  (e: 'load-more'): void
}

const props = withDefaults(defineProps<Props>(), {
  autoScroll: true,
  hasMoreHistory: false,
  isLoadingMore: false,
})

const emit = defineEmits<Emits>()

const containerRef = ref<HTMLElement>()
const bottomAnchorRef = ref<HTMLElement>()
const showScrollButton = ref(false)
const stickToBottom = ref(true)
// 标记程序主动触发的滚动，避免把自动锚点滚动误判成用户手动滚动
let isProgrammaticScroll = false

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
  const atBottom = isAtBottom()
  showScrollButton.value = !atBottom

  // 程序主动滚动时不更新用户滚动状态
  if (isProgrammaticScroll) return

  // 用户离开底部时关闭自动锚点，回到底部时重新启用
  stickToBottom.value = atBottom
}

// 滚动到底部
const scrollToBottom = (smooth = true) => {
  if (!containerRef.value) return

  // 标记为程序触发，避免被 handleScroll 误判为用户滚动
  isProgrammaticScroll = true
  const behavior = smooth ? 'smooth' : 'auto'

  if (bottomAnchorRef.value) {
    bottomAnchorRef.value.scrollIntoView({
      block: 'end',
      behavior,
    })
  } else {
    containerRef.value.scrollTo({
      top: containerRef.value.scrollHeight,
      behavior,
    })
  }

  // 在下一个 event-loop tick 后重置（scroll 事件为同步触发）
  setTimeout(() => { isProgrammaticScroll = false }, 50)

  stickToBottom.value = true
  showScrollButton.value = false
}

// 监听消息数量变化
watch(
  () => props.messages.length,
  async (newLength, oldLength) => {
    if (newLength > oldLength) {
      const shouldAnchorToLatest = props.autoScroll && stickToBottom.value
      await nextTick()
      
      if (shouldAnchorToLatest) {
        scrollToBottom(true)
      }
    }
  }
)

// 监听最后一条消息的任何结构变化（content / reasoning / toolCalls / workflow / spawn）
watch(
  () => props.messages[props.messages.length - 1],
  async (latestMessage, previousMessage) => {
    if (!latestMessage || latestMessage.id !== previousMessage?.id) {
      return
    }

    const shouldAnchorToLatest = props.autoScroll && stickToBottom.value
    await nextTick()

    if (shouldAnchorToLatest) {
      scrollToBottom(false)
    }
  },
  { deep: true }
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
@import './styles/MessageList.css';
</style>
