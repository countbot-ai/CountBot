<template>
  <div class="shell-executor">
    <div class="executor-header">
      <h3 class="executor-title">
        {{ $t('tools.shell.title') }}
      </h3>
      <p class="executor-desc">
        {{ $t('tools.shell.description') }}
      </p>
    </div>

    <div class="executor-body">
      <div class="form-group">
        <label class="form-label">
          {{ $t('tools.shell.command') }}
          <span class="required">*</span>
        </label>
        <div class="command-input-wrapper">
          <span class="command-prompt">$</span>
          <input
            v-model="command"
            type="text"
            class="command-input"
            :placeholder="$t('tools.shell.commandPlaceholder')"
            @keydown.enter="executeCommand"
          >
        </div>
        <span class="form-hint">
          {{ $t('tools.shell.commandHint') }}
        </span>
      </div>

      <div class="form-group">
        <label class="form-label">
          {{ $t('tools.shell.workingDir') }}
        </label>
        <input
          v-model="workingDir"
          type="text"
          class="form-input"
          :placeholder="$t('tools.shell.workingDirPlaceholder')"
        >
        <span class="form-hint">
          {{ $t('tools.shell.workingDirHint') }}
        </span>
      </div>

      <div class="executor-actions">
        <button
          class="execute-btn"
          :disabled="!command || executing"
          @click="executeCommand"
        >
          <component
            :is="executing ? LoaderIcon : TerminalIcon"
            :size="16"
            :class="{ 'spin': executing }"
          />
          {{ executing ? $t('tools.executing') : $t('tools.execute') }}
        </button>
        <button
          v-if="history.length > 0"
          class="clear-btn"
          @click="clearHistory"
        >
          <component
            :is="TrashIcon"
            :size="16"
          />
          {{ $t('tools.shell.clearHistory') }}
        </button>
      </div>

      <!-- Command History -->
      <div
        v-if="history.length > 0"
        class="history-section"
      >
        <h4 class="history-title">
          {{ $t('tools.shell.history') }}
        </h4>
        <div class="history-list">
          <div
            v-for="(item, index) in history"
            :key="index"
            class="history-item"
          >
            <div class="history-header">
              <div class="history-command">
                <span class="command-prompt">$</span>
                <span class="command-text">{{ item.command }}</span>
              </div>
              <div class="history-meta">
                <span class="history-time">{{ formatTime(item.timestamp) }}</span>
                <span
                  class="history-status"
                  :class="{ success: item.success, error: !item.success }"
                >
                  {{ item.success ? $t('common.success') : $t('common.error') }}
                </span>
              </div>
            </div>
            <div
              v-if="item.workingDir"
              class="history-cwd"
            >
              <component
                :is="FolderIcon"
                :size="14"
              />
              {{ item.workingDir }}
            </div>
            <div class="history-output">
              <pre>{{ item.output }}</pre>
            </div>
          </div>
        </div>
      </div>

      <!-- Empty State -->
      <div
        v-else
        class="empty-state"
      >
        <component
          :is="TerminalIcon"
          :size="48"
        />
        <p>{{ $t('tools.shell.emptyState') }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  Terminal as TerminalIcon,
  Loader2 as LoaderIcon,
  Trash2 as TrashIcon,
  Folder as FolderIcon
} from 'lucide-vue-next'
import { toolsAPI } from '@/api/endpoints'
import { useToast } from '@/composables/useToast'

const { t } = useI18n()
const toast = useToast()

interface HistoryItem {
  command: string
  workingDir?: string
  output: string
  success: boolean
  timestamp: Date
}

const command = ref('')
const workingDir = ref('')
const executing = ref(false)
const history = ref<HistoryItem[]>([])

const executeCommand = async () => {
  if (!command.value || executing.value) return
  
  executing.value = true
  const currentCommand = command.value
  const currentWorkingDir = workingDir.value
  
  try {
    const args: any = { command: currentCommand }
    if (currentWorkingDir) {
      args.working_dir = currentWorkingDir
    }
    
    const result = await toolsAPI.execute({
      tool: 'exec',
      arguments: args
    }) as { result: string; success: boolean; error?: string }
    
    // Add to history
    history.value.unshift({
      command: currentCommand,
      workingDir: currentWorkingDir || undefined,
      output: result.success ? result.result : (result.error || result.result),
      success: result.success,
      timestamp: new Date()
    })
    
    // Keep only last 20 items
    if (history.value.length > 20) {
      history.value = history.value.slice(0, 20)
    }
    
    if (result.success) {
      toast.success(t('tools.executeSuccess'))
      // Clear command input on success
      command.value = ''
    } else {
      toast.error(t('tools.executeError'))
    }
  } catch (err: any) {
    history.value.unshift({
      command: currentCommand,
      workingDir: currentWorkingDir || undefined,
      output: err.message || 'Unknown error',
      success: false,
      timestamp: new Date()
    })
    toast.error(t('tools.executeError'))
  } finally {
    executing.value = false
  }
}

const clearHistory = () => {
  history.value = []
  toast.success(t('tools.shell.historyCleared'))
}

const formatTime = (date: Date) => {
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  const seconds = Math.floor(diff / 1000)
  const minutes = Math.floor(seconds / 60)
  const hours = Math.floor(minutes / 60)
  
  if (seconds < 60) {
    return t('sessions.justNow')
  } else if (minutes < 60) {
    return t('sessions.minutesAgo', { count: minutes })
  } else if (hours < 24) {
    return t('sessions.hoursAgo', { count: hours })
  } else {
    return date.toLocaleString()
  }
}
</script>

<style scoped>
.shell-executor {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-secondary, #f9fafb);
}

.executor-header {
  padding: var(--spacing-xl);
  border-bottom: 1px solid var(--border-color, #e5e7eb);
  background: var(--bg-primary, #ffffff);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}

.executor-title {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  margin: 0 0 var(--spacing-sm) 0;
}

.executor-desc {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  margin: 0;
  line-height: 1.6;
}

.executor-body {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-xl);
}

.form-group {
  margin-bottom: var(--spacing-lg);
}

.form-label {
  display: block;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--text-primary);
  margin-bottom: var(--spacing-xs);
}

.required {
  color: var(--color-error);
  margin-left: 2px;
}

.command-input-wrapper {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: var(--radius-md);
  background: var(--bg-primary, #ffffff);
  transition: border-color var(--transition-base);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

.command-input-wrapper:focus-within {
  border-color: var(--color-primary, #3b82f6);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.command-prompt {
  font-family: var(--font-mono);
  font-size: var(--font-size-base);
  color: var(--color-primary);
  font-weight: var(--font-weight-semibold);
}

.command-input {
  flex: 1;
  border: none;
  background: transparent;
  color: var(--text-primary);
  font-size: var(--font-size-sm);
  font-family: var(--font-mono);
  outline: none;
}

.form-input {
  width: 100%;
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: var(--font-size-sm);
  font-family: var(--font-sans);
  transition: border-color var(--transition-base);
}

.form-input:focus {
  outline: none;
  border-color: var(--color-primary);
}

.form-hint {
  display: block;
  margin-top: var(--spacing-xs);
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
}

.executor-actions {
  display: flex;
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-xl);
}

.execute-btn,
.clear-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-lg);
  border: none;
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: all var(--transition-base);
}

.execute-btn {
  background: var(--color-primary, #3b82f6);
  color: #ffffff;
  border: 1px solid var(--color-primary, #3b82f6);
  box-shadow: 0 2px 4px rgba(59, 130, 246, 0.3);
}

.execute-btn:hover:not(:disabled) {
  background: var(--color-primary-hover, #2563eb);
  box-shadow: 0 4px 6px rgba(59, 130, 246, 0.4);
  transform: translateY(-1px);
}

.execute-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.clear-btn {
  background: var(--bg-primary, #ffffff);
  color: var(--text-secondary, #6b7280);
  border: 1px solid var(--border-color, #e5e7eb);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

.clear-btn:hover {
  background: var(--hover-bg, #f3f4f6);
  color: var(--text-primary, #1f2937);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.history-section {
  margin-top: var(--spacing-xl);
}

.history-title {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  margin: 0 0 var(--spacing-md) 0;
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.history-item {
  padding: var(--spacing-md);
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: var(--radius-md);
  background: var(--bg-primary, #ffffff);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
  transition: all var(--transition-base);
}

.history-item:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  transform: translateY(-1px);
}

.history-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--spacing-sm);
}

.history-command {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  flex: 1;
}

.command-text {
  font-family: var(--font-mono);
  font-size: var(--font-size-sm);
  color: var(--text-primary);
  font-weight: var(--font-weight-medium);
}

.history-meta {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}

.history-time {
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
}

.history-status {
  padding: 2px var(--spacing-sm);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
}

.history-status.success {
  background: rgba(16, 185, 129, 0.1);
  color: var(--color-success);
}

.history-status.error {
  background: rgba(239, 68, 68, 0.1);
  color: var(--color-error);
}

.history-cwd {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  margin-bottom: var(--spacing-sm);
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
}

.history-output {
  padding: var(--spacing-sm);
  border-radius: var(--radius-sm);
  background: var(--bg-primary);
  max-height: 200px;
  overflow-y: auto;
}

.history-output pre {
  margin: 0;
  font-size: var(--font-size-xs);
  font-family: var(--font-mono);
  color: var(--text-primary);
  white-space: pre-wrap;
  word-wrap: break-word;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-md);
  padding: var(--spacing-3xl);
  color: var(--text-tertiary);
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

/* 深色模式 */
:root[data-theme="dark"] .shell-executor {
  background: var(--bg-secondary, #111827);
}

:root[data-theme="dark"] .executor-header {
  background: var(--bg-primary, #1f2937);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}

:root[data-theme="dark"] .history-item {
  background: var(--bg-primary, #1f2937);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}

:root[data-theme="dark"] .history-output {
  background: var(--bg-tertiary, #374151);
}
</style>
