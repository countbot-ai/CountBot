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
@import './styles/ShellExecutor.css';
</style>
