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
@import './styles/ToolsPanel.css';
</style>
