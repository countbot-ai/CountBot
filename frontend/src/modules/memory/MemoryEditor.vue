<template>
  <div ref="rootEl" class="memory-editor">
    <div class="editor-shell">
      <div class="editor-header">
        <div class="header-left">
          <button class="btn-icon" :title="t('common.close')" @click="handleClose">
            <XIcon :size="20" />
          </button>
          <div class="editor-header-copy">
            <div class="editor-kicker">
              {{ t('memory.longTermMemory') }}
            </div>
            <h2 class="editor-title">{{ title }}</h2>
          </div>
        </div>
        <div class="header-right">
          <div class="editor-metrics">
            <span class="editor-metric">
              <strong>{{ charCount }}</strong>
              <span>{{ t('memory.characters') }}</span>
            </span>
            <span class="editor-metric">
              <strong>{{ lineCount }}</strong>
              <span>{{ t('memory.lines') }}</span>
            </span>
          </div>
          <button class="btn-secondary" :disabled="isSaving" @click="handleClose">
            {{ t('common.cancel') }}
          </button>
          <button class="btn-primary" :disabled="isSaving || !hasChanges" @click="handleSave">
            <SaveIcon :size="18" />
            <span>{{ isSaving ? t('common.saving') : t('common.save') }}</span>
          </button>
        </div>
      </div>

      <div v-if="error" class="error-message">
        <AlertCircleIcon :size="18" />
        <span>{{ error }}</span>
        <button class="btn-text" @click="clearError">{{ t('common.close') }}</button>
      </div>

      <div class="editor-content">
        <div class="editor-pane">
          <div class="pane-header">
            <div>
              <h3>{{ t('memory.editor') }}</h3>
              <p class="pane-description">{{ placeholder }}</p>
            </div>
          </div>
          <textarea
            ref="textareaRef"
            v-model="content"
            class="editor-textarea"
            :placeholder="placeholder"
            @keydown.ctrl.s.prevent="handleSave"
            @keydown.meta.s.prevent="handleSave"
          />
          <div class="editor-footer">
            <span class="char-count">{{ charCount }} {{ t('memory.characters') }}</span>
            <span class="line-count">{{ lineCount }} {{ t('memory.lines') }}</span>
          </div>
        </div>

        <div class="preview-pane">
          <div class="pane-header">
            <div>
              <h3>{{ t('memory.preview') }}</h3>
              <p class="pane-description">{{ title }}</p>
            </div>
          </div>
          <div class="preview-content" v-html="previewHtml" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMemoryStore } from '@/store/memory'
import { useMarkdown } from '@/composables/useMarkdown'
import { useMermaid } from '@/composables/useMermaid'
import { AlertCircleIcon, SaveIcon, XIcon } from 'lucide-vue-next'

type MemoryTarget = 'long-term'

const props = defineProps<{
  target: MemoryTarget
}>()

const emit = defineEmits<{
  close: []
  saved: []
}>()

const { t } = useI18n()
const memoryStore = useMemoryStore()
const { renderMarkdown } = useMarkdown()
const rootEl = ref<HTMLElement | null>(null)
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const content = ref('')
const originalContent = ref('')
const isSaving = ref(false)
const error = ref<string | null>(null)

const title = computed(() =>
  t('memory.editLongTerm'),
)

const placeholder = computed(() =>
  t('memory.longTermPlaceholder'),
)

const hasChanges = computed(() => content.value !== originalContent.value)
const charCount = computed(() => content.value.length)
const lineCount = computed(() => content.value.split('\n').length)
const previewHtml = computed(() => {
  if (!content.value.trim()) {
    return `<div class="empty-preview">${t('memory.emptyPreview')}</div>`
  }
  return renderMarkdown(content.value)
})

useMermaid(rootEl, [previewHtml])

const loadContent = async () => {
  await memoryStore.loadLongTermMemory()
  content.value = memoryStore.longTermMemory
  originalContent.value = content.value
}

const handleSave = async () => {
  if (!hasChanges.value || isSaving.value) return

  isSaving.value = true
  error.value = null

  try {
    await memoryStore.saveLongTermMemory(content.value)
    originalContent.value = content.value
    emit('saved')
    emit('close')
  } catch (err: any) {
    error.value = err.message || t('memory.saveError')
  } finally {
    isSaving.value = false
  }
}

const handleClose = () => {
  if (hasChanges.value) {
    const confirmed = confirm(t('memory.unsavedChanges'))
    if (!confirmed) return
  }
  emit('close')
}

const clearError = () => {
  error.value = null
}

onMounted(() => {
  loadContent()
})
</script>
<style scoped>
@import './styles/MemoryEditor.css';
</style>
