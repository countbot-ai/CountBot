<template>
  <footer class="nc-composer-area" :class="variant">
    <TeamPicker
      :show="showTeamPicker"
      :filtered-teams="filteredTeams"
      :active-index="teamPickerIndex"
      @select="handleTeamSelect"
    />

    <div class="nc-composer" :class="{ focused: isInputFocused, busy: isUploadingAttachments }">
      <div v-if="quotedMessage" class="nc-quote-strip">
        <span class="nc-quote-label">
          {{ $t('chat.quote.label') }} · {{ quotedMessage.role === 'user' ? $t('chat.quote.self') : $t('chat.quote.assistant') }}
        </span>
        <span class="nc-quote-text">{{ quotedPreview }}</span>
        <button
          type="button"
          class="nc-quote-remove"
          :aria-label="$t('chat.quote.remove')"
          :title="$t('chat.quote.remove')"
          @click="$emit('remove-quote')"
        >
          <component :is="XIcon" :size="12" />
        </button>
      </div>

      <div v-if="attachments.length > 0" class="nc-attachment-strip">
        <div
          v-for="attachment in attachments"
          :key="attachment.id"
          class="nc-attachment-chip"
          :class="[`status-${attachment.status}`, `kind-${attachment.kind}`]"
        >
          <component :is="getAttachmentIcon(attachment)" :size="14" class="nc-attachment-icon" />
          <span class="nc-attachment-name" :title="attachment.path || attachment.name">
            {{ attachment.name }}
          </span>
          <span class="nc-attachment-size">{{ formatFileSize(attachment.size) }}</span>
          <component
            v-if="attachment.status === 'uploading'"
            :is="Loader2Icon"
            :size="12"
            class="nc-attachment-spinner"
          />
          <button
            type="button"
            class="nc-attachment-remove"
            :aria-label="$t('common.remove')"
            :title="$t('common.remove')"
            @click="$emit('remove-attachment', attachment.id)"
          >
            <component :is="XIcon" :size="12" />
          </button>
        </div>
      </div>

      <textarea
        ref="localTextareaRef"
        :value="inputMessage"
        :placeholder="$t('chat.inputPlaceholder')"
        :aria-label="$t('chat.inputPlaceholder')"
        class="nc-textarea"
        rows="1"
        @input="handleInput"
        @focus="isInputFocused = true"
        @blur="isInputFocused = false"
        @keydown="handleKeydown"
        @paste="handlePaste"
      />

      <div class="nc-composer-toolbar">
        <input
          ref="fileInputRef"
          type="file"
          class="nc-file-input"
          multiple
          @change="handleFileSelect"
        />

        <button
          type="button"
          class="nc-tool-button"
          :aria-label="$t('chat.attachFile')"
          :title="$t('chat.attachFile')"
          @click="openFileDialog"
        >
          <component :is="PaperclipIcon" :size="16" />
        </button>

        <ModelPicker
          v-if="showModelPicker"
          :groups="modelGroups || []"
          :provider-id="activeProviderId"
          :model-id="activeModelId"
          :is-session-override="isSessionOverride"
          @select="handleModelSelect"
        />
        <ReasoningLevelSelect
          v-if="showReasoningLevelSelect"
          :levels="reasoningLevels || []"
          :model-value="activeReasoningLevel ?? null"
          @change="(level: string) => $emit('select-reasoning-level', level)"
        />
        <ChatModeToggle
          v-if="showModelPicker && canSwitchChatMode"
          :mode="chatMode"
          :allowed-modes="allowedChatModes"
          @change="(mode: ChatMode) => $emit('select-chat-mode', mode)"
        />

        <button
          v-if="nativeCapabilities?.asr"
          type="button"
          class="nc-tool-button"
          :class="{ 'is-recording': isRecording, 'is-busy': isTranscribing }"
          :disabled="isTranscribing"
          :aria-label="isRecording ? $t('chat.native.stopRecording') : $t('chat.native.voiceInput')"
          :title="isRecording ? $t('chat.native.stopRecording') : $t('chat.native.voiceInput')"
          @click="toggleVoiceInput"
        >
          <component
            :is="isTranscribing ? Loader2Icon : isRecording ? SquareIcon : MicIcon"
            :size="15"
            :class="{ spin: isTranscribing }"
          />
        </button>

        <span class="nc-toolbar-spacer" />

        <button
          v-if="workspacePath"
          type="button"
          class="nc-workspace-button"
          :title="workspacePath"
          :aria-label="$t('chat.sessionConfig.openWorkspaceConfig')"
          @click="$emit('open-workspace')"
        >
          <component :is="FolderIcon" :size="14" />
          <span class="nc-workspace-name">{{ workspaceLabel }}</span>
        </button>

        <button
          v-if="isStreaming"
          class="nc-send-button is-stop"
          :aria-label="$t('chat.stopGenerationWarning')"
          :title="$t('chat.stopGenerationWarning')"
          @click="$emit('stop')"
        >
          <span class="nc-stop-square" />
        </button>
        <button
          v-else
          class="nc-send-button"
          :class="{ ready: canSend }"
          :disabled="!canSend"
          :aria-label="$t('chat.send')"
          :title="$t('chat.send')"
          @click="$emit('send')"
        >
          <component :is="ArrowUpIcon" :size="16" />
        </button>
      </div>
    </div>

    <p class="nc-composer-hint">{{ shortcutHint }}</p>
  </footer>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  AlertCircle as AlertCircleIcon,
  ArrowUp as ArrowUpIcon,
  File as FileIcon,
  Film as FilmIcon,
  Folder as FolderIcon,
  Image as ImageIcon,
  Loader2 as Loader2Icon,
  Mic as MicIcon,
  Music4 as MusicIcon,
  Paperclip as PaperclipIcon,
  Square as SquareIcon,
  X as XIcon,
} from 'lucide-vue-next'
import TeamPicker from '@/components/chat/TeamPicker.vue'
import ModelPicker from '@/components/chat/ModelPicker.vue'
import ReasoningLevelSelect from '@/components/chat/ReasoningLevelSelect.vue'
import ChatModeToggle from '@/components/chat/ChatModeToggle.vue'
import type { ModelPickerGroup } from '@/components/chat/ModelPicker.vue'
import type { ChatMode } from '@/api'
import { transcribeAudio } from '@/api/nativeCaps'
import { useToast } from '@/composables/useToast'
import type { NativeCapabilities } from '@/types/nativeCaps'
import type { AgentTeam } from '@/store/agentTeams'
import type { ComposerAttachment } from '@/composables/useChatAttachments'
import type { MessageQuote } from '@/types/chat'

interface Props {
  inputMessage: string
  isStreaming: boolean
  canSend: boolean
  showTeamPicker: boolean
  filteredTeams: AgentTeam[]
  teamPickerIndex: number
  isMac: () => boolean
  attachments: ComposerAttachment[]
  isUploadingAttachments: boolean
  modelGroups?: ModelPickerGroup[]
  activeProviderId?: string
  activeModelId?: string
  isSessionOverride?: boolean
  reasoningLevels?: string[]
  activeReasoningLevel?: string | null
  /** 对话模式：agent 可调用工具；chat 纯对话 */
  chatMode?: ChatMode
  /** 当前用户可用的对话模式；只剩一种时隐藏切换器 */
  allowedChatModes?: ChatMode[]
  /** 当前生效的工作空间路径，作为输入卡顶部的上下文条 */
  workspacePath?: string
  /** 当前模型启用的原生能力 */
  nativeCapabilities?: NativeCapabilities
  /** 已选中待引用的消息，发送时拼到正文前面进入上下文 */
  quotedMessage?: MessageQuote | null
  /** hero：欢迎页居中独立卡片；docked：对话页贴底 */
  variant?: 'hero' | 'docked'
}

const props = withDefaults(defineProps<Props>(), {
  modelGroups: () => [],
  activeProviderId: undefined,
  activeModelId: undefined,
  isSessionOverride: false,
  reasoningLevels: () => [],
  activeReasoningLevel: null,
  chatMode: 'agent',
  allowedChatModes: () => ['agent', 'chat'],
  workspacePath: '',
  nativeCapabilities: undefined,
  quotedMessage: null,
  variant: 'docked',
})

const emit = defineEmits<{
  (e: 'input', value: string): void
  (e: 'send'): void
  (e: 'stop'): void
  (e: 'keydown', event: KeyboardEvent): void
  (e: 'team-select', team: AgentTeam): void
  (e: 'files-selected', files: File[]): void
  (e: 'remove-attachment', id: string): void
  (e: 'select-model', providerId: string, modelId: string): void
  (e: 'select-reasoning-level', level: string): void
  (e: 'select-chat-mode', mode: ChatMode): void
  (e: 'open-workspace'): void
  (e: 'remove-quote'): void
}>()

const canSwitchChatMode = computed(() => props.allowedChatModes.length > 1)

const isInputFocused = ref(false)
const localTextareaRef = ref<HTMLTextAreaElement>()
const fileInputRef = ref<HTMLInputElement>()

const { t } = useI18n()
const toast = useToast()

const isRecording = ref(false)
const isTranscribing = ref(false)
let recorder: MediaRecorder | null = null
let recordingStream: MediaStream | null = null
let recordedChunks: Blob[] = []

function cleanupRecorder(): void {
  recordingStream?.getTracks().forEach(track => track.stop())
  recordingStream = null
  recorder = null
  recordedChunks = []
  isRecording.value = false
}

async function toggleVoiceInput(): Promise<void> {
  if (isTranscribing.value) {
    return
  }
  if (isRecording.value) {
    recorder?.stop()
    return
  }
  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
    toast.error(t('chat.native.voiceUnsupported'))
    return
  }
  try {
    recordingStream = await navigator.mediaDevices.getUserMedia({ audio: true })
    const preferred = 'audio/webm;codecs=opus'
    recorder = MediaRecorder.isTypeSupported(preferred)
      ? new MediaRecorder(recordingStream, { mimeType: preferred })
      : new MediaRecorder(recordingStream)
    recordedChunks = []
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        recordedChunks.push(event.data)
      }
    }
    recorder.onstop = () => {
      const mimeType = recorder?.mimeType || 'audio/webm'
      const chunks = [...recordedChunks]
      cleanupRecorder()
      void transcribeRecording(new Blob(chunks, { type: mimeType }))
    }
    recorder.start()
    isRecording.value = true
  } catch (error) {
    console.error('Failed to start recording:', error)
    cleanupRecorder()
    toast.error(t('chat.native.micDenied'))
  }
}

async function transcribeRecording(blob: Blob): Promise<void> {
  if (!blob.size) {
    return
  }
  isTranscribing.value = true
  try {
    const result = await transcribeAudio(
      blob,
      props.activeProviderId || '',
      props.activeModelId || '',
    )
    const text = result.text.trim()
    if (!text) {
      return
    }
    const prefix = props.inputMessage
      ? `${props.inputMessage}${props.inputMessage.endsWith(' ') ? '' : ' '}`
      : ''
    emit('input', `${prefix}${text}`)
  } catch (error: any) {
    console.error('Failed to transcribe recording:', error)
    toast.error(error?.response?.data?.detail || t('chat.native.transcribeFailed'))
  } finally {
    isTranscribing.value = false
  }
}

onBeforeUnmount(() => {
  recorder?.stop()
  cleanupRecorder()
})

const shortcutHint = computed(() =>
  `Enter ${t('chat.send')} · Shift+Enter ${t('chat.newLine')}`,
)

// 工具栏空间有限，路径用省略号截断，完整值放在 title 里
const workspaceLabel = computed(() => (props.workspacePath || '').replace(/[\\/]+$/, ''))

// 引用条只展示一行摘要，完整内容发送时才带入
const quotedPreview = computed(() => {
  const text = (props.quotedMessage?.content || '').replace(/\s+/g, ' ').trim()
  return text.length > 140 ? `${text.slice(0, 140)}…` : text
})

const showModelPicker = computed(() => (props.modelGroups?.length ?? 0) > 0)
const showReasoningLevelSelect = computed(
  () => showModelPicker.value && (props.reasoningLevels?.length ?? 0) > 0,
)

const resizeTextarea = () => {
  const textarea = localTextareaRef.value
  if (!textarea) return
  textarea.style.height = 'auto'
  textarea.style.height = `${Math.min(textarea.scrollHeight, 220)}px`
}

const handleInput = (event: Event) => {
  emit('input', (event.target as HTMLTextAreaElement).value)
  nextTick(resizeTextarea)
}

const handleKeydown = (event: KeyboardEvent) => {
  emit('keydown', event)
}

const handleTeamSelect = (team: AgentTeam) => {
  emit('team-select', team)
}

const handleModelSelect = (providerId: string, modelId: string) => {
  emit('select-model', providerId, modelId)
}

const openFileDialog = () => {
  fileInputRef.value?.click()
}

const emitFiles = (files: File[]) => {
  if (files.length > 0) {
    emit('files-selected', files)
  }
}

const handleFileSelect = (event: Event) => {
  const target = event.target as HTMLInputElement
  emitFiles(Array.from(target.files || []))
  target.value = ''
}

const handlePaste = (event: ClipboardEvent) => {
  const items = Array.from(event.clipboardData?.items || [])
  const files = items
    .filter(item => item.kind === 'file')
    .map(item => item.getAsFile())
    .filter((file): file is File => Boolean(file))

  if (files.length === 0) return
  event.preventDefault()
  emitFiles(files)
}

const formatFileSize = (bytes: number): string => {
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  const value = bytes / Math.pow(1024, index)
  return `${value.toFixed(value >= 10 || index === 0 ? 0 : 1)} ${units[index]}`
}

const getAttachmentIcon = (attachment: ComposerAttachment) => {
  if (attachment.status === 'error') return AlertCircleIcon
  if (attachment.kind === 'image') return ImageIcon
  if (attachment.kind === 'audio') return MusicIcon
  if (attachment.kind === 'video') return FilmIcon
  return FileIcon
}

watch(
  () => props.inputMessage,
  () => nextTick(resizeTextarea),
)

// 选中引用后把光标送回输入框，用户可以直接接着打字
watch(
  () => props.quotedMessage,
  (quote) => {
    if (quote) nextTick(() => localTextareaRef.value?.focus())
  },
)

onMounted(resizeTextarea)

defineExpose({
  textareaRef: localTextareaRef,
})
</script>

<style scoped>
@import './styles/NextComposer.css';
</style>
