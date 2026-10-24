<template>
  <div
    class="tool-call"
    :class="[
      `status-${normalizedStatus}`,
      `context-${normalizedContextKind}`,
      { 'is-open': !isCollapsed, 'is-mcp': isMcpTool }
    ]"
  >
    <!-- 摘要行：图标 + 动作 + 目标 + 状态/耗时，一眼扫完，不占版面 -->
    <button
      type="button"
      class="tool-call-summary"
      :aria-expanded="!isCollapsed"
      :title="summaryTitle"
      @click="toggleCollapse"
    >
      <span class="tool-call-glyph">
        <component
          v-if="normalizedStatus === 'running'"
          :is="LoaderIcon"
          :size="13"
          class="spin"
        />
        <component v-else :is="getToolIcon()" :size="13" />
      </span>

      <span class="tool-call-kind">{{ kindLabel }}</span>

      <span v-if="argumentPreview" class="tool-call-target">{{ argumentPreview }}</span>

      <span v-if="statusNote" class="tool-call-note">{{ statusNote }}</span>
      <span v-if="durationText" class="tool-call-duration">{{ durationText }}</span>

      <component
        :is="ChevronRightIcon"
        :size="13"
        class="tool-call-chevron"
        :class="{ 'is-open': !isCollapsed }"
      />
    </button>

    <!-- 运行态进度：细线，不做卡片 -->
    <div v-if="showProgressStrip" class="tool-call-progress">
      <div class="tool-call-progress-track">
        <div
          class="tool-call-progress-fill"
          :class="{ 'is-indeterminate': isProgressIndeterminate }"
          :style="progressFillStyle"
        />
      </div>
      <span class="tool-call-progress-text">{{ resolvedProgressMessage }}</span>
    </div>

    <transition name="tool-body">
      <div v-if="!isCollapsed" class="tool-call-body">
        <p v-if="showDetailHint" class="tool-call-hint">{{ detailHintText }}</p>

        <div v-if="hasArguments" class="tool-call-section">
          <div class="tool-call-section-label">
            <span>{{ $t('tools.arguments') }}</span>
          </div>
          <dl class="tool-call-args">
            <div
              v-for="(value, key) in effectiveArguments"
              :key="key"
              class="tool-call-arg"
              :class="{ 'is-media': isSendMediaFilePaths(key, value) }"
            >
              <dt class="tool-call-arg-key">{{ key }}</dt>
              <dd class="tool-call-arg-value">
                <div v-if="isSendMediaFilePaths(key, value)" class="send-media-files">
                  <div
                    v-for="(filePath, fileIndex) in normalizeFilePaths(value)"
                    :key="fileIndex"
                    class="send-media-file-item"
                  >
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
                        <component :is="ExpandIcon" :size="16" />
                      </div>
                    </div>
                    <div v-else class="send-media-file-card">
                      <component :is="getFileIcon(filePath)" :size="14" class="send-media-file-icon" />
                      <span class="send-media-file-name">{{ getFileName(filePath) }}</span>
                      <button
                        class="send-media-download-btn"
                        :title="$t('chat.download') || '下载'"
                        @click.stop="handleDownloadFile(filePath)"
                      >
                        <component :is="DownloadIcon" :size="13" />
                      </button>
                    </div>
                  </div>
                </div>
                <pre v-else class="tool-call-arg-text">{{ formatValue(value) }}</pre>
              </dd>
            </div>
          </dl>
        </div>

        <div v-if="effectiveResult && showResult" class="tool-call-section">
          <div class="tool-call-section-label">
            <span>{{ $t('tools.result') }}</span>
            <span class="tool-call-section-meta">{{ $t('tools.card.lines', { count: resultLineCount }) }}</span>
            <button
              class="tool-call-copy"
              :title="copied ? $t('common.copied') : $t('common.copy')"
              @click.stop="copyResult"
            >
              <component :is="copied ? CheckIcon : CopyIcon" :size="12" />
            </button>
          </div>
          <pre class="tool-call-result">{{ effectiveResult }}</pre>
        </div>

        <div v-if="effectiveError" class="tool-call-section">
          <div class="tool-call-section-label">
            <span class="is-error">{{ $t('tools.error') }}</span>
          </div>
          <pre class="tool-call-error">{{ effectiveError }}</pre>
        </div>
      </div>
    </transition>

    <!-- 图片预览模态框 -->
    <Teleport to="body">
      <div v-if="showImagePreviewModal" class="tool-image-preview-modal" @click="closeImagePreview">
        <div class="tool-image-preview-backdrop" />
        <div class="tool-image-preview-content" @click.stop>
          <button class="tool-image-preview-close" @click="closeImagePreview">
            <component :is="XIcon" :size="22" />
          </button>
          <img :src="previewImageUrl" alt="Preview" class="tool-image-preview-img" />
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
    Boolean(props.progressMessage)
  )
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

/**
 * 摘要行的目标文本：优先取最能标识这次调用的参数（路径 / 命令 / 查询词），
 * 而不是把整段 JSON 摊在行里。
 */
const argumentPreview = computed(() => {
  if (!effectiveArguments.value) return ''

  const preferredKeys = ['path', 'file_path', 'filepath', 'command', 'cmd', 'query', 'url', 'pattern', 'task', 'message', 'content']
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
  return compact.length > 96 ? `${compact.slice(0, 96)}…` : compact
})

const summaryTitle = computed(() => {
  const target = argumentPreview.value
  return target ? `${kindLabel.value} ${target}` : kindLabel.value
})

/** 动作词：沿用 tools.names 词表，未知工具回落到原始名，不做猜测性翻译。 */
const kindLabel = computed(() => {
  const name = props.toolName || ''
  if (!name) return t('tools.card.unknownTool')

  const i18nKey = `tools.names.${name}`
  const translated = t(i18nKey)
  if (translated && translated !== i18nKey) {
    return translated
  }

  return name
})

const statusLabel = computed(() => {
  const value = t(`tools.card.status.${normalizedStatus.value}`)
  return value && value !== `tools.card.status.${normalizedStatus.value}`
    ? value
    : normalizedStatus.value
})

/**
 * 状态提示只在「需要注意」时出现：成功状态不额外写一个字，
 * 运行/失败/停止才占用摘要行右侧的位置。
 */
const statusNote = computed(() => {
  if (normalizedStatus.value === 'success') return ''
  if (normalizedStatus.value === 'running') return ''
  return statusLabel.value
})

const resultLineCount = computed(() => {
  const value = effectiveResult.value
  if (!value) return 0
  return value.replace(/\r\n/g, '\n').split('\n').length
})

const showDetailHint = computed(() => {
  return isDetailLoading.value || (props.detailAvailable && !resolvedDetailLoaded.value)
})
const detailHintText = computed(() => {
  if (isDetailLoading.value) {
    return t('tools.card.loadingDetail')
  }
  return t('tools.card.previewOnly')
})

const durationText = computed(() => {
  if (effectiveDuration.value === null || effectiveDuration.value === undefined) return ''
  return formatDuration(effectiveDuration.value)
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
