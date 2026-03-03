<template>
  <div class="tools-panel">
    <!-- 工具导航 -->
    <div class="tools-nav">
      <button
        v-for="view in views"
        :key="view.id"
        class="nav-btn"
        :class="{ active: activeView === view.id }"
        @click="activeView = view.id"
      >
        <component
          :is="view.icon"
          :size="18"
        />
        <span>{{ $t(view.label) }}</span>
      </button>
    </div>

    <!-- 工具内容 -->
    <div class="tools-content">
      <!-- 文件操作视图 -->
      <FileOperations v-if="activeView === 'files'" />

      <!-- Shell 执行视图 -->
      <ShellExecutor v-else-if="activeView === 'shell'" />

      <!-- 执行历史视图 -->
      <ToolHistory v-else-if="activeView === 'history'" />

      <!-- 工具列表视图（默认） -->
      <div
        v-else
        class="tools-list-view"
      >
        <div class="section-header">
          <h3 class="section-title">
            {{ $t('tools.availableTools') }}
          </h3>
          <button
            class="refresh-btn"
            :disabled="loading"
            @click="loadTools"
          >
            <component
              :is="RefreshIcon"
              :size="16"
              :class="{ 'spin': loading }"
            />
          </button>
        </div>

        <!-- 加载状态 -->
        <div
          v-if="loading"
          class="loading-state"
        >
          <component
            :is="LoaderIcon"
            :size="24"
            class="spin"
          />
          <p>{{ $t('common.loading') }}</p>
        </div>

        <!-- 错误状态 -->
        <div
          v-else-if="error"
          class="error-state"
        >
          <component
            :is="AlertCircleIcon"
            :size="24"
          />
          <p>{{ error }}</p>
          <button
            class="retry-btn"
            @click="loadTools"
          >
            {{ $t('common.retry') }}
          </button>
        </div>

        <!-- 工具卡片 -->
        <div
          v-else-if="tools.length > 0"
          class="tools-grid"
        >
          <div
            v-for="tool in tools"
            :key="tool.name"
            class="tool-card"
          >
            <div class="tool-header">
              <component
                :is="getToolIcon(tool.name)"
                :size="20"
              />
              <h4 class="tool-name">
                {{ tool.name }}
              </h4>
            </div>
            <p class="tool-description">
              {{ tool.description }}
            </p>
            <div class="tool-params">
              <span class="param-count">
                {{ getParamCount(tool.parameters) }} {{ $t('tools.parameters') }}
              </span>
            </div>
          </div>
        </div>

        <!-- 空状态 -->
        <div
          v-else
          class="empty-state"
        >
          <component
            :is="PackageIcon"
            :size="48"
          />
          <p>{{ $t('tools.noTools') }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  RefreshCw as RefreshIcon,
  Loader2 as LoaderIcon,
  AlertCircle as AlertCircleIcon,
  Package as PackageIcon,
  FileText as FileIcon,
  Terminal as TerminalIcon,
  Globe as GlobeIcon,
  Folder as FolderIcon,
  Edit as EditIcon,
  List as ListIcon,
  History as HistoryIcon
} from 'lucide-vue-next'
import { toolsAPI } from '@/api/endpoints'
import FileOperations from './FileOperations.vue'
import ShellExecutor from './ShellExecutor.vue'
import ToolHistory from './ToolHistory.vue'

const { t } = useI18n()

type ViewType = 'list' | 'files' | 'shell' | 'history'

const views = [
  { id: 'list' as ViewType, icon: ListIcon, label: 'tools.views.list' },
  { id: 'files' as ViewType, icon: FileIcon, label: 'tools.views.files' },
  { id: 'shell' as ViewType, icon: TerminalIcon, label: 'tools.views.shell' },
  { id: 'history' as ViewType, icon: HistoryIcon, label: 'tools.views.history' }
]

interface ToolDefinition {
  name: string
  description: string
  parameters: {
    type: string
    properties: Record<string, any>
    required?: string[]
  }
}

const activeView = ref<ViewType>('files')
const tools = ref<ToolDefinition[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

const loadTools = async () => {
  loading.value = true
  error.value = null
  
  try {
    const response = await toolsAPI.list() as { tools: ToolDefinition[] }
    tools.value = response.tools
  } catch (err: any) {
    console.error('Failed to load tools:', err)
    error.value = err.message || t('tools.loadError')
  } finally {
    loading.value = false
  }
}

const getToolIcon = (toolName: string) => {
  if (toolName.includes('read') || toolName.includes('file')) return FileIcon
  if (toolName.includes('exec') || toolName.includes('shell')) return TerminalIcon
  if (toolName.includes('web') || toolName.includes('search')) return GlobeIcon
  if (toolName.includes('list') || toolName.includes('dir')) return FolderIcon
  if (toolName.includes('edit') || toolName.includes('write')) return EditIcon
  return PackageIcon
}

const getParamCount = (parameters: any) => Object.keys(parameters.properties || {}).length

onMounted(() => {
  loadTools()
})
</script>

<style scoped>
.tools-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-secondary, #f9fafb);
}

.tools-nav {
  display: flex;
  gap: var(--spacing-xs);
  padding: var(--spacing-md);
  border-bottom: 1px solid var(--border-color, #e5e7eb);
  background: var(--bg-primary, #ffffff);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}

.nav-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--text-secondary, #6b7280);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: all var(--transition-base);
}

.nav-btn:hover {
  background: var(--hover-bg, #f3f4f6);
  color: var(--text-primary, #1f2937);
}

.nav-btn.active {
  background: var(--bg-secondary, #f9fafb);
  color: var(--color-primary, #3b82f6);
  border-color: var(--color-primary, #3b82f6);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

.tools-content {
  flex: 1;
  overflow: hidden;
}

.tools-list-view {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
  height: 100%;
  padding: var(--spacing-xl);
  overflow-y: auto;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-md) var(--spacing-xl);
  border-bottom: 1px solid var(--border-color, #e5e7eb);
  background: var(--bg-primary, #ffffff);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}

.section-title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary, #1f2937);
  margin: 0;
}

.refresh-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: var(--radius-md);
  background: var(--bg-primary, #ffffff);
  color: var(--text-secondary, #6b7280);
  cursor: pointer;
  transition: all var(--transition-base);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

.refresh-btn:hover:not(:disabled) {
  background: var(--hover-bg, #f3f4f6);
  color: var(--text-primary, #1f2937);
  border-color: var(--color-primary, #3b82f6);
}

.refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 状态 */
.loading-state,
.error-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-md);
  padding: var(--spacing-3xl);
  color: var(--text-secondary);
  text-align: center;
}

.error-state {
  color: var(--color-error);
}

.retry-btn {
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-size: var(--font-size-sm);
  cursor: pointer;
  transition: all var(--transition-base);
}

.retry-btn:hover {
  background: var(--hover-bg);
}

/* 工具网格 */
.tools-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: var(--spacing-lg);
}

.tool-card {
  padding: var(--spacing-lg);
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: var(--radius-lg);
  background: var(--bg-primary, #ffffff);
  transition: all var(--transition-base);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}

.tool-card:hover {
  border-color: var(--color-primary, #3b82f6);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  transform: translateY(-2px);
}

.tool-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-sm);
}

.tool-name {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  margin: 0;
}

.tool-description {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  margin: 0 0 var(--spacing-sm) 0;
  line-height: 1.5;
}

.tool-params {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.param-count {
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
}

/* 动画 */
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
:root[data-theme="dark"] .tools-panel {
  background: var(--bg-secondary, #111827);
}

:root[data-theme="dark"] .tools-nav {
  background: var(--bg-primary, #1f2937);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}

:root[data-theme="dark"] .section-header {
  background: var(--bg-primary, #1f2937);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}

:root[data-theme="dark"] .tool-card {
  background: var(--bg-primary, #1f2937);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}

:root[data-theme="dark"] .tool-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
}
</style>
