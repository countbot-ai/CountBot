<template>
  <div class="message-attachment" :class="`attachment-${attachment.kind}`">
    <!-- 图片附件：显示缩略图预览 -->
    <div
      v-if="isImage"
      class="attachment-image-preview"
      @click="handlePreviewImage"
    >
      <img
        :src="attachmentPath"
        :alt="attachment.name"
        class="attachment-thumbnail"
        @error="handleImageError"
      />
      <div class="attachment-overlay">
        <component :is="ExpandIcon" :size="20" />
      </div>
    </div>

    <!-- 文件附件：显示带下载按钮的卡片 -->
    <div v-else class="attachment-file-card">
      <div class="attachment-file-icon">
        <component :is="getIconComponent" :size="20" />
      </div>
      <div class="attachment-file-info">
        <div class="attachment-file-name">{{ attachment.name }}</div>
        <div class="attachment-file-meta">
          <span>{{ formatAttachmentSize(attachment.size) }}</span>
          <span v-if="attachment.kind">{{ attachment.kind }}</span>
        </div>
      </div>
      <button
        class="attachment-download-btn"
        :title="$t('chat.download') || '下载'"
        @click="handleDownload"
      >
        <component :is="DownloadIcon" :size="16" />
      </button>
    </div>
  </div>

  <!-- 图片预览模态框 -->
  <Teleport to="body">
    <div
      v-if="showImagePreview"
      class="image-preview-modal"
      @click="closePreview"
    >
      <div class="image-preview-backdrop" />
      <div class="image-preview-content" @click.stop>
        <button class="image-preview-close" @click="closePreview">
          <component :is="XIcon" :size="24" />
        </button>
        <img
          :src="attachmentPath"
          :alt="attachment.name"
          class="image-preview-image"
        />
        <div class="image-preview-info">
          <span class="image-preview-name">{{ attachment.name }}</span>
          <span class="image-preview-size">{{ formatAttachmentSize(attachment.size) }}</span>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  File as FileIcon,
  Film as FilmIcon,
  Image as ImageIcon,
  Music4 as MusicIcon,
  Expand as ExpandIcon,
  Download as DownloadIcon,
  X as XIcon
} from 'lucide-vue-next'
import type { AttachmentItem } from '@/api/endpoints'

interface Props {
  attachment: AttachmentItem
  sessionId: string
}

const props = defineProps<Props>()

const showImagePreview = ref(false)
const imageError = ref(false)

const isImage = computed(() => {
  return props.attachment.kind === 'image' && !imageError.value
})

const attachmentPath = computed(() => {
  const path = props.attachment.path
  if (!path) return ''
  
  if (path.startsWith('http://') || path.startsWith('https://')) {
    return path
  }
  
  const sessionId = props.sessionId
  return `/api/chat/sessions/${sessionId}/attachments/${encodeURIComponent(path)}`
})

const getIconComponent = computed(() => {
  const kind = props.attachment.kind
  if (kind === 'audio') return MusicIcon
  if (kind === 'video') return FilmIcon
  if (kind === 'image') return ImageIcon
  return FileIcon
})

const formatAttachmentSize = (bytes?: number | null): string => {
  const value = Number(bytes || 0)
  if (!value) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const index = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1)
  const formatted = value / Math.pow(1024, index)
  return `${formatted.toFixed(formatted >= 10 || index === 0 ? 0 : 1)} ${units[index]}`
}

const handlePreviewImage = () => {
  if (imageError.value) return
  showImagePreview.value = true
}

const closePreview = () => {
  showImagePreview.value = false
}

const handleImageError = () => {
  imageError.value = true
}

const handleDownload = async () => {
  const url = attachmentPath.value
  if (!url) return

  try {
    const response = await fetch(url)
    if (!response.ok) {
      throw new Error('Download failed')
    }
    const blob = await response.blob()
    const blobUrl = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = blobUrl
    link.download = props.attachment.name
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(blobUrl)
  } catch (error) {
    console.error('Failed to download file:', error)
  }
}
</script>

<style scoped>
.message-attachment {
  max-width: 480px;
}

/* 图片预览 */
.attachment-image-preview {
  position: relative;
  border-radius: 12px;
  overflow: hidden;
  cursor: pointer;
  transition: all 0.2s ease;
  background: var(--bg-secondary);
}

.attachment-image-preview:hover {
  transform: scale(1.02);
  box-shadow: var(--shadow-sm);
}

.attachment-thumbnail {
  display: block;
  width: 100%;
  max-height: 300px;
  object-fit: cover;
  border-radius: 12px;
}

.attachment-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-bg-overlay);
  transition: background 0.2s ease;
  color: white;
}

.attachment-image-preview:hover .attachment-overlay {
  background: var(--color-bg-overlay);
}

/* 文件卡片 */
.attachment-file-card {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid var(--color-border-primary);
  background: var(--color-bg-secondary);
  box-shadow: var(--shadow-sm);
  transition: all 0.2s ease;
}

.attachment-file-card:hover {
  border-color: var(--color-border-primary);
  box-shadow: var(--shadow-sm);
}

.attachment-file-icon {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-bg-elevated);
  color: var(--text-secondary);
  flex-shrink: 0;
}

.attachment-file-info {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.attachment-file-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.attachment-file-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  color: var(--text-secondary);
}

.attachment-download-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 8px;
  background: var(--color-bg-tertiary);
  color: var(--color-accent);
  cursor: pointer;
  transition: all 0.2s ease;
  flex-shrink: 0;
}

.attachment-download-btn:hover {
  background: var(--color-bg-tertiary);
  color: var(--color-accent);
  transform: scale(1.08);
}

.attachment-download-btn:active {
  transform: scale(0.95);
}

/* 图片预览模态框 */
.image-preview-modal {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
}

.image-preview-backdrop {
  position: absolute;
  inset: 0;
  background: var(--color-bg-overlay);
  backdrop-filter: blur(8px);
}

.image-preview-content {
  position: relative;
  max-width: 90vw;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}

.image-preview-close {
  position: absolute;
  top: -48px;
  right: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 50%;
  background: var(--color-bg-elevated);
  color: white;
  cursor: pointer;
  transition: all 0.2s ease;
}

.image-preview-close:hover {
  background: var(--color-bg-elevated);
  transform: scale(1.1);
}

.image-preview-image {
  max-width: 100%;
  max-height: calc(90vh - 80px);
  border-radius: 12px;
  box-shadow: var(--shadow-sm);
  object-fit: contain;
}

.image-preview-info {
  display: flex;
  align-items: center;
  gap: 12px;
  color: white;
  font-size: 13px;
}

.image-preview-name {
  font-weight: 600;
  opacity: 0.9;
}

.image-preview-size {
  opacity: 0.6;
}

/* 深色主题适配 */












/* 响应式 */
@media (max-width: 768px) {
  .message-attachment {
    max-width: 100%;
  }

  .attachment-thumbnail {
    max-height: 240px;
  }
}
</style>
