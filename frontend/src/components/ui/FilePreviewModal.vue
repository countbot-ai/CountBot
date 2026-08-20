<template>
  <Modal
    :model-value="show"
    :title="file?.name || $t('chat.filePreview')"
    size="large"
    @update:model-value="(value) => !value && handleClose()"
  >
    <div class="file-preview-modal">
      <!-- Image Preview -->
      <div
        v-if="isImage"
        class="preview-image-container"
      >
        <img
          :src="previewUrl"
          :alt="file?.name"
          class="preview-image"
          @error="handleImageError"
        />
      </div>
      
      <!-- Text Preview -->
      <div
        v-else-if="isText"
        class="preview-text-container"
      >
        <pre class="preview-text">{{ textContent }}</pre>
      </div>
      
      <!-- PDF Preview -->
      <div
        v-else-if="isPDF"
        class="preview-pdf-container"
      >
        <iframe
          :src="previewUrl"
          class="preview-pdf"
          title="PDF Preview"
        />
      </div>
      
      <!-- Generic File Info -->
      <div
        v-else
        class="preview-generic"
      >
        <component
          :is="FileIcon"
          :size="64"
          class="generic-icon"
        />
        <div class="generic-info">
          <p class="generic-name">
            {{ file?.name }}
          </p>
          <p class="generic-type">
            {{ file?.type || $t('common.unknown') }}
          </p>
          <p class="generic-size">
            {{ formatFileSize(file?.size || 0) }}
          </p>
        </div>
        <p class="generic-hint">
          {{ $t('chat.previewNotAvailable') }}
        </p>
      </div>
      
      <!-- File Info Footer -->
      <div class="preview-footer">
        <div class="preview-info">
          <span class="info-label">{{ $t('common.size') }}:</span>
          <span class="info-value">{{ formatFileSize(file?.size || 0) }}</span>
        </div>
        <div
          v-if="file?.type"
          class="preview-info"
        >
          <span class="info-label">{{ $t('common.type') }}:</span>
          <span class="info-value">{{ file.type }}</span>
        </div>
        <div
          v-if="file?.lastModified"
          class="preview-info"
        >
          <span class="info-label">{{ $t('common.modified') }}:</span>
          <span class="info-value">{{ formatDate(file.lastModified) }}</span>
        </div>
      </div>
    </div>
    
    <template #footer>
      <div class="modal-actions">
        <Button
          variant="secondary"
          @click="handleClose"
        >
          {{ $t('common.close') }}
        </Button>
      </div>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { File as FileIcon } from 'lucide-vue-next'
import { Modal, Button } from '@/components/ui'
import { useI18n } from 'vue-i18n'

interface Props {
  show: boolean
  file: File | null
}

const props = defineProps<Props>()

interface Emits {
  (e: 'close'): void
}

const emit = defineEmits<Emits>()

const { t } = useI18n()

const previewUrl = ref<string>('')
const textContent = ref<string>('')
const imageError = ref(false)

const isImage = computed(() => {
  return props.file?.type.startsWith('image/') && !imageError.value
})

const isText = computed(() => {
  if (!props.file) return false
  return props.file.type.startsWith('text/') || 
         props.file.name.endsWith('.txt') ||
         props.file.name.endsWith('.md') ||
         props.file.name.endsWith('.json') ||
         props.file.name.endsWith('.xml')
})

const isPDF = computed(() => {
  return props.file?.type === 'application/pdf'
})

const handleClose = () => {
  emit('close')
}

const handleImageError = () => {
  imageError.value = true
}

const formatFileSize = (bytes: number): string => {
  if (bytes === 0) return '0 B'
  
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`
}

const formatDate = (timestamp: number): string => {
  const date = new Date(timestamp)
  return date.toLocaleString()
}

// Load preview content when file changes
watch(() => props.file, async (newFile) => {
  // Clean up previous preview URL
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = ''
  }
  
  textContent.value = ''
  imageError.value = false
  
  if (!newFile) return
  
  // Generate preview URL for images and PDFs
  if (newFile.type.startsWith('image/') || newFile.type === 'application/pdf') {
    previewUrl.value = URL.createObjectURL(newFile)
  }
  
  // Load text content for text files
  if (isText.value) {
    try {
      const text = await newFile.text()
      // Limit text preview to 10KB
      textContent.value = text.length > 10000 
        ? text.substring(0, 10000) + '\n\n... (truncated)'
        : text
    } catch (error) {
      console.error('Failed to read text file:', error)
      textContent.value = t('chat.failedToLoadPreview')
    }
  }
}, { immediate: true })

// Clean up on unmount
watch(() => props.show, (newShow) => {
  if (!newShow && previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = ''
  }
})
</script>

<style scoped>
.file-preview-modal {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
  min-height: 400px;
}

/* Image Preview */
.preview-image-container {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 400px;
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.preview-image {
  max-width: 100%;
  max-height: 600px;
  object-fit: contain;
}

/* Text Preview */
.preview-text-container {
  min-height: 400px;
  max-height: 600px;
  overflow: auto;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: var(--spacing-md);
}

.preview-text {
  margin: 0;
  font-family: var(--font-mono);
  font-size: var(--font-size-sm);
  color: var(--text-primary);
  white-space: pre-wrap;
  word-wrap: break-word;
}

/* PDF Preview */
.preview-pdf-container {
  min-height: 600px;
  border-radius: var(--radius-md);
  overflow: hidden;
}

.preview-pdf {
  width: 100%;
  height: 600px;
  border: none;
}

/* Generic Preview */
.preview-generic {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-lg);
  min-height: 400px;
  padding: var(--spacing-xl);
  text-align: center;
}

.generic-icon {
  color: var(--text-tertiary);
}

.generic-info {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.generic-name {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  margin: 0;
  word-break: break-all;
}

.generic-type {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  margin: 0;
}

.generic-size {
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
  margin: 0;
}

.generic-hint {
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
  margin: 0;
}

/* Footer */
.preview-footer {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-lg);
  padding: var(--spacing-md);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-color);
}

.preview-info {
  display: flex;
  gap: var(--spacing-xs);
  font-size: var(--font-size-sm);
}

.info-label {
  color: var(--text-secondary);
  font-weight: var(--font-weight-medium);
}

.info-value {
  color: var(--text-primary);
}

/* Modal Actions */
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-sm);
}

/* Scrollbar */
.preview-text-container::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

.preview-text-container::-webkit-scrollbar-track {
  background: var(--bg-primary);
}

.preview-text-container::-webkit-scrollbar-thumb {
  background: var(--border-color);
  border-radius: 4px;
}

.preview-text-container::-webkit-scrollbar-thumb:hover {
  background: var(--text-tertiary);
}
</style>
