<template>
  <footer class="input-area">
    <TeamPicker
      :show="showTeamPicker"
      :filtered-teams="filteredTeams"
      :active-index="teamPickerIndex"
      @select="handleTeamSelect"
    />

    <div class="input-shell" :class="{ focused: isInputFocused, busy: isUploadingAttachments }">
      <div v-if="attachments.length > 0" class="attachment-strip">
        <div
          v-for="attachment in attachments"
          :key="attachment.id"
          class="attachment-chip"
          :class="[`status-${attachment.status}`, `kind-${attachment.kind}`]"
        >
          <div class="attachment-chip-icon">
            <component :is="getAttachmentIcon(attachment)" :size="16" />
          </div>
          <div class="attachment-chip-copy">
            <div class="attachment-chip-name">{{ attachment.name }}</div>
            <div class="attachment-chip-meta">
              <span class="attachment-chip-path">
                {{ attachment.path || $t('chat.uploadingAttachment') }}
              </span>
              <span>{{ formatFileSize(attachment.size) }}</span>
            </div>
          </div>
          <div class="attachment-chip-trailing">
            <component
              v-if="attachment.status === 'uploading'"
              :is="Loader2Icon"
              :size="14"
              class="attachment-spinner"
            />
            <component
              v-else-if="attachment.status === 'error'"
              :is="AlertCircleIcon"
              :size="14"
              class="attachment-error-icon"
            />
            <button
              type="button"
              class="attachment-remove-btn"
              :aria-label="$t('common.remove')"
              :title="$t('common.remove')"
              @click="$emit('remove-attachment', attachment.id)"
            >
              <component :is="XIcon" :size="14" />
            </button>
          </div>
        </div>
      </div>

      <div class="composer-row">
        <input
          ref="fileInputRef"
          type="file"
          class="file-input"
          multiple
          @change="handleFileSelect"
        />

        <button
          type="button"
          class="attach-btn"
          :aria-label="$t('chat.attachFile')"
          :title="$t('chat.attachFile')"
          @click="openFileDialog"
        >
          <component :is="PaperclipIcon" :size="16" />
        </button>

        <div class="composer-main">
          <textarea
            ref="localTextareaRef"
            :value="inputMessage"
            :placeholder="$t('chat.inputPlaceholder')"
            :aria-label="$t('chat.inputPlaceholder')"
            class="chat-input"
            rows="1"
            @input="$emit('input', ($event.target as HTMLTextAreaElement).value)"
            @focus="isInputFocused = true"
            @blur="isInputFocused = false"
            @keydown="handleKeydown"
            @paste="handlePaste"
          />

          <!-- 模型选择器内嵌在输入框底部，与输入区同一边框 -->
          <div v-if="showModelPicker" class="composer-footer">
            <ModelPicker
              :groups="modelGroups || []"
              :provider-id="activeProviderId"
              :model-id="activeModelId"
              :is-session-override="isSessionOverride"
              @select="handleModelSelect"
            />
            <ReasoningLevelSelect
              v-if="showReasoningLevelSelect"
              :levels="reasoningLevels || []"
              :model-value="activeReasoningLevel"
              @change="(level) => emit('select-reasoning-level', level)"
            />
            <ChatModeToggle
              v-if="showModelPicker && canSwitchChatMode"
              :mode="chatMode"
              :allowed-modes="allowedChatModes"
              @change="(mode) => emit('select-chat-mode', mode)"
            />
          </div>
        </div>

        <div class="input-actions">
          <button
            v-if="isStreaming"
            class="stop-generation-btn"
            :aria-label="$t('chat.stopGenerationWarning')"
            :title="$t('chat.stopGenerationWarning')"
            @click="$emit('stop')"
          >
            <span class="stop-square" />
          </button>
          <button
            v-else
            class="send-message-btn"
            :class="{ ready: canSend }"
            :disabled="!canSend"
            :aria-label="$t('chat.send')"
            @click="$emit('send')"
          >
            <component :is="SendIcon" :size="16" />
          </button>
        </div>
      </div>
    </div>

    <p class="input-hint">
      {{ $t('chat.pickTeamHint') }} ·
      Enter {{ $t('chat.send') }} ·
      Shift+Enter {{ $t('chat.newLine') }}
    </p>
  </footer>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  AlertCircle as AlertCircleIcon,
  File as FileIcon,
  Film as FilmIcon,
  Image as ImageIcon,
  Loader2 as Loader2Icon,
  Music4 as MusicIcon,
  Paperclip as PaperclipIcon,
  Send as SendIcon,
  X as XIcon,
} from 'lucide-vue-next'
import TeamPicker from './TeamPicker.vue'
import ModelPicker from './ModelPicker.vue'
import ReasoningLevelSelect from './ReasoningLevelSelect.vue'
import ChatModeToggle from './ChatModeToggle.vue'
import type { ModelPickerGroup } from './ModelPicker.vue'
import type { ChatMode } from '@/api'
import type { AgentTeam } from '@/store/agentTeams'
import type { ComposerAttachment } from '@/composables/useChatAttachments'

interface Props {
  inputMessage: string
  textareaRef: HTMLTextAreaElement | undefined
  isStreaming: boolean
  canSend: boolean
  showTeamPicker: boolean
  filteredTeams: AgentTeam[]
  teamPickerIndex: number
  isMac: () => boolean
  attachments: ComposerAttachment[]
  isUploadingAttachments: boolean
  /** 模型选择器数据；为空数组时不渲染工具栏 */
  modelGroups?: ModelPickerGroup[]
  activeProviderId?: string
  activeModelId?: string
  isSessionOverride?: boolean
  /** 当前模型的思考档位；为空数组时不渲染「思考强度」下拉 */
  reasoningLevels?: string[]
  activeReasoningLevel?: string | null
  /** 对话模式：agent 可调用工具；chat 纯对话 */
  chatMode?: ChatMode
  /** 当前用户可用的对话模式；只剩一种时隐藏切换器 */
  allowedChatModes?: ChatMode[]
}

const props = defineProps<Props>()

interface Emits {
  input: [value: string]
  send: []
  stop: []
  keydown: [event: KeyboardEvent]
  'team-select': [team: AgentTeam]
  'files-selected': [files: File[]]
  'remove-attachment': [id: string]
  'select-model': [providerId: string, modelId: string]
  'select-reasoning-level': [level: string]
  'select-chat-mode': [mode: ChatMode]
}

const emit = defineEmits<Emits>()

const canSwitchChatMode = computed(() => (props.allowedChatModes?.length ?? 2) > 1)

const isInputFocused = ref(false)
const localTextareaRef = ref<HTMLTextAreaElement>()
const fileInputRef = ref<HTMLInputElement>()

const handleKeydown = (event: KeyboardEvent) => {
  emit('keydown', event)
}

const handleTeamSelect = (team: AgentTeam) => {
  emit('team-select', team)
}

const showModelPicker = computed(() => (props.modelGroups?.length ?? 0) > 0)

const showReasoningLevelSelect = computed(
  () => showModelPicker.value && (props.reasoningLevels?.length ?? 0) > 0,
)

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
  const files = Array.from(target.files || [])
  emitFiles(files)
  target.value = ''
}

const handlePaste = (event: ClipboardEvent) => {
  const items = Array.from(event.clipboardData?.items || [])
  const files = items
    .filter((item) => item.kind === 'file')
    .map((item) => item.getAsFile())
    .filter((file): file is File => Boolean(file))

  if (files.length === 0) {
    return
  }

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

defineExpose({
  textareaRef: localTextareaRef
})
</script>
<style scoped>
@import './styles/ChatInput.css';
</style>
