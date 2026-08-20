<template>
  <div class="chat-window" :class="{ 'resizing': isResizing }">
    <!-- 顶部工具栏 -->
    <ChatHeader
      :actions="headerActions"
      @toggle-sidebar="showSystemSidebar = !showSystemSidebar"
      @clear-chat="clearCurrentChat"
    />

    <!-- 连接状态条 -->
    <ConnectionStatusBar
      :is-connected="isConnected"
      :is-connecting="isConnecting"
      :reconnecting-visible="reconnectingVisible"
      :reconnect-attempts-display="reconnectAttemptsDisplay"
      @reconnect="() => manualReconnect(chatStore.currentSessionId || '')"
    />

    <!-- 安全警告横幅 -->
    <SecurityWarningBanner
      :visible="securityWarningVisible"
      @setup-password="showPasswordSetup = true"
      @dismiss="dismissSecurityWarning"
    />

    <!-- 密码设置对话框 -->
    <PasswordSetupDialog
      v-model:show="showPasswordSetup"
      @success="handlePasswordSetupSuccess"
    />

    <!-- 会话配置面板 -->
    <SessionConfigPanel
      v-if="showSessionConfig"
      :session-id="configSessionId || chatStore.currentSessionId || ''"
      @close="showSessionConfig = false"
      @updated="handleSessionConfigUpdated"
    />

    <!-- 聊天区域 -->
    <main
      class="main"
      @dragenter.prevent="handleDragEnter"
      @dragover.prevent="handleDragOver"
      @dragleave.prevent="handleDragLeave"
      @drop.prevent="handleDrop"
    >
      <div v-if="isLoadingMessages" class="loading-container">
        <LoadingState type="skeleton" :lines="5" />
      </div>
      
      <WelcomeGuide
        v-else-if="messages.length === 0"
        :icon-svg="WELCOME_ICON_SVG || undefined"
        @open-settings="handleOpenSettings"
      />
      
      <MessageList
        v-else
        ref="messageListRef"
        :messages="messages"
        :auto-scroll="true"
        :has-more-history="hasMoreHistory"
        :is-loading-more="isLoadingOlderMessages"
        @regenerate="handleRegenerate"
        @delete="handleDelete"
        @load-more="handleLoadOlderMessages"
      />
    </main>

    <!-- 输入区域 -->
    <ChatInput
      ref="chatInputRef"
      :input-message="inputMessage"
      :textarea-ref="textareaRef"
      :is-streaming="isStreaming"
      :can-send="canSend"
      :show-team-picker="showTeamPicker"
      :filtered-teams="filteredTeams"
      :team-picker-index="teamPickerIndex"
      :is-mac="isMac"
      :attachments="attachments"
      :is-uploading-attachments="isUploading"
      @input="(value) => { inputMessage = value; handleInput() }"
      @send="sendMessage"
      @stop="stopGeneration"
      @keydown="(e) => handleKeydown(e, filteredTeams, sendMessage)"
      @team-select="selectTeam"
      @files-selected="handleComposerFiles"
      @remove-attachment="removeAttachment"
    />

    <!-- Drag and Drop Overlay -->
    <div v-if="isDraggingOver" class="drag-overlay">
      <div class="drag-overlay-content">
        <component :is="UploadIcon" :size="64" class="drag-overlay-icon" />
        <p class="drag-overlay-text">{{ $t('chat.releaseToUpload') }}</p>
      </div>
    </div>

    <!-- 侧边面板 -->
    <aside v-if="activePanel" ref="panelRef" class="panel" :style="panelStyle">
      <div class="resize-handle" @mousedown="startResize">
        <div class="resize-handle-line" />
      </div>
      
      <div class="panel-header">
        <h2 class="panel-title">{{ getPanelTitle() }}</h2>
        <button class="icon-btn" @click="closePanel">
          <component :is="XIcon" :size="20" />
        </button>
      </div>
      <div class="panel-body">
        <SessionPanel 
          v-if="activePanel === 'sessions'" 
          @open-config="handleOpenSessionConfig"
        />
        <ToolsPanel v-else-if="activePanel === 'tools'" />
        <SkillsLibrary v-else-if="activePanel === 'skills'" />
        <WikiPanel v-else-if="activePanel === 'wiki'" />
        <CronManager v-else-if="activePanel === 'cron'" />
        <SettingsPanel
          v-else-if="activePanel === 'settings'"
          :initial-tab="settingsInitialTab"
          @close="closePanel"
          @saved="handleSettingsSaved"
        />
        <p v-else class="panel-placeholder">{{ $t('common.comingSoon') }}</p>
      </div>
    </aside>

    <!-- 左侧系统信息侧边栏 -->
    <SystemSidebar :visible="showSystemSidebar" @close="showSystemSidebar = false" />

    <!-- 右侧时间轴面板 -->
    <transition name="timeline-slide">
      <div v-if="showTimeline" class="timeline-sidebar">
        <TimelinePanel
          :messages="messages"
          :active-message-id="activeMessageId"
          @close="showTimeline = false"
          @scroll-to="handleTimelineScrollTo"
        />
      </div>
    </transition>

    <!-- 遮罩 -->
    <div
      v-if="activePanel || showTimeline"
      class="overlay"
      :class="{ 'resizing': isResizing }"
      @click="!isResizing && (activePanel ? closePanel() : showTimeline = false)"
    />
    
    <!-- File Preview Modal -->
    <FilePreviewModal :show="showPreviewModal" :file="previewFile" @close="closePreviewModal" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch, inject } from 'vue'
import {
  PanelLeftOpen as SessionsIcon,
  BrainCircuit as WorkflowIcon,
  Blocks as SkillsIcon,
  AlarmClock as CronIcon,
  SlidersHorizontal as SettingsIcon,
  X as XIcon,
  Upload as UploadIcon,
  Route as TimelineIcon,
  BookOpen as WikiIcon
} from 'lucide-vue-next'
import { LoadingState, FilePreviewModal } from '@/components/ui'
import MessageList from './MessageList.vue'
import SessionPanel from './SessionPanel.vue'
import SettingsPanel from '@/modules/settings/SettingsPanel.vue'
import ToolsPanel from '@/modules/tools/ToolsPanel.vue'
import SkillsLibrary from '@/modules/skills/SkillsLibrary.vue'
import CronManager from '@/modules/scheduler/CronManager.vue'
import WikiPanel from '@/modules/wiki/WikiPanel.vue'
import SystemSidebar from '@/modules/system/SystemSidebar.vue'
import TimelinePanel from './TimelinePanel.vue'

// 新的模块化组件
import ChatHeader from '@/components/chat/ChatHeader.vue'
import ConnectionStatusBar from '@/components/chat/ConnectionStatusBar.vue'
import SecurityWarningBanner from '@/components/chat/SecurityWarningBanner.vue'
import PasswordSetupDialog from '@/components/chat/PasswordSetupDialog.vue'
import ChatInput from '@/components/chat/ChatInput.vue'
import WelcomeGuide from '@/components/chat/WelcomeGuide.vue'
import SessionConfigPanel from '@/components/chat/SessionConfigPanel.vue'

// ---------------------------------------------------------------
// 🎨 自定义 Welcome 图标
// 把你的 SVG 字符串粘贴到下面引号内即可替换欢迎页图标。
// 留空字符串 '' 则显示默认聊天气泡图标。
// 示例：'<svg xmlns="http://www.w3.org/2000/svg" ...>...</svg>'
// ---------------------------------------------------------------
const WELCOME_ICON_SVG = ''

// Composables
import { useWebSocket } from '@/composables/useWebSocket'
import { useMessageStreaming } from '@/composables/useMessageStreaming'
import { useChatAttachments } from '@/composables/useChatAttachments'
import { useChatInput } from '@/composables/useChatInput'
import { useQueuedMessages } from '@/modules/chat/composables/useQueuedMessages'
import { useSessionHistoryLoader } from '@/modules/chat/composables/useSessionHistoryLoader'
import { useChatRealtime } from '@/modules/chat/composables/useChatRealtime'

import { useI18n } from 'vue-i18n'
import { useChatStore } from '@/store/chat'
import { useAgentTeamsStore, type AgentTeam } from '@/store/agentTeams'
import { useToast } from '@/composables/useToast'
import { useKeyboard, commonShortcuts } from '@/composables/useKeyboard'
import { queueAPI } from '@/api/endpoints'
import type { SettingsTab } from '@/types/settings'

const { t } = useI18n()
const chatStore = useChatStore()
const agentTeamsStore = useAgentTeamsStore()
const toast = useToast()

// WebSocket 管理
const {
  isConnected,
  isConnecting,
  reconnectingVisible,
  reconnectAttemptsDisplay,
  connectWebSocket,
  sendMessage: wsSendMessage,
  closeConnection,
  manualReconnect,
  setHandlers
} = useWebSocket()

// 消息流式处理
const {
  messages,
  isStreaming,
  dispatchStreamEvent,
  replaceMessages,
  stopStreaming,
  clearMessages,
  addThinkingMessage,
  getCachedSpawnTask,
  cacheSessionMessages,
  restoreSessionMessages,
  clearSessionCache
} = useMessageStreaming()

// 聊天输入
const {
  inputMessage,
  textareaRef,
  showTeamPicker,
  teamPickerQuery,
  teamPickerIndex,
  handleInput,
  handleKeydown,
  selectTeam,
  clearInput,
  isMac
} = useChatInput()

// 聊天附件
const {
  attachments,
  readyAttachments,
  isUploading,
  addFiles,
  removeAttachment,
  clearAttachments
} = useChatAttachments()
const isDraggingOver = ref(false)
const dragCounter = ref(0)

// 安全警告
const showSecurityWarning = inject<import('vue').Ref<boolean>>('showSecurityWarning', ref(false))
const securityWarningDismissed = ref(false)
const securityWarningVisible = computed(() => showSecurityWarning.value && !securityWarningDismissed.value)
const dismissSecurityWarning = () => { securityWarningDismissed.value = true }

// 密码设置对话框
const showPasswordSetup = ref(false)

const handlePasswordSetupSuccess = () => {
  securityWarningDismissed.value = true
  showSecurityWarning.value = false
}

// 会话配置面板
const showSessionConfig = ref(false)
const configSessionId = ref<string>('')

/**
 * 打开会话配置面板
 */
function handleOpenSessionConfig(sessionId: string) {
  configSessionId.value = sessionId
  showSessionConfig.value = true
  // 如果从侧边栏打开，关闭侧边栏
  if (activePanel.value === 'sessions') {
    closePanel()
  }
}

type PanelType = 'sessions' | 'tools' | 'skills' | 'wiki' | 'cron' | 'settings' | null

const isStoppingTask = ref(false)
const messageListRef = ref<InstanceType<typeof MessageList>>()
const chatInputRef = ref<InstanceType<typeof ChatInput>>()
const panelRef = ref<HTMLElement>()
const activePanel = ref<PanelType>(null)
const settingsInitialTab = ref<SettingsTab>('general')
const showSystemSidebar = ref(false)
const showTimeline = ref(false)
const activeMessageId = ref<string | null>(null)
const showPreviewModal = ref(false)
const previewFile = ref<File | null>(null)

// 面板宽度调整 - 固定宽度
const panelWidth = ref(720)  // 固定宽度 720px（比原来的 560px 更宽）
const isResizing = ref(false)
const minPanelWidth = 380
const maxPanelWidth = 1200
const clampPanelWidth = (width: number) => Math.min(Math.max(width, minPanelWidth), maxPanelWidth)
const panelStyle = computed(() => ({
  width: `min(${panelWidth.value}px, calc(100vw - 24px))`,
  maxWidth: 'calc(100vw - 24px)'
}))

// 过滤激活的团队
const filteredTeams = computed<AgentTeam[]>(() => {
  const active = agentTeamsStore.teams.filter(t => t.is_active)
  const q = teamPickerQuery.value.trim().toLowerCase()
  if (!q) return active
  return active.filter(t =>
    t.name.toLowerCase().includes(q) ||
    (t.description ?? '').toLowerCase().includes(q)
  )
})

const canSend = computed(() => {
  return (inputMessage.value.trim().length > 0 || readyAttachments.value.length > 0) &&
         isConnected.value &&
         !isUploading.value &&
         !isStreaming.value
})

const openSettingsTab = (tab: SettingsTab = 'general') => {
  settingsInitialTab.value = tab
  showPanel('settings')
}

const headerActions = computed(() => [
  { id: 'sessions', icon: SessionsIcon, label: 'nav.sessions', tooltip: 'nav.sessionsTooltip', onClick: () => showPanel('sessions') },
  { id: 'multiagent', icon: WorkflowIcon, label: 'nav.multiagent', tooltip: 'nav.multiagentTooltip', onClick: () => openSettingsTab('multiagent') },
  { id: 'skills', icon: SkillsIcon, label: 'nav.skills', tooltip: 'nav.skillsTooltip', emphasis: true, shortLabel: 'Skills', onClick: () => showPanel('skills') },
  { id: 'wiki', icon: WikiIcon, label: 'nav.wiki', tooltip: 'nav.wikiTooltip', onClick: () => showPanel('wiki') },
  { id: 'cron', icon: CronIcon, label: 'nav.cron', tooltip: 'nav.cronTooltip', onClick: () => showPanel('cron') },
  { id: 'timeline', icon: TimelineIcon, label: 'nav.timeline', tooltip: 'nav.timelineTooltip', onClick: () => toggleTimeline() },
  { id: 'settings', icon: SettingsIcon, label: 'settings.title', tooltip: 'nav.settingsTooltip', onClick: () => openSettingsTab('general') }
])

const {
  sendOrQueueMessage,
  sendImmediateMessage,
  flushNextQueuedMessage,
  clearPendingMessages
} = useQueuedMessages({
  messages,
  isStreaming,
  getCurrentSessionId: () => chatStore.currentSessionId,
  sendRealtimeMessage: wsSendMessage,
  addThinkingMessage,
  toast,
  scrollToBottom: () => messageListRef.value?.scrollToBottom()
})

const {
  isLoadingMessages,
  isLoadingOlderMessages,
  hasMoreHistory,
  initializeChat,
  loadSessionMessages,
  loadOlderMessages,
  resetInitializedSession,
  cacheCurrentSession
} = useSessionHistoryLoader({
  loadMessages: chatStore.loadMessages,
  connectWebSocket,
  replaceMessages,
  clearMessages,
  restoreSessionMessages,
  clearSessionCache,
  cacheSessionMessages,
  getCachedSpawnTask
})

useChatRealtime({
  setHandlers,
  dispatchStreamEvent,
  getCurrentSessionId: () => chatStore.currentSessionId,
  refreshSessionMessages: loadSessionMessages,
  refreshSessions: chatStore.loadSessions,
  cacheSessionMessages,
  flushNextQueuedMessage,
  toast
})

// 监听会话变化
watch(() => chatStore.currentSessionId, (newSessionId, oldSessionId) => {
  clearAttachments()
  if (newSessionId) {
    // 只有在真正切换会话时才清空消息
    // 如果是首次加载（oldSessionId 为 undefined），不清空（可能有缓存）
    const shouldClear = oldSessionId !== undefined && oldSessionId !== newSessionId
    initializeChat(newSessionId, shouldClear)
  }
})

// 发送消息
const sendMessage = () => {
  const payload = {
    content: inputMessage.value.trim(),
    attachmentItems: readyAttachments.value.map((item) => ({
      path: item.path,
      name: item.name,
      size: item.size,
      content_type: item.content_type,
      kind: item.kind,
    }))
  }

  if (!payload.content && payload.attachmentItems.length === 0) return

  clearInput()
  clearAttachments()
  sendOrQueueMessage(payload)
}

const handleComposerFiles = async (files: File[]) => {
  await addFiles(files, chatStore.currentSessionId)
}

const handleDragEnter = (event: DragEvent) => {
  if (!isConnected.value) return
  if (!(event.dataTransfer?.types || []).includes('Files')) return
  dragCounter.value += 1
  isDraggingOver.value = true
}

const handleDragOver = (event: DragEvent) => {
  if (!isConnected.value) return
  if (event.dataTransfer) {
    event.dataTransfer.dropEffect = 'copy'
  }
}

const handleDragLeave = () => {
  dragCounter.value = Math.max(0, dragCounter.value - 1)
  if (dragCounter.value === 0) {
    isDraggingOver.value = false
  }
}

const handleDrop = async (event: DragEvent) => {
  isDraggingOver.value = false
  dragCounter.value = 0
  if (!isConnected.value) return

  const files = Array.from(event.dataTransfer?.files || [])
  if (files.length === 0) return
  await handleComposerFiles(files)
}

// 停止生成
const stopGeneration = async () => {
  if (!isStreaming.value || !chatStore.currentSessionId) return
  
  // 防止重复点击
  if (isStoppingTask.value) {
    console.log('[ChatWindow] 已在停止中，忽略重复请求')
    return
  }
  
  isStoppingTask.value = true
  
  try {
    // 设置超时保护（5秒）
    const timeoutPromise = new Promise((_, reject) => {
      setTimeout(() => reject(new Error('停止操作超时')), 5000)
    })
    
    const cancelPromise = queueAPI.cancelTask(chatStore.currentSessionId)
    
    const result = await Promise.race([cancelPromise, timeoutPromise]) as any
    
    if (result.success) {
      toast.success('已停止生成')
    } else {
      toast.warning(result.message || '没有正在执行的任务')
    }
  } catch (error: any) {
    console.error('[ChatWindow] 停止生成失败:', error)
    if (error.message === '停止操作超时') {
      toast.warning('停止请求超时，但任务可能已停止')
    } else {
      toast.error('停止失败，请重试')
    }
  } finally {
    // 无论成功失败，都清理流式状态
    stopStreaming()
    isStoppingTask.value = false
    
    // 处理排队的消息
    flushNextQueuedMessage(300)
  }
}

// 清空当前对话
async function clearCurrentChat() {
  if (messages.value.length === 0) {
    toast.info(t('chat.noMessagesToClear'))
    return
  }
  
  if (!confirm(t('chat.confirmClearChat'))) return
  
  try {
    clearMessages()
    clearAttachments()
    if (chatStore.currentSessionId) {
      await chatStore.clearMessages(chatStore.currentSessionId)
      clearSessionCache(chatStore.currentSessionId)  // 清除缓存
    }
    toast.success(t('chat.chatCleared'))
  } catch (error) {
    console.error('Failed to clear chat:', error)
    toast.error(t('chat.clearChatFailed'))
  }
}

const handleRegenerate = (messageId: string) => {
  const messageIndex = messages.value.findIndex(m => m.id === messageId)
  if (messageIndex <= 0) return
  
  for (let i = messageIndex - 1; i >= 0; i--) {
    if (messages.value[i].role === 'user') {
      const userMessage = messages.value[i].content
      const userAttachments = messages.value[i].attachmentItems || []
      messages.value.splice(messageIndex)

      sendImmediateMessage({
        content: userMessage,
        attachmentItems: userAttachments,
      })
      break
    }
  }
}

const handleDelete = async (messageId: string) => {
  if (!chatStore.currentSessionId) return
  
  try {
    const messageIndex = messages.value.findIndex(m => m.id === messageId)
    if (messageIndex === -1) return
    
    messages.value.splice(messageIndex, 1)
    await chatStore.deleteMessage(chatStore.currentSessionId, parseInt(messageId))
    toast.success(t('chat.messageDeleted') || '消息已删除')
  } catch (error) {
    console.error('Failed to delete message:', error)
    toast.error(t('chat.deleteMessageFailed') || '删除消息失败')
    
    if (chatStore.currentSessionId) {
      await loadSessionMessages(chatStore.currentSessionId)
    }
  }
}

const handleLoadOlderMessages = async () => {
  if (!chatStore.currentSessionId) return
  await loadOlderMessages(chatStore.currentSessionId)
}

const closePreviewModal = () => {
  showPreviewModal.value = false
  previewFile.value = null
}

// 面板管理
const showPanel = (panel: Exclude<PanelType, null>) => {
  activePanel.value = panel
}

const closePanel = () => {
  activePanel.value = null
}

const toggleTimeline = () => {
  showTimeline.value = !showTimeline.value
}

const handleTimelineScrollTo = (messageId: string) => {
  activeMessageId.value = messageId
  messageListRef.value?.scrollToMessage?.(messageId)
  
  setTimeout(() => {
    activeMessageId.value = null
  }, 3000)
}

const handleSettingsSaved = () => {
  if (chatStore.currentSessionId) {
    closeConnection()
    resetInitializedSession()
    
    setTimeout(() => {
      if (chatStore.currentSessionId) {
        initializeChat(chatStore.currentSessionId, false)  // 重连不清空
      }
    }, 500)
  }
}

const handleSessionConfigUpdated = (action: 'saved' | 'reset') => {
  showSessionConfig.value = false
  toast.success(
    action === 'reset'
      ? t('chat.sessionConfig.resetNextMessage')
      : t('chat.sessionConfig.updatedNextMessage')
  )
}

// 拖动调整面板宽度
const startResize = (e: MouseEvent) => {
  e.preventDefault()
  isResizing.value = true
  
  const startX = e.clientX
  const startWidth = panelWidth.value
  
  const handleMouseMove = (e: MouseEvent) => {
    const deltaX = startX - e.clientX
    panelWidth.value = clampPanelWidth(startWidth + deltaX)
  }
  
  const handleMouseUp = () => {
    isResizing.value = false
    document.removeEventListener('mousemove', handleMouseMove)
    document.removeEventListener('mouseup', handleMouseUp)
    localStorage.setItem('panelWidth', panelWidth.value.toString())
  }
  
  document.addEventListener('mousemove', handleMouseMove)
  document.addEventListener('mouseup', handleMouseUp)
}

const getPanelTitle = () => {
  const titles: Record<Exclude<PanelType, null>, string> = {
    sessions: t('nav.sessions'),
    tools: t('nav.tools'),
    skills: t('nav.skills'),
    wiki: t('nav.wiki'),
    cron: t('nav.cron'),
    settings: t('settings.title')
  }
  return activePanel.value ? titles[activePanel.value] : ''
}

// 处理欢迎页面的设置打开
const handleOpenSettings = (section: string) => {
  // 映射欢迎页面的 section 到 SettingsPanel 的 tab
  const sectionToTab: Record<string, SettingsTab> = {
    'provider': 'provider',
    'channels': 'channels',
    'personality': 'persona',
    'teams': 'multiagent',
    'memory': 'memory',
    'multiagent': 'multiagent'
  }

  openSettingsTab(sectionToTab[section] || 'general')
}

// 快捷键支持
useKeyboard([
  commonShortcuts.send(() => {
    if (canSend.value) {
      sendMessage()
    }
  }),
  commonShortcuts.escape(() => {
    if (activePanel.value) {
      closePanel()
    }
  }),
  commonShortcuts.search(() => {
    showPanel('sessions')
  }),
  commonShortcuts.new(async () => {
    try {
      await chatStore.createSession()
      toast.success(t('chat.sessionCreated'))
    } catch (error) {
      toast.error(t('common.error'))
    }
  }),
  commonShortcuts.toggleSidebar(() => {
    if (activePanel.value) {
      closePanel()
    } else {
      showPanel('sessions')
    }
  }),
  commonShortcuts.settings(() => {
    showPanel('settings')
  })
])

// 初始化
onMounted(async () => {
  try {
    const savedWidth = localStorage.getItem('panelWidth')
    if (savedWidth) {
      const parsedWidth = parseInt(savedWidth, 10)
      if (!Number.isNaN(parsedWidth)) {
        panelWidth.value = clampPanelWidth(parsedWidth)
      }
    }
    
    // 同步 textarea ref
    if (chatInputRef.value?.textareaRef) {
      textareaRef.value = chatInputRef.value.textareaRef
    }
    
    await chatStore.loadSessions()
    agentTeamsStore.loadTeams().catch(() => {})
    
    if (chatStore.sessions.length === 0) {
      await chatStore.createSession()
    } else if (!chatStore.currentSessionId) {
      chatStore.switchSession(chatStore.sessions[0].id)
    }
    
    if (chatStore.currentSessionId) {
      initializeChat(chatStore.currentSessionId, false)  // 首次加载不清空
    }
    
    // 监听页面刷新/关闭，缓存当前消息
    window.addEventListener('beforeunload', handleBeforeUnload)
  } catch (error) {
    console.error('Failed to initialize:', error)
    toast.error(t('common.error'))
  }
})

// 页面刷新前缓存消息
function handleBeforeUnload() {
  cacheCurrentSession(chatStore.currentSessionId, messages.value.length > 0)
}

// 清理
onBeforeUnmount(() => {
  // 移除事件监听
  window.removeEventListener('beforeunload', handleBeforeUnload)
  
  closeConnection()
  resetInitializedSession()
  clearPendingMessages()
  clearAttachments()
})
</script>
<style scoped>
@import './styles/ChatWindow.css';
</style>
