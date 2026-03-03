<template>
  <div class="session-panel">
    <!-- Header -->
    <div class="panel-header">
      <h2 class="panel-title">
        {{ $t('sessions.title') }}
      </h2>
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

    <!-- Session List -->
    <div class="panel-body">
      <!-- Loading State -->
      <LoadingState
        v-if="chatStore.isLoadingSessions"
        type="skeleton"
        :lines="5"
      />

      <!-- Empty State -->
      <EmptyState
        v-else-if="chatStore.sessions.length === 0"
        icon="message-square"
        :title="$t('sessions.empty')"
        :description="$t('sessions.emptyDescription')"
        :action="$t('sessions.createFirst')"
        @action="handleCreateSession"
      />

      <!-- Session List -->
      <div
        v-else
        class="session-list"
      >
        <div
          v-for="session in chatStore.sortedSessions"
          :key="session.id"
          class="session-item"
          :class="{ active: session.id === chatStore.currentSessionId }"
          @click="handleSwitchSession(session.id)"
        >
          <!-- Session Info -->
          <div
            v-if="editingSessionId !== session.id"
            class="session-info"
          >
            <div class="session-name">
              {{ session.name }}
            </div>
            <div class="session-date">
              {{ formatDate(session.updatedAt) }}
            </div>
          </div>

          <!-- Edit Mode -->
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

          <!-- Actions -->
          <div
            v-if="editingSessionId !== session.id"
            class="session-actions"
            @click.stop
          >
            <button
              class="action-btn"
              :title="$t('sessions.summarizeToMemory')"
              :disabled="summarizingSessionId === session.id"
              @click="handleSummarizeToMemory(session)"
            >
              <component
                :is="BrainIcon"
                :size="16"
                :class="{ spinning: summarizingSessionId === session.id }"
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
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue'
import {
  Plus as PlusIcon,
  Edit2 as EditIcon,
  Trash2 as TrashIcon,
  Download as DownloadIcon,
  Brain as BrainIcon
} from 'lucide-vue-next'
import { useChatStore, type Session } from '@/store/chat'
import { useToast } from '@/composables/useToast'
import { useConfirm } from '@/composables/useConfirm'
import { useI18n } from 'vue-i18n'
import { LoadingState, EmptyState } from '@/components/ui'
import { chatAPI } from '@/api'

const chatStore = useChatStore()
const toast = useToast()
const { confirmDelete } = useConfirm()
const { t } = useI18n()

const editingSessionId = ref<string | null>(null)
const editingName = ref('')
const editInputRef = ref<HTMLInputElement>()

// 正在总结的会话 ID
const summarizingSessionId = ref<string | null>(null)

/**
 * 创建新会话
 */
async function handleCreateSession() {
  try {
    await chatStore.createSession()
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
async function handleSummarizeToMemory(session: Session) {
  if (summarizingSessionId.value) return // 防止重复点击

  const confirmed = confirm(t('sessions.confirmSummarize'))
  if (!confirmed) return

  summarizingSessionId.value = session.id
  
  try {
    const result = await chatAPI.summarizeSessionToMemory(session.id)
    
    if (result.success) {
      toast.success(t('sessions.summarizeSuccess', { summary: result.summary }))
    } else {
      toast.error(t('sessions.summarizeError'))
    }
  } catch (error: any) {
    console.error('Failed to summarize session:', error)
    const errorMsg = error.response?.data?.detail || error.message || t('sessions.summarizeError')
    toast.error(errorMsg)
  } finally {
    summarizingSessionId.value = null
  }
}


</script>

<style scoped>
.session-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-secondary, #f9fafb);
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-lg);
  border-bottom: 1px solid var(--border-color, #e5e7eb);
  background: var(--bg-primary, #ffffff);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}

.panel-title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary, #1f2937);
  margin: 0;
}

.icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: 1px solid var(--color-primary, #3b82f6);
  border-radius: var(--radius-md);
  background: var(--color-primary, #3b82f6);
  color: #ffffff;
  cursor: pointer;
  transition: all var(--transition-base);
  box-shadow: 0 2px 4px rgba(59, 130, 246, 0.3);
}

.icon-btn:hover:not(:disabled) {
  background: var(--color-primary-hover, #2563eb);
  box-shadow: 0 4px 6px rgba(59, 130, 246, 0.4);
  transform: translateY(-1px);
}

.icon-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.panel-body {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-lg);
}

/* Session List */
.session-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.session-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-md);
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: var(--radius-lg);
  background: var(--bg-primary, #ffffff);
  cursor: pointer;
  transition: all var(--transition-base);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}

.session-item:hover {
  background: var(--bg-primary, #ffffff);
  border-color: var(--color-primary, #3b82f6);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.1);
  transform: translateY(-1px);
}

.session-item.active {
  background: var(--color-primary, #3b82f6);
  border-color: var(--color-primary, #3b82f6);
  color: #ffffff;
  box-shadow: 0 4px 8px rgba(59, 130, 246, 0.3);
}

.session-item.active .session-name {
  color: #ffffff;
}

.session-item.active .session-date {
  color: rgba(255, 255, 255, 0.9);
}

.session-info {
  flex: 1;
  min-width: 0;
}

.session-name {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-medium);
  color: var(--text-primary, #1f2937);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-date {
  font-size: var(--font-size-xs);
  color: var(--text-tertiary, #9ca3af);
  margin-top: 4px;
}

.session-edit-input {
  flex: 1;
  padding: var(--spacing-xs) var(--spacing-sm);
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: var(--radius-md);
  background: var(--bg-primary, #ffffff);
  color: var(--text-primary, #1f2937);
  font-size: var(--font-size-base);
  outline: none;
  transition: all var(--transition-base);
}

.session-edit-input:focus {
  border-color: var(--color-primary, #3b82f6);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.session-actions {
  display: flex;
  gap: var(--spacing-xs);
  opacity: 0;
  transition: opacity var(--transition-base);
}

.session-item:hover .session-actions {
  opacity: 1;
}

.session-item.active .session-actions {
  opacity: 1;
}

.action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  background: rgba(0, 0, 0, 0.05);
  color: var(--text-secondary, #6b7280);
  cursor: pointer;
  transition: all var(--transition-base);
}

.session-item.active .action-btn {
  background: rgba(255, 255, 255, 0.2);
  border-color: rgba(255, 255, 255, 0.3);
  color: #ffffff;
}

.action-btn:hover:not(:disabled) {
  background: rgba(0, 0, 0, 0.1);
  border-color: var(--border-color, #e5e7eb);
}

.session-item.active .action-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.3);
  border-color: rgba(255, 255, 255, 0.5);
}

.action-btn.danger:hover:not(:disabled) {
  background: var(--color-error, #ef4444);
  border-color: var(--color-error, #ef4444);
  color: #ffffff;
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.spinning {
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

/* 深色模式 */
:root[data-theme="dark"] .session-panel {
  background: #0e1422;
}

:root[data-theme="dark"] .panel-header {
  background: #0a0e1a;
  border-color: #152035;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.4);
}

:root[data-theme="dark"] .panel-title {
  color: #d0e8f0;
}

:root[data-theme="dark"] .icon-btn {
  background: #131b2c;
  border-color: #00f0ff;
  color: #00f0ff;
  box-shadow: 0 0 6px rgba(0, 240, 255, 0.1);
}

:root[data-theme="dark"] .icon-btn:hover:not(:disabled) {
  background: #152035;
  border-color: #33f5ff;
  color: #33f5ff;
  box-shadow: 0 0 10px rgba(0, 240, 255, 0.2);
}

:root[data-theme="dark"] .session-item {
  background: #0a0e1a;
  border-color: #152035;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
}

:root[data-theme="dark"] .session-item:hover {
  border-color: rgba(0, 240, 255, 0.2);
  box-shadow: 0 0 8px rgba(0, 240, 255, 0.05), 0 2px 6px rgba(0, 0, 0, 0.3);
}

:root[data-theme="dark"] .session-name {
  color: #d0e8f0;
}

:root[data-theme="dark"] .session-date {
  color: #4a6578;
}

:root[data-theme="dark"] .session-item.active {
  background: #111828;
  border-color: #00f0ff;
  border-left: 3px solid #00f0ff;
  color: #d0e8f0;
  box-shadow: 0 0 10px rgba(0, 240, 255, 0.08), 0 2px 6px rgba(0, 0, 0, 0.3);
}

:root[data-theme="dark"] .session-item.active .session-name {
  color: #00f0ff;
}

:root[data-theme="dark"] .session-item.active .session-date {
  color: #5eead4;
}

:root[data-theme="dark"] .action-btn {
  background: rgba(122, 154, 176, 0.1);
  color: #7a9ab0;
}

:root[data-theme="dark"] .action-btn:hover:not(:disabled) {
  background: rgba(0, 240, 255, 0.1);
  border-color: rgba(0, 240, 255, 0.2);
  color: #00f0ff;
}

:root[data-theme="dark"] .session-item.active .action-btn {
  background: rgba(0, 240, 255, 0.1);
  border-color: rgba(0, 240, 255, 0.15);
  color: #00f0ff;
}

:root[data-theme="dark"] .session-item.active .action-btn:hover:not(:disabled) {
  background: rgba(0, 240, 255, 0.18);
  border-color: rgba(0, 240, 255, 0.3);
}

:root[data-theme="dark"] .action-btn.danger:hover:not(:disabled) {
  background: rgba(255, 45, 111, 0.15);
  border-color: rgba(255, 45, 111, 0.3);
  color: #ff2d6f;
}

:root[data-theme="dark"] .session-edit-input {
  background: #0a0e1a;
  border-color: #152035;
  color: #d0e8f0;
}

:root[data-theme="dark"] .session-edit-input:focus {
  border-color: #00f0ff;
  box-shadow: 0 0 0 2px rgba(0, 240, 255, 0.08);
}
</style>
