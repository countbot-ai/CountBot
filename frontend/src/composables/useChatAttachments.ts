import { computed, ref } from 'vue'
import type { AttachmentItem } from '@/api/endpoints'
import { chatAPI } from '@/api'
import { useToast } from '@/composables/useToast'
import { useI18n } from 'vue-i18n'

export type ComposerAttachment = AttachmentItem & {
  id: string
  status: 'uploading' | 'ready' | 'error'
  error?: string
}

const MAX_ATTACHMENTS = 10
const MAX_ATTACHMENT_SIZE = 25 * 1024 * 1024

function inferAttachmentKind(file: File): ComposerAttachment['kind'] {
  if (file.type.startsWith('image/')) return 'image'
  if (file.type.startsWith('audio/')) return 'audio'
  if (file.type.startsWith('video/')) return 'video'
  return 'file'
}

function formatFileSize(bytes: number): string {
  if (bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  const value = bytes / Math.pow(1024, index)
  return `${value.toFixed(value >= 10 || index === 0 ? 0 : 1)} ${units[index]}`
}

export function useChatAttachments() {
  const toast = useToast()
  const { t } = useI18n()

  const attachments = ref<ComposerAttachment[]>([])
  const isUploading = computed(() => attachments.value.some((item) => item.status === 'uploading'))
  const readyAttachments = computed(() => attachments.value.filter((item) => item.status === 'ready'))

  function removeAttachment(id: string) {
    attachments.value = attachments.value.filter((item) => item.id !== id)
  }

  function clearAttachments() {
    attachments.value = []
  }

  function buildDuplicateKey(file: File) {
    return `${file.name}::${file.size}`
  }

  async function addFiles(files: File[], sessionId: string | null) {
    if (!sessionId) {
      toast.error(t('chat.attachmentSessionRequired'))
      return
    }

    const currentKeys = new Set(
      attachments.value.map((item) => `${item.name}::${item.size}`)
    )

    const incoming = files.filter((file) => !!file)
    if (incoming.length === 0) {
      return
    }

    const remainingSlots = MAX_ATTACHMENTS - attachments.value.length
    if (remainingSlots <= 0) {
      toast.error(t('chat.fileSelectorMaxFiles', { max: MAX_ATTACHMENTS }))
      return
    }

    const limited = incoming.slice(0, remainingSlots)
    if (limited.length < incoming.length) {
      toast.warning(t('chat.fileSelectorMaxFiles', { max: MAX_ATTACHMENTS }))
    }

    for (const file of limited) {
      if (file.size > MAX_ATTACHMENT_SIZE) {
        toast.error(
          t('chat.fileSelectorMaxSize', {
            max: formatFileSize(MAX_ATTACHMENT_SIZE),
            file: file.name || t('chat.unnamedAttachment'),
          })
        )
        continue
      }

      const duplicateKey = buildDuplicateKey(file)
      if (currentKeys.has(duplicateKey)) {
        continue
      }
      currentKeys.add(duplicateKey)

      const id = `attachment-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
      attachments.value.push({
        id,
        path: '',
        name: file.name || t('chat.unnamedAttachment'),
        size: file.size,
        content_type: file.type || null,
        kind: inferAttachmentKind(file),
        status: 'uploading',
      })

      try {
        const uploaded = await chatAPI.uploadAttachment(sessionId, file)
        const index = attachments.value.findIndex((item) => item.id === id)
        if (index === -1) {
          continue
        }
        attachments.value[index] = {
          ...attachments.value[index],
          ...uploaded,
          status: 'ready',
          error: undefined,
        }
      } catch (error: any) {
        const index = attachments.value.findIndex((item) => item.id === id)
        const errorMessage = error?.message || t('chat.attachmentUploadFailed')
        if (index !== -1) {
          attachments.value[index] = {
            ...attachments.value[index],
            status: 'error',
            error: errorMessage,
          }
        }
        toast.error(errorMessage)
      }
    }
  }

  return {
    attachments,
    readyAttachments,
    isUploading,
    maxAttachments: MAX_ATTACHMENTS,
    maxAttachmentSize: MAX_ATTACHMENT_SIZE,
    addFiles,
    removeAttachment,
    clearAttachments,
    formatFileSize,
  }
}
