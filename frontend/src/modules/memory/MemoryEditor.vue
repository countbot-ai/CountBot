<template>
  <div ref="rootEl" class="memory-editor">
    <SettingsCard :title="title" flush>
      <template #actions>
        <span class="co-row-value">{{ charCount }} {{ t('memory.characters') }} · {{ lineCount }} {{ t('memory.lines') }}</span>
        <button class="co-btn co-btn--secondary btn-compact" :disabled="isSaving" @click="handleClose">
          {{ t('common.cancel') }}
        </button>
        <button class="co-btn co-btn--primary btn-compact" :disabled="isSaving || !hasChanges" @click="handleSave">
          {{ isSaving ? t('common.saving') : t('common.save') }}
        </button>
      </template>

      <p v-if="error" class="error-row">
        <component :is="AlertCircleIcon" :size="14" />
        <span>{{ error }}</span>
        <button class="link-btn" @click="clearError">{{ t('common.close') }}</button>
      </p>

      <div class="editor-grid">
        <section class="pane">
          <header class="pane-head">
            <span class="pane-title">{{ t('memory.editor') }}</span>
            <span class="pane-hint">Ctrl/⌘ + S</span>
          </header>
          <textarea
            ref="textareaRef"
            v-model="content"
            class="pane-textarea"
            :placeholder="placeholder"
            @keydown.ctrl.s.prevent="handleSave"
            @keydown.meta.s.prevent="handleSave"
          />
        </section>

        <section class="pane pane--preview">
          <header class="pane-head">
            <span class="pane-title">{{ t('memory.preview') }}</span>
          </header>
          <div class="pane-preview" v-html="previewHtml" />
        </section>
      </div>
    </SettingsCard>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { AlertCircle as AlertCircleIcon } from 'lucide-vue-next'
import { useConfirm } from '@/composables/useConfirm'
import { useMemoryStore } from '@/store/memory'
import { useMarkdown } from '@/composables/useMarkdown'
import { useMermaid } from '@/composables/useMermaid'
import { SettingsCard } from '@/modules/settings/ui'

type MemoryTarget = 'long-term'

defineProps<{
  target: MemoryTarget
}>()

const emit = defineEmits<{
  close: []
  saved: []
}>()

const { t } = useI18n()
const { confirm } = useConfirm()
const memoryStore = useMemoryStore()
const { renderMarkdown } = useMarkdown()
const rootEl = ref<HTMLElement | null>(null)
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const content = ref('')
const originalContent = ref('')
const isSaving = ref(false)
const error = ref<string | null>(null)

const title = computed(() => t('memory.editLongTerm'))
const placeholder = computed(() => t('memory.longTermPlaceholder'))

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

const handleClose = async () => {
  if (hasChanges.value) {
    const confirmed = await confirm({
      title: t('memory.unsavedChanges'),
      type: 'warning',
      confirmText: t('common.confirm'),
      cancelText: t('common.cancel'),
    })
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
.btn-compact {
  height: 26px;
  padding: 0 10px;
  font-size: var(--font-size-xs);
}

.error-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  padding: 8px var(--co-row-gutter);
  border-bottom: 1px solid var(--color-border-primary);
  font-size: var(--font-size-xs);
  color: var(--color-error);
}

.link-btn {
  margin-left: auto;
  border: none;
  background: none;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-xs);
  cursor: pointer;
}

/* 编辑与预览并排，两栏同高，滚动各自独立 */
.editor-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  height: 520px;
}

.pane {
  display: flex;
  min-width: 0;
  min-height: 0;
  flex-direction: column;
}

.pane--preview {
  border-left: 1px solid var(--color-border-primary);
}

.pane-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
  height: 32px;
  padding: 0 var(--co-row-gutter);
  border-bottom: 1px solid var(--color-border-primary);
}

.pane-title {
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
}

.pane-hint {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--color-text-disabled);
}

.pane-textarea {
  flex: 1;
  min-height: 0;
  padding: 12px var(--co-row-gutter);
  border: none;
  background: transparent;
  color: var(--color-text-primary);
  font-family: var(--font-mono);
  font-size: var(--font-size-sm);
  line-height: 1.7;
  resize: none;
}

.pane-textarea:focus {
  outline: none;
}

.pane-preview {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 12px var(--co-row-gutter);
  font-size: var(--font-size-sm);
  line-height: 1.75;
  color: var(--color-text-primary);
}

.pane-preview :deep(> :first-child) {
  margin-top: 0;
}

/* 预览区与只读态的正文同一套标题档位 */
.pane-preview :deep(h1) {
  margin: 16px 0 6px;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
}

.pane-preview :deep(h2) {
  margin: 14px 0 6px;
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
}

.pane-preview :deep(h3),
.pane-preview :deep(h4) {
  margin: 12px 0 4px;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
}

.pane-preview :deep(p) {
  margin: 0 0 6px;
}

.pane-preview :deep(ul),
.pane-preview :deep(ol) {
  margin: 0 0 6px;
  padding-left: 18px;
}

@media (max-width: 900px) {
  .editor-grid {
    grid-template-columns: minmax(0, 1fr);
    height: auto;
  }

  .pane--preview {
    border-left: none;
    border-top: 1px solid var(--color-border-primary);
  }

  .pane-textarea {
    min-height: 320px;
  }

  .pane-preview {
    min-height: 240px;
  }
}
</style>
