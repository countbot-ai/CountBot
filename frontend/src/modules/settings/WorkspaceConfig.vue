<template>
  <div class="workspace-config">
    <div class="section-header">
      <h3 class="section-title">
        {{ $t('settings.workspace.title') }}
      </h3>
      <p class="section-desc">
        {{ $t('settings.workspace.description') }}
      </p>
    </div>

    <div class="config-options">
      <!-- 重要提示卡片 -->
      <div class="config-card warning-card">
        <div class="card-header">
          <div class="header-left">
            <component
              :is="AlertTriangleIcon"
              :size="20"
              class="icon icon-warning"
            />
            <div class="header-text">
              <h4 class="card-title">{{ $t('settings.workspace.warning.title') }}</h4>
              <p class="card-desc">{{ $t('settings.workspace.warning.message') }}</p>
            </div>
          </div>
        </div>
        <div class="card-body">
          <ul class="warning-list">
            <li>{{ $t('settings.workspace.warning.skills') }}</li>
            <li>{{ $t('settings.workspace.warning.memory') }}</li>
            <li>{{ $t('settings.workspace.warning.files') }}</li>
          </ul>
        </div>
      </div>

      <!-- 工作空间路径配置卡片 -->
      <div class="config-card">
        <div class="card-header">
          <div class="header-left">
            <component
              :is="FolderIcon"
              :size="20"
              class="icon"
            />
            <div class="header-text">
              <h4 class="card-title">{{ $t('settings.workspace.workspacePath') }}</h4>
              <p class="card-desc">{{ $t('settings.workspace.pathHint') }}</p>
            </div>
          </div>
        </div>
        <div class="card-body">
          <div class="path-input-group">
            <Input
              v-model="workspaceConfig.path"
              type="text"
              :placeholder="defaultWorkspacePath || $t('settings.workspace.workspacePathPlaceholder')"
              @blur="handlePathChange"
            />
            <Button
              variant="secondary"
              :icon="FolderOpenIcon"
              @click="handleSelectDirectory"
            >
              {{ $t('settings.workspace.selectDirectory') }}
            </Button>
          </div>
          <p v-if="defaultWorkspacePath" class="hint-text">
            {{ $t('settings.workspace.defaultPath') }}：{{ defaultWorkspacePath }}
          </p>
        </div>
      </div>

      <!-- 工作空间信息卡片 -->
      <div v-if="workspaceInfo" class="config-card">
        <div class="card-header">
          <div class="header-left">
            <component
              :is="FolderIcon"
              :size="20"
              class="icon"
            />
            <div class="header-text">
              <h4 class="card-title">{{ $t('settings.workspace.info.title') }}</h4>
            </div>
          </div>
        </div>
        <div class="card-body">
          <div class="info-grid">
            <div class="info-item">
              <span class="info-label">{{ $t('settings.workspace.info.workspace') }}</span>
              <span class="info-value">
                {{ workspaceInfo.workspace.files }} {{ $t('settings.workspace.info.files') }}，{{ workspaceInfo.workspace.directories }} {{ $t('settings.workspace.info.directories') }}
              </span>
              <span class="info-size">{{ workspaceInfo.workspace.size_formatted }}</span>
            </div>
            
            <div class="info-item">
              <span class="info-label">{{ $t('settings.workspace.info.tempFiles') }}</span>
              <span class="info-value">{{ workspaceInfo.temp.files }} {{ $t('settings.workspace.info.files') }}</span>
              <span class="info-size">{{ workspaceInfo.temp.size_formatted }}</span>
              <div v-if="workspaceInfo.temp.files > 0" class="info-actions">
                <Button
                  variant="secondary"
                  size="sm"
                  @click="cleanTempFiles(false)"
                >
                  {{ $t('settings.workspace.info.clean') }}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  @click="cleanTempFiles(true)"
                >
                  {{ $t('settings.workspace.info.cleanAll') }}
                </Button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 当前路径显示卡片 -->
      <div v-if="workspaceConfig.path" class="config-card">
        <div class="card-header">
          <div class="header-left">
            <component
              :is="FolderIcon"
              :size="20"
              class="icon"
            />
            <div class="header-text">
              <h4 class="card-title">{{ $t('settings.workspace.currentPath') }}</h4>
            </div>
          </div>
        </div>
        <div class="card-body">
          <div class="path-display">
            <component :is="FolderIcon" :size="16" />
            <span>{{ workspaceConfig.path }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { FolderOpen as FolderOpenIcon, Folder as FolderIcon, AlertTriangle as AlertTriangleIcon } from 'lucide-vue-next'
import Input from '@/components/ui/Input.vue'
import Button from '@/components/ui/Button.vue'
import { useSettingsStore } from '@/store/settings'
import { useToast } from '@/composables/useToast'

const { t } = useI18n()
const settingsStore = useSettingsStore()
const toast = useToast()

const workspaceConfig = ref({
  path: ''
})

const defaultWorkspacePath = ref('')
const workspaceInfo = ref(null)
const isUpdating = ref(false)
const isLoadingInfo = ref(false)
const lastLoadTime = ref(0)
const CACHE_TTL = 30000 // 30秒缓存

// 防抖加载工作空间信息
let loadInfoTimer: number | null = null
const debouncedLoadWorkspaceInfo = (forceRefresh = false) => {
  if (loadInfoTimer) {
    clearTimeout(loadInfoTimer)
  }
  loadInfoTimer = window.setTimeout(() => loadWorkspaceInfo(forceRefresh), 500)
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
  // 路径变化已通过 v-model + watch 自动同步到 store 和后端
  // 此处可做额外校验
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
@import './styles/WorkspaceConfig.css';
</style>
