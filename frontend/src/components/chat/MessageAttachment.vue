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
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
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
  background: rgba(0, 0, 0, 0);
  transition: background 0.2s ease;
  color: white;
}

.attachment-image-preview:hover .attachment-overlay {
  background: rgba(0, 0, 0, 0.3);
}

/* 文件卡片 */
.attachment-file-card {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid rgba(191, 219, 254, 0.76);
  background: linear-gradient(135deg, rgba(250, 252, 255, 0.98), rgba(242, 247, 252, 0.96));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.78), 0 8px 20px rgba(15, 23, 42, 0.04);
  transition: all 0.2s ease;
}

.attachment-file-card:hover {
  border-color: rgba(147, 197, 253, 0.9);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.85), 0 12px 28px rgba(15, 23, 42, 0.06);
}

.attachment-file-icon {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.86);
  color: #475569;
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
  color: #0f172a;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.attachment-file-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  color: #64748b;
}

.attachment-download-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 8px;
  background: rgba(59, 130, 246, 0.08);
  color: #2563eb;
  cursor: pointer;
  transition: all 0.2s ease;
  flex-shrink: 0;
}

.attachment-download-btn:hover {
  background: rgba(59, 130, 246, 0.16);
  color: #1d4ed8;
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
  background: rgba(0, 0, 0, 0.85);
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
  background: rgba(255, 255, 255, 0.1);
  color: white;
  cursor: pointer;
  transition: all 0.2s ease;
}

.image-preview-close:hover {
  background: rgba(255, 255, 255, 0.2);
  transform: scale(1.1);
}

.image-preview-image {
  max-width: 100%;
  max-height: calc(90vh - 80px);
  border-radius: 12px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.4);
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
[data-theme='dark'] .attachment-file-card {
  border-color: rgba(73, 90, 113, 0.82);
  background: linear-gradient(135deg, rgba(21, 28, 38, 0.98), rgba(16, 22, 31, 0.98));
}

[data-theme='dark'] .attachment-file-icon {
  background: rgba(255, 255, 255, 0.04);
  color: #c7d3e0;
}

[data-theme='dark'] .attachment-file-name {
  color: #e5ecf6;
}

[data-theme='dark'] .attachment-file-meta {
  color: #91a1b6;
}

[data-theme='dark'] .attachment-download-btn {
  background: rgba(96, 165, 250, 0.12);
  color: #60a5fa;
}

[data-theme='dark'] .attachment-download-btn:hover {
  background: rgba(96, 165, 250, 0.24);
  color: #93c5fd;
}

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
