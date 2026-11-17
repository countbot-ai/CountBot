import { ref } from 'vue'
import { useToast } from '@/composables/useToast'
import { useI18n } from 'vue-i18n'

export function useFileUpload() {
  const toast = useToast()
  const { t } = useI18n()
  
  const isDraggingOver = ref(false)
  const dragCounter = ref(0)
  const selectedFiles = ref<File[]>([])
  
  const maxSize = 10 * 1024 * 1024 // 10MB
  const maxFiles = 5
  
  // 格式化文件大小
  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`
  }
  
  // 验证文件
  const validateFiles = (files: File[]): { valid: boolean; error?: string } => {
    // 检查文件数量
    const totalFiles = selectedFiles.value.length + files.length
    if (totalFiles > maxFiles) {
      return {
        valid: false,
        error: t('chat.fileSelectorMaxFiles', { max: maxFiles })
      }
    }
    
    // 检查文件大小
    const invalidFiles = files.filter(file => file.size > maxSize)
    if (invalidFiles.length > 0) {
      return {
        valid: false,
        error: t('chat.fileSelectorMaxSize', {
          max: formatFileSize(maxSize),
          file: invalidFiles[0].name
        })
      }
    }
    
    return { valid: true }
  }
  
  // 拖拽进入
  const handleDragEnter = (e: DragEvent, isConnected: boolean, isStreaming: boolean) => {
    if (!isConnected || isStreaming) return
    
    dragCounter.value++
    
    if (e.dataTransfer?.types.includes('Files')) {
      isDraggingOver.value = true
    }
  }
  
  // 拖拽悬停
  const handleDragOver = (e: DragEvent, isConnected: boolean, isStreaming: boolean) => {
    if (!isConnected || isStreaming) return
    
    if (e.dataTransfer) {
      e.dataTransfer.dropEffect = 'copy'
    }
  }
  
  // 拖拽离开
  const handleDragLeave = (e: DragEvent, isConnected: boolean, isStreaming: boolean) => {
    if (!isConnected || isStreaming) return
    
    dragCounter.value--
    
    if (dragCounter.value === 0) {
      isDraggingOver.value = false
    }
  }
  
  // 拖拽放下
  const handleDrop = (e: DragEvent, isConnected: boolean, isStreaming: boolean) => {
    if (!isConnected || isStreaming) return
    
    isDraggingOver.value = false
    dragCounter.value = 0
    
    const files = Array.from(e.dataTransfer?.files || [])
    
    if (files.length === 0) return
    
    const validation = validateFiles(files)
    if (!validation.valid) {
      toast.error(validation.error!)
      return
    }
    
    selectedFiles.value.push(...files)
    toast.success(t('chat.filesAdded', { count: files.length }))
  }
  
  // 清空文件
  const clearFiles = () => {
    selectedFiles.value = []
  }
  
  return {
    // 状态
    isDraggingOver,
    selectedFiles,
    
    // 方法
    handleDragEnter,
    handleDragOver,
    handleDragLeave,
    handleDrop,
    clearFiles,
    validateFiles,
    formatFileSize
  }
}
