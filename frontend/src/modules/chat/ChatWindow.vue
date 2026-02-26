<template>
  <div
    class="chat-window"
    :class="{ 'resizing': isResizing }"
  >
    <!-- 顶部工具栏 -->
    <header class="header">
      <div class="header-left">
        <h1
          class="title title-clickable brand-title"
          @click="showSystemSidebar = !showSystemSidebar"
        >
          <span class="brand-count">Count</span><span class="brand-bot">Bot</span>
        </h1>
      </div>
      
      <div class="header-right">
        <button
          class="icon-btn clear-chat-btn"
          :title="$t('chat.clearCurrentChat')"
          @click="clearCurrentChat"
        >
          <component
            :is="TrashIcon"
            :size="20"
          />
        </button>
        <div class="divider" />
        <button
          v-for="action in headerActions"
          :key="action.id"
          class="icon-btn"
          :title="$t(action.tooltip || action.label)"
          @click="action.onClick"
        >
          <component
            :is="action.icon"
            :size="20"
          />
        </button>
        <div class="divider" />
        <LanguageSelector />
        <ThemeToggle />
      </div>
    </header>

    <!-- 连接状态条 -->
    <transition name="status-bar">
      <div
        v-if="!isConnected || isConnecting || reconnectingVisible"
        class="connection-status-bar"
        :class="{
          'status-reconnecting': isConnecting || reconnectingVisible,
          'status-disconnected': !isConnected && !isConnecting && !reconnectingVisible
        }"
      >
        <span v-if="isConnecting || reconnectingVisible" class="status-bar-content">
          <span class="status-spinner" />
          正在重连...（第 {{ reconnectAttemptsDisplay }}/10 次）
        </span>
        <span v-else class="status-bar-content">
          连接已断开
          <button class="status-bar-action" @click="manualReconnect">立即重连</button>
        </span>
      </div>
    </transition>

    <!-- 安全警告横幅 -->
    <div
      v-if="securityWarningVisible"
      class="security-warning-banner"
    >
      <div class="security-warning-icon">
        <component :is="ShieldAlertIcon" :size="16" />
      </div>
      <span class="security-warning-text">{{ $t('security.remoteWarning') }}</span>
      <button
        class="security-warning-action"
        @click="showPasswordSetup = true"
      >
        {{ $t('security.setupPassword') }}
      </button>
      <button
        class="security-warning-dismiss"
        :title="$t('common.close')"
        @click="dismissSecurityWarning"
      >
        <component
          :is="XIcon"
          :size="14"
        />
      </button>
    </div>

    <!-- 密码设置对话框 -->
    <div v-if="showPasswordSetup" class="password-dialog-overlay" @click.self="showPasswordSetup = false">
      <div class="password-dialog">
        <div class="password-dialog-header">
          <h3>{{ $t('security.setupPasswordTitle') }}</h3>
          <button class="icon-btn" @click="showPasswordSetup = false">
            <component :is="XIcon" :size="18" />
          </button>
        </div>
        <div class="password-dialog-body">
          <p class="password-dialog-desc">{{ $t('security.setupPasswordDesc') }}</p>
          <div class="password-field">
            <label>{{ $t('security.username') }}</label>
            <input v-model="setupUsername" type="text" :placeholder="$t('security.usernamePlaceholder')" autocomplete="username" />
          </div>
          <div class="password-field">
            <label>{{ $t('security.password') }}</label>
            <input v-model="setupPassword" type="password" :placeholder="$t('security.passwordPlaceholder')" autocomplete="new-password" />
          </div>
          <div class="password-field">
            <label>{{ $t('security.confirmPassword') }}</label>
            <input v-model="setupPasswordConfirm" type="password" :placeholder="$t('security.confirmPasswordPlaceholder')" autocomplete="new-password" @keydown.enter="handleSetupPassword" />
          </div>
          <p v-if="setupError" class="password-error">{{ setupError }}</p>
        </div>
        <div class="password-dialog-footer">
          <button class="btn-cancel" @click="showPasswordSetup = false">{{ $t('common.cancel') }}</button>
          <button class="btn-confirm" :disabled="setupLoading" @click="handleSetupPassword">
            <span v-if="setupLoading" class="spin-small" />
            {{ $t('security.confirm') }}
          </button>
        </div>
      </div>
    </div>

    <!-- 聊天区域 -->
    <main
      class="main"
      @dragenter.prevent="handleMainDragEnter"
      @dragover.prevent="handleMainDragOver"
      @dragleave.prevent="handleMainDragLeave"
      @drop.prevent="handleMainDrop"
    >
      <!-- 加载状态 -->
      <div
        v-if="isLoadingMessages"
        class="loading-container"
      >
        <LoadingState
          type="skeleton"
          :lines="5"
        />
      </div>
      
      <!-- 空状态 -->
      <EmptyState
        v-else-if="messages.length === 0"
        icon="message-square"
        :title="$t('chat.emptyTitle')"
        :description="$t('chat.emptyDescription')"
      />
      
      <!-- 消息列表 (虚拟滚动) -->
      <MessageList
        v-else
        ref="messageListRef"
        :messages="messages"
        :auto-scroll="true"
        @regenerate="handleRegenerate"
        @delete="handleDelete"
      />
    </main>

    <!-- 输入区域 -->
    <footer class="input-area">
      <div
        class="input-container"
        :class="{ focused: isInputFocused }"
      >
        <textarea
          ref="textareaRef"
          v-model="inputMessage"
          :placeholder="$t('chat.inputPlaceholder')"
          class="chat-input"
          rows="1"
          @input="adjustHeight"
          @focus="isInputFocused = true"
          @blur="isInputFocused = false"
          @keydown.enter.exact="handleEnterKey"
          @keydown.shift.enter.exact.prevent="sendMessage"
          @keydown.ctrl.enter.prevent="sendMessage"
          @keydown.meta.enter.prevent="sendMessage"
        />
        <div class="input-actions">
          <button
            v-if="isStreaming"
            class="stop-generation-btn"
            :title="$t('chat.stopGeneration')"
            @click="stopGeneration()"
          >
            <span class="stop-square" />
          </button>
          <button
            v-else
            class="send-message-btn"
            :class="{ ready: canSend }"
            :disabled="!canSend"
            @click="sendMessage()"
          >
            <component
              :is="SendIcon"
              :size="16"
            />
          </button>
        </div>
      </div>
      <p class="input-hint">
        Shift+Enter {{ $t('chat.send') }}，Enter {{ $t('chat.newLine') }}
      </p>
    </footer>

    <!-- Drag and Drop Overlay -->
    <div
      v-if="isDraggingOver"
      class="drag-overlay"
    >
      <div class="drag-overlay-content">
        <component
          :is="UploadIcon"
          :size="64"
          class="drag-overlay-icon"
        />
        <p class="drag-overlay-text">
          {{ $t('chat.releaseToUpload') }}
        </p>
      </div>
    </div>

    <!-- 侧边面板 -->
    <aside
      v-if="activePanel"
      ref="panelRef"
      class="panel"
      :style="{ width: `${panelWidth}px` }"
    >
      <!-- 拖动手柄 -->
      <div
        class="resize-handle"
        @mousedown="startResize"
      >
        <div class="resize-handle-line" />
      </div>
      
      <div class="panel-header">
        <h2 class="panel-title">
          {{ getPanelTitle() }}
        </h2>
        <button
          class="icon-btn"
          @click="closePanel"
        >
          <component
            :is="XIcon"
            :size="20"
          />
        </button>
      </div>
      <div class="panel-body">
        <!-- Sessions Panel -->
        <SessionPanel v-if="activePanel === 'sessions'" />
        
        <!-- Tools Panel -->
        <ToolsPanel v-else-if="activePanel === 'tools'" />
        
        <!-- Memory Panel -->
        <MemoryPanel v-else-if="activePanel === 'memory'" />
        
        <!-- Skills Panel -->
        <SkillsLibrary v-else-if="activePanel === 'skills'" />
        
        <!-- Cron Panel -->
        <CronManager v-else-if="activePanel === 'cron'" />
        
        <!-- Settings Panel -->
        <SettingsPanel
          v-else-if="activePanel === 'settings'"
          @close="closePanel"
          @saved="handleSettingsSaved"
        />
        
        <!-- Other Panels (Coming Soon) -->
        <p
          v-else
          class="panel-placeholder"
        >
          {{ $t('common.comingSoon') }}
        </p>
      </div>
    </aside>

    <!-- 左侧系统信息侧边栏 -->
    <SystemSidebar
      :visible="showSystemSidebar"
      @close="showSystemSidebar = false"
    />

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
    <FilePreviewModal
      :show="showPreviewModal"
      :file="previewFile"
      @close="closePreviewModal"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted, onBeforeUnmount, watch, inject } from 'vue'
import {
  History as HistoryIcon,
  Wrench as ToolsIcon,
  Brain as BrainIcon,
  Zap as ZapIcon,
  Clock as ClockIcon,
  Settings as SettingsIcon,
  Send as SendIcon,
  X as XIcon,
  Loader2 as LoaderIcon,
  Upload as UploadIcon,
  Download as DownloadIcon,
  ShieldAlert as ShieldAlertIcon,
  Trash2 as TrashIcon,
  List as ListIcon
} from 'lucide-vue-next'
import ThemeToggle from '@/components/ui/ThemeToggle.vue'
import LanguageSelector from '@/components/ui/LanguageSelector.vue'
import { LoadingState, EmptyState, FileSelector, FilePreviewModal } from '@/components/ui'
import MessageItem from './MessageItem.vue'
import MessageList from './MessageList.vue'
import SessionPanel from './SessionPanel.vue'
import SettingsPanel from '@/modules/settings/SettingsPanel.vue'
import ToolsPanel from '@/modules/tools/ToolsPanel.vue'
import MemoryPanel from '@/modules/memory/MemoryPanel.vue'
import SkillsLibrary from '@/modules/skills/SkillsLibrary.vue'
import CronManager from '@/modules/scheduler/CronManager.vue'
import SystemSidebar from '@/modules/system/SystemSidebar.vue'
import TimelinePanel from './TimelinePanel.vue'
import { useI18n } from 'vue-i18n'
import { useChatStore } from '@/store/chat'
import { useToolsStore } from '@/store/tools'
import { useToast } from '@/composables/useToast'
import { useKeyboard, commonShortcuts } from '@/composables/useKeyboard'
import { toolsAPI, authAPI } from '@/api/endpoints'

// 导入停止 API
import { stopAPI } from '@/api/endpoints'

const { t } = useI18n()
const chatStore = useChatStore()
const toolsStore = useToolsStore()
const toast = useToast()

// 安全警告
const showSecurityWarning = inject<import('vue').Ref<boolean>>('showSecurityWarning', ref(false))
const securityWarningDismissed = ref(false)
const securityWarningVisible = computed(() => showSecurityWarning.value && !securityWarningDismissed.value)
const dismissSecurityWarning = () => { securityWarningDismissed.value = true }

// 密码设置对话框
const showPasswordSetup = ref(false)
const setupUsername = ref('admin')
const setupPassword = ref('')
const setupPasswordConfirm = ref('')
const setupError = ref('')
const setupLoading = ref(false)

const handleSetupPassword = async () => {
  setupError.value = ''
  if (!setupUsername.value.trim()) {
    setupError.value = t('security.errorUsernameRequired')
    return
  }
  if (setupPassword.value !== setupPasswordConfirm.value) {
    setupError.value = t('security.errorPasswordMismatch')
    return
  }
  if (setupPassword.value.length < 8 || !/[A-Z]/.test(setupPassword.value) || !/[a-z]/.test(setupPassword.value) || !/\d/.test(setupPassword.value)) {
    setupError.value = t('security.errorPasswordWeak')
    return
  }
  setupLoading.value = true
  try {
    const result = await authAPI.setup({ username: setupUsername.value.trim(), password: setupPassword.value })
    if (result.success && result.token) {
      localStorage.setItem('CountBot_token', result.token)
    }
    showPasswordSetup.value = false
    securityWarningDismissed.value = true
    showSecurityWarning.value = false
    toast.success(t('security.setupSuccess'))
    // 重置表单
    setupPassword.value = ''
    setupPasswordConfirm.value = ''
  } catch (err: any) {
    setupError.value = err?.message || err?.details?.detail || t('common.error')
  } finally {
    setupLoading.value = false
  }
}

type PanelType = 'sessions' | 'tools' | 'memory' | 'skills' | 'cron' | 'settings' | null

// Initialize chat composable with reactive session ID
const messages = ref<any[]>([])
const isStreaming = ref(false)
const isConnected = ref(true)
const isConnecting = ref(false)
const isLoadingMessages = ref(false)

let ws: WebSocket | null = null
let currentStreamingMessage: any = null
let heartbeatInterval: number | null = null
let currentConnectedSessionId: string | null = null
let reconnectAttempts = 0
const maxReconnectAttempts = 10
const baseReconnectDelay = 1000 // 1秒
const reconnectingVisible = ref(false)
const reconnectAttemptsDisplay = ref(0)
let heartbeatFailures = 0
const maxHeartbeatFailures = 3

// 消息队列：当AI正在回复时，用户发送的消息会排队等待
let pendingMessages: string[] = []
// 停止标记：停止后忽略后续到达的chunk
let isStopping = false

// 心跳机制
function startHeartbeat() {
  if (heartbeatInterval) {
    clearInterval(heartbeatInterval)
  }
  
  heartbeatFailures = 0
  
  heartbeatInterval = window.setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      try {
        ws.send(JSON.stringify({ type: 'ping' }))
      } catch (error) {
        heartbeatFailures++
        
        if (heartbeatFailures >= maxHeartbeatFailures) {
          stopHeartbeat()
        }
      }
    }
  }, 30000)
}

function stopHeartbeat() {
  if (heartbeatInterval) {
    clearInterval(heartbeatInterval)
    heartbeatInterval = null
  }
}

// 计算重连延迟（指数退避）
function getReconnectDelay(): number {
  // 指数退避: 1s, 2s, 4s, 8s, 16s, 最大30s
  const delay = Math.min(
    baseReconnectDelay * Math.pow(2, reconnectAttempts),
    30000
  )
  return delay
}

// 检查服务器是否就绪
async function isServerReady(): Promise<boolean> {
  try {
    const response = await fetch('/api/health', {
      method: 'GET',
      signal: AbortSignal.timeout(2000)
    })
    return response.ok
  } catch {
    return false
  }
}

// 带健康检查的重连
async function reconnectWithHealthCheck(sessionId: string) {
  reconnectingVisible.value = true
  reconnectAttemptsDisplay.value = reconnectAttempts + 1
  const ready = await isServerReady()
  
  if (ready) {
    reconnectAttempts = 0
    reconnectingVisible.value = false
    connectWebSocket(sessionId)
  } else {
    if (reconnectAttempts < maxReconnectAttempts) {
      const delay = getReconnectDelay()
      reconnectAttempts++
      reconnectAttemptsDisplay.value = reconnectAttempts
      
      setTimeout(() => {
        if (chatStore.currentSessionId && !ws) {
          reconnectWithHealthCheck(chatStore.currentSessionId)
        }
      }, delay)
    } else {
      reconnectingVisible.value = false
      toast.error('连接失败，请点击状态条重试或刷新页面')
    }
  }
}

// 手动重连
function manualReconnect() {
  if (chatStore.currentSessionId) {
    reconnectAttempts = 0
    reconnectWithHealthCheck(chatStore.currentSessionId)
  }
}

// WebSocket 连接
function connectWebSocket(sessionId: string) {
  // 防止重复连接同一个session
  if (currentConnectedSessionId === sessionId && ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return
  }

  // 先关闭现有连接
  if (ws) {
    stopHeartbeat()
    ws.close()
    ws = null
    currentConnectedSessionId = null
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.host
  const wsUrl = `${protocol}//${host}/ws/chat`

  isConnecting.value = true

  ws = new WebSocket(wsUrl)

  ws.onopen = () => {
    isConnected.value = true
    isConnecting.value = false
    reconnectingVisible.value = false
    currentConnectedSessionId = sessionId
    reconnectAttempts = 0

    // 启动心跳
    startHeartbeat()

    // 订阅会话
    let retryCount = 0
    const maxRetries = 3
    
    const trySubscribe = () => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          type: 'subscribe',
          sessionId: sessionId
        }))
      } else if (retryCount < maxRetries) {
        retryCount++
        setTimeout(trySubscribe, 200)
      } else {
        console.error('[ChatWindow] 订阅失败')
        toast.error('订阅会话失败，请刷新页面')
      }
    }
    
    setTimeout(trySubscribe, 100)
  }

  ws.onmessage = (event) => {
    try {
      const message = JSON.parse(event.data)

      // 处理pong响应
      if (message.type === 'pong') {
        heartbeatFailures = 0
        return
      }

      if (message.type === 'message_chunk') {
        // 停止后忽略后续chunk
        if (isStopping) return
        
        if (!currentStreamingMessage || currentStreamingMessage.isThinking) {
          if (currentStreamingMessage && currentStreamingMessage.isThinking) {
            // 复用占位消息，移除 thinking 状态
            const index = messages.value.findIndex(m => m.id === currentStreamingMessage.id)
            if (index !== -1) {
              messages.value[index].isThinking = false
              messages.value[index].content = message.content || ''
              currentStreamingMessage = messages.value[index]
            }
          } else {
            // 创建新消息
            const newMessage = {
              id: `temp-${Date.now()}`,
              role: 'assistant',
              content: message.content || '',
              timestamp: new Date(),
              toolCalls: []
            }
            messages.value.push(newMessage)
            currentStreamingMessage = newMessage
          }
          isStreaming.value = true
        } else {
          // 更新内容 - 直接修改对象属性以确保响应式
          const index = messages.value.findIndex(m => m.id === currentStreamingMessage.id)
          if (index !== -1) {
            messages.value[index].content += (message.content || '')
            currentStreamingMessage = messages.value[index]
          }
        }
        
        // 立即滚动到底部
        nextTick(() => {
          if (messageListRef.value?.isAtBottom()) {
            messageListRef.value?.scrollToBottom(false)
          }
        })
      } else if (message.type === 'tool_call') {
        // 工具调用通知 - 使用 messageId 关联
        if (!isStreaming.value) {
          isStreaming.value = true
        }
        
        const toolCallId = `${Date.now()}-${message.tool}`
        const messageId = message.messageId || null
        
        // 添加工具调用到当前消息
        if (currentStreamingMessage) {
          const index = messages.value.findIndex(m => m.id === currentStreamingMessage.id)
          if (index !== -1) {
            // 如果是思考中占位消息，移除 thinking 状态
            if (messages.value[index].isThinking) {
              messages.value[index].isThinking = false
            }
            if (!messages.value[index].toolCalls) {
              messages.value[index].toolCalls = []
            }
            
            const exists = messages.value[index].toolCalls.some(
              tc => tc.name === message.tool && tc.status === 'running'
            )
            
            if (!exists) {
              const newToolCall = {
                id: toolCallId,
                name: message.tool,
                arguments: message.arguments,
                status: 'running',
                messageId: messageId
              }
              
              messages.value[index].toolCalls = [...messages.value[index].toolCalls, newToolCall]
              messages.value = [...messages.value]
            }
          }
        } else {
          const toolMessage = {
            id: `tool-${Date.now()}`,
            role: 'assistant',
            content: '',
            timestamp: new Date(),
            toolCalls: [{
              id: toolCallId,
              name: message.tool,
              arguments: message.arguments,
              status: 'running',
              messageId: messageId
            }]
          }
          messages.value.push(toolMessage)
          currentStreamingMessage = toolMessage
        }
      } else if (message.type === 'tool_result') {
        // 工具结果通知
        if (currentStreamingMessage && currentStreamingMessage.toolCalls) {
          const index = messages.value.findIndex(m => m.id === currentStreamingMessage.id)
          if (index !== -1) {
            const toolCalls = messages.value[index].toolCalls
            for (let i = toolCalls.length - 1; i >= 0; i--) {
              if (toolCalls[i].name === message.tool && toolCalls[i].status === 'running') {
                const updatedToolCall = {
                  ...toolCalls[i],
                  status: 'success',
                  result: message.result,
                  duration: message.duration
                }
                
                const newToolCalls = [...toolCalls]
                newToolCalls[i] = updatedToolCall
                messages.value[index].toolCalls = newToolCalls
                messages.value = [...messages.value]
                break
              }
            }
          }
        }
      } else if (message.type === 'message_complete') {
        currentStreamingMessage = null
        isStreaming.value = false
        isStopping = false
        
        // 处理排队的消息
        if (pendingMessages.length > 0) {
          const nextMsg = pendingMessages.shift()!
          // 延迟发送，让UI有时间更新
          setTimeout(() => sendQueuedMessage(nextMsg), 100)
        }
      } else if (message.type === 'error') {
        console.error('[ChatWindow] Error:', message.message)
        toast.error(message.message || '发生错误')
        currentStreamingMessage = null
        isStreaming.value = false
        isStopping = false
      }
    } catch (error) {
      console.error('[ChatWindow] 解析消息失败:', error)
    }
  }

  ws.onerror = (error) => {
    console.error('[ChatWindow] WebSocket error:', error)
    isConnected.value = false
    isConnecting.value = false
    stopHeartbeat()
    // 不再只报错，onclose 会处理重连
  }

  ws.onclose = (event) => {
    isConnected.value = false
    isConnecting.value = false
    
    const sessionToReconnect = currentConnectedSessionId
    currentConnectedSessionId = null
    stopHeartbeat()
    
    if (currentStreamingMessage) {
      currentStreamingMessage = null
      isStreaming.value = false
    }
    
    if (event.code === 1000 || event.code === 1001) {
      reconnectAttempts = 0
      reconnectingVisible.value = false
    } else if (event.code === 1012) {
      reconnectingVisible.value = true
      reconnectAttemptsDisplay.value = 1
      
      if (sessionToReconnect) {
        setTimeout(() => {
          if (!ws && chatStore.currentSessionId === sessionToReconnect) {
            reconnectWithHealthCheck(sessionToReconnect)
          }
        }, 2000)
      }
    } else {
      if (reconnectAttempts < maxReconnectAttempts && sessionToReconnect) {
        const delay = getReconnectDelay()
        reconnectAttempts++
        reconnectingVisible.value = true
        reconnectAttemptsDisplay.value = reconnectAttempts
        
        setTimeout(() => {
          if (!ws && chatStore.currentSessionId === sessionToReconnect) {
            connectWebSocket(sessionToReconnect)
          }
        }, delay)
      } else if (reconnectAttempts >= maxReconnectAttempts) {
        reconnectingVisible.value = false
      }
    }
  }
}

// Initialize or reinitialize chat when session changes
let lastInitializedSessionId: string | null = null

function initializeChat(sessionId: string) {
  // 防止重复初始化同一个session
  if (sessionId === lastInitializedSessionId) {
    return
  }
  
  lastInitializedSessionId = sessionId
  
  // 清空当前消息
  messages.value = []
  currentStreamingMessage = null
  
  // 连接 WebSocket
  connectWebSocket(sessionId)
  
  // 加载历史消息
  loadSessionMessages(sessionId)
}

// Load messages from backend
async function loadSessionMessages(sessionId: string) {
  try {
    isLoadingMessages.value = true
    
    // 并行加载消息和工具调用历史（备用，用于没有 message_id 的旧数据）
    const [historyMessages, toolHistory] = await Promise.all([
      chatStore.loadMessages(sessionId),
      toolsAPI.getConversations({ 
        session_id: sessionId,
        limit: 200
      }).catch(() => ({ conversations: [] })) // 如果失败，返回空数组
    ])
    
    // 确保 messages 是数组
    if (Array.isArray(historyMessages)) {
      messages.value = historyMessages.map(m => ({
        id: String(m.id),
        role: m.role,
        content: m.content,
        timestamp: m.createdAt.includes('+') || m.createdAt.includes('Z')
          ? new Date(m.createdAt)
          : new Date(m.createdAt + 'Z'),
        // 使用 API 返回的 tool_calls，如果没有则为空数组
        toolCalls: m.toolCalls?.map((tc: any) => ({
          id: tc.id,
          name: tc.name,
          arguments: tc.arguments,
          result: tc.result,
          error: tc.error,
          status: tc.status || (tc.error ? 'error' : 'success'),
          duration: tc.duration
        })) || []
      }))
      
      // 将工具调用历史关联到消息
      if (toolHistory && toolHistory.conversations.length > 0) {
        // 构建工具调用对象
        const buildToolCallObj = (tc: any) => ({
          id: tc.id,
          name: tc.tool_name,
          arguments: tc.arguments,
          result: tc.result,
          error: tc.error,
          status: tc.error ? 'error' : 'success',
          duration: tc.duration_ms
        })
        
        // 分离有 message_id 和没有 message_id 的工具调用
        const withMsgId: any[] = []
        const withoutMsgId: any[] = []
        
        toolHistory.conversations.forEach(tc => {
          if (tc.message_id) {
            withMsgId.push(tc)
          } else {
            withoutMsgId.push(tc)
          }
        })
        
        if (withMsgId.length > 0) {
          const byMsgId = new Map()
          withMsgId.forEach(tc => {
            const mid = tc.message_id
            if (!byMsgId.has(mid)) byMsgId.set(mid, [])
            byMsgId.get(mid).push(buildToolCallObj(tc))
          })
          
          messages.value.forEach(msg => {
            const mid = parseInt(msg.id)
            // 只在消息没有 toolCalls 时才使用备用数据
            if (byMsgId.has(mid) && (!msg.toolCalls || msg.toolCalls.length === 0)) {
              msg.toolCalls = byMsgId.get(mid)
            }
          })
        }
        
        // 2. 没有 message_id 的用时间戳关联（兼容旧数据，仅用于没有 toolCalls 的消息）
        if (withoutMsgId.length > 0) {
          // 获取所有 assistant 消息及其时间范围
          const assistantMsgs = messages.value
            .map((msg, idx) => ({ msg, idx }))
            .filter(item => item.msg.role === 'assistant' && (!item.msg.toolCalls || item.msg.toolCalls.length === 0))
          
          if (assistantMsgs.length > 0) {
            // 按时间排序工具调用
            const sorted = [...withoutMsgId].sort((a, b) =>
              new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
            )
            
            sorted.forEach(tc => {
              const tcTime = new Date(tc.timestamp).getTime()
              
              // 找到时间上最接近的 assistant 消息
              // 策略：找到工具调用时间之后最近的 assistant 消息
              // （因为 assistant 消息在工具调用完成后才保存）
              let target = null
              for (const item of assistantMsgs) {
                const msgTime = new Date(item.msg.timestamp).getTime()
                if (msgTime >= tcTime) {
                  target = item.msg
                  break
                }
              }
              
              // 如果没找到之后的，取最后一个 assistant 消息
              if (!target) {
                target = assistantMsgs[assistantMsgs.length - 1].msg
              }
              
              if (target) {
                if (!target.toolCalls) target.toolCalls = []
                // 避免重复添加
                const exists = target.toolCalls.some(t => t.id === tc.id)
                if (!exists) {
                  target.toolCalls.push(buildToolCallObj(tc))
                }
              }
            })
          }
        }
      }
    } else {
      messages.value = []
    }
  } catch (error) {
    console.error('[ChatWindow] 加载消息失败:', error)
    messages.value = []
  } finally {
    isLoadingMessages.value = false
  }
}

// Watch for session changes
watch(() => chatStore.currentSessionId, (newSessionId) => {
  if (newSessionId) {
    initializeChat(newSessionId)
  }
})

const inputMessage = ref('')
const textareaRef = ref<HTMLTextAreaElement>()
const messageListRef = ref<InstanceType<typeof MessageList>>()
const panelRef = ref<HTMLElement>()
const fileSelectorRef = ref<InstanceType<typeof FileSelector>>()
const activePanel = ref<PanelType>(null)
const selectedFiles = ref<File[]>([])
const showSystemSidebar = ref(false)
const showTimeline = ref(false)
const activeMessageId = ref<string | null>(null)
const isDraggingOver = ref(false)
const isInputFocused = ref(false)
const dragCounter = ref(0)
const showPreviewModal = ref(false)
const previewFile = ref<File | null>(null)

// 面板宽度调整
const panelWidth = ref(560) // 默认宽度
const isResizing = ref(false)
const minPanelWidth = 380 // 最小宽度
const maxPanelWidth = 1200 // 最大宽度

const canSend = computed(() => {
  return inputMessage.value.trim() && 
         isConnected.value &&
         ws !== null &&
         ws.readyState === WebSocket.OPEN
})

const headerActions = computed(() => [
  { id: 'sessions', icon: HistoryIcon, label: 'nav.sessions', tooltip: 'nav.sessionsTooltip', onClick: () => showPanel('sessions') },
  // { id: 'tools', icon: ToolsIcon, label: 'nav.tools', onClick: () => showPanel('tools') }, // 隐藏工具面板
  { id: 'memory', icon: BrainIcon, label: 'nav.memory', tooltip: 'nav.memoryTooltip', onClick: () => showPanel('memory') },
  { id: 'skills', icon: ZapIcon, label: 'nav.skills', tooltip: 'nav.skillsTooltip', onClick: () => showPanel('skills') },
  { id: 'cron', icon: ClockIcon, label: 'nav.cron', tooltip: 'nav.cronTooltip', onClick: () => showPanel('cron') },
  { id: 'timeline', icon: ListIcon, label: 'nav.timeline', tooltip: 'nav.timelineTooltip', onClick: () => toggleTimeline() },
  { id: 'settings', icon: SettingsIcon, label: 'settings.title', tooltip: 'nav.settingsTooltip', onClick: () => showPanel('settings') }
])

const sendMessage = () => {
  if (!ws || ws.readyState !== WebSocket.OPEN || !isConnected.value) {
    // 自动重连而非要求手动刷新
    const message = inputMessage.value.trim()
    if (!message) return
    
    toast.warning('连接已断开，正在自动重连...')
    
    if (chatStore.currentSessionId) {
      // 将消息暂存，重连成功后自动发送
      const pendingMsg = message
      inputMessage.value = ''
      if (textareaRef.value) {
        textareaRef.value.style.height = 'auto'
      }
      
      // 先显示用户消息
      messages.value.push({
        id: `user-${Date.now()}`,
        role: 'user',
        content: pendingMsg,
        timestamp: new Date(),
        queued: true
      })
      
      // 监听重连成功后自动发送
      const unwatch = watch(isConnected, (connected) => {
        if (connected && ws && ws.readyState === WebSocket.OPEN) {
          unwatch()
          setTimeout(() => {
            sendQueuedMessage(pendingMsg)
          }, 300)
        }
      })
      
      // 超时清理 watcher（60秒）
      setTimeout(() => {
        unwatch()
      }, 60000)
      
      // 触发重连
      reconnectAttempts = 0
      reconnectWithHealthCheck(chatStore.currentSessionId)
    } else {
      toast.error('无法重连，请刷新页面')
    }
    return
  }
  
  const message = inputMessage.value.trim()
  if (!message) return
  
  inputMessage.value = ''
  if (textareaRef.value) {
    textareaRef.value.style.height = 'auto'
  }

  // 清除文件
  if (selectedFiles.value.length > 0) {
    fileSelectorRef.value?.clearFiles()
    selectedFiles.value = []
  }

  // 如果正在流式传输，将消息加入队列
  if (isStreaming.value) {
    pendingMessages.push(message)
    // 显示用户消息到界面
    messages.value.push({
      id: `user-${Date.now()}`,
      role: 'user',
      content: message,
      timestamp: new Date(),
      queued: true
    })
    toast.info(`消息已排队 (${pendingMessages.length})`)
    nextTick(() => {
      messageListRef.value?.scrollToBottom()
    })
    return
  }

  // 直接发送
  doSendMessage(message)
}

// 清空当前对话
async function clearCurrentChat() {
  if (messages.value.length === 0) {
    toast.info(t('chat.noMessagesToClear'))
    return
  }
  
  // 确认对话框
  if (!confirm(t('chat.confirmClearChat'))) {
    return
  }
  
  try {
    // 清空本地消息
    messages.value = []
    
    // 如果有当前会话，也清空服务器端的消息
    if (chatStore.currentSessionId) {
      await chatStore.clearMessages(chatStore.currentSessionId)
    }
    
    toast.success(t('chat.chatCleared'))
  } catch (error) {
    console.error('Failed to clear chat:', error)
    toast.error(t('chat.clearChatFailed'))
  }
}

// 发送排队的消息
function sendQueuedMessage(message: string) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return
  doSendMessage(message)
}

// 实际发送消息
function doSendMessage(message: string) {
  // 添加用户消息（如果还没添加过，即非排队消息）
  const existingQueued = messages.value.find(
    m => m.role === 'user' && m.content === message && m.queued
  )
  if (existingQueued) {
    // 移除排队标记
    delete existingQueued.queued
  } else {
    messages.value.push({
      id: `user-${Date.now()}`,
      role: 'user',
      content: message,
      timestamp: new Date()
    })
  }

  const payload = {
    type: 'message',
    sessionId: chatStore.currentSessionId,
    content: message
  }
  
  try {
    ws!.send(JSON.stringify(payload))
    isStreaming.value = true
    
    // 立即添加一个空的 assistant 消息作为占位，显示"思考中"状态
    const placeholderId = `assistant-${Date.now()}`
    messages.value.push({
      id: placeholderId,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      isThinking: true
    })
    currentStreamingMessage = messages.value[messages.value.length - 1]
    
  } catch (error) {
    console.error('[ChatWindow] 发送消息失败:', error)
    toast.error('发送失败，请重试')
    return
  }

  nextTick(() => {
    messageListRef.value?.scrollToBottom()
  })
}

// 停止生成
const stopGeneration = async () => {
  if (!isStreaming.value || !chatStore.currentSessionId) {
    return
  }

  isStopping = true

  try {
    const result = await stopAPI.stopTask(chatStore.currentSessionId)
    
    if (result.success) {
      toast.success('已停止生成')
      // 标记当前流式消息的工具调用为已取消
      if (currentStreamingMessage?.toolCalls) {
        const index = messages.value.findIndex(m => m.id === currentStreamingMessage.id)
        if (index !== -1) {
          messages.value[index].toolCalls = messages.value[index].toolCalls.map(tc => 
            tc.status === 'running' ? { ...tc, status: 'cancelled' } : tc
          )
          messages.value = [...messages.value]
        }
      }
      currentStreamingMessage = null
      isStreaming.value = false
      isStopping = false
      
      // 处理排队的消息
      if (pendingMessages.length > 0) {
        const nextMsg = pendingMessages.shift()!
        setTimeout(() => sendQueuedMessage(nextMsg), 300)
      }
    } else {
      isStopping = false
      toast.warning(result.message || '没有正在执行的任务')
    }
  } catch (error) {
    isStopping = false
    console.error('[ChatWindow] 停止生成失败:', error)
    toast.error('停止失败，请重试')
  }
}

const handleFilesChange = (files: File[]) => {
  selectedFiles.value = files
}

const handleFileError = (message: string) => {
  toast.error(message)
}

const handleFilePreview = (file: File) => {
  previewFile.value = file
  showPreviewModal.value = true
}

const closePreviewModal = () => {
  showPreviewModal.value = false
  previewFile.value = null
}

// Drag and drop handlers
const handleMainDragEnter = (e: DragEvent) => {
  if (!isConnected.value || isStreaming.value) return
  
  dragCounter.value++
  
  if (e.dataTransfer?.types.includes('Files')) {
    isDraggingOver.value = true
  }
}

const handleMainDragOver = (e: DragEvent) => {
  if (!isConnected.value || isStreaming.value) return
  
  if (e.dataTransfer) {
    e.dataTransfer.dropEffect = 'copy'
  }
}

const handleMainDragLeave = (e: DragEvent) => {
  if (!isConnected.value || isStreaming.value) return
  
  dragCounter.value--
  
  if (dragCounter.value === 0) {
    isDraggingOver.value = false
  }
}

const handleMainDrop = (e: DragEvent) => {
  if (!isConnected.value || isStreaming.value) return
  
  isDraggingOver.value = false
  dragCounter.value = 0
  
  const files = Array.from(e.dataTransfer?.files || [])
  
  if (files.length === 0) return
  
  // Validate and add files
  const maxSize = 10 * 1024 * 1024 // 10MB
  const maxFiles = 5
  
  // Check file count
  const totalFiles = selectedFiles.value.length + files.length
  if (totalFiles > maxFiles) {
    toast.error(t('chat.fileSelectorMaxFiles', { max: maxFiles }))
    return
  }
  
  // Check file sizes
  const invalidFiles = files.filter(file => file.size > maxSize)
  if (invalidFiles.length > 0) {
    const formatFileSize = (bytes: number): string => {
      if (bytes === 0) return '0 B'
      const k = 1024
      const sizes = ['B', 'KB', 'MB', 'GB']
      const i = Math.floor(Math.log(bytes) / Math.log(k))
      return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`
    }
    
    toast.error(t('chat.fileSelectorMaxSize', { 
      max: formatFileSize(maxSize),
      file: invalidFiles[0].name 
    }))
    return
  }
  
  // Add files to selector
  selectedFiles.value.push(...files)
  
  // Notify file selector to update its display
  if (fileSelectorRef.value) {
    // The FileSelector component will handle the display
    handleFilesChange(selectedFiles.value)
  }
  
  toast.success(t('chat.filesAdded', { count: files.length }))
}

const handleRegenerate = (messageId: string) => {
  const messageIndex = messages.value.findIndex(m => m.id === messageId)
  if (messageIndex <= 0) return
  
  // Find the last user message before this assistant message
  for (let i = messageIndex - 1; i >= 0; i--) {
    if (messages.value[i].role === 'user') {
      const userMessage = messages.value[i].content
      
      // Remove the assistant message and all messages after it
      messages.value.splice(messageIndex)
      
      // Resend the user message
      if (ws && ws.readyState === WebSocket.OPEN && chatStore.currentSessionId) {
        ws.send(JSON.stringify({
          type: 'message',
          sessionId: chatStore.currentSessionId,
          content: userMessage
        }))
      }
      
      // Auto-scroll to bottom
      nextTick(() => {
        messageListRef.value?.scrollToBottom()
      })
      
      break
    }
  }
}

const handleDelete = async (messageId: string) => {
  if (!chatStore.currentSessionId) return
  
  try {
    // 从本地消息列表中删除
    const messageIndex = messages.value.findIndex(m => m.id === messageId)
    if (messageIndex === -1) return
    
    messages.value.splice(messageIndex, 1)
    
    // 调用API删除服务器端的消息
    await chatStore.deleteMessage(chatStore.currentSessionId, parseInt(messageId))
    
    toast.success(t('chat.messageDeleted') || '消息已删除')
  } catch (error) {
    console.error('Failed to delete message:', error)
    toast.error(t('chat.deleteMessageFailed') || '删除消息失败')
    
    // 重新加载消息以恢复状态
    if (chatStore.currentSessionId) {
      await loadSessionMessages(chatStore.currentSessionId)
    }
  }
}

const adjustHeight = () => {
  nextTick(() => {
    if (textareaRef.value) {
      textareaRef.value.style.height = 'auto'
      textareaRef.value.style.height = `${Math.min(textareaRef.value.scrollHeight, 160)}px`
    }
  })
}

// 处理回车键：单独回车换行，不发送消息
const handleEnterKey = (e: KeyboardEvent) => {
  // 单独按回车键时，不阻止默认行为，允许换行
  // 浏览器会自动插入换行符
  adjustHeight()
}

const showPanel = (panel: Exclude<PanelType, null>) => {
  activePanel.value = panel
}

const closePanel = () => {
  activePanel.value = null
}

const toggleTimeline = () => {
  showTimeline.value = !showTimeline.value
  if (showTimeline.value && activePanel.value) {
    activePanel.value = null
  }
}

const handleTimelineScrollTo = (messageId: string) => {
  activeMessageId.value = messageId
  messageListRef.value?.scrollToMessage(messageId)
  
  // 3秒后清除高亮
  setTimeout(() => {
    activeMessageId.value = null
  }, 3000)
}

// 设置保存后重连 WebSocket，使新的 provider 配置生效
const handleSettingsSaved = () => {
  if (chatStore.currentSessionId) {
    // 关闭旧连接，强制重新创建 provider
    if (ws) {
      stopHeartbeat()
      ws.close()
      ws = null
      currentConnectedSessionId = null
      lastInitializedSessionId = null
    }
    // 短暂延迟后重连，等后端配置刷新
    setTimeout(() => {
      if (chatStore.currentSessionId) {
        initializeChat(chatStore.currentSessionId)
      }
    }, 500)
  }
}

// 拖动调整面板宽度
const startResize = (e: MouseEvent) => {
  e.preventDefault()
  isResizing.value = true
  
  const startX = e.clientX
  const startWidth = panelWidth.value
  
  const handleMouseMove = (e: MouseEvent) => {
    const deltaX = startX - e.clientX
    const newWidth = Math.min(
      Math.max(startWidth + deltaX, minPanelWidth),
      maxPanelWidth
    )
    panelWidth.value = newWidth
  }
  
  const handleMouseUp = () => {
    isResizing.value = false
    document.removeEventListener('mousemove', handleMouseMove)
    document.removeEventListener('mouseup', handleMouseUp)
    
    // 保存宽度到 localStorage
    localStorage.setItem('panelWidth', panelWidth.value.toString())
  }
  
  document.addEventListener('mousemove', handleMouseMove)
  document.addEventListener('mouseup', handleMouseUp)
}

const getPanelTitle = () => {
  const titles: Record<Exclude<PanelType, null>, string> = {
    sessions: t('nav.sessions'),
    tools: t('nav.tools'),
    memory: t('nav.memory'),
    skills: t('nav.skills'),
    cron: t('nav.cron'),
    settings: t('settings.title')
  }
  return activePanel.value ? titles[activePanel.value] : ''
}

// 快捷键支持
useKeyboard([
  // Ctrl/Cmd + Enter: 发送消息
  commonShortcuts.send(() => {
    if (canSend.value) {
      sendMessage()
    }
  }),
  // Escape: 关闭侧边栏
  commonShortcuts.escape(() => {
    if (activePanel.value) {
      closePanel()
    }
  }),
  // Ctrl/Cmd + K: 快速搜索（打开会话面板）
  commonShortcuts.search(() => {
    showPanel('sessions')
  }),
  // Ctrl/Cmd + N: 新建会话
  commonShortcuts.new(async () => {
    try {
      await chatStore.createSession()
      toast.success(t('chat.sessionCreated'))
    } catch (error) {
      toast.error(t('common.error'))
    }
  }),
  // Ctrl/Cmd + /: 切换侧边栏
  commonShortcuts.toggleSidebar(() => {
    if (activePanel.value) {
      closePanel()
    } else {
      showPanel('sessions')
    }
  }),
  // Ctrl/Cmd + ,: 打开设置
  commonShortcuts.settings(() => {
    showPanel('settings')
  })
])

// Initialize on mount
onMounted(async () => {
  try {
    // 恢复保存的面板宽度
    const savedWidth = localStorage.getItem('panelWidth')
    if (savedWidth) {
      panelWidth.value = parseInt(savedWidth, 10)
    }
    
    // Load sessions
    await chatStore.loadSessions()
    
    // If no sessions exist, create one
    if (chatStore.sessions.length === 0) {
      await chatStore.createSession()
    } else if (!chatStore.currentSessionId) {
      // Set first session as current
      chatStore.switchSession(chatStore.sessions[0].id)
    }
    
    // Initialize chat with current session
    if (chatStore.currentSessionId) {
      initializeChat(chatStore.currentSessionId)
    }
  } catch (error) {
    console.error('Failed to initialize:', error)
    toast.error(t('common.error'))
  }
})

// Cleanup on unmount
onBeforeUnmount(() => {
  stopHeartbeat()
  
  if (ws) {
    ws.close()
    ws = null
  }
  
  currentConnectedSessionId = null
  lastInitializedSessionId = null
  currentStreamingMessage = null
  pendingMessages = []
  isStopping = false
})
</script>

<style scoped>
/* 布局 - 使用 Grid 替代 Flex */
.chat-window {
  display: grid;
  grid-template-rows: auto 1fr auto;
  height: 100vh;
  background: var(--bg-secondary, #f9fafb);
  overflow: hidden;
}

.chat-window.resizing {
  cursor: ew-resize;
  user-select: none;
}

.chat-window.resizing * {
  cursor: ew-resize !important;
  user-select: none !important;
}

/* 顶部工具栏 */
.header {
  grid-row: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 56px;
  padding: 0 var(--spacing-lg);
  border-bottom: 1px solid var(--border-color, #e5e7eb);
  background: var(--bg-primary, #ffffff);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
  z-index: 10;
}

.header-left,
.header-right {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  margin: 0;
}

.title-clickable {
  cursor: pointer;
  user-select: none;
  transition: all 0.2s ease;
}

.brand-title {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  font-size: 20px;
  font-weight: 700;
  letter-spacing: -0.02em;
  display: flex;
  align-items: center;
  gap: 0;
}

.brand-count {
  color: var(--text-primary, #1f2937);
  transition: all 0.2s ease;
}

.brand-bot {
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 50%, #1d4ed8 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  font-weight: 800;
  transition: all 0.2s ease;
}

.title-clickable:hover .brand-count {
  color: var(--color-primary, #3b82f6);
}

.title-clickable:hover .brand-bot {
  background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 50%, #1e40af 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  transform: translateY(-1px);
}

/* Dark theme brand colors */
:root[data-theme="dark"] .brand-count {
  color: var(--text-primary, #e5e7eb);
}

:root[data-theme="dark"] .brand-bot {
  background: linear-gradient(135deg, #00f0ff 0%, #00d4ff 50%, #00b8ff 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

:root[data-theme="dark"] .title-clickable:hover .brand-count {
  color: #00f0ff;
}

:root[data-theme="dark"] .title-clickable:hover .brand-bot {
  background: linear-gradient(135deg, #33f5ff 0%, #00f0ff 50%, #00d4ff 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--text-secondary, #6b7280);
  cursor: pointer;
  transition: all var(--transition-base);
}

.icon-btn:hover {
  background: var(--hover-bg, #f3f4f6);
  color: var(--text-primary, #1f2937);
  border-color: var(--border-color, #e5e7eb);
}

.clear-chat-btn {
  color: var(--text-tertiary, #9ca3af);
}

.clear-chat-btn:hover {
  background: var(--color-error-bg, #fee2e2);
  color: var(--color-error, #ef4444);
  border-color: var(--color-error-light, #fecaca);
}

:root[data-theme="dark"] .clear-chat-btn:hover {
  background: rgba(239, 68, 68, 0.1);
  color: #ff6b8a;
  border-color: rgba(255, 45, 111, 0.3);
}

.divider {
  width: 1px;
  height: 20px;
  background: var(--border-color);
}

/* 连接状态条 */
.connection-status-bar {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 6px 16px;
  font-size: 13px;
  font-weight: 500;
  z-index: 10;
  transition: all 0.3s ease;
}

.status-reconnecting {
  background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%);
  border-bottom: 1px solid #fbbf24;
  color: #92400e;
}

:root[data-theme="dark"] .status-reconnecting {
  background: linear-gradient(135deg, #451a03 0%, #78350f 100%);
  border-bottom-color: #b45309;
  color: #fde68a;
}

.status-disconnected {
  background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%);
  border-bottom: 1px solid #fca5a5;
  color: #991b1b;
}

:root[data-theme="dark"] .status-disconnected {
  background: linear-gradient(135deg, #450a0a 0%, #7f1d1d 100%);
  border-bottom-color: #dc2626;
  color: #fca5a5;
}

.status-bar-content {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid rgba(146, 64, 14, 0.3);
  border-top-color: #d97706;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

:root[data-theme="dark"] .status-spinner {
  border-color: rgba(253, 230, 138, 0.3);
  border-top-color: #fbbf24;
}

.status-bar-action {
  padding: 2px 12px;
  border: 1px solid currentColor;
  border-radius: var(--radius-md, 8px);
  background: transparent;
  color: inherit;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  opacity: 0.8;
}

.status-bar-action:hover {
  opacity: 1;
  background: rgba(0, 0, 0, 0.05);
}

:root[data-theme="dark"] .status-bar-action:hover {
  background: rgba(255, 255, 255, 0.1);
}

/* 状态条过渡动画 */
.status-bar-enter-active,
.status-bar-leave-active {
  transition: all 0.3s ease;
  max-height: 40px;
  overflow: hidden;
}

.status-bar-enter-from,
.status-bar-leave-to {
  max-height: 0;
  padding-top: 0;
  padding-bottom: 0;
  opacity: 0;
}

/* 安全警告横幅 */
.security-warning-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px var(--spacing-lg);
  background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%);
  border-bottom: 1px solid #fbbf24;
  color: #78350f;
  font-size: 13px;
  line-height: 1.4;
  z-index: 10;
}

:root[data-theme="dark"] .security-warning-banner {
  background: linear-gradient(135deg, #451a03 0%, #78350f 100%);
  border-bottom-color: #b45309;
  color: #fde68a;
}

.security-warning-icon {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: rgba(245, 158, 11, 0.15);
  color: #d97706;
}

:root[data-theme="dark"] .security-warning-icon {
  background: rgba(251, 191, 36, 0.15);
  color: #fbbf24;
}

.security-warning-text {
  flex: 1;
}

.security-warning-action {
  flex-shrink: 0;
  padding: 5px 14px;
  border: none;
  border-radius: var(--radius-md);
  background: #d97706;
  color: #fff;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
}

.security-warning-action:hover {
  background: #b45309;
}

:root[data-theme="dark"] .security-warning-action {
  background: #f59e0b;
  color: #451a03;
}

:root[data-theme="dark"] .security-warning-action:hover {
  background: #fbbf24;
}

.security-warning-dismiss {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: #92400e;
  cursor: pointer;
  opacity: 0.6;
  transition: all 0.15s ease;
}

.security-warning-dismiss:hover {
  opacity: 1;
  background: rgba(0, 0, 0, 0.08);
}

:root[data-theme="dark"] .security-warning-dismiss {
  color: #fde68a;
}

:root[data-theme="dark"] .security-warning-dismiss:hover {
  background: rgba(255, 255, 255, 0.1);
}

/* 密码设置对话框 */
.password-dialog-overlay {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(4px);
  z-index: 200;
}

.password-dialog {
  width: 420px;
  max-width: 90vw;
  background: var(--bg-primary, #fff);
  border-radius: var(--radius-lg, 12px);
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15);
  overflow: hidden;
}

.password-dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px 0;
}

.password-dialog-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary, #111827);
}

.password-dialog-body {
  padding: 16px 24px 8px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.password-dialog-desc {
  margin: 0;
  font-size: 13px;
  color: var(--text-secondary, #6b7280);
  line-height: 1.5;
}

.password-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.password-field label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary, #374151);
}

.password-field input {
  padding: 10px 12px;
  border: 1.5px solid var(--border-color, #d1d5db);
  border-radius: var(--radius-md, 8px);
  font-size: 14px;
  color: var(--text-primary, #111827);
  background: var(--bg-primary, #fff);
  outline: none;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.password-field input:focus {
  border-color: var(--color-primary, #3b82f6);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.password-error {
  margin: 0;
  padding: 8px 12px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: var(--radius-md, 8px);
  color: #dc2626;
  font-size: 13px;
}

:root[data-theme="dark"] .password-error {
  background: #450a0a;
  border-color: #7f1d1d;
  color: #fca5a5;
}

.password-dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 16px 24px 20px;
}

.btn-cancel {
  padding: 8px 18px;
  border: 1.5px solid var(--border-color, #d1d5db);
  border-radius: var(--radius-md, 8px);
  background: transparent;
  color: var(--text-secondary, #6b7280);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-cancel:hover {
  background: var(--hover-bg, #f3f4f6);
}

.btn-confirm {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 20px;
  border: none;
  border-radius: var(--radius-md, 8px);
  background: #111827;
  color: #fff;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-confirm:hover {
  background: #1f2937;
}

.btn-confirm:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

:root[data-theme="dark"] .btn-confirm {
  background: var(--color-primary, #3b82f6);
}

:root[data-theme="dark"] .btn-confirm:hover {
  background: var(--color-primary-hover, #2563eb);
}

.spin-small {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

/* 主区域 */
.main {
  grid-row: 2;
  position: relative;
  overflow: hidden;
  /* Grid 自动处理高度 */
}

/* 确保子元素填满 main 区域 */
.main > * {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  flex-direction: column;
}

/* 加载状态 */
.loading-container {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
  max-width: 800px;
  margin: 0 auto;
  width: 100%;
  padding: var(--spacing-xl);
}

/* 输入区域 */
.input-area {
  grid-row: 3;
  padding: 12px 24px 16px;
  background: var(--bg-primary, #ffffff);
  z-index: 10;
}

.input-container {
  max-width: 820px;
  margin: 0 auto;
  display: flex;
  align-items: flex-end;
  gap: 0;
  background: var(--bg-primary, #ffffff);
  border: 1.5px solid var(--border-color, #d1d5db);
  border-radius: 24px;
  padding: 4px 4px 4px 0;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.input-container.focused {
  border-color: var(--text-tertiary, #9ca3af);
  box-shadow: 0 0 0 1px var(--text-tertiary, #9ca3af);
}

.chat-input {
  flex: 1;
  min-height: 24px;
  max-height: 160px;
  padding: 12px 0 12px 20px;
  border: none;
  background: transparent;
  color: var(--text-primary, #111827);
  font-size: 15px;
  font-family: var(--font-sans);
  line-height: 1.5;
  resize: none;
  outline: none;
}

.chat-input::placeholder {
  color: var(--text-disabled, #9ca3af);
}

.input-actions {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  padding: 0 4px;
  align-self: flex-end;
  margin-bottom: 4px;
}

/* 发送按钮 */
.send-message-btn {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 50%;
  background: #d1d5db;
  color: #ffffff;
  cursor: not-allowed;
  transition: background 0.15s ease, transform 0.1s ease;
}

.send-message-btn.ready {
  background: #111827;
  cursor: pointer;
}

.send-message-btn.ready:hover {
  background: #1f2937;
}

.send-message-btn.ready:active {
  transform: scale(0.9);
}

/* 停止按钮 */
.stop-generation-btn {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 50%;
  background: #111827;
  cursor: pointer;
  transition: background 0.15s ease, transform 0.1s ease;
  animation: stop-pulse 2s ease-in-out infinite;
}

.stop-generation-btn:hover {
  background: #1f2937;
}

.stop-generation-btn:active {
  transform: scale(0.9);
  animation: none;
}

.stop-square {
  display: block;
  width: 10px;
  height: 10px;
  border-radius: 2px;
  background: #ffffff;
}

@keyframes stop-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}

.input-hint {
  max-width: 820px;
  margin: 6px auto 0;
  padding: 0 8px;
  font-size: 11px;
  color: var(--text-disabled, #9ca3af);
  text-align: center;
}

.spin {
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

/* 侧边面板 */
.panel {
  position: fixed;
  top: 0;
  right: 0;
  height: 100vh;
  background: var(--bg-primary, #ffffff);
  border-left: 1px solid var(--border-color, #e5e7eb);
  z-index: 100;
  display: flex;
  flex-direction: column;
  box-shadow: -4px 0 24px rgba(0, 0, 0, 0.08);
  transition: box-shadow var(--transition-base);
}

.panel:hover {
  box-shadow: -4px 0 32px rgba(0, 0, 0, 0.12);
}

/* 拖动手柄 */
.resize-handle {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 8px;
  cursor: ew-resize;
  z-index: 101;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background-color var(--transition-base);
}

.resize-handle:hover {
  background-color: var(--color-primary-alpha);
}

.resize-handle:hover .resize-handle-line {
  background-color: var(--color-primary);
  opacity: 1;
}

.resize-handle-line {
  width: 2px;
  height: 40px;
  background-color: var(--border-color);
  border-radius: 2px;
  opacity: 0.5;
  transition: all var(--transition-base);
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 56px;
  padding: 0 var(--spacing-lg);
  border-bottom: 1px solid var(--border-color, #e5e7eb);
  background: var(--bg-primary, #ffffff);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}

.panel-title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  margin: 0;
}

.panel-body {
  flex: 1;
  overflow-y: auto;
  padding: 0;
  background: var(--bg-secondary, #f9fafb);
}

.panel-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-tertiary);
  font-size: var(--font-size-base);
}

/* 遮罩 */
.overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 99;
  backdrop-filter: blur(2px);
  transition: opacity var(--transition-base);
}

.overlay.resizing {
  pointer-events: none;
  cursor: ew-resize;
}

/* Drag and Drop Overlay */
.drag-overlay {
  position: fixed;
  top: 56px;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-primary-alpha);
  backdrop-filter: blur(8px);
  border: 3px dashed var(--color-primary);
  z-index: 1000;
  animation: fadeIn 0.2s ease-out;
  pointer-events: none;
}

@keyframes fadeIn {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

.drag-overlay-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-lg);
  padding: var(--spacing-xl);
}

.drag-overlay-icon {
  color: var(--color-primary);
  animation: bounce 0.6s ease-in-out infinite;
}

@keyframes bounce {
  0%, 100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-10px);
  }
}

.drag-overlay-text {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-primary);
  margin: 0;
  text-align: center;
}

/* 响应式 */
@media (max-width: 768px) {
  .panel {
    width: 100% !important;
  }
  
  .resize-handle {
    display: none;
  }
  
  .header-right {
    gap: 4px;
  }
  
  .icon-btn {
    width: 32px;
    height: 32px;
  }
}

/* 时间轴侧边栏 */
.timeline-sidebar {
  position: fixed;
  top: 0;
  right: 0;
  width: 320px;
  height: 100vh;
  background: var(--bg-primary, #ffffff);
  border-left: 1px solid var(--border-color, #e5e7eb);
  box-shadow: -4px 0 24px rgba(0, 0, 0, 0.08);
  z-index: 100;
}

/* 时间轴滑入动画 */
.timeline-slide-enter-active,
.timeline-slide-leave-active {
  transition: transform 0.3s ease, opacity 0.3s ease;
}

.timeline-slide-enter-from {
  transform: translateX(100%);
  opacity: 0;
}

.timeline-slide-leave-to {
  transform: translateX(100%);
  opacity: 0;
}

/* 深色模式 */
:root[data-theme="dark"] .timeline-sidebar {
  background: var(--bg-primary, #0a0e1a);
  border-left-color: var(--border-color, #1f2937);
}

/* 响应式 */
@media (max-width: 768px) {
  .timeline-sidebar {
    width: 100%;
  }
}
</style>
