<template>
  <div class="tool-history">
    <div class="history-header">
      <div class="header-content">
        <component :is="HistoryIcon" :size="20" class="header-icon" />
        <h3 class="history-title">{{ $t('tools.history.title') }}</h3>
      </div>
      <button class="refresh-btn" @click="loadHistory" :disabled="loading">
        <component :is="RefreshCwIcon" :size="16" :class="{ spin: loading }" />
      </button>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading && conversations.length === 0" class="loading-state">
      <component :is="LoaderIcon" :size="24" class="spin" />
      <p>{{ $t('common.loading') }}</p>
    </div>

    <!-- 错误状态 -->
    <div v-else-if="error" class="error-state">
      <component :is="AlertCircleIcon" :size="24" />
      <p>{{ error }}</p>
      <button class="retry-btn" @click="loadHistory">
        {{ $t('common.retry') }}
      </button>
    </div>

    <!-- 空状态 -->
    <div v-else-if="conversations.length === 0" class="empty-state">
      <component :is="InboxIcon" :size="48" />
      <p>{{ $t('tools.history.empty') }}</p>
    </div>

    <!-- 对话列表 -->
    <div v-else class="conversations-list">
      <div
        v-for="conv in conversations"
        :key="conv.id"
        class="conversation-item"
        @click="toggleExpand(conv.id)"
      >
        <div class="conv-header">
          <component :is="WrenchIcon" :size="16" class="tool-icon" />
          <span class="tool-name">{{ conv.tool_name }}</span>
          <span class="tool-time">{{ formatTime(conv.timestamp) }}</span>
          <component
            :is="ChevronRightIcon"
            :size="14"
            class="chevron"
            :class="{ expanded: expandedIds.has(conv.id) }"
          />
        </div>

        <transition name="slide">
          <div v-show="expandedIds.has(conv.id)" class="conv-details">
            <!-- 参数 -->
            <div v-if="conv.arguments" class="detail-section">
              <div class="detail-label">{{ $t('tools.history.arguments') }}</div>
              <pre class="detail-content">{{ formatJson(conv.arguments) }}</pre>
            </div>

            <!-- 结果 -->
            <div v-if="conv.result" class="detail-section">
              <div class="detail-label">{{ $t('tools.history.result') }}</div>
              <pre class="detail-content">{{ truncate(conv.result, 500) }}</pre>
            </div>

            <!-- 错误 -->
            <div v-if="conv.error" class="detail-section error">
              <div class="detail-label">{{ $t('tools.history.error') }}</div>
              <pre class="detail-content">{{ conv.error }}</pre>
            </div>

            <!-- 元信息 -->
            <div class="detail-meta">
              <span v-if="conv.duration_ms">
                {{ $t('tools.history.duration') }}: {{ conv.duration_ms }}ms
              </span>
              <span v-if="conv.session_id">
                {{ $t('tools.history.session') }}: {{ conv.session_id.slice(0, 8) }}...
              </span>
            </div>
          </div>
        </transition>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  History as HistoryIcon,
  RefreshCw as RefreshCwIcon,
  Loader2 as LoaderIcon,
  AlertCircle as AlertCircleIcon,
  Inbox as InboxIcon,
  Wrench as WrenchIcon,
  ChevronRight as ChevronRightIcon,
} from 'lucide-vue-next'
import { toolsAPI } from '@/api/endpoints'

const { t } = useI18n()

interface ToolConversation {
  id: string
  session_id: string
  timestamp: string
  tool_name: string
  arguments: any
  result?: string
  error?: string
  duration_ms?: number
}

const conversations = ref<ToolConversation[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const expandedIds = ref(new Set<string>())

const loadHistory = async () => {
  loading.value = true
  error.value = null

  try {
    const response = await toolsAPI.getConversations() as { conversations: ToolConversation[] }
    conversations.value = response.conversations || []
  } catch (err: any) {
    console.error('Failed to load tool history:', err)
    error.value = err.message || t('tools.history.loadError')
  } finally {
    loading.value = false
  }
}

const toggleExpand = (id: string) => {
  if (expandedIds.value.has(id)) {
    expandedIds.value.delete(id)
  } else {
    expandedIds.value.add(id)
  }
}

const formatTime = (timestamp: string) => {
  const date = new Date(timestamp)
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

const formatJson = (obj: any) => {
  try {
    if (typeof obj === 'string') {
      obj = JSON.parse(obj)
    }
    return JSON.stringify(obj, null, 2)
  } catch {
    return String(obj)
  }
}

const truncate = (text: string, maxLength: number) => {
  if (!text) return ''
  if (text.length <= maxLength) return text
  return text.slice(0, maxLength) + '...'
}

onMounted(() => {
  loadHistory()
})
</script>
<style scoped>
@import './styles/ToolHistory.css';
</style>
