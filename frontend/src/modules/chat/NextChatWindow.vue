<template>
  <div class="nc-shell" :class="{ 'sidebar-collapsed': !sidebarOpen, resizing: isResizing }">
    <div class="nc-sidebar-wrap">
      <NextSidebar
        :sessions="chatStore.sessions"
        :current-session-id="chatStore.currentSessionId"
        :loading="chatStore.isLoadingSessions"
        :open="sidebarOpen"
        @create="handleCreateSession"
        @select="handleSelectSession"
        @config="handleOpenSessionConfig"
        @rename="handleRenameSession"
        @delete="handleDeleteSession"
        @open-panel="handleOpenPanel"
        @open-settings="openSettingsTab"
        @toggle="toggleSidebar"
        @close="sidebarOpen = false"
      />
    </div>

    <div class="nc-workspace">
      <NextTopbar
        :title="topbarTitle"
        :has-messages="messages.length > 0"
        :is-streaming="isStreaming"
        @toggle-sidebar="toggleSidebar"
        @new-session="handleCreateSession"
        @clear-chat="clearCurrentChat"
        @open-panel="handleOpenTopbarPanel"
        @open-settings="openSettingsTab('general')"
        @open-system="showSystemSidebar = true"
      />

      <ConnectionStatusBar
        :is-connected="isConnected"
        :is-connecting="isConnecting"
        :reconnecting-visible="reconnectingVisible"
        :reconnect-attempts-display="reconnectAttemptsDisplay"
        :max-attempts="maxReconnectAttempts"
        :disconnected-reason="connectionError"
        @reconnect="() => manualReconnect(chatStore.currentSessionId || undefined)"
      />

      <SecurityWarningBanner
        :visible="securityWarningVisible"
        @setup-password="showPasswordSetup = true"
        @dismiss="dismissSecurityWarning"
      />

      <main
        class="nc-main"
        @dragenter.prevent="handleDragEnter"
        @dragover.prevent="handleDragOver"
        @dragleave.prevent="handleDragLeave"
        @drop.prevent="handleDrop"
      >
        <div v-if="isLoadingMessages" class="nc-loading">
          <LoadingState type="skeleton" :lines="5" />
        </div>

        <NextWelcome
          v-else-if="messages.length === 0"
          @quick-action="handleWelcomeAction"
        >
          <template #composer>
            <NextComposer
              :ref="bindComposerRef"
              v-bind="(composerBindings as any)"
              variant="hero"
              :context-label="currentSessionName"
              @open-context="showPanel('sessions')"
            />
          </template>
        </NextWelcome>

        <MessageList
          v-else
          ref="messageListRef"
          :messages="messages"
          :auto-scroll="true"
          :has-more-history="hasMoreHistory"
          :is-loading-more="isLoadingOlderMessages"
          :is-streaming="isStreaming"
          @regenerate="handleRegenerate"
          @delete="handleDelete"
          @load-more="handleLoadOlderMessages"
        />
      </main>

      <NextComposer
        v-if="!isLoadingMessages && messages.length > 0"
        :ref="bindComposerRef"
        v-bind="(composerBindings as any)"
        variant="docked"
        :context-label="currentSessionName"
        @open-context="showPanel('sessions')"
      />
    </div>

    <!-- 拖拽上传遮罩 -->
    <div v-if="isDraggingOver" class="nc-drag-overlay">
      <div class="nc-drag-content">
        <component :is="UploadIcon" :size="56" class="nc-drag-icon" />
        <p>{{ $t('chat.releaseToUpload') }}</p>
      </div>
    </div>

    <!-- 密码设置对话框 -->
    <PasswordSetupDialog v-model:show="showPasswordSetup" @success="handlePasswordSetupSuccess" />

    <!-- 会话配置面板 -->
    <SessionConfigPanel
      v-if="showSessionConfig"
      :session-id="configSessionId || chatStore.currentSessionId || ''"
      @close="showSessionConfig = false"
      @updated="handleSessionConfigUpdated"
    />

    <!-- 右侧面板 -->
    <aside v-if="activePanel" ref="panelRef" class="nc-panel" :style="panelStyle">
      <div class="nc-resize-handle" @mousedown="startResize">
        <div class="nc-resize-line" />
      </div>
      <div class="nc-panel-head">
        <h2 class="nc-panel-title">{{ getPanelTitle() }}</h2>
        <button class="nc-panel-close" :title="$t('common.close')" @click="closePanel">
          <component :is="XIcon" :size="18" />
        </button>
      </div>
      <div class="nc-panel-body">
        <SessionPanel v-if="activePanel === 'sessions'" @open-config="handleOpenSessionConfig" />
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
        <p v-else class="nc-panel-placeholder">{{ $t('common.comingSoon') }}</p>
      </div>
    </aside>

    <!-- 左侧系统信息侧边栏 -->
    <SystemSidebar :visible="showSystemSidebar" @close="showSystemSidebar = false" />

    <!-- 右侧时间轴面板 -->
    <transition name="nc-timeline-slide">
      <div v-if="showTimeline" class="nc-timeline">
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
      v-if="activePanel || showTimeline || isMobileSidebarOpen"
      class="nc-overlay"
      @click="handleOverlayClick"
    />

    <FilePreviewModal :show="showPreviewModal" :file="previewFile" @close="closePreviewModal" />
  </div>
</template>

<script setup lang="ts">
import { computed, inject, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  X as XIcon,
  Upload as UploadIcon
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

// 新主窗口布局组件
import NextSidebar from './next/NextSidebar.vue'
import NextTopbar from './next/NextTopbar.vue'
import NextWelcome from './next/NextWelcome.vue'
import type { WelcomeQuickAction } from './next/types'
import NextComposer from './next/NextComposer.vue'

import ConnectionStatusBar from '@/components/chat/ConnectionStatusBar.vue'
import SecurityWarningBanner from '@/components/chat/SecurityWarningBanner.vue'
import PasswordSetupDialog from '@/components/chat/PasswordSetupDialog.vue'
import SessionConfigPanel from '@/components/chat/SessionConfigPanel.vue'

// Composables
import { useWebSocket } from '@/composables/useWebSocket'
import { useMessageStreaming } from '@/composables/useMessageStreaming'
import { useChatAttachments } from '@/composables/useChatAttachments'
import { useChatInput } from '@/composables/useChatInput'
import { useQueuedMessages } from '@/modules/chat/composables/useQueuedMessages'
import { useSessionHistoryLoader } from '@/modules/chat/composables/useSessionHistoryLoader'
import { useChatRealtime } from '@/modules/chat/composables/useChatRealtime'
import { useSessionModelSelection } from '@/modules/chat/composables/useSessionModelSelection'

import { useI18n } from 'vue-i18n'
import { useChatStore } from '@/store/chat'
import { useAgentTeamsStore, type AgentTeam } from '@/store/agentTeams'
import { useSettingsStore } from '@/store/settings'
import { useToast } from '@/composables/useToast'
import { useConfirm } from '@/composables/useConfirm'
import { useKeyboard, commonShortcuts } from '@/composables/useKeyboard'
import { queueAPI } from '@/api/endpoints'
import type { SettingsTab } from '@/types/settings'

const { t } = useI18n()
const chatStore = useChatStore()
const agentTeamsStore = useAgentTeamsStore()
const toast = useToast()
const { confirm } = useConfirm()

const {
  isConnected,
  isConnecting,
  reconnectingVisible,
  reconnectAttemptsDisplay,
  connectionError,
  maxReconnectAttempts,
  connectWebSocket,
  sendMessage: wsSendMessage,
  closeConnection,
  manualReconnect,
  setHandlers
} = useWebSocket()

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

function handleOpenSessionConfig(sessionId: string) {
  configSessionId.value = sessionId
  showSessionConfig.value = true
  if (activePanel.value === 'sessions') {
    closePanel()
  }
}

// 侧边栏删除会话：不可逆操作，确认弹窗 loading 锁死直到删除完成
async function handleDeleteSession(sessionId: string) {
  await confirm({
    title: t('common.confirmDelete'),
    message: t('sessions.deleteConfirm'),
    type: 'danger',
    confirmText: t('common.delete'),
    confirmVariant: 'danger',
    onConfirm: async () => {
      try {
        await chatStore.deleteSession(sessionId)
        clearSessionCache(sessionId)
        toast.success(t('sessions.deleteSuccess'))
      } catch (error) {
        toast.error(t('sessions.deleteError'))
      }
    }
  })
}

// 侧边栏行内改名：由侧边栏负责输入态，这里只落库并给出反馈
async function handleRenameSession(payload: { sessionId: string; name: string }) {
  try {
    await chatStore.renameSession(payload.sessionId, payload.name)
    toast.success(t('sessions.renameSuccess'))
  } catch (error) {
    toast.error(t('sessions.renameError'))
  }
}

type PanelType = 'sessions' | 'tools' | 'skills' | 'wiki' | 'cron' | 'settings' | null

const isMobile = () => typeof window !== 'undefined' && window.innerWidth <= 860
const sidebarOpen = ref(!isMobile())
const isMobileSidebarOpen = computed(() => isMobile() && sidebarOpen.value)

const isStoppingTask = ref(false)
const messageListRef = ref<InstanceType<typeof MessageList>>()
const chatInputRef = ref<InstanceType<typeof NextComposer>>()
const panelRef = ref<HTMLElement>()
const activePanel = ref<PanelType>(null)
const settingsInitialTab = ref<SettingsTab>('general')
const showSystemSidebar = ref(false)
const showTimeline = ref(false)
const activeMessageId = ref<string | null>(null)
const showPreviewModal = ref(false)
const previewFile = ref<File | null>(null)

// 面板宽度调整
const panelWidth = ref(720)
const isResizing = ref(false)
const minPanelWidth = 380
const maxPanelWidth = 1200
const clampPanelWidth = (width: number) => Math.min(Math.max(width, minPanelWidth), maxPanelWidth)
const panelStyle = computed(() => ({
  width: `min(${panelWidth.value}px, calc(100vw - 24px))`,
  maxWidth: 'calc(100vw - 24px)'
}))

const currentSession = computed(() =>
  chatStore.sessions.find(session => session.id === chatStore.currentSessionId)
)
const currentSessionName = computed(() => currentSession.value?.name || '')
const topbarTitle = computed(() => (messages.value.length > 0 ? currentSessionName.value : ''))

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

const toggleSidebar = () => {
  sidebarOpen.value = !sidebarOpen.value
}

const openSettingsTab = (tab: SettingsTab = 'general') => {
  settingsInitialTab.value = tab
  showPanel('settings')
}

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
  toast,
  isBusy: () => isStreaming.value
})

watch(() => chatStore.currentSessionId, (newSessionId, oldSessionId) => {
  clearAttachments()
  if (newSessionId) {
    modelSelection.loadSessionSelection(newSessionId).catch(() => {})
    const shouldClear = oldSessionId !== undefined && oldSessionId !== newSessionId
    initializeChat(newSessionId, shouldClear)
  }
})

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

// 输入框里的模型切换
const settingsStore = useSettingsStore()
const modelSelection = useSessionModelSelection()
const modelGroups = computed(() => modelSelection.groups.value)

const handleSelectModel = async (providerId: string, modelId: string) => {
  try {
    await modelSelection.selectModel(chatStore.currentSessionId || '', providerId, modelId)
  } catch (error: any) {
    toast.error(error?.response?.data?.detail || t('chat.modelPicker.switchFailed'))
  }
}

const reasoningLevels = computed(() => modelSelection.reasoningLevels.value)

const handleSelectReasoningLevel = async (level: string) => {
  try {
    await modelSelection.selectReasoningLevel(chatStore.currentSessionId || '', level)
  } catch (error: any) {
    toast.error(error?.response?.data?.detail || t('chat.reasoningLevel.saveFailed'))
  }
}

watch(
  () => settingsStore.persistedSettings,
  persisted => {
    if (persisted) {
      modelSelection.refreshOptions().catch(() => {})
    }
  },
  { deep: false },
)

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

const stopGeneration = async () => {
  if (!isStreaming.value || !chatStore.currentSessionId) return

  if (isStoppingTask.value) {
    return
  }

  isStoppingTask.value = true

  try {
    const timeoutPromise = new Promise((_, reject) => {
      setTimeout(() => reject(new Error('停止操作超时')), 5000)
    })

    const cancelPromise = queueAPI.cancelTask(chatStore.currentSessionId)
    const result = await Promise.race([cancelPromise, timeoutPromise]) as any

    if (result.success) {
      toast.success(t('chat.stopped'))
    } else {
      toast.warning(result.message || t('chat.noRunningTask'))
    }
  } catch (error: any) {
    console.error('[NextChatWindow] 停止生成失败:', error)
    if (error.message === '停止操作超时') {
      toast.warning(t('chat.stopTimeout'))
    } else {
      toast.error(t('chat.stopFailed'))
    }
  } finally {
    stopStreaming()
    isStoppingTask.value = false
    flushNextQueuedMessage(300)
  }
}

async function clearCurrentChat() {
  if (messages.value.length === 0) {
    toast.info(t('chat.noMessagesToClear'))
    return
  }

  // 危险操作：弹窗 loading 锁死，等清空完成后再关闭
  await confirm({
    title: t('common.confirmClear'),
    message: t('chat.confirmClearChat'),
    type: 'warning',
    confirmText: t('common.clear'),
    confirmVariant: 'warning',
    onConfirm: async () => {
      try {
        clearMessages()
        clearAttachments()
        if (chatStore.currentSessionId) {
          await chatStore.clearMessages(chatStore.currentSessionId)
          clearSessionCache(chatStore.currentSessionId)
        }
        toast.success(t('chat.chatCleared'))
      } catch (error) {
        console.error('Failed to clear chat:', error)
        toast.error(t('chat.clearChatFailed'))
      }
    }
  })
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
    toast.success(t('chat.messageDeleted'))
  } catch (error) {
    console.error('Failed to delete message:', error)
    toast.error(t('chat.deleteMessageFailed'))

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
  if (panel === 'settings') {
    panelWidth.value = clampPanelWidth(maxPanelWidth)
  }
}

const closePanel = () => {
  activePanel.value = null
}

const handleOpenPanel = (panel: 'sessions' | 'skills' | 'cron' | 'wiki') => {
  showPanel(panel)
}

const handleOpenTopbarPanel = (panel: 'timeline') => {
  if (panel === 'timeline') {
    toggleTimeline()
  }
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

const handleOverlayClick = () => {
  if (isResizing.value) return
  if (activePanel.value) {
    closePanel()
  } else if (showTimeline.value) {
    showTimeline.value = false
  } else if (isMobileSidebarOpen.value) {
    sidebarOpen.value = false
  }
}

const handleSettingsSaved = () => {
  if (chatStore.currentSessionId) {
    closeConnection()
    resetInitializedSession()

    setTimeout(() => {
      if (chatStore.currentSessionId) {
        initializeChat(chatStore.currentSessionId, false)
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
  let targetWidth = startWidth
  let rafId = 0
  let velocity = 0
  let lastTs = performance.now()

  const prefersReducedMotion =
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches

  const springStep = (now: number) => {
    const dt = Math.min((now - lastTs) / 1000, 0.032)
    lastTs = now
    const displacement = panelWidth.value - targetWidth
    const acceleration = -1200 * displacement - 80 * velocity
    velocity += acceleration * dt
    panelWidth.value += velocity * dt

    if (Math.abs(panelWidth.value - targetWidth) < 0.4 && Math.abs(velocity) < 4) {
      panelWidth.value = targetWidth
      velocity = 0
      rafId = 0
      return
    }
    rafId = requestAnimationFrame(springStep)
  }

  const handleMouseMove = (e: MouseEvent) => {
    const deltaX = startX - e.clientX
    targetWidth = clampPanelWidth(startWidth + deltaX)
    if (prefersReducedMotion) {
      panelWidth.value = targetWidth
      return
    }
    if (!rafId) {
      lastTs = performance.now()
      rafId = requestAnimationFrame(springStep)
    }
  }

  const handleMouseUp = () => {
    isResizing.value = false
    document.removeEventListener('mousemove', handleMouseMove)
    document.removeEventListener('mouseup', handleMouseUp)
    if (rafId) {
      cancelAnimationFrame(rafId)
      rafId = 0
    }
    panelWidth.value = targetWidth
    velocity = 0
    localStorage.setItem('panelWidth', String(Math.round(panelWidth.value)))
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

const handleOpenSettings = (section: string) => {
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

const handleWelcomeAction = (action: WelcomeQuickAction) => {
  if (action.kind === 'panel') {
    showPanel(action.value as Exclude<PanelType, null>)
    return
  }
  handleOpenSettings(action.value)
}

const handleCreateSession = async () => {
  try {
    await chatStore.createSession()
    toast.success(t('chat.sessionCreated'))
    if (isMobile()) sidebarOpen.value = false
  } catch (error) {
    toast.error(t('common.error'))
  }
}

const handleSelectSession = (sessionId: string) => {
  chatStore.switchSession(sessionId)
  if (isMobile()) sidebarOpen.value = false
}

// 两个位置的输入卡会随消息状态互相切换，切换后需要重新同步 textarea
const bindComposerRef = (instance: any) => {
  chatInputRef.value = instance ?? undefined
  const element = instance?.textareaRef as HTMLTextAreaElement | undefined
  if (element) {
    textareaRef.value = element
  }
}

const composerBindings = computed<Record<string, any>>(() => ({
  inputMessage: inputMessage.value,
  isStreaming: isStreaming.value,
  canSend: canSend.value,
  showTeamPicker: showTeamPicker.value,
  filteredTeams: filteredTeams.value,
  teamPickerIndex: teamPickerIndex.value,
  isMac,
  attachments: attachments.value,
  isUploadingAttachments: isUploading.value,
  modelGroups: modelGroups.value,
  activeProviderId: modelSelection.currentProviderId.value,
  activeModelId: modelSelection.currentModelId.value,
  isSessionOverride: modelSelection.isSessionOverride.value,
  reasoningLevels: reasoningLevels.value,
  activeReasoningLevel: modelSelection.currentReasoningLevel.value,
  onInput: (value: string) => {
    inputMessage.value = value
    handleInput()
  },
  onSend: sendMessage,
  onStop: stopGeneration,
  onKeydown: (event: KeyboardEvent) => handleKeydown(event, filteredTeams.value, sendMessage),
  onTeamSelect: selectTeam,
  onFilesSelected: handleComposerFiles,
  onRemoveAttachment: removeAttachment,
  onSelectModel: handleSelectModel,
  onSelectReasoningLevel: handleSelectReasoningLevel,
}))

watch(
  () => messages.value.length === 0,
  async () => {
    await nextTick()
    const element = chatInputRef.value?.textareaRef
    if (element) {
      textareaRef.value = element
    }
  }
)

// 快捷键
useKeyboard([
  commonShortcuts.send(() => {
    if (canSend.value) {
      sendMessage()
    }
  }),
  commonShortcuts.escape(() => {
    if (activePanel.value) {
      closePanel()
    } else if (isMobileSidebarOpen.value) {
      sidebarOpen.value = false
    }
  }),
  commonShortcuts.search(() => {
    showPanel('sessions')
  }),
  commonShortcuts.new(async () => {
    await handleCreateSession()
  }),
  commonShortcuts.toggleSidebar(() => {
    toggleSidebar()
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

    if (chatInputRef.value?.textareaRef) {
      textareaRef.value = chatInputRef.value.textareaRef
    }

    await chatStore.loadSessions()
    agentTeamsStore.loadTeams().catch(() => {})
    await modelSelection.loadGlobalDefaults().catch(() => {})

    if (chatStore.sessions.length === 0) {
      await chatStore.createSession()
    } else if (!chatStore.currentSessionId) {
      chatStore.switchSession(chatStore.sessions[0].id)
    }

    if (chatStore.currentSessionId) {
      initializeChat(chatStore.currentSessionId, false)
      modelSelection.loadSessionSelection(chatStore.currentSessionId).catch(() => {})
    }

    window.addEventListener('beforeunload', handleBeforeUnload)
  } catch (error) {
    console.error('Failed to initialize:', error)
    toast.error(t('common.error'))
  }
})

function handleBeforeUnload() {
  cacheCurrentSession(chatStore.currentSessionId, messages.value.length > 0)
}

onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', handleBeforeUnload)
  closeConnection()
  resetInitializedSession()
  clearPendingMessages()
  clearAttachments()
})
</script>

<style scoped>
@import './styles/NextChatWindow.css';
</style>
