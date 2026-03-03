<template>
  <div
    ref="dropZoneRef"
    class="drop-zone"
    :class="{
      'is-dragging': isDragging,
      'is-disabled': disabled
    }"
    @dragenter.prevent="handleDragEnter"
    @dragover.prevent="handleDragOver"
    @dragleave.prevent="handleDragLeave"
    @drop.prevent="handleDrop"
  >
    <slot :is-dragging="isDragging">
      <!-- Default content -->
      <div class="drop-zone-content">
        <component
          :is="UploadIcon"
          :size="48"
          class="drop-zone-icon"
        />
        <p class="drop-zone-text">
          {{ $t('chat.dropFilesHere') }}
        </p>
        <p class="drop-zone-hint">
          {{ $t('chat.dropFilesHint') }}
        </p>
      </div>
    </slot>
    
    <!-- Overlay when dragging -->
    <div
      v-if="isDragging && !disabled"
      class="drop-zone-overlay"
    >
      <div class="drop-zone-overlay-content">
        <component
          :is="UploadIcon"
          :size="64"
          class="drop-zone-overlay-icon"
        />
        <p class="drop-zone-overlay-text">
          {{ $t('chat.releaseToUpload') }}
        </p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { Upload as UploadIcon } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'

interface Props {
  accept?: string
  multiple?: boolean
  maxSize?: number
  maxFiles?: number
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  accept: '*/*',
  multiple: true,
  maxSize: 10 * 1024 * 1024,
  maxFiles: 5,
  disabled: false
})

interface Emits {
  (e: 'files-dropped', files: File[]): void
  (e: 'error', message: string): void
}

const emit = defineEmits<Emits>()

const { t } = useI18n()

const dropZoneRef = ref<HTMLElement>()
const isDragging = ref(false)
const dragCounter = ref(0)

const handleDragEnter = (event: DragEvent) => {
  if (props.disabled) return
  
  dragCounter.value++
  
  if (event.dataTransfer?.types.includes('Files')) {
    isDragging.value = true
  }
}

const handleDragOver = (event: DragEvent) => {
  if (props.disabled) return
  
  if (event.dataTransfer) {
    event.dataTransfer.dropEffect = 'copy'
  }
}

const handleDragLeave = (event: DragEvent) => {
  if (props.disabled) return
  
  dragCounter.value--
  
  if (dragCounter.value === 0) {
    isDragging.value = false
  }
}

const handleDrop = (event: DragEvent) => {
  if (props.disabled) return
  
  isDragging.value = false
  dragCounter.value = 0
  
  const files = Array.from(event.dataTransfer?.files || [])
  
  if (files.length === 0) return
  
  // Validate file count
  if (!props.multiple && files.length > 1) {
    emit('error', t('chat.fileSelectorSingleOnly'))
    return
  }
  
  if (files.length > props.maxFiles) {
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
  
  // Validate file types if accept is specified
  if (props.accept !== '*/*') {
    const acceptedTypes = props.accept.split(',').map(t => t.trim())
    const invalidTypeFiles = files.filter(file => {
      return !acceptedTypes.some(type => {
        if (type.startsWith('.')) {
          return file.name.toLowerCase().endsWith(type.toLowerCase())
        }
        if (type.endsWith('/*')) {
          const category = type.split('/')[0]
          return file.type.startsWith(category + '/')
        }
        return file.type === type
      })
    })
    
    if (invalidTypeFiles.length > 0) {
      emit('error', t('chat.invalidFileType', { 
        file: invalidTypeFiles[0].name,
        accept: props.accept
      }))
      return
    }
  }
  
  emit('files-dropped', files)
}

const formatFileSize = (bytes: number): string => {
  if (bytes === 0) return '0 B'
  
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`
}

// Prevent default drag behavior on window
const preventDefaults = (e: Event) => {
  e.preventDefault()
  e.stopPropagation()
}

onMounted(() => {
  // Prevent default drag behavior on the entire window
  window.addEventListener('dragenter', preventDefaults)
  window.addEventListener('dragover', preventDefaults)
  window.addEventListener('dragleave', preventDefaults)
  window.addEventListener('drop', preventDefaults)
})

onBeforeUnmount(() => {
  window.removeEventListener('dragenter', preventDefaults)
  window.removeEventListener('dragover', preventDefaults)
  window.removeEventListener('dragleave', preventDefaults)
  window.removeEventListener('drop', preventDefaults)
})
</script>

<style scoped>
.drop-zone {
  position: relative;
  width: 100%;
  height: 100%;
  transition: all var(--transition-base);
}

.drop-zone.is-disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.drop-zone-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-md);
  padding: var(--spacing-xl);
  text-align: center;
}

.drop-zone-icon {
  color: var(--text-tertiary);
  transition: color var(--transition-base);
}

.drop-zone.is-dragging .drop-zone-icon {
  color: var(--color-primary);
}

.drop-zone-text {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-medium);
  color: var(--text-primary);
  margin: 0;
}

.drop-zone-hint {
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
  margin: 0;
}

/* Overlay */
.drop-zone-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-primary-alpha);
  backdrop-filter: blur(4px);
  border: 2px dashed var(--color-primary);
  border-radius: var(--radius-lg);
  z-index: 1000;
  animation: fadeIn 0.2s ease-out;
}

@keyframes fadeIn {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

.drop-zone-overlay-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-md);
  padding: var(--spacing-xl);
}

.drop-zone-overlay-icon {
  color: var(--color-primary);
  animation: bounce 0.6s ease-in-out infinite;
}

@keyframes bounce {
  0%, 100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-10px);
  }
}

.drop-zone-overlay-text {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-primary);
  margin: 0;
}
</style>
