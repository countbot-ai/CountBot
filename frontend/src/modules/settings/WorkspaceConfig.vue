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

    <!-- Workspace Path -->
    <div class="form-group">
      <label class="label">{{ $t('settings.workspace.workspacePath') }}</label>
      <div class="path-input-group">
        <Input
          v-model="workspaceConfig.path"
          type="text"
          :placeholder="$t('settings.workspace.workspacePathPlaceholder')"
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
      <p class="hint-text">{{ $t('settings.workspace.pathHint') }}</p>
    </div>

    <!-- Current Path Display -->
    <div
      v-if="workspaceConfig.path"
      class="current-path"
    >
      <label class="label">{{ $t('settings.workspace.currentPath') }}</label>
      <div class="path-display">
        <component
          :is="FolderIcon"
          :size="16"
        />
        <span>{{ workspaceConfig.path }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { FolderOpen as FolderOpenIcon, Folder as FolderIcon } from 'lucide-vue-next'
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

const isUpdating = ref(false)

// 初始化配置
onMounted(() => {
  if (settingsStore.settings?.workspace) {
    isUpdating.value = true
    workspaceConfig.value = {
      path: settingsStore.settings.workspace.path || ''
    }
    isUpdating.value = false
  }
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

// 监听本地变化，同步到 store（由父组件统一保存）
watch(workspaceConfig, (newConfig) => {
  if (!isUpdating.value && settingsStore.settings?.workspace) {
    isUpdating.value = true
    settingsStore.settings.workspace.path = newConfig.path
    isUpdating.value = false
  }
}, { deep: true })

// 处理路径输入变化（blur 时触发）
const handlePathChange = () => {
  // 路径变化已通过 v-model + watch 自动同步到 store
  // 此处可做额外校验
  const path = workspaceConfig.value.path.trim()
  if (path && !path.startsWith('/') && !path.match(/^[A-Za-z]:\\/)) {
    toast.warning('请输入绝对路径')
  }
}

// 处理目录选择
const handleSelectDirectory = async () => {
  try {
    // 使用 pywebview 的文件选择对话框
    if (window.pywebview) {
      const result = await window.pywebview.api.select_directory()
      if (result) {
        workspaceConfig.value.path = result
        toast.success('工作空间路径已选择')
      }
    } else {
      // 浏览器模式：使用 HTML5 File API
      // 创建一个隐藏的 input 元素
      const input = document.createElement('input')
      input.type = 'file'
      input.webkitdirectory = true
      input.directory = true
      input.multiple = true

      input.onchange = (e: Event) => {
        const target = e.target as HTMLInputElement
        if (target.files && target.files.length > 0) {
          // 获取第一个文件的路径，提取目录路径
          const firstFile = target.files[0]
          const fullPath = firstFile.webkitRelativePath || firstFile.name
          // 提取目录名（去掉文件名）
          const dirPath = fullPath.split('/')[0]

          // 在浏览器模式下，我们只能获取相对路径
          // 提示用户手动输入完整路径
          toast.warning('浏览器模式下请手动输入完整路径', {
            title: '提示',
            duration: 5000
          })

          // 将目录名填入输入框作为参考
          if (dirPath) {
            workspaceConfig.value.path = dirPath
          }
        }
      }

      input.click()
    }
  } catch (error) {
    console.error('Failed to select directory:', error)
    toast.error('选择目录失败')
  }
}

</script>

<style scoped>
.workspace-config {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xl);
  max-width: 800px;
}

.section-header {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.section-title {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  margin: 0;
}

.section-desc {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  margin: 0;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.label {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--text-primary);
}

.path-input-group {
  display: flex;
  gap: var(--spacing-sm);
  align-items: stretch;
}

.path-input-group :deep(.input-wrapper) {
  flex: 1;
  min-width: 0;
}

.path-input-group :deep(input) {
  width: 100%;
}

.path-input-group button {
  flex-shrink: 0;
  white-space: nowrap;
}

.hint-text {
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
  margin: 0;
  line-height: 1.5;
}

.current-path {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.path-display {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-md);
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  font-family: var(--font-mono);
  word-break: break-all;
  overflow-wrap: break-word;
}

.path-display svg {
  flex-shrink: 0;
}

.checkbox-label {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-sm);
  cursor: pointer;
  padding: var(--spacing-md);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  transition: all var(--transition-base);
}

.checkbox-label:hover {
  background: var(--bg-secondary);
  border-color: var(--color-primary);
}

.checkbox {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  margin-top: 2px;
  border: 2px solid var(--border-color);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition-base);
  appearance: none;
  position: relative;
}

.checkbox:checked {
  background-color: var(--color-primary);
  border-color: var(--color-primary);
}

.checkbox:checked::after {
  content: '';
  position: absolute;
  left: 4px;
  top: 1px;
  width: 4px;
  height: 8px;
  border: solid white;
  border-width: 0 2px 2px 0;
  transform: rotate(45deg);
}

.checkbox-content {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
  flex: 1;
}

.checkbox-title {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--text-primary);
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-lg);
  background: var(--color-bg-primary);
  border: 1px dashed var(--color-border-primary);
  border-radius: var(--radius-md);
  color: var(--color-text-tertiary);
  font-size: var(--font-size-sm);
  font-style: italic;
}
</style>
