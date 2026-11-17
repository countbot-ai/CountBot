<template>
  <div class="nc-shell">
    <NextRail
      :active-section="activeSection"
      :show-logout="showLogout"
      @select-section="handleSelectSection"
      @open-settings="openSettingsTab"
      @logout="handleLogout"
    />

    <div v-show="isChatView" class="nc-chat-view">
      <NextListPane
        ref="listPaneRef"
        :open="listPaneOpen"
        :sessions="chatStore.sessions"
        :current-session-id="chatStore.currentSessionId"
        :loading="chatStore.isLoadingSessions"
        @create="handleCreateSession"
        @select="handleSelectSession"
        @config="handleOpenSessionConfig"
        @rename="handleRenameSession"
        @delete="handleDeleteSession"
        @close="closeListPane"
      />

      <div class="nc-workspace">
        <NextTopbar
          :title="topbarTitle"
          :has-messages="messages.length > 0"
          :is-streaming="isStreaming"
          @toggle-sidebar="toggleListPane"
          @new-session="handleCreateSession"
          @clear-chat="clearCurrentChat"
          @open-panel="handleOpenTopbarPanel"
          @open-settings="openSettingsTab('general')"
          @open-system="showSystemSidebar = true"
          :show-logout="showLogout"
          @logout="handleLogout"
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
                :workspace-path="currentWorkspacePath"
                @open-workspace="handleOpenWorkspaceConfig"
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
            :tts-enabled="currentCapabilities.tts"
            :tts-provider-id="modelSelection.currentProviderId.value"
            :tts-model-id="modelSelection.currentModelId.value"
            @regenerate="handleRegenerate"
            @delete="handleDelete"
            @resend="handleResend"
            @quote="handleQuote"
            @load-more="handleLoadOlderMessages"
          />
        </main>

        <NextComposer
          v-if="!isLoadingMessages && messages.length > 0"
          :ref="bindComposerRef"
          v-bind="(composerBindings as any)"
          variant="docked"
          :workspace-path="currentWorkspacePath"
          @open-workspace="handleOpenWorkspaceConfig"
        />
      </div>
    </div>

    <!-- 非聊天分区：整屏业务页，聊天窗口不参与渲染 -->
    <HomeSection v-if="pageSection" :section="pageSection" />

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
      v-if="showTimeline || isMobileListOpen"
      class="nc-overlay"
      @click="handleOverlayClick"
    />

    <FilePreviewModal :show="showPreviewModal" :file="previewFile" @close="closePreviewModal" />
  </div>
</template>

<script setup lang="ts">
import { computed, inject, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Upload as UploadIcon } from 'lucide-vue-next'
import { LoadingState, FilePreviewModal } from '@/components/ui'
import MessageList from './MessageList.vue'
import SystemSidebar from '@/modules/system/SystemSidebar.vue'
import TimelinePanel from './TimelinePanel.vue'

// 新主窗口布局组件
import NextRail from './next/NextRail.vue'
import NextListPane from './next/NextListPane.vue'
import NextTopbar from './next/NextTopbar.vue'
import NextWelcome from './next/NextWelcome.vue'
import type { ChatSection, WelcomeQuickAction } from './next/types'
import NextComposer from './next/NextComposer.vue'
import HomeSection from '@/modules/sections/HomeSection.vue'

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
import { buildQuotedContent } from '@/modules/chat/utils/messageQuote'
import type { MessageQuote } from '@/types/chat'

import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { useChatStore } from '@/store/chat'
import { useAgentTeamsStore, type AgentTeam } from '@/store/agentTeams'
import { useSettingsStore } from '@/store/settings'
import { useUserStore } from '@/store/user'
import { useToast } from '@/composables/useToast'
import { useConfirm } from '@/composables/useConfirm'
import { useKeyboard, commonShortcuts } from '@/composables/useKeyboard'
import { authAPI, queueAPI } from '@/api/endpoints'
import type { SettingsTab } from '@/types/settings'

const { t } = useI18n()
const router = useRouter()
const chatStore = useChatStore()
const agentTeamsStore = useAgentTeamsStore()
const userStore = useUserStore()
const toast = useToast()
const { confirm } = useConfirm()

/** 登录态下显示注销入口；本机免登录时隐藏 */
const showLogout = computed(() => userStore.isAuthenticated)

const handleLogout = async () => {
  const ok = await confirm({
    title: t('sidebar.logout') || '注销',
    message: '确认退出当前登录？',
  })
  if (!ok) return
  try {
    await authAPI.logout()
  } catch {
    // 请求失败也要清本地凭据并跳转，否则用户无法退出
  }
  localStorage.removeItem('CountBot_token')
  window.location.href = '/login'
}

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

/** 待引用的消息，发送时拼到正文开头进入上下文 */
const quotedMessage = ref<MessageQuote | null>(null)

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

const isMobile = () => typeof window !== 'undefined' && window.innerWidth <= 860

/** 当前分区：sessions 渲染聊天视图，其余分区渲染整屏业务页 */
const activeSection = ref<ChatSection>('sessions')
const isChatView = computed(() => activeSection.value === 'sessions')
const pageSection = computed(() =>
  activeSection.value === 'sessions' ? null : activeSection.value,
)

/** 聊天视图下的会话列表展开状态；移动端默认收起 */
const listPaneOpen = ref(!isMobile())
const isMobileListOpen = computed(
  () => isMobile() && isChatView.value && listPaneOpen.value,
)

const isStoppingTask = ref(false)
const messageListRef = ref<InstanceType<typeof MessageList>>()
const chatInputRef = ref<InstanceType<typeof NextComposer>>()
const listPaneRef = ref<InstanceType<typeof NextListPane>>()

const showSystemSidebar = ref(false)
const showTimeline = ref(false)
const activeMessageId = ref<string | null>(null)
const showPreviewModal = ref(false)
const previewFile = ref<File | null>(null)

const settingsStore = useSettingsStore()

const currentSession = computed(() =>
  chatStore.sessions.find(session => session.id === chatStore.currentSessionId)
)
const currentSessionName = computed(() => currentSession.value?.name || '')
const topbarTitle = computed(() => (messages.value.length > 0 ? currentSessionName.value : ''))

// 输入框顶部展示实际生效的工作空间：会话自定义优先，否则用全局默认。
// 普通用户工作区由系统自动分配、不可自定义，直接不显示该入口。
const currentWorkspacePath = computed(() => {
  if (!userStore.isAdmin) {
    return ''
  }
  const sessionWorkspace = currentSession.value?.effectiveWorkspacePath
  if (sessionWorkspace) {
    return sessionWorkspace
  }
  return settingsStore.settings?.workspace?.path || ''
})

function handleOpenWorkspaceConfig() {
  if (chatStore.currentSessionId) {
    handleOpenSessionConfig(chatStore.currentSessionId)
    return
  }
  openSettingsTab('workspace')
}

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

/** 顶栏 / 快捷键的折叠开关：非聊天分区先回到聊天，再控制列表 */
const toggleListPane = () => {
  if (!isChatView.value) {
    activeSection.value = 'sessions'
    listPaneOpen.value = true
    return
  }
  listPaneOpen.value = !listPaneOpen.value
}

const closeListPane = () => {
  listPaneOpen.value = false
}

/** 会话再点一次折叠列表；其它分区直接整屏切换 */
const handleSelectSection = (section: ChatSection) => {
  if (section === activeSection.value) {
    if (section === 'sessions') toggleListPane()
    return
  }
  activeSection.value = section
  if (section === 'sessions' && !isMobile()) {
    listPaneOpen.value = true
  }
}

const openSettingsTab = (tab: SettingsTab = 'general') => {
  void router.push({ name: 'settings', params: { tab } })
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
  quotedMessage.value = null
  if (newSessionId) {
    modelSelection.loadSessionSelection(newSessionId).catch(() => {})
    const shouldClear = oldSessionId !== undefined && oldSessionId !== newSessionId
    initializeChat(newSessionId, shouldClear)
  }
})

const sendMessage = () => {
  const text = inputMessage.value.trim()
  const payload = {
    // 引用内容拼在正文前面，作为普通用户消息进入上下文，历史记录里也能原样还原
    content: quotedMessage.value ? buildQuotedContent(quotedMessage.value, text) : text,
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
  quotedMessage.value = null
  sendOrQueueMessage(payload)
}

const handleComposerFiles = async (files: File[]) => {
  await addFiles(files, chatStore.currentSessionId)
}

// 输入框里的模型切换
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
const currentCapabilities = computed(() => modelSelection.currentCapabilities.value)
const chatMode = computed(() => modelSelection.chatMode.value)

const handleSelectReasoningLevel = async (level: string) => {
  try {
    await modelSelection.selectReasoningLevel(chatStore.currentSessionId || '', level)
  } catch (error: any) {
    toast.error(error?.response?.data?.detail || t('chat.reasoningLevel.saveFailed'))
  }
}

const handleSelectChatMode = async (mode: 'agent' | 'chat') => {
  try {
    await modelSelection.selectChatMode(chatStore.currentSessionId || '', mode)
  } catch (error: any) {
    toast.error(error?.response?.data?.detail || t('chat.mode.saveFailed'))
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
        quotedMessage.value = null
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
    if (quotedMessage.value?.id === messageId) {
      quotedMessage.value = null
    }
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

/** 重发：从这条用户消息起截断，原样再发一次 */
const handleResend = (messageId: string) => {
  const messageIndex = messages.value.findIndex(m => m.id === messageId)
  if (messageIndex === -1) return

  const target = messages.value[messageIndex]
  if (target.role !== 'user') return

  const content = target.content
  const attachmentItems = target.attachmentItems || []
  messages.value.splice(messageIndex)

  sendImmediateMessage({ content, attachmentItems })
}

const handleQuote = (quote: MessageQuote) => {
  quotedMessage.value = { ...quote }
  nextTick(() => chatInputRef.value?.textareaRef?.focus())
}

const handleLoadOlderMessages = async () => {
  if (!chatStore.currentSessionId) return
  await loadOlderMessages(chatStore.currentSessionId)
}

const closePreviewModal = () => {
  showPreviewModal.value = false
  previewFile.value = null
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
  if (showTimeline.value) {
    showTimeline.value = false
  } else if (isMobileListOpen.value) {
    closeListPane()
  }
}

const handleSessionConfigUpdated = (action: 'saved' | 'reset') => {
  showSessionConfig.value = false
  // 刷新会话列表以同步自定义工作空间，输入框顶部胶囊立即更新
  chatStore.loadSessions().catch(() => {})
  toast.success(
    action === 'reset'
      ? t('chat.sessionConfig.resetNextMessage')
      : t('chat.sessionConfig.updatedNextMessage')
  )
}

const handleOpenSettings = (section: string) => {
  const sectionToTab: Record<string, SettingsTab> = {
    'provider': 'provider',
    'channels': 'channels',
    'personality': 'persona',
    'teams': 'multiagent',
    'memory': 'memory',
    'multiagent': 'multiagent',
    'model': 'model',
    'persona': 'persona',
    'sharedskills': 'sharedskills'
  }

  openSettingsTab(sectionToTab[section] || 'general')
}

/** 已从设置页剥离的入口：欢迎页快捷方式直接落到对应整屏页 */
const HOME_SECTION_OF: Record<string, ChatSection> = {
  channels: 'channels',
  teams: 'multiagent',
  persona: 'persona',
}

const handleWelcomeAction = (action: WelcomeQuickAction) => {
  if (action.kind === 'panel') {
    activeSection.value = action.value as ChatSection
    return
  }
  const section = HOME_SECTION_OF[action.value]
  if (section) {
    activeSection.value = section
    return
  }
  handleOpenSettings(action.value)
}

const handleCreateSession = async () => {
  try {
    await chatStore.createSession()
    toast.success(t('chat.sessionCreated'))
    activeSection.value = 'sessions'
    if (isMobile()) closeListPane()
  } catch (error) {
    toast.error(t('common.error'))
  }
}

const handleSelectSession = (sessionId: string) => {
  chatStore.switchSession(sessionId)
  activeSection.value = 'sessions'
  if (isMobile()) closeListPane()
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
  nativeCapabilities: currentCapabilities.value,
  chatMode: chatMode.value,
  allowedChatModes: modelSelection.allowedChatModes.value,
  quotedMessage: quotedMessage.value,
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
  onRemoveQuote: () => {
    quotedMessage.value = null
  },
  onSelectModel: handleSelectModel,
  onSelectReasoningLevel: handleSelectReasoningLevel,
  onSelectChatMode: handleSelectChatMode,
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
    if (showTimeline.value) {
      showTimeline.value = false
    } else if (isMobileListOpen.value) {
      closeListPane()
    }
  }),
  commonShortcuts.search(() => {
    activeSection.value = 'sessions'
    listPaneOpen.value = true
    void listPaneRef.value?.focusSearch()
  }),
  commonShortcuts.new(async () => {
    await handleCreateSession()
  }),
  commonShortcuts.toggleSidebar(() => {
    toggleListPane()
  }),
  commonShortcuts.settings(() => {
    openSettingsTab('general')
  })
])

// 初始化
onMounted(async () => {
  try {
    if (chatInputRef.value?.textareaRef) {
      textareaRef.value = chatInputRef.value.textareaRef
    }

    // /api/settings 仅管理员可读，判定前必须先加载 profile
    await userStore.loadProfile().catch(() => undefined)
    if (userStore.isAdmin && !settingsStore.settings) {
      await settingsStore.loadSettings().catch(() => {})
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
