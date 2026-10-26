<template>
  <footer class="nc-composer-area" :class="variant">
    <TeamPicker
      :show="showTeamPicker"
      :filtered-teams="filteredTeams"
      :active-index="teamPickerIndex"
      @select="handleTeamSelect"
    />

    <div class="nc-composer" :class="{ focused: isInputFocused, busy: isUploadingAttachments }">
      <div v-if="contextLabel" class="nc-composer-context">
        <button
          type="button"
          class="nc-context-pill"
          :title="contextLabel"
          @click="$emit('open-context')"
        >
          <span class="nc-context-dot" aria-hidden="true" />
          <span class="nc-context-name">{{ contextLabel }}</span>
          <component :is="ChevronDownIcon" :size="12" class="nc-context-chevron" />
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

        <span class="nc-toolbar-spacer" />

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
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  AlertCircle as AlertCircleIcon,
  ArrowUp as ArrowUpIcon,
  ChevronDown as ChevronDownIcon,
  File as FileIcon,
  Film as FilmIcon,
  Image as ImageIcon,
  Loader2 as Loader2Icon,
  Music4 as MusicIcon,
  Paperclip as PaperclipIcon,
  X as XIcon,
} from 'lucide-vue-next'
import TeamPicker from '@/components/chat/TeamPicker.vue'
import ModelPicker from '@/components/chat/ModelPicker.vue'
import ReasoningLevelSelect from '@/components/chat/ReasoningLevelSelect.vue'
import type { ModelPickerGroup } from '@/components/chat/ModelPicker.vue'
import type { AgentTeam } from '@/store/agentTeams'
import type { ComposerAttachment } from '@/composables/useChatAttachments'

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
  /** 当前会话名，作为输入卡顶部的上下文条 */
  contextLabel?: string
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
  contextLabel: '',
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
  (e: 'open-context'): void
}>()

const isInputFocused = ref(false)
const localTextareaRef = ref<HTMLTextAreaElement>()
const fileInputRef = ref<HTMLInputElement>()

const { t } = useI18n()

const shortcutHint = computed(() =>
  props.isMac()
    ? `⌘+Enter ${t('chat.send')} · Enter ${t('chat.newLine')}`
    : `Enter ${t('chat.send')} · Shift+Enter ${t('chat.newLine')}`,
)

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

onMounted(resizeTextarea)

defineExpose({
  textareaRef: localTextareaRef,
})
</script>

<style scoped>
@import './styles/NextComposer.css';
</style>
