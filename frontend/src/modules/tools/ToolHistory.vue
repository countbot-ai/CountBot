<template>
  <div class="tool-history-container">
    <!-- Header -->
    <div class="history-header">
      <div class="header-content">
        <component :is="MessageSquareIcon" :size="24" class="header-icon" />
        <div class="header-text">
          <h3 class="history-title">工具调用历史</h3>
          <p class="history-subtitle">查看 AI 与工具的对话记录（持久化存储）</p>
        </div>
      </div>
      <button
        v-if="conversations.length > 0"
        class="clear-btn"
        @click="handleClearConversations"
      >
        <component :is="TrashIcon" :size="16" />
        <span>清空历史</span>
      </button>
    </div>

    <!-- Search Bar -->
    <div
      v-if="conversations.length > 0"
      class="search-bar"
    >
      <div class="search-input-wrapper">
        <component :is="SearchIcon" :size="20" class="search-icon" />
        <input
          ref="searchInputRef"
          v-model="searchQuery"
          type="text"
          class="search-input"
          placeholder="搜索工具名称、参数、结果或会话..."
          @input="handleSearch"
          @keydown.esc="clearSearch"
        />
        <button
          v-if="searchQuery"
          class="clear-search-btn"
          title="清除搜索"
          @click="clearSearch"
        >
          <component :is="XIcon" :size="18" />
        </button>
      </div>
      <div v-if="searchQuery" class="search-results-info">
        <span class="results-count">找到 {{ filteredConversations.length }} 条记录</span>
      </div>
    </div>

    <!-- Stats -->
    <div
      v-if="conversationStats"
      class="stats-container"
    >
      <div class="stats-row">
        <span class="stat-item">
          总计 <strong>{{ conversationStats.total }}</strong>
        </span>
        <span class="stat-divider">|</span>
        <span class="stat-item">
          已加载 <strong>{{ conversations.length }}</strong>
        </span>
        <span class="stat-divider">|</span>
        <span class="stat-item">
          成功率 <strong>{{ conversationStats.success_rate }}%</strong>
        </span>
      </div>
    </div>

    <!-- Scrollable List -->
    <div ref="historyListContainerRef" class="history-list-container">
      <div
        v-if="filteredConversations.length > 0"
        class="history-list"
      >
        <div
          v-for="conv in filteredConversations"
          :key="conv.id"
          class="conversation-card"
          :class="{ 'collapsed': isCollapsed(conv.id) }"
        >
          <div class="conversation-header" @click="toggleCollapse(conv.id)">
            <div class="conversation-title">
              <component 
                :is="isCollapsed(conv.id) ? ChevronRightIcon : ChevronDownIcon" 
                :size="16" 
                class="collapse-icon" 
              />
              <component :is="MessageSquareIcon" :size="16" class="conversation-icon" />
              <span class="tool-name">{{ conv.tool_name }}</span>
              <span v-if="conv.error" class="status-badge error">失败</span>
              <span v-else class="status-badge success">成功</span>
            </div>
            <div class="conversation-meta">
              <span class="timestamp">{{ formatTimestamp(conv.timestamp) }}</span>
              <span v-if="conv.duration_ms" class="duration">{{ conv.duration_ms }}ms</span>
            </div>
          </div>
          
          <div v-show="!isCollapsed(conv.id)" class="conversation-body">
            <div v-if="conv.user_message" class="conversation-section">
              <div class="section-label">用户消息</div>
              <div class="user-message-box">{{ conv.user_message }}</div>
            </div>
            
            <div class="conversation-section">
              <div class="section-label">请求参数</div>
              <pre class="code-block">{{ JSON.stringify(conv.arguments, null, 2) }}</pre>
            </div>
            
            <div v-if="conv.result" class="conversation-section">
              <div class="section-label">执行结果</div>
              <pre class="code-block result">{{ conv.result }}</pre>
            </div>
            
            <div v-if="conv.error" class="conversation-section">
              <div class="section-label">错误信息</div>
              <pre class="code-block error">{{ conv.error }}</pre>
            </div>
          </div>
        </div>
        
        <!-- Loading More Indicator -->
        <div v-if="loadingMore" class="loading-more">
          <component :is="LoaderIcon" :size="20" class="spinner" />
          <span>加载更多...</span>
        </div>
        
        <!-- No More Data -->
        <div v-else-if="!hasMore && conversations.length > 0 && !searchQuery" class="no-more-data">
          <span>已加载全部记录</span>
        </div>
      </div>

      <!-- No Search Results -->
      <div
        v-else-if="searchQuery && filteredConversations.length === 0"
        class="empty-state"
      >
        <div class="empty-icon">
          <component :is="SearchXIcon" :size="64" />
        </div>
        <h3 class="empty-title">未找到匹配的对话记录</h3>
        <p class="empty-description">尝试使用不同的关键词搜索</p>
        <button class="clear-search-link" @click="clearSearch">
          清除搜索
        </button>
      </div>

      <!-- Empty State -->
      <div v-else class="empty-state">
        <div class="empty-icon">
          <component :is="MessageSquareIcon" :size="64" />
        </div>
        <h3 class="empty-title">暂无对话历史</h3>
        <p class="empty-description">AI 与工具的对话记录将显示在这里</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  Trash2 as TrashIcon,
  Search as SearchIcon,
  X as XIcon,
  SearchX as SearchXIcon,
  MessageSquare as MessageSquareIcon,
  ChevronRight as ChevronRightIcon,
  ChevronDown as ChevronDownIcon,
  Loader2 as LoaderIcon
} from 'lucide-vue-next'
import { useToolsStore } from '@/store/tools'
import { useToast } from '@/composables/useToast'
import { toolsAPI } from '@/api/endpoints'

const { t } = useI18n()
const toast = useToast()
const toolsStore = useToolsStore()

// 搜索状态
const searchQuery = ref('')
const searchInputRef = ref<HTMLInputElement | null>(null)

// 对话历史数据
const conversations = ref<any[]>([])
const conversationStats = ref<any>(null)
const loading = ref(false)
const loadingMore = ref(false)
const hasMore = ref(true)

// 分页参数
const pageSize = 10
const currentOffset = ref(0)

// 滚动容器引用
const historyListContainerRef = ref<HTMLElement | null>(null)

// 折叠状态管理
const collapsedItems = ref<Set<string>>(new Set())

// 默认全部折叠
const initializeCollapsedState = () => {
  collapsedItems.value.clear()
  conversations.value.forEach(conv => {
    collapsedItems.value.add(conv.id)
  })
}

// 切换折叠状态
const toggleCollapse = (id: string) => {
  if (collapsedItems.value.has(id)) {
    collapsedItems.value.delete(id)
  } else {
    collapsedItems.value.add(id)
  }
}

// 检查是否折叠
const isCollapsed = (id: string) => {
  return collapsedItems.value.has(id)
}

// 初始加载对话历史
const loadConversations = async (reset = false) => {
  try {
    if (reset) {
      loading.value = true
      conversations.value = []
      currentOffset.value = 0
      hasMore.value = true
    } else {
      loadingMore.value = true
    }
    
    const [convResponse, statsResponse] = await Promise.all([
      toolsAPI.getConversations({ limit: pageSize, offset: currentOffset.value }),
      toolsAPI.getConversationStats()
    ])
    
    if (reset) {
      conversations.value = convResponse.conversations
    } else {
      conversations.value.push(...convResponse.conversations)
    }
    
    conversationStats.value = statsResponse
    
    // 检查是否还有更多数据
    hasMore.value = conversations.value.length < statsResponse.total
    
    // 更新偏移量
    currentOffset.value = conversations.value.length
    
    // 初始化新加载记录的折叠状态（默认全部折叠）
    convResponse.conversations.forEach(conv => {
      collapsedItems.value.add(conv.id)
    })
    
    console.log('[ToolHistory] 加载对话历史:', conversations.value.length, '/', statsResponse.total, '还有更多:', hasMore.value)
  } catch (error) {
    console.error('Failed to load conversations:', error)
    toast.error('加载对话历史失败')
  } finally {
    loading.value = false
    loadingMore.value = false
  }
}

// 滚动加载更多
const handleScroll = async () => {
  if (!historyListContainerRef.value || loadingMore.value || !hasMore.value || searchQuery.value) {
    return
  }
  
  const container = historyListContainerRef.value
  const scrollTop = container.scrollTop
  const scrollHeight = container.scrollHeight
  const clientHeight = container.clientHeight
  
  // 当滚动到距离底部 200px 时加载更多
  if (scrollTop + clientHeight >= scrollHeight - 200) {
    await loadConversations(false)
  }
}

// 组件挂载
onMounted(() => {
  console.log('ToolHistory mounted')
  loadConversations(true)
  
  // 添加滚动监听
  nextTick(() => {
    if (historyListContainerRef.value) {
      historyListContainerRef.value.addEventListener('scroll', handleScroll)
    }
  })
})

// 组件卸载
onUnmounted(() => {
  if (historyListContainerRef.value) {
    historyListContainerRef.value.removeEventListener('scroll', handleScroll)
  }
})

// 过滤对话历史记录
const filteredConversations = computed(() => {
  if (!searchQuery.value.trim()) {
    return conversations.value
  }

  const query = searchQuery.value.toLowerCase()
  
  return conversations.value.filter(conv => {
    // 搜索工具名称
    if (conv.tool_name.toLowerCase().includes(query)) {
      return true
    }
    
    // 搜索会话ID
    if (conv.session_id.toLowerCase().includes(query)) {
      return true
    }
    
    // 搜索参数
    const argsStr = JSON.stringify(conv.arguments).toLowerCase()
    if (argsStr.includes(query)) {
      return true
    }
    
    // 搜索结果
    if (conv.result && conv.result.toLowerCase().includes(query)) {
      return true
    }
    
    // 搜索错误信息
    if (conv.error && conv.error.toLowerCase().includes(query)) {
      return true
    }
    
    return false
  })
})

const handleSearch = () => {
  // 搜索逻辑在 computed 中自动执行
}

const clearSearch = () => {
  searchQuery.value = ''
  searchInputRef.value?.focus()
}

const handleClearConversations = async () => {
  if (confirm('确定要清空所有对话历史吗？')) {
    try {
      await toolsAPI.clearConversations()
      conversations.value = []
      conversationStats.value = { total: 0, by_tool: {}, by_session: {}, success_rate: 0 }
      currentOffset.value = 0
      hasMore.value = false
      toast.success('对话历史已清空')
      searchQuery.value = ''
    } catch (error) {
      console.error('Failed to clear conversations:', error)
      toast.error('清空对话历史失败')
    }
  }
}

const formatTimestamp = (timestamp: string) => {
  const date = new Date(timestamp)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}
</script>

<style scoped>
/* 容器 - 使用固定高度 */
.tool-history-container {
  display: flex;
  flex-direction: column;
  height: 100vh;
  width: 100%;
  background: var(--bg-secondary, #f9fafb);
  overflow: hidden;
}

/* Header */
.history-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 24px;
  border-bottom: 1px solid var(--border-color, #e5e7eb);
  background: var(--bg-primary, #ffffff);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}

/* Conversation Card */
.conversation-card {
  background: var(--bg-primary, #ffffff);
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 12px;
  padding: 16px;
  transition: all 0.2s;
}

.conversation-card.collapsed {
  padding: 12px 16px;
}

.conversation-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  border-color: var(--color-primary);
}

.conversation-header {
  cursor: pointer;
  user-select: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-color, #e5e7eb);
}

.conversation-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.collapse-icon {
  color: var(--text-secondary);
  transition: transform 0.2s;
  flex-shrink: 0;
}

.conversation-icon {
  color: var(--color-primary);
}

.tool-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.status-badge {
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
}

.status-badge.success {
  background: rgba(16, 185, 129, 0.1);
  color: var(--color-success, #10b981);
}

.status-badge.error {
  background: rgba(239, 68, 68, 0.1);
  color: var(--color-error, #ef4444);
}

.conversation-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 13px;
  color: var(--text-tertiary, #9ca3af);
}

.timestamp {
  display: flex;
  align-items: center;
  gap: 4px;
}

.duration {
  padding: 2px 8px;
  background: var(--bg-secondary, #f9fafb);
  border-radius: 4px;
  font-weight: 500;
}

.conversation-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.conversation-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.section-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary, #6b7280);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.code-block {
  padding: 12px;
  background: var(--bg-secondary, #f9fafb);
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 8px;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-primary);
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
}

.code-block.result {
  background: rgba(16, 185, 129, 0.05);
  border-color: rgba(16, 185, 129, 0.2);
}

.code-block.error {
  background: rgba(239, 68, 68, 0.05);
  border-color: rgba(239, 68, 68, 0.2);
  color: var(--color-error, #ef4444);
}

.user-message-box {
  padding: 12px;
  background: rgba(99, 102, 241, 0.05);
  border: 1px solid rgba(99, 102, 241, 0.2);
  border-radius: 8px;
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-primary);
  white-space: pre-wrap;
  word-break: break-word;
}

.header-content {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-icon {
  color: var(--color-primary);
}

.header-text {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.history-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.history-subtitle {
  font-size: 14px;
  color: var(--text-secondary);
  margin: 0;
}

.clear-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 8px;
  background: var(--bg-primary, #ffffff);
  color: var(--text-secondary, #6b7280);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.clear-btn:hover {
  background: var(--hover-bg, #f3f4f6);
  color: var(--color-error);
  border-color: var(--color-error);
}

/* Search Bar */
.search-bar {
  flex-shrink: 0;
  padding: 12px 24px;
  background: var(--bg-secondary, #f9fafb);
  border-bottom: 1px solid var(--border-color, #e5e7eb);
}

.search-input-wrapper {
  position: relative;
  display: flex;
  align-items: center;
  max-width: 600px;
  margin: 0 auto;
}

.search-icon {
  position: absolute;
  left: 1rem;
  color: var(--text-tertiary, #9ca3af);
  pointer-events: none;
}

.search-input {
  width: 100%;
  padding: 0.75rem 3rem;
  border: 2px solid var(--border-color, #e5e7eb);
  border-radius: 8px;
  background: var(--bg-primary, #ffffff);
  color: var(--text-primary);
  font-size: 14px;
  transition: all 0.2s;
}

.search-input:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.1);
}

.clear-search-btn {
  position: absolute;
  right: 0.75rem;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--text-tertiary, #9ca3af);
  cursor: pointer;
  transition: all 0.2s;
}

.clear-search-btn:hover {
  background: var(--hover-bg, #f3f4f6);
  color: var(--text-primary);
}

.search-results-info {
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 8px;
}

.results-count {
  padding: 6px 12px;
  background: rgba(99, 102, 241, 0.1);
  color: var(--color-primary);
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
}

/* Stats - Compact Single Row */
.stats-container {
  flex-shrink: 0;
  padding: 12px 24px;
  background: var(--bg-primary, #ffffff);
  border-bottom: 1px solid var(--border-color, #e5e7eb);
}

.stats-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  flex-wrap: wrap;
  font-size: 14px;
  color: var(--text-secondary, #6b7280);
}

.stats-note {
  margin-top: 8px;
  text-align: center;
  font-size: 13px;
  color: var(--text-tertiary, #9ca3af);
  padding: 6px 12px;
  background: rgba(99, 102, 241, 0.05);
  border-radius: 6px;
}

.stat-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}

.stat-item strong {
  font-weight: 600;
  color: var(--text-primary, #1f2937);
  font-size: 15px;
}

.stat-item.stat-success strong {
  color: var(--color-success, #10b981);
}

.stat-item.stat-error strong {
  color: var(--color-error, #ef4444);
}

.stat-divider {
  color: var(--border-color, #e5e7eb);
  font-weight: 300;
}

/* 滚动列表容器 */
.history-list-container {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 24px;
}

/* 列表 */
.history-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* 滚动条样式 */
.history-list-container::-webkit-scrollbar {
  width: 8px;
}

.history-list-container::-webkit-scrollbar-track {
  background: var(--bg-secondary);
  border-radius: 4px;
}

.history-list-container::-webkit-scrollbar-thumb {
  background: var(--border-color);
  border-radius: 4px;
}

.history-list-container::-webkit-scrollbar-thumb:hover {
  background: var(--text-tertiary);
}

/* 空状态 */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 48px 32px;
  color: var(--text-tertiary);
  text-align: center;
  min-height: 300px;
}

.empty-icon {
  color: var(--text-tertiary);
  opacity: 0.5;
}

.empty-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-secondary);
  margin: 0;
}

.empty-description {
  font-size: 14px;
  color: var(--text-tertiary);
  margin: 0;
}

.clear-search-link {
  padding: 8px 24px;
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 8px;
  background: var(--bg-primary, #ffffff);
  color: var(--color-primary);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.clear-search-link:hover {
  background: var(--color-primary);
  color: #ffffff;
  border-color: var(--color-primary);
}

/* Loading More Indicator */
.loading-more {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 24px;
  color: var(--text-secondary);
  font-size: 14px;
}

.spinner {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

/* No More Data */
.no-more-data {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  color: var(--text-tertiary);
  font-size: 13px;
}

/* 响应式 */
@media (max-width: 640px) {
  .stats-row {
    font-size: 13px;
    gap: 8px;
  }
  
  .stat-item strong {
    font-size: 14px;
  }
  
  .history-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }
  
  .clear-btn {
    width: 100%;
    justify-content: center;
  }
}
</style>
