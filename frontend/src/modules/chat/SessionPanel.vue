<template>
  <div class="session-panel">
    <div class="panel-shell">
      <div class="panel-header">
        <div class="panel-header-copy">
          <div class="panel-kicker">{{ $t('sessions.title') }}</div>
          <div class="panel-title-row">
            <h2 class="panel-title">
              {{ $t('sessions.panelTitle') }}
            </h2>
            <span class="panel-counter">{{ displayedSessionCount }}</span>
          </div>
        </div>
        <button
          class="icon-btn"
          :title="$t('sessions.newSession')"
          :disabled="chatStore.isCreatingSession"
          @click="handleCreateSession"
        >
          <component
            :is="PlusIcon"
            :size="20"
          />
        </button>
      </div>

      <div class="panel-body">
        <div class="session-guide">
          <div class="session-guide-backdrop" />

          <div class="session-guide-topline">
            <div class="session-guide-icon">
              <component :is="SparklesIcon" :size="20" />
            </div>
            <div class="session-guide-badge">{{ $t('sessions.customConfigBadge') }}</div>
          </div>

          <div class="session-guide-content">
            <div class="session-guide-copy">
              <h3 class="session-guide-title">{{ $t('sessions.customConfigTitle') }}</h3>
              <p class="session-guide-description">
                {{ $t('sessions.customConfigDescription') }}
              </p>
            </div>

            <div class="session-guide-meta">
              <div
                class="session-guide-meta-card"
                :title="currentSessionChipTitle"
              >
                <span class="session-guide-meta-label">{{ $t('sessions.currentSessionMetaLabel') }}</span>
                <span class="session-guide-meta-value">
                  {{ hasCurrentSession ? currentSessionName : $t('sessions.noActiveSession') }}
                </span>
              </div>
              <div
                v-if="hasCurrentSession"
                class="session-guide-meta-card session-guide-meta-card-secondary"
                :class="{ 'is-empty': !currentSessionChannelMetaValue }"
                :title="currentSessionChannelMetaLabel"
              >
                <span class="session-guide-meta-label">{{ $t('sessions.channelChatIdMetaLabel') }}</span>
                <span class="session-guide-meta-value">
                  {{ currentSessionChannelMetaValue || $t('sessions.channelChatIdNotConfigured') }}
                </span>
              </div>
            </div>
          </div>

          <div class="session-guide-actions">
            <button
              class="session-guide-btn"
              :disabled="!hasCurrentSession"
              @click="handleOpenCurrentConfig"
            >
              <component :is="SettingsIcon" :size="16" />
              <span>
                {{ hasCurrentSession ? $t('sessions.openCurrentConfig') : $t('sessions.selectSessionFirst') }}
              </span>
            </button>
          </div>
        </div>

        <div class="session-search">
          <label
            class="session-search-box"
            :class="{ 'is-active': isSearchMode, 'is-loading': isSearchingSessions }"
          >
            <component :is="SearchIcon" :size="16" class="session-search-icon" />
            <input
              v-model="searchQuery"
              class="session-search-input"
              type="search"
              :placeholder="$t('sessions.searchPlaceholder')"
              @input="handleSearchInput"
            >
            <component
              v-if="isSearchingSessions"
              :is="Loader2Icon"
              :size="16"
              class="session-search-spinner"
            />
            <button
              v-else-if="searchQuery"
              class="session-search-clear"
              type="button"
              :title="$t('sessions.clearSearch')"
              @click.stop="clearSessionSearch"
            >
              <component :is="ClearIcon" :size="14" />
            </button>
          </label>

          <p class="session-search-meta">
            {{
              isSearchMode
                ? $t('sessions.searchActiveLabel', { count: displayedSessionCount })
                : $t('sessions.searchHint')
            }}
          </p>
        </div>

        <LoadingState
          v-if="chatStore.isLoadingSessions"
          type="skeleton"
          :lines="5"
        />

        <div
          v-else-if="isSearchMode && !isSearchingSessions && displayedSessions.length === 0"
          class="panel-state"
        >
          <EmptyState
            icon="message-square"
            :title="$t('sessions.searchEmpty')"
            :description="sessionSearchError || $t('sessions.searchEmptyDescription')"
            :action="$t('sessions.clearSearch')"
            @action="clearSessionSearch"
          />
        </div>

        <div
          v-else-if="chatStore.sessions.length === 0"
          class="panel-state"
        >
          <EmptyState
            icon="message-square"
            :title="$t('sessions.empty')"
            :description="$t('sessions.emptyDescription')"
            :action="$t('sessions.createFirst')"
            @action="handleCreateSession"
          />
        </div>

        <div
          v-else
          class="session-list"
        >
          <div
            v-for="session in displayedSessions"
            :key="session.id"
            class="session-item"
            :class="{ active: session.id === chatStore.currentSessionId }"
            @click="handleSwitchSession(session.id)"
          >
            <div class="session-accent" />

            <div
              v-if="editingSessionId !== session.id"
              class="session-info"
            >
              <div class="session-title-row">
                <div class="session-name">
                  {{ session.name }}
                </div>
                <div class="session-status-group">
                  <span
                    v-if="session.id === chatStore.currentSessionId"
                    class="session-badge is-active"
                  >
                    {{ $t('sessions.activeBadge') }}
                  </span>
                  <span class="session-badge">
                    {{ formatDate(session.updatedAt || session.createdAt) }}
                  </span>
                </div>
              </div>

              <div class="session-subline">
                <span class="session-date">
                  {{ session.id }}
                </span>
                <span
                  v-if="isSearchMode && session.messageCount"
                  class="session-meta-chip"
                >
                  {{ $t('sessions.messageCount', { count: session.messageCount }) }}
                </span>
              </div>

              <div
                v-if="isSearchMode && (session.summary || session.preview || firstSearchSnippet(session))"
                class="session-search-result"
              >
                <p
                  v-if="session.summary"
                  class="session-search-summary"
                >
                  {{ session.summary }}
                </p>
                <p
                  v-else-if="session.preview"
                  class="session-search-summary"
                >
                  {{ session.preview }}
                </p>

                <p
                  v-if="firstSearchSnippet(session)"
                  class="session-search-snippet"
                >
                  {{ formatSearchSnippet(firstSearchSnippet(session)) }}
                </p>
              </div>
            </div>

            <input
              v-else
              ref="editInputRef"
              v-model="editingName"
              class="session-edit-input"
              type="text"
              @blur="handleSaveRename"
              @keydown.enter="handleSaveRename"
              @keydown.esc="handleCancelRename"
              @click.stop
            >

            <div
              v-if="editingSessionId !== session.id"
              class="session-actions"
              @click.stop
            >
              <button
                class="action-btn"
                :title="$t('chat.sessionConfig.title')"
                @click="handleOpenConfig(session.id)"
              >
                <component
                  :is="SettingsIcon"
                  :size="16"
                />
              </button>
              <button
                class="action-btn action-btn-memory"
                :title="$t('sessions.summarizeToMemory')"
                :disabled="isSummarizing(session.id)"
                @click="handleSummarizeToMemory(session)"
              >
                <component
                  :is="BrainIcon"
                  :size="16"
                  :class="{ spinning: isSummarizing(session.id, 'long-term') }"
                />
              </button>
              <button
                class="action-btn"
                :title="$t('sessions.exportSession')"
                @click="handleExportSession(session.id)"
              >
                <component
                  :is="DownloadIcon"
                  :size="16"
                />
              </button>
              <button
                class="action-btn"
                :title="$t('common.edit')"
                @click="handleStartRename(session)"
              >
                <component
                  :is="EditIcon"
                  :size="16"
                />
              </button>
              <button
                class="action-btn danger"
                :title="$t('common.delete')"
                :disabled="chatStore.isDeletingSession"
                @click="handleDeleteSession(session.id)"
              >
                <component
                  :is="TrashIcon"
                  :size="16"
                />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, computed, onMounted, onBeforeUnmount } from 'vue'
import {
  Plus as PlusIcon,
  Edit2 as EditIcon,
  Trash2 as TrashIcon,
  Download as DownloadIcon,
  Brain as BrainIcon,
  Settings as SettingsIcon,
  Sparkles as SparklesIcon,
  Search as SearchIcon,
  X as ClearIcon,
  Loader2 as Loader2Icon
} from 'lucide-vue-next'
import { useChatStore, type Session } from '@/store/chat'
import { useMemoryStore } from '@/store/memory'
import { useToast } from '@/composables/useToast'
import { useConfirm } from '@/composables/useConfirm'
import { useI18n } from 'vue-i18n'
import { LoadingState, EmptyState } from '@/components/ui'
import { chatAPI, type SessionSearchHit as ApiSessionSearchHit } from '@/api'

const chatStore = useChatStore()
const memoryStore = useMemoryStore()
const toast = useToast()
const { confirmDelete } = useConfirm()
const { t } = useI18n()

// 定义事件
const emit = defineEmits<{
  (e: 'open-config', sessionId: string): void
}>()

const editingSessionId = ref<string | null>(null)
const editingName = ref('')
const editInputRef = ref<HTMLInputElement>()
const hasCurrentSession = computed(() => !!chatStore.currentSessionId)
const currentSessionName = computed(() => chatStore.currentSession?.name || t('sessions.session'))

const SESSION_CHANNEL_ALIASES: Record<string, string> = {
  dingding: 'dingtalk'
}

const SESSION_CHANNELS = new Set([
  'feishu',
  'qq',
  'dingtalk',
  'telegram',
  'discord',
  'wechat',
  'weibo'
])

const currentSessionChannelMeta = computed(() => parseSessionChannelMeta(currentSessionName.value))

const currentSessionChannelMetaValue = computed(() => {
  if (!hasCurrentSession.value || !currentSessionChannelMeta.value) return ''

  const { channel, accountId, chatId } = currentSessionChannelMeta.value
  const channelName = formatChannelName(channel)
  const parts = [channelName || channel]
  if (accountId) parts.push(accountId)
  parts.push(chatId)
  return parts.filter(Boolean).join(' / ')
})

const currentSessionChannelMetaLabel = computed(() => {
  if (!hasCurrentSession.value) return ''
  return currentSessionChannelMetaValue.value
    ? t('sessions.channelChatIdLabel', { value: currentSessionChannelMetaValue.value })
    : t('sessions.channelChatIdNotConfigured')
})

const currentSessionChipTitle = computed(() => {
  if (!hasCurrentSession.value) return t('sessions.noActiveSession')

  const segments = [t('sessions.currentSessionLabel', { name: currentSessionName.value })]
  if (currentSessionChannelMetaLabel.value) {
    segments.push(currentSessionChannelMetaLabel.value)
  }

  return segments.join(' · ')
})

interface SessionPanelItem extends Session {
  summary?: string | null
  messageCount?: number
  preview?: string
  snippets?: string[]
}

const searchQuery = ref('')
const searchResults = ref<SessionPanelItem[]>([])
const isSearchingSessions = ref(false)
const sessionSearchError = ref('')
let searchDebounceHandle: number | null = null
let latestSearchRequestId = 0

const isSearchMode = computed(() => searchQuery.value.trim().length > 0)

const displayedSessions = computed<SessionPanelItem[]>(() => {
  if (isSearchMode.value) {
    return searchResults.value
  }

  return chatStore.sortedSessions.map((session) => ({
    ...session,
    summary: null,
    messageCount: undefined,
    preview: '',
    snippets: [],
  }))
})

const displayedSessionCount = computed(() => displayedSessions.value.length)

function normalizeSearchHit(hit: ApiSessionSearchHit): SessionPanelItem {
  return {
    id: hit.session_id,
    name: hit.session_name,
    createdAt: hit.created_at || hit.updated_at || '',
    updatedAt: hit.updated_at || hit.created_at || '',
    summary: hit.summary,
    messageCount: hit.message_count,
    preview: hit.preview,
    snippets: Array.isArray(hit.snippets) ? hit.snippets : [],
  }
}

function resetSessionSearchState() {
  latestSearchRequestId += 1
  searchResults.value = []
  isSearchingSessions.value = false
  sessionSearchError.value = ''
  if (searchDebounceHandle !== null) {
    window.clearTimeout(searchDebounceHandle)
    searchDebounceHandle = null
  }
}

async function runSessionSearch(query: string) {
  const normalizedQuery = query.trim()
  if (!normalizedQuery) {
    resetSessionSearchState()
    return
  }

  const requestId = ++latestSearchRequestId
  isSearchingSessions.value = true
  sessionSearchError.value = ''

  try {
    const response = await chatAPI.searchSessions({
      query: normalizedQuery,
      limit: 12,
      per_session_snippets: 2,
    })

    if (requestId !== latestSearchRequestId) {
      return
    }

    searchResults.value = response.hits.map(normalizeSearchHit)
  } catch (error) {
    if (requestId !== latestSearchRequestId) {
      return
    }

    console.error('Failed to search sessions:', error)
    searchResults.value = []
    sessionSearchError.value = t('sessions.searchError')
  } finally {
    if (requestId === latestSearchRequestId) {
      isSearchingSessions.value = false
    }
  }
}

function handleSearchInput() {
  const normalizedQuery = searchQuery.value.trim()
  sessionSearchError.value = ''

  if (searchDebounceHandle !== null) {
    window.clearTimeout(searchDebounceHandle)
    searchDebounceHandle = null
  }

  if (!normalizedQuery) {
    resetSessionSearchState()
    return
  }

  searchDebounceHandle = window.setTimeout(() => {
    searchDebounceHandle = null
    void runSessionSearch(normalizedQuery)
  }, 220)
}

function clearSessionSearch() {
  searchQuery.value = ''
  resetSessionSearchState()
}

async function refreshSessionSearch() {
  if (!isSearchMode.value) {
    return
  }
  await runSessionSearch(searchQuery.value)
}

function firstSearchSnippet(session: SessionPanelItem): string {
  return session.snippets?.find((snippet) => String(snippet || '').trim()) || ''
}

function formatSearchSnippet(snippet: string): string {
  return String(snippet || '')
    .replaceAll('<<', '【')
    .replaceAll('>>', '】')
}

// 正在总结的会话 ID
type SummaryTarget = 'long-term'

const summarizeState = ref<{ sessionId: string; target: SummaryTarget } | null>(null)

function isSummarizing(sessionId: string, target?: SummaryTarget) {
  if (!summarizeState.value || summarizeState.value.sessionId !== sessionId) {
    return false
  }

  return target ? summarizeState.value.target === target : true
}

// 组件挂载时自动刷新一次会话列表
onMounted(() => {
  // 打开会话历史面板时自动刷新最新的历史消息
  chatStore.loadSessions().catch(() => {
    // 静默处理错误，避免干扰用户
  })
})

onBeforeUnmount(() => {
  if (searchDebounceHandle !== null) {
    window.clearTimeout(searchDebounceHandle)
    searchDebounceHandle = null
  }
})

/**
 * 打开会话配置
 */
function handleOpenConfig(sessionId: string) {
  emit('open-config', sessionId)
}

function handleOpenCurrentConfig() {
  if (!chatStore.currentSessionId) return
  handleOpenConfig(chatStore.currentSessionId)
}

function formatChannelName(channel: string) {
  if (!channel) return ''

  const key = `settings.persona.heartbeat.channelNames.${channel}`
  const translated = t(key)

  return translated !== key
    ? translated
    : channel.charAt(0).toUpperCase() + channel.slice(1)
}

function parseSessionChannelMeta(sessionName: string) {
  if (!sessionName || !sessionName.includes(':')) return null

  const parts = sessionName.split(':')
  if (parts.length < 2) return null

  const rawChannel = parts[0]?.trim().toLowerCase()
  const hasAccountSegment = parts.length >= 4
  const accountId = hasAccountSegment ? parts[1]?.trim() : ''
  const chatId = hasAccountSegment ? parts[2]?.trim() : parts[1]?.trim()

  if (!rawChannel || !chatId) return null

  const normalizedChannel = SESSION_CHANNEL_ALIASES[rawChannel] || rawChannel
  if (!SESSION_CHANNELS.has(normalizedChannel)) return null

  return {
    channel: normalizedChannel,
    accountId,
    chatId
  }
}

/**
 * 创建新会话
 */
async function handleCreateSession() {
  try {
    await chatStore.createSession()
    clearSessionSearch()
    toast.success(t('sessions.createSuccess'))
  } catch (error) {
    toast.error(t('sessions.createError'))
  }
}

/**
 * 切换会话
 */
function handleSwitchSession(sessionId: string) {
  if (editingSessionId.value) return // Don't switch while editing
  chatStore.switchSession(sessionId)
}

/**
 * 开始重命名
 */
function handleStartRename(session: Session) {
  editingSessionId.value = session.id
  editingName.value = session.name
  
  nextTick(() => {
    editInputRef.value?.focus()
    editInputRef.value?.select()
  })
}

/**
 * 保存重命名
 */
async function handleSaveRename() {
  if (!editingSessionId.value) return
  
  const newName = editingName.value.trim()
  if (!newName) {
    handleCancelRename()
    return
  }
  
  try {
    await chatStore.renameSession(editingSessionId.value, newName)
    await refreshSessionSearch()
    toast.success(t('sessions.renameSuccess'))
  } catch (error) {
    toast.error(t('sessions.renameError'))
  } finally {
    editingSessionId.value = null
    editingName.value = ''
  }
}

/**
 * 取消重命名
 */
function handleCancelRename() {
  editingSessionId.value = null
  editingName.value = ''
}

/**
 * 删除会话
 */
async function handleDeleteSession(sessionId: string) {
  const session = chatStore.sessions.find(s => s.id === sessionId)
  const confirmed = await confirmDelete(session?.name || t('sessions.session'))
  
  if (!confirmed) {
    return
  }
  
  try {
    await chatStore.deleteSession(sessionId)
    await refreshSessionSearch()
    toast.success(t('sessions.deleteSuccess'))
  } catch (error) {
    toast.error(t('sessions.deleteError'))
  }
}

/**
 * 导出会话完整记录（包括系统提示词）
 */
async function handleExportSession(sessionId: string) {
  try {
    const session = chatStore.sessions.find(s => s.id === sessionId)
    if (!session) {
      toast.error(t('sessions.sessionNotFound'))
      return
    }

    // 获取完整的会话上下文（包括系统提示词和工具历史）
    const response = await chatAPI.exportSessionContext(sessionId)
    
    if (!response || !response.messages) {
      toast.warning(t('sessions.noMessagesToExport'))
      return
    }

    // 格式化为文本
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5)
    let textContent = ''
    
    // 标题和元数据
    textContent += '='.repeat(80) + '\n'
    textContent += `会话导出 - ${session.name}\n`
    textContent += '='.repeat(80) + '\n\n'
    
    textContent += `会话ID: ${session.id}\n`
    textContent += `会话名称: ${session.name}\n`
    textContent += `创建时间: ${new Date(session.createdAt).toLocaleString('zh-CN')}\n`
    textContent += `更新时间: ${new Date(session.updatedAt).toLocaleString('zh-CN')}\n`
    textContent += `导出时间: ${new Date(response.exported_at).toLocaleString('zh-CN')}\n`
    
    // 过滤掉 role 为 'system' 的消息
    const userMessages = response.messages.filter(msg => msg.role !== 'system')
    textContent += `消息数量: ${userMessages.length}\n`
    
    if (response.tool_history && response.tool_history.length > 0) {
      textContent += `工具调用数量: ${response.tool_history.length}\n`
    }
    
    textContent += '\n'
    
    // 重要说明（更新为不包含系统提示词）
    textContent += '⚠️ 重要说明\n'
    textContent += '-'.repeat(80) + '\n'
    textContent += '此导出仅包含用户和助手的对话内容，不包含系统提示词。\n'
    textContent += '工具调用历史为全局记录，可能包含其他会话的工具调用。\n\n'
    
    // 工具执行历史
    if (response.tool_history && response.tool_history.length > 0) {
      textContent += '='.repeat(80) + '\n'
      textContent += '工具执行历史 (Tool Execution History)\n'
      textContent += '='.repeat(80) + '\n\n'
      
      response.tool_history.forEach((tool, index) => {
        const status = tool.success ? '✓ 成功' : '✗ 失败'
        const time = tool.timestamp ? new Date(tool.timestamp).toLocaleString('zh-CN') : '未知'
        const duration = tool.duration ? `${tool.duration.toFixed(2)}ms` : '未知'
        
        textContent += `[工具 ${index + 1}] ${tool.tool} ${status}\n`
        textContent += `时间: ${time}\n`
        textContent += `耗时: ${duration}\n`
        textContent += `参数: ${JSON.stringify(tool.arguments, null, 2)}\n`
        
        if (tool.success && tool.result) {
          textContent += `结果:\n${tool.result}\n`
        } else if (tool.error) {
          textContent += `错误: ${tool.error}\n`
        }
        
        textContent += '\n'
      })
    }
    
    // 对话历史（过滤掉系统提示词）
    textContent += '='.repeat(80) + '\n'
    textContent += '对话历史 (Conversation History)\n'
    textContent += '='.repeat(80) + '\n\n'
    
    userMessages.forEach((msg, index) => {
      const role = msg.role === 'user' ? '👤 用户' : '🤖 AI助手'
      const time = new Date(msg.created_at).toLocaleString('zh-CN')
      
      textContent += `[消息 ${index + 1}] ${role}\n`
      textContent += `时间: ${time}\n`
      textContent += `ID: ${msg.id}\n`
      textContent += '-'.repeat(80) + '\n'
      textContent += msg.content + '\n\n'
    })
    
    textContent += '='.repeat(80) + '\n'
    textContent += `导出完成 - 共 ${userMessages.length} 条消息`
    if (response.tool_history && response.tool_history.length > 0) {
      textContent += `，${response.tool_history.length} 次工具调用`
    }
    textContent += '\n'
    textContent += '='.repeat(80) + '\n'
    
    // 创建并下载文件
    const blob = new Blob([textContent], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${session.name}_完整导出_${timestamp}.txt`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
    
    toast.success(t('sessions.exportSuccess'))
  } catch (error) {
    console.error('导出会话失败:', error)
    toast.error(t('sessions.exportError'))
  }
}

/**
 * 格式化日期
 */
function formatDate(dateString: string): string {
  // 如果时间戳没有时区信息，假设它是UTC时间
  let timestamp = dateString
  if (!timestamp.includes('+') && !timestamp.includes('Z')) {
    timestamp = timestamp + 'Z'
  }
  
  const date = new Date(timestamp)
  const now = new Date()
  
  // 计算时间差（毫秒）
  const diff = now.getTime() - date.getTime()
  
  // 小于 1 分钟
  if (diff < 60000 && diff >= 0) {
    return t('sessions.justNow')
  }
  
  // 小于 1 小时
  if (diff < 3600000 && diff >= 0) {
    const minutes = Math.floor(diff / 60000)
    return t('sessions.minutesAgo', { count: minutes })
  }
  
  // 小于 24 小时
  if (diff < 86400000 && diff >= 0) {
    const hours = Math.floor(diff / 3600000)
    return t('sessions.hoursAgo', { count: hours })
  }
  
  // 小于 7 天
  if (diff < 604800000 && diff >= 0) {
    const days = Math.floor(diff / 86400000)
    return t('sessions.daysAgo', { count: days })
  }
  
  // 超过 7 天，显示完整日期
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  })
}

/**
 * 自动总结会话并保存到记忆
 */
async function handleSummarizeSession(session: Session, target: SummaryTarget) {
  if (summarizeState.value) return

  const confirmed = confirm(t('sessions.confirmSummarize'))
  if (!confirmed) return

  summarizeState.value = { sessionId: session.id, target }

  try {
    const result = await chatAPI.summarizeSessionToMemory(session.id)

    if (result.success) {
      await memoryStore.loadLongTermMemory()
      toast.success(
        result.message || t('sessions.summarizeSuccess', { summary: result.summary })
      )
    } else {
      toast.error(t('sessions.summarizeError'))
    }
  } catch (error: any) {
    console.error('Failed to summarize session:', error)
    const errorMsg =
      error.response?.data?.detail
      || error.message
      || t('sessions.summarizeError')
    toast.error(errorMsg)
  } finally {
    summarizeState.value = null
  }
}

async function handleSummarizeToMemory(session: Session) {
  await handleSummarizeSession(session, 'long-term')
}


</script>
<style scoped>
@import './styles/SessionPanel.css';
</style>

