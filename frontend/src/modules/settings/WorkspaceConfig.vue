<template>
  <SettingsCard :title="$t('settings.workspace.pathCardTitle')" :description="$t('settings.workspace.pathHint')">
    <SettingsRow :label="$t('settings.workspace.workspacePath')" layout="block">
      <div class="path-row">
        <input
          v-model="workspaceConfig.path"
          class="co-input path-input"
          type="text"
          :placeholder="defaultWorkspacePath || $t('settings.workspace.workspacePathPlaceholder')"
          @blur="handlePathChange"
        >
        <button class="co-btn co-btn--secondary" @click="handleSelectDirectory">
          <component :is="FolderOpenIcon" :size="14" />
          {{ $t('settings.workspace.selectDirectory') }}
        </button>
      </div>
      <template #below>
        <p v-if="defaultWorkspacePath" class="note-line">
          {{ $t('settings.workspace.defaultPath') }}：<code>{{ defaultWorkspacePath }}</code>
        </p>
        <p class="note-line">{{ $t('settings.workspace.globalScopeHint') }}</p>
      </template>
    </SettingsRow>
  </SettingsCard>

  <SettingsCard v-if="currentSession" :title="$t('settings.workspace.currentSessionTitle')">
    <SettingsRow
      :label="$t('settings.workspace.currentSessionTitle')"
      :description="currentSessionIsCustom
        ? $t('settings.workspace.currentSessionCustom')
        : $t('settings.workspace.currentSessionGlobal')"
      wide-control
    >
      <code class="path-text">{{ currentSessionWorkspacePath }}</code>
      <button
        v-if="currentSessionIsCustom"
        class="co-btn co-btn--secondary"
        @click="handleFollowGlobal"
      >
        {{ $t('settings.workspace.followGlobal') }}
      </button>
      <template #below>
        <p class="note-line">{{ $t('settings.workspace.currentSessionHint') }}</p>
      </template>
    </SettingsRow>
  </SettingsCard>

  <SettingsCard v-if="workspaceInfo" :title="$t('settings.workspace.info.title')">
    <SettingsRow :label="$t('settings.workspace.info.workspace')">
      <span class="metric">{{ workspaceInfo.workspace.size_formatted }}</span>
      <span class="metric-sub">
        {{ workspaceInfo.workspace.files }} {{ $t('settings.workspace.info.files') }} ·
        {{ workspaceInfo.workspace.directories }} {{ $t('settings.workspace.info.directories') }}
      </span>
    </SettingsRow>

    <SettingsRow :label="$t('settings.workspace.info.tempFiles')">
      <template v-if="workspaceInfo.temp.files > 0">
        <button class="co-btn co-btn--secondary btn-compact" @click="cleanTempFiles(false)">
          {{ $t('settings.workspace.info.clean') }}
        </button>
        <button class="co-btn co-btn--secondary btn-compact" @click="cleanTempFiles(true)">
          {{ $t('settings.workspace.info.cleanAll') }}
        </button>
      </template>
      <span class="metric">{{ workspaceInfo.temp.size_formatted }}</span>
      <span class="metric-sub">
        {{ workspaceInfo.temp.files }} {{ $t('settings.workspace.info.files') }}
      </span>
    </SettingsRow>
  </SettingsCard>

  <SettingsCard :title="$t('settings.workspace.warning.title')">
    <div class="warning-block">
      <p class="warning-lead">
        <component :is="AlertTriangleIcon" :size="14" />
        <span>{{ $t('settings.workspace.warning.message') }}</span>
      </p>
      <ul class="warning-list">
        <li>{{ $t('settings.workspace.warning.skills') }}</li>
        <li>{{ $t('settings.workspace.warning.memory') }}</li>
        <li>{{ $t('settings.workspace.warning.files') }}</li>
      </ul>
    </div>
  </SettingsCard>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { FolderOpen as FolderOpenIcon, AlertTriangle as AlertTriangleIcon } from 'lucide-vue-next'
import { SettingsCard, SettingsRow } from './ui'
import { useSettingsStore } from '@/store/settings'
import { useChatStore } from '@/store/chat'
import { useToast } from '@/composables/useToast'
import { useConfirm } from '@/composables/useConfirm'
import { chatAPI } from '@/api'

const { t } = useI18n()
const settingsStore = useSettingsStore()
const chatStore = useChatStore()
const toast = useToast()
const { confirm } = useConfirm()

const workspaceConfig = ref({
  path: ''
})

const defaultWorkspacePath = ref('')
interface WorkspaceInfo {
  workspace: { path?: string; files: number; directories: number; size_formatted: string }
  temp: { files: number; size_formatted: string }
}

const workspaceInfo = ref<WorkspaceInfo | null>(null)
const isUpdating = ref(false)
const isLoadingInfo = ref(false)
const lastLoadTime = ref(0)
const CACHE_TTL = 30000 // 30秒缓存

const currentSession = computed(() =>
  chatStore.sessions.find(session => session.id === chatStore.currentSessionId) || null
)
const currentSessionIsCustom = computed(() => !!currentSession.value?.workspacePath)
const currentSessionWorkspacePath = computed(() =>
  currentSession.value?.effectiveWorkspacePath
    || workspaceConfig.value.path
    || defaultWorkspacePath.value
    || ''
)

async function handleFollowGlobal() {
  const sessionId = chatStore.currentSessionId
  if (!sessionId) {
    return
  }

  const confirmed = await confirm({
    title: t('common.confirm'),
    message: t('settings.workspace.followGlobalConfirm'),
    type: 'warning',
    confirmText: t('common.confirm'),
    confirmVariant: 'primary'
  })
  if (!confirmed) {
    return
  }

  try {
    await chatAPI.updateSessionWorkspace(sessionId, null)
    await chatStore.loadSessions()
    toast.success(t('settings.workspace.followGlobalDone'), t('common.success'))
  } catch (error) {
    console.error('Failed to reset session workspace:', error)
    toast.error(t('chat.sessionConfig.workspaceSaveFailed'), t('common.error'))
  }
}

// 初始化配置
onMounted(async () => {
  if (settingsStore.settings?.workspace) {
    isUpdating.value = true
    workspaceConfig.value = {
      path: settingsStore.settings.workspace.path || ''
    }
    isUpdating.value = false
  }
  
  // 获取工作空间信息
  await loadWorkspaceInfo()
})

// 监听 store 变化（从外部更新）
watch(() => settingsStore.settings?.workspace, (newWorkspace) => {
  if (newWorkspace && !isUpdating.value) {
    isUpdating.value = true
    workspaceConfig.value = {
      path: newWorkspace.path || ''
    }
    isUpdating.value = false
  }
}, { deep: true })

// 监听本地变化，同步到 store
watch(workspaceConfig, async (newConfig, oldConfig) => {
  if (!isUpdating.value && settingsStore.settings?.workspace) {
    isUpdating.value = true
    
    // 路径变化后立即设置并刷新
    if (newConfig.path && newConfig.path !== oldConfig?.path) {
      try {
        // 调用后端API设置工作空间路径
        const response = await fetch('/api/settings/workspace/set-path', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ path: newConfig.path })
        })
        
        if (response.ok) {
          const data = await response.json()
          if (data.success) {
            // 更新store中的设置并保存
            await settingsStore.saveSettings({
              workspace: { path: newConfig.path }
            })
            
            // 立即刷新工作空间信息
            await loadWorkspaceInfo(true)
          }
        }
      } catch (error) {
        console.error('设置工作空间路径失败:', error)
      }
    } else {
      // 如果路径没有变化，只更新本地store
      settingsStore.settings.workspace.path = newConfig.path
    }
    
    isUpdating.value = false
  }
}, { deep: true })

// 加载工作空间信息
const loadWorkspaceInfo = async (forceRefresh = false) => {
  if (isLoadingInfo.value) return // 防止重复加载
  
  // 检查缓存是否有效
  const now = Date.now()
  if (!forceRefresh && workspaceInfo.value && (now - lastLoadTime.value) < CACHE_TTL) {
    return // 使用缓存
  }
  
  try {
    isLoadingInfo.value = true
    const url = forceRefresh ? '/api/settings/workspace/info?force=true' : '/api/settings/workspace/info'
    const response = await fetch(url)
    if (response.ok) {
      const data = await response.json()
      if (data.success) {
        workspaceInfo.value = data
        lastLoadTime.value = now
        // 设置默认路径提示
        if (data.workspace?.path && !workspaceConfig.value.path) {
          defaultWorkspacePath.value = data.workspace.path
        }
      }
    }
  } catch (error) {
    console.error('Failed to load workspace info:', error)
  } finally {
    isLoadingInfo.value = false
  }
}

// 清理临时文件
const cleanTempFiles = async (cleanAll = false) => {
  if (isLoadingInfo.value) return // 防止在加载时操作
  
  try {
    const response = await fetch('/api/settings/workspace/clean-temp', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ 
        max_age_hours: 24,
        clean_all: cleanAll
      })
    })
    
    if (response.ok) {
      const data = await response.json()
      if (data.success) {
        toast.success(data.message, t('settings.workspace.info.clean'))
        // 重新加载工作空间信息
        await loadWorkspaceInfo(true) // 强制刷新
      } else {
        toast.error(data.message || t('settings.workspace.cleanTempFilesFailed'), t('common.error'))
      }
    } else {
      toast.error(t('settings.workspace.cleanTempFilesFailed'), t('common.error'))
    }
  } catch (error) {
    console.error(t('settings.workspace.cleanTempFilesFailed'), error)
    toast.error(t('settings.workspace.cleanTempFilesFailed'), t('common.error'))
  }
}

// 处理路径输入变化（blur 时触发）
const handlePathChange = () => {
  // 路径变化已由 v-model + watch 同步到 store 与后端，此处仅做校验
  const path = workspaceConfig.value.path.trim()
  if (path) {
    // 更智能的路径验证
    const isAbsolutePath = path.startsWith('/') || // Unix 绝对路径
                          path.match(/^[A-Za-z]:[\\\/]/) || // Windows 绝对路径
                          path.startsWith('\\\\') || // UNC 路径
                          path.startsWith('~') // 用户目录
    
    if (!isAbsolutePath) {
      // 只有在路径看起来像相对路径时才提示
      if (!path.includes('/') && !path.includes('\\')) {
        // 单个目录名，可能是相对路径
        toast.warning(t('settings.workspace.pleaseEnterAbsolutePath'), t('settings.workspace.pathValidation'))
      }
    }
  }
}

// 处理目录选择
const handleSelectDirectory = async () => {
  try {
    // 优先使用后端API（支持多种桌面环境）
    try {
      const response = await fetch('/api/settings/workspace/select-directory', {
        method: 'POST'
      })
      if (response.ok) {
        const data = await response.json()
        if (data.success && data.path) {
          workspaceConfig.value.path = data.path
          toast.success(t('settings.workspace.workspacePathSelected'), t('common.success'))
          // 路径变化会通过watch自动处理保存和刷新
          return
        } else if (data.message) {
          toast.info(data.message)
        }
      }
    } catch (apiError) {
      console.log(t('settings.workspace.backendDirectoryApiUnavailable'), apiError)
    }
    
    // 备用方案：pywebview API（如果可用）
    if (window.pywebview && window.pywebview.api && window.pywebview.api.select_directory) {
      try {
        const result = await window.pywebview.api.select_directory()
        if (result) {
          workspaceConfig.value.path = result
          toast.success(t('settings.workspace.workspacePathSelected'), t('common.success'))
          // 路径变化会通过watch自动处理保存和刷新
          return
        }
      } catch (pywebviewError) {
        console.log(t('settings.workspace.pywebviewDirectorySelectionFailed'), pywebviewError)
      }
    }
    
    // 最后备用方案：浏览器文件选择（受限）
    const input = document.createElement('input')
    input.type = 'file'
    input.webkitdirectory = true
    input.directory = true
    input.multiple = true

    input.onchange = async (e: Event) => {
      const target = e.target as HTMLInputElement
      if (target.files && target.files.length > 0) {
        const firstFile = target.files[0]
        const fullPath = firstFile.webkitRelativePath || firstFile.name
        const dirPath = fullPath.split('/')[0]

        toast.warning(t('settings.workspace.browserModeManualInput'), t('common.warning'))

        if (dirPath) {
          workspaceConfig.value.path = dirPath
          // 路径变化会通过watch自动处理保存和刷新
        }
      }
    }

    input.click()
  } catch (error) {
    console.error(t('settings.workspace.selectDirectoryFailed'), error)
    toast.error(t('settings.workspace.selectDirectoryFailed'), t('common.error'))
  }
}
</script>

<style scoped>
.path-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.path-input {
  flex: 1;
  min-width: 0;
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
}

.path-text {
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.note-line {
  margin: 0;
  font-size: var(--font-size-xs);
  line-height: 1.6;
  color: var(--color-text-tertiary);
}

.note-line + .note-line {
  margin-top: 3px;
}

.note-line code {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--color-text-secondary);
}

.metric {
  font-size: var(--font-size-sm);
  font-variant-numeric: tabular-nums;
  color: var(--color-text-primary);
}

.metric-sub {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  white-space: nowrap;
}

.btn-compact {
  height: 26px;
  padding: 0 10px;
  font-size: var(--font-size-xs);
}

.warning-block {
  padding: 12px var(--co-row-gutter) 14px;
}

.warning-lead {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin: 0;
  font-size: var(--font-size-xs);
  line-height: 1.6;
  color: var(--color-text-secondary);
}

.warning-list {
  margin: 8px 0 0;
  padding-left: 18px;
  font-size: var(--font-size-xs);
  line-height: 1.8;
  color: var(--color-text-tertiary);
}

@media (max-width: 680px) {
  .path-row {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
