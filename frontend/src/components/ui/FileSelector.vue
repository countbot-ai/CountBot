<template>
  <div class="file-selector">
    <!-- Hidden file input -->
    <input
      ref="fileInputRef"
      type="file"
      :accept="accept"
      :multiple="multiple"
      class="file-input"
      @change="handleFileSelect"
    />
    
    <!-- Trigger button -->
    <button
      type="button"
      class="file-btn"
      :class="{ disabled: disabled }"
      :disabled="disabled"
      :title="title || $t('chat.attachFile')"
      @click="openFileDialog"
    >
      <slot>
        <component
          :is="PaperclipIcon"
          :size="size"
        />
      </slot>
    </button>
    
    <!-- Selected files preview -->
    <div
      v-if="selectedFiles.length > 0 && showPreview"
      class="files-preview"
    >
      <div
        v-for="(file, index) in selectedFiles"
        :key="index"
        class="file-item"
      >
        <!-- Image preview -->
        <div
          v-if="isImage(file)"
          class="file-preview"
          @click="handlePreviewClick(file)"
        >
          <img
            :src="getFilePreview(file)"
            :alt="file.name"
            class="preview-image"
          />
        </div>
        
        <!-- File icon for non-images -->
        <div
          v-else
          class="file-preview file-icon"
          @click="handlePreviewClick(file)"
        >
          <component
            :is="FileIcon"
            :size="24"
          />
        </div>
        
        <!-- File info -->
        <div class="file-info">
          <div class="file-name">
            {{ file.name }}
          </div>
          <div class="file-size">
            {{ formatFileSize(file.size) }}
          </div>
        </div>
        
        <!-- Remove button -->
        <button
          type="button"
          class="remove-btn"
          :title="$t('common.remove')"
          @click="removeFile(index)"
        >
          <component
            :is="XIcon"
            :size="16"
          />
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Paperclip as PaperclipIcon, File as FileIcon, X as XIcon } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'

interface Props {
  accept?: string
  multiple?: boolean
  maxSize?: number // in bytes
  maxFiles?: number
  disabled?: boolean
  title?: string
  size?: number
  showPreview?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  accept: '*/*',
  multiple: true,
  maxSize: 10 * 1024 * 1024, // 10MB default
  maxFiles: 5,
  disabled: false,
  size: 20,
  showPreview: true
})

interface Emits {
  (e: 'change', files: File[]): void
  (e: 'error', message: string): void
  (e: 'preview', file: File): void
}

const emit = defineEmits<Emits>()

const { t } = useI18n()

const fileInputRef = ref<HTMLInputElement>()
const selectedFiles = ref<File[]>([])
const previewUrls = ref<Map<File, string>>(new Map())

const openFileDialog = () => {
  if (props.disabled) return
  fileInputRef.value?.click()
}

const handleFileSelect = (event: Event) => {
  const target = event.target as HTMLInputElement
  const files = Array.from(target.files || [])
  
  if (files.length === 0) return
  
  // Validate file count
  if (!props.multiple && files.length > 1) {
    emit('error', t('chat.fileSelectorSingleOnly'))
    return
  }
  
  const totalFiles = selectedFiles.value.length + files.length
  if (totalFiles > props.maxFiles) {
    emit('error', t('chat.fileSelectorMaxFiles', { max: props.maxFiles }))
    return
  }
  
  // Validate file sizes
  const invalidFiles = files.filter(file => file.size > props.maxSize)
  if (invalidFiles.length > 0) {
    emit('error', t('chat.fileSelectorMaxSize', { 
      max: formatFileSize(props.maxSize),
      file: invalidFiles[0].name 
    }))
    return
  }
  
  // Add files
  selectedFiles.value.push(...files)
  
  // Generate previews for images
  files.forEach(file => {
    if (isImage(file)) {
      const url = URL.createObjectURL(file)
      previewUrls.value.set(file, url)
    }
  })
  
  // Emit change event
  emit('change', selectedFiles.value)
  
  // Reset input
  if (target) {
    target.value = ''
  }
}

const removeFile = (index: number) => {
  const file = selectedFiles.value[index]
  
  // Revoke preview URL if exists
  const previewUrl = previewUrls.value.get(file)
  if (previewUrl) {
    URL.revokeObjectURL(previewUrl)
    previewUrls.value.delete(file)
  }
  
  // Remove file
  selectedFiles.value.splice(index, 1)
  
  // Emit change event
  emit('change', selectedFiles.value)
}

const clearFiles = () => {
  // Revoke all preview URLs
  previewUrls.value.forEach(url => URL.revokeObjectURL(url))
  previewUrls.value.clear()
  
  // Clear files
  selectedFiles.value = []
  
  // Emit change event
  emit('change', [])
}

const isImage = (file: File): boolean => {
  return file.type.startsWith('image/')
}

const getFilePreview = (file: File): string => {
  return previewUrls.value.get(file) || ''
}

const formatFileSize = (bytes: number): string => {
  if (bytes === 0) return '0 B'
  
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`
}

const handlePreviewClick = (file: File) => {
  emit('preview', file)
}

// Expose methods for parent component
defineExpose({
  clearFiles,
  getFiles: () => selectedFiles.value
})
</script>

<style scoped>
.file-selector {
  position: relative;
}

.file-input {
  display: none;
}

.file-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border: none;
  border-radius: var(--radius-md);
  background: var(--bg-secondary);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--transition-base);
}

.file-btn:hover:not(.disabled) {
  background: var(--hover-bg);
  color: var(--text-primary);
}

.file-btn.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Files preview */
.files-preview {
  position: absolute;
  bottom: 100%;
  left: 0;
  right: 0;
  margin-bottom: var(--spacing-sm);
  padding: var(--spacing-sm);
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  max-height: 300px;
  overflow-y: auto;
  z-index: 10;
}

.file-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm);
  border-radius: var(--radius-sm);
  transition: background-color var(--transition-base);
}

.file-item:hover {
  background: var(--hover-bg);
}

.file-item + .file-item {
  margin-top: var(--spacing-xs);
}

.file-preview {
  flex-shrink: 0;
  width: 48px;
  height: 48px;
  border-radius: var(--radius-sm);
  overflow: hidden;
  background: var(--bg-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: transform var(--transition-base);
}

.file-preview:hover {
  transform: scale(1.05);
}

.preview-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.file-icon {
  color: var(--text-tertiary);
}

.file-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.file-name {
  font-size: var(--font-size-sm);
  color: var(--text-primary);
  font-weight: var(--font-weight-medium);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.file-size {
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
}

.remove-btn {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-tertiary);
  cursor: pointer;
  transition: all var(--transition-base);
}

.remove-btn:hover {
  background: var(--color-error-alpha);
  color: var(--color-error);
}

/* Scrollbar styling */
.files-preview::-webkit-scrollbar {
  width: 6px;
}

.files-preview::-webkit-scrollbar-track {
  background: transparent;
}

.files-preview::-webkit-scrollbar-thumb {
  background: var(--border-color);
  border-radius: 3px;
}

.files-preview::-webkit-scrollbar-thumb:hover {
  background: var(--text-tertiary);
}
</style>
