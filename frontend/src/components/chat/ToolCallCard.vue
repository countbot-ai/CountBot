<template>
  <div
    class="tool-call-card"
    :class="[
      `status-${normalizedStatus}`,
      `context-${normalizedContextKind}`,
      { collapsed: isCollapsed, 'mcp-tool': isMcpTool }
    ]"
  >
    <div class="tool-header" @click="toggleCollapse">
      <div class="tool-header-main">
        <div class="status-dot" :class="`dot-${normalizedStatus}`">
          <component v-if="normalizedStatus === 'running'" :is="LoaderIcon" :size="12" class="spin" />
        </div>

        <div class="tool-icon-shell">
          <component :is="getToolIcon()" :size="15" class="tool-type-icon" />
        </div>

        <div class="tool-summary">
          <div class="tool-context-row">
            <span class="tool-context-chip">{{ contextChipLabel }}</span>
            <span v-if="isMcpTool" class="mcp-badge-chip">MCP</span>
            <span class="tool-context-label">{{ resolvedContextLabel }}</span>
            <span v-if="contextMeta" class="tool-context-meta">{{ contextMeta }}</span>
          </div>
          <div class="tool-name-row">
            <span class="tool-name">{{ getToolDisplayName(toolName) }}</span>
            <span v-if="argumentPreview" class="tool-preview">{{ argumentPreview }}</span>
          </div>
        </div>
      </div>

      <div class="tool-header-meta">
        <span class="tool-status-chip">{{ statusLabel }}</span>
        <span v-if="effectiveDuration != null" class="tool-duration">{{ formatDuration(effectiveDuration) }}</span>
        <component :is="ChevronRightIcon" :size="14" class="chevron-icon" :class="{ expanded: !isCollapsed }" />
      </div>
    </div>

    <div v-if="showProgressStrip" class="tool-progress-strip">
      <div class="tool-progress-meta">
        <span class="tool-progress-message">{{ resolvedProgressMessage }}</span>
        <span v-if="normalizedProgress != null" class="tool-progress-value">{{ normalizedProgress }}%</span>
      </div>
      <div class="tool-progress-bar">
        <div
          class="tool-progress-fill"
          :class="{ indeterminate: isProgressIndeterminate }"
          :style="progressFillStyle"
        />
      </div>
      <div v-if="latestOutputPreview" class="tool-progress-preview">
        <div class="tool-progress-preview-label">Latest output</div>
        <pre class="tool-progress-preview-text">{{ latestOutputPreview }}</pre>
      </div>
      <div v-else-if="latestStderrPreview" class="tool-progress-preview tool-progress-preview-error">
        <div class="tool-progress-preview-label">Latest stderr</div>
        <pre class="tool-progress-preview-text">{{ latestStderrPreview }}</pre>
      </div>
    </div>

    <transition name="slide">
      <div v-if="!isCollapsed" class="tool-body">
        <div v-if="showDetailHint" class="tool-detail-hint">
          <span>{{ detailHintText }}</span>
        </div>

        <div v-if="hasArguments" class="tool-section">
          <div class="section-label">{{ $t('tools.arguments') }}</div>
          <div class="tool-arguments">
            <div
              v-for="(value, key) in effectiveArguments"
              :key="key"
              class="arg-item"
              :class="{ 'arg-item-file-paths': isSendMediaFilePaths(key, value) }"
            >
              <span class="arg-key">{{ key }}</span>
              <div v-if="isSendMediaFilePaths(key, value)" class="send-media-files">
                <div
                  v-for="(filePath, fileIndex) in normalizeFilePaths(value)"
                  :key="fileIndex"
                  class="send-media-file-item"
                  :class="getFileItemClass(filePath)"
                >
                  <!-- 图片预览 -->
                  <div
                    v-if="isImageFile(filePath) && !imageErrors[getImageKey(filePath)]"
                    class="send-media-image-preview"
                    @click="handleImageClick(filePath)"
                  >
                    <img
                      :src="getWorkspaceFileUrl(filePath)"
                      :alt="filePath"
                      class="send-media-image"
                      @error="handleImageError(filePath)"
                    />
                    <div class="send-media-image-overlay">
                      <component :is="ExpandIcon" :size="18" />
                    </div>
                  </div>
                  <!-- 文件下载卡片 -->
                  <div v-else class="send-media-file-card">
                    <div class="send-media-file-icon">
                      <component :is="getFileIcon(filePath)" :size="16" />
                    </div>
                    <div class="send-media-file-info">
                      <div class="send-media-file-name">{{ getFileName(filePath) }}</div>
                      <div class="send-media-file-path">{{ filePath }}</div>
                    </div>
                    <button
                      class="send-media-download-btn"
                      :title="$t('chat.download') || '下载'"
                      @click.stop="handleDownloadFile(filePath)"
                    >
                      <component :is="DownloadIcon" :size="14" />
                    </button>
                  </div>
                </div>
              </div>
              <span v-else class="arg-value">{{ formatValue(value) }}</span>
            </div>
          </div>
        </div>

        <div v-if="effectiveResult && showResult" class="tool-section result-section">
          <div class="section-label">
            <span>{{ $t('tools.result') }}</span>
            <button class="copy-btn" @click.stop="copyResult" :title="copied ? $t('common.copied') : $t('common.copy')">
              <component :is="copied ? CheckIcon : CopyIcon" :size="12" />
            </button>
          </div>
          <div class="result-viewer">
            <div class="result-toolbar">
              <div class="result-toolbar-main">
                <span class="result-toolbar-lights" aria-hidden="true">
                  <span class="result-toolbar-light" />
                  <span class="result-toolbar-light" />
                  <span class="result-toolbar-light" />
                </span>
                <span class="result-toolbar-tab">
                  <component :is="TerminalIcon" :size="12" class="result-toolbar-icon" />
                  <span>{{ $t('tools.card.outputLog') }}</span>
                </span>
              </div>
              <span class="result-toolbar-meta">{{ $t('tools.card.lines', { count: resultLineCount }) }}</span>
            </div>

            <div class="result-scroll">
              <div
                v-for="(line, index) in resultLines"
                :key="`${index}-${line}`"
                class="result-line"
              >
                <span class="result-line-number">{{ index + 1 }}</span>
                <code class="result-line-text">{{ line || ' ' }}</code>
              </div>
            </div>
          </div>
        </div>

        <div v-if="effectiveError" class="tool-section error-section">
          <div class="section-label error-label">{{ $t('tools.error') }}</div>
          <pre class="tool-error">{{ effectiveError }}</pre>
        </div>
      </div>
    </transition>

    <!-- 图片预览模态框 -->
    <Teleport to="body">
      <div
        v-if="showImagePreviewModal"
        class="tool-image-preview-modal"
        @click="closeImagePreview"
      >
        <div class="tool-image-preview-backdrop" />
        <div class="tool-image-preview-content" @click.stop>
          <button class="tool-image-preview-close" @click="closeImagePreview">
            <component :is="XIcon" :size="24" />
          </button>
          <img
            :src="previewImageUrl"
            alt="Preview"
            class="tool-image-preview-img"
          />
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  Wrench as WrenchIcon,
  Terminal as TerminalIcon,
  FileText as FileIcon,
  Folder as FolderIcon,
  Globe as GlobeIcon,
  Loader2 as LoaderIcon,
  Copy as CopyIcon,
  Check as CheckIcon,
  ChevronRight as ChevronRightIcon,
  Pencil as PencilIcon,
  Image as ImageIcon,
  Download as DownloadIcon,
  File as FileDefaultIcon,
  Music4 as MusicIcon,
  Film as FilmIcon,
  Expand as ExpandIcon,
  X as XIcon,
} from 'lucide-vue-next'
import { useToast } from '@/composables/useToast'
import { useI18n } from 'vue-i18n'
import { chatAPI, type ToolCall as ApiToolCall } from '@/api'

type ToolCardStatus = 'pending' | 'running' | 'success' | 'error' | 'cancelled'
type ToolCardContext = 'main' | 'agent' | 'subagent'

interface Props {
  toolId?: string | null
  toolName: string
  arguments?: Record<string, any>
  status: ToolCardStatus
  result?: string | null
  error?: string | null
  duration?: number | null
  detailAvailable?: boolean
  detailLoaded?: boolean
  resultTruncated?: boolean
  errorTruncated?: boolean
  progress?: number | null
  progressMessage?: string | null
  progressDetails?: Record<string, any> | null
  timestamp?: Date
  defaultCollapsed?: boolean
  isReplaying?: boolean
  showResult?: boolean
  contextKind?: ToolCardContext
  contextLabel?: string | null
  contextMeta?: string | null
}

const props = withDefaults(defineProps<Props>(), {
  toolId: null,
  arguments: () => ({}),
  duration: null,
  detailAvailable: false,
  detailLoaded: true,
  resultTruncated: false,
  errorTruncated: false,
  progress: null,
  progressMessage: null,
  progressDetails: null,
  timestamp: () => new Date(),
  defaultCollapsed: true,
  isReplaying: false,
  showResult: true,
  contextKind: 'main',
  contextLabel: null,
  contextMeta: null,
})

const { t } = useI18n()
const toast = useToast()
const copied = ref(false)
const isCollapsed = ref(props.defaultCollapsed)
const isDetailLoading = ref(false)
const detailPayload = ref<ApiToolCall | null>(null)

const effectiveArguments = computed<Record<string, any>>(() => {
  return detailPayload.value?.arguments || props.arguments || {}
})

const effectiveResult = computed(() => detailPayload.value?.result ?? props.result)
const effectiveError = computed(() => detailPayload.value?.error ?? props.error)
const effectiveStatus = computed<ToolCardStatus>(() => {
  return (detailPayload.value?.status as ToolCardStatus | undefined) || props.status || 'success'
})
const effectiveDuration = computed(() => detailPayload.value?.duration ?? props.duration)
const resolvedDetailLoaded = computed(() => props.detailLoaded || detailPayload.value !== null || !props.detailAvailable)
const shouldFetchDetail = computed(() => {
  return Boolean(props.toolId) && props.detailAvailable && !resolvedDetailLoaded.value
})

const normalizedStatus = computed<ToolCardStatus>(() => effectiveStatus.value || 'success')
const normalizedContextKind = computed<ToolCardContext>(() => props.contextKind || 'main')
const normalizedProgress = computed<number | null>(() => {
  if (props.progress === null || props.progress === undefined) {
    return null
  }

  const value = Number(props.progress)
  if (Number.isNaN(value)) {
    return null
  }

  return Math.max(0, Math.min(100, Math.round(value)))
})
const isProgressIndeterminate = computed(() => normalizedProgress.value === null)
const showProgressStrip = computed(() => {
  return normalizedStatus.value === 'running' && (
    normalizedProgress.value !== null ||
    Boolean(props.progressMessage) ||
    Boolean(latestOutputPreview.value) ||
    Boolean(latestStderrPreview.value)
  )
})
const latestOutputPreview = computed(() => {
  const value = props.progressDetails?.latest_output_preview
  return typeof value === 'string' && value.trim() ? value.trim() : ''
})
const latestStderrPreview = computed(() => {
  const value = props.progressDetails?.latest_stderr_preview
  return typeof value === 'string' && value.trim() ? value.trim() : ''
})
const resolvedProgressMessage = computed(() => {
  const message = String(props.progressMessage || '').trim()
  if (message) {
    return message
  }
  if (normalizedProgress.value !== null) {
    return `${statusLabel.value} ${normalizedProgress.value}%`
  }
  return statusLabel.value
})
const progressFillStyle = computed(() => {
  if (normalizedProgress.value === null) {
    return undefined
  }

  return {
    width: `${Math.max(normalizedProgress.value, 4)}%`,
  }
})

const hasArguments = computed(() => {
  return Object.keys(effectiveArguments.value || {}).length > 0
})

const argumentPreview = computed(() => {
  if (!effectiveArguments.value) return ''

  const preferredKeys = ['command', 'path', 'file_path', 'pattern', 'query', 'url', 'task', 'message']
  const matchedKey = preferredKeys.find((key) => {
    const value = effectiveArguments.value?.[key]
    return value !== undefined && value !== null && String(value).trim() !== ''
  })
  const previewKey = matchedKey || Object.keys(effectiveArguments.value)[0]
  if (!previewKey) return ''

  const value = effectiveArguments.value[previewKey]
  const formatted = typeof value === 'string' ? value : JSON.stringify(value)
  if (!formatted) return ''

  const compact = formatted.replace(/\s+/g, ' ').trim()
  return compact.length > 84 ? `${compact.slice(0, 84)}...` : compact
})

const contextChipLabel = computed(() => {
  const value = t(`tools.card.contextChip.${normalizedContextKind.value}`)
  return value && value !== `tools.card.contextChip.${normalizedContextKind.value}`
    ? value
    : normalizedContextKind.value
})

const resolvedContextLabel = computed(() => {
  if (props.contextLabel && props.contextLabel.trim()) {
    return props.contextLabel.trim()
  }

  const value = t(`tools.card.contextLabel.${normalizedContextKind.value}`)
  return value && value !== `tools.card.contextLabel.${normalizedContextKind.value}`
    ? value
    : normalizedContextKind.value
})

const statusLabel = computed(() => {
  const value = t(`tools.card.status.${normalizedStatus.value}`)
  return value && value !== `tools.card.status.${normalizedStatus.value}`
    ? value
    : normalizedStatus.value
})

const splitOutput = (value: string | null | undefined): string[] => {
  if (!value) return []
  return value.replace(/\r\n/g, '\n').split('\n')
}

const resultLines = computed(() => {
  if (isCollapsed.value || !props.showResult) {
    return []
  }
  return splitOutput(effectiveResult.value)
})
const resultLineCount = computed(() => resultLines.value.length)
const showDetailHint = computed(() => {
  return isDetailLoading.value || (props.detailAvailable && !resolvedDetailLoaded.value)
})
const detailHintText = computed(() => {
  if (isDetailLoading.value) {
    return t('tools.card.loadingDetail')
  }
  return t('tools.card.previewOnly')
})

const ensureDetailLoaded = async () => {
  if (!shouldFetchDetail.value || isDetailLoading.value || !props.toolId) {
    return
  }

  try {
    isDetailLoading.value = true
    detailPayload.value = await chatAPI.getToolCallDetail(props.toolId)
  } catch (error) {
    console.error('[ToolCallCard] 加载工具详情失败:', error)
    toast.error(t('tools.card.loadDetailFailed'))
  } finally {
    isDetailLoading.value = false
  }
}

watch(
  () => isCollapsed.value,
  (collapsed) => {
    if (!collapsed) {
      void ensureDetailLoaded()
    }
  },
  { immediate: true }
)

const toggleCollapse = () => {
  isCollapsed.value = !isCollapsed.value
}

const formatDuration = (ms: number): string => {
  if (ms < 1000) {
    return `${ms}ms`
  }
  if (ms < 60000) {
    const seconds = (ms / 1000).toFixed(1)
    return `${seconds}s`
  }
  if (ms < 3600000) {
    const minutes = Math.floor(ms / 60000)
    const seconds = Math.floor((ms % 60000) / 1000)
    return seconds > 0 ? `${minutes}m ${seconds}s` : `${minutes}m`
  }

  const hours = Math.floor(ms / 3600000)
  const minutes = Math.floor((ms % 3600000) / 60000)
  return minutes > 0 ? `${hours}h ${minutes}m` : `${hours}h`
}

const getToolIcon = () => {
  if (!props.toolName) return WrenchIcon
  const name = props.toolName.toLowerCase()

  if (name.includes('external_coding') || name.includes('coding_agent') || name.includes('coder')) return TerminalIcon
  if (name.includes('exec') || name.includes('shell') || name.includes('command')) return TerminalIcon
  if (name.includes('write') || name.includes('edit') || name.includes('create')) return PencilIcon
  if (name.includes('read') || name.includes('file')) return FileIcon
  if (name.includes('list') || name.includes('dir')) return FolderIcon
  if (name.includes('web') || name.includes('search') || name.includes('fetch')) return GlobeIcon
  // MCP tools: use specific icons based on tool name patterns
  if (name.startsWith('mcp_')) {
    if (name.includes('weather') || name.includes('fetch')) return GlobeIcon
    if (name.includes('search') || name.includes('doc')) return GlobeIcon
    if (name.includes('format') || name.includes('json')) return FileIcon
    if (name.includes('random') || name.includes('calc')) return TerminalIcon
    if (name.includes('translate')) return GlobeIcon
    if (name.includes('echo')) return TerminalIcon
    return GlobeIcon
  }
  return WrenchIcon
}

const isMcpTool = computed(() => {
  return props.toolName?.startsWith('mcp_') || false
})

const getToolDisplayName = (toolName: string): string => {
  const i18nKey = `tools.names.${toolName}`
  const translated = t(i18nKey)

  if (translated && translated !== i18nKey) {
    return translated
  }

  return toolName
}

const formatValue = (value: any): string => {
  if (typeof value === 'string') return value
  if (typeof value === 'object' && value !== null) return JSON.stringify(value, null, 2)
  return String(value)
}

const copyResult = async () => {
  try {
    await navigator.clipboard.writeText(effectiveResult.value || '')
    copied.value = true
    toast.success(t('common.copied'))
    setTimeout(() => {
      copied.value = false
    }, 2000)
  } catch {
    toast.error(t('common.copyFailed'))
  }
}

const IMAGE_EXTENSIONS = new Set(['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg'])
const isSendMediaFilePaths = (key: string, value: any): boolean => {
  return props.toolName === 'send_media' && key === 'file_paths' && Array.isArray(value)
}

const normalizeFilePaths = (value: any): string[] => {
  if (!Array.isArray(value)) return []
  return value.filter((p) => typeof p === 'string' && p.trim() !== '')
}

const isImageFile = (path: string): boolean => {
  const ext = path.split('.').pop()?.toLowerCase()
  return IMAGE_EXTENSIONS.has(ext || '')
}

const getFileItemClass = (path: string): string => {
  if (isImageFile(path)) return 'file-type-image'
  return 'file-type-other'
}

const getWorkspaceFileUrl = (path: string): string => {
  if (path.startsWith('http://') || path.startsWith('https://')) return path
  if (!path.startsWith('/')) return `/api/chat/workspace/${encodeURIComponent(path)}`
  const workspaceIndex = path.indexOf('/workspace/')
  if (workspaceIndex !== -1) {
    const relativePath = path.slice(workspaceIndex + '/workspace/'.length)
    return `/api/chat/workspace/${encodeURIComponent(relativePath)}`
  }
  return ''
}

const getFileName = (path: string): string => {
  return path.split('/').pop() || path
}

const getFileIcon = (path: string) => {
  const ext = path.split('.').pop()?.toLowerCase() || ''
  if (['mp3', 'wav', 'ogg', 'm4a'].includes(ext)) return MusicIcon
  if (['mp4', 'avi', 'mov', 'webm'].includes(ext)) return FilmIcon
  if (['pdf'].includes(ext)) return FileIcon
  return FileDefaultIcon
}

const imageErrors = ref<Record<string, boolean>>({})
const getImageKey = (path: string): string => path
const handleImageError = (path: string) => {
  imageErrors.value[getImageKey(path)] = true
}

const showImagePreviewModal = ref(false)
const previewImageUrl = ref('')
const handleImageClick = (path: string) => {
  previewImageUrl.value = getWorkspaceFileUrl(path)
  showImagePreviewModal.value = true
}
const closeImagePreview = () => {
  showImagePreviewModal.value = false
  previewImageUrl.value = ''
}

const handleDownloadFile = async (path: string) => {
  const url = getWorkspaceFileUrl(path)
  try {
    const response = await fetch(url)
    if (!response.ok) throw new Error('Download failed')
    const blob = await response.blob()
    const blobUrl = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = blobUrl
    link.download = getFileName(path)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(blobUrl)
    toast.success(t('common.downloaded') || '下载成功')
  } catch {
    toast.error(t('common.downloadFailed') || '下载失败')
  }
}
</script>
<style scoped>
@import './styles/ToolCallCard.css';
</style>
