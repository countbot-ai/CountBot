<template>
  <div class="memory-editor">
    <div class="editor-header">
      <div class="header-left">
        <button
          class="btn-icon"
          :title="t('common.close')"
          @click="handleClose"
        >
          <XIcon :size="20" />
        </button>
        <h2 class="editor-title">
          {{ t('memory.editLongTerm') }}
        </h2>
      </div>
      <div class="header-right">
        <button
          class="btn-secondary"
          :disabled="isSaving"
          @click="handleClose"
        >
          {{ t('common.cancel') }}
        </button>
        <button
          class="btn-primary"
          :disabled="isSaving || !hasChanges"
          @click="handleSave"
        >
          <SaveIcon :size="18" />
          <span>{{ isSaving ? t('common.saving') : t('common.save') }}</span>
        </button>
      </div>
    </div>

    <div
      v-if="error"
      class="error-message"
    >
      <AlertCircleIcon :size="18" />
      <span>{{ error }}</span>
      <button
        class="btn-text"
        @click="clearError"
      >
        {{ t('common.close') }}
      </button>
    </div>

    <div class="editor-content">
      <div class="editor-pane">
        <div class="pane-header">
          <h3>{{ t('memory.editor') }}</h3>
          <div class="editor-tools">
            <button
              class="tool-btn"
              :title="t('memory.bold')"
              @click="insertMarkdown('**', '**')"
            >
              <BoldIcon :size="16" />
            </button>
            <button
              class="tool-btn"
              :title="t('memory.italic')"
              @click="insertMarkdown('*', '*')"
            >
              <ItalicIcon :size="16" />
            </button>
            <button
              class="tool-btn"
              :title="t('memory.code')"
              @click="insertMarkdown('`', '`')"
            >
              <CodeIcon :size="16" />
            </button>
            <button
              class="tool-btn"
              :title="t('memory.codeBlock')"
              @click="insertMarkdown('\n```\n', '\n```\n')"
            >
              <FileCodeIcon :size="16" />
            </button>
            <button
              class="tool-btn"
              :title="t('memory.heading')"
              @click="insertMarkdown('## ', '')"
            >
              <Heading2Icon :size="16" />
            </button>
            <button
              class="tool-btn"
              :title="t('memory.list')"
              @click="insertMarkdown('- ', '')"
            >
              <ListIcon :size="16" />
            </button>
            <button
              class="tool-btn"
              :title="t('memory.quote')"
              @click="insertMarkdown('> ', '')"
            >
              <QuoteIcon :size="16" />
            </button>
          </div>
        </div>
        <textarea
          ref="textareaRef"
          v-model="content"
          class="editor-textarea"
          :placeholder="t('memory.longTermPlaceholder')"
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
          <h3>{{ t('memory.preview') }}</h3>
        </div>
        <div
          class="preview-content"
          v-html="previewHtml"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMemoryStore } from '@/store/memory'
import { useMarkdown } from '@/composables/useMarkdown'
import {
    XIcon,
    SaveIcon,
    AlertCircleIcon,
    BoldIcon,
    ItalicIcon,
    CodeIcon,
    FileCodeIcon,
    Heading2Icon,
    ListIcon,
    QuoteIcon,
} from 'lucide-vue-next'

const { t } = useI18n()
const memoryStore = useMemoryStore()
const { renderMarkdown } = useMarkdown()

const emit = defineEmits<{
    close: []
    saved: []
}>()

// 状态
const content = ref<string>('')
const originalContent = ref<string>('')
const isSaving = ref(false)
const error = ref<string | null>(null)
const textareaRef = ref<HTMLTextAreaElement | null>(null)

// 计算属性
const hasChanges = computed(() => content.value !== originalContent.value)

const charCount = computed(() => content.value.length)

const lineCount = computed(() => content.value.split('\n').length)

const previewHtml = computed(() => {
    if (!content.value.trim()) {
        return `<div class="empty-preview">${t('memory.emptyPreview')}</div>`
    }
    return renderMarkdown(content.value)
})

// 方法
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

const insertMarkdown = (before: string, after: string) => {
    const textarea = textareaRef.value
    if (!textarea) return

    const start = textarea.selectionStart
    const end = textarea.selectionEnd
    const selectedText = content.value.substring(start, end)
    const newText = before + selectedText + after

    content.value = content.value.substring(0, start) + newText + content.value.substring(end)

    // 恢复光标位置
    setTimeout(() => {
        textarea.focus()
        const newCursorPos = start + before.length + selectedText.length
        textarea.setSelectionRange(newCursorPos, newCursorPos)
    }, 0)
}

// 初始化
onMounted(() => {
    loadContent()
})
</script>

<style scoped>
.memory-editor {
    display: flex;
    flex-direction: column;
    height: 100%;
    background: var(--bg-primary);
}

.editor-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1rem 1.5rem;
    border-bottom: 1px solid var(--border-color);
    background: var(--bg-secondary);
}

.header-left {
    display: flex;
    align-items: center;
    gap: 1rem;
}

.btn-icon {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 2.5rem;
    height: 2.5rem;
    border: none;
    border-radius: 0.5rem;
    background: var(--bg-tertiary);
    color: var(--text-secondary);
    cursor: pointer;
    transition: all 0.2s;
}

.btn-icon:hover {
    background: var(--bg-primary);
    color: var(--text-primary);
}

.editor-title {
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--text-primary);
    margin: 0;
}

.date-badge {
    padding: 0.375rem 0.75rem;
    background: var(--primary-bg);
    color: var(--primary);
    border-radius: 0.375rem;
    font-size: 0.875rem;
    font-weight: 500;
}

.header-right {
    display: flex;
    gap: 0.75rem;
}

.btn-secondary {
    padding: 0.625rem 1.25rem;
    border: 1px solid var(--border-color);
    border-radius: 0.5rem;
    background: var(--bg-primary);
    color: var(--text-primary);
    font-size: 0.9375rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
}

.btn-secondary:hover:not(:disabled) {
    background: var(--bg-tertiary);
    border-color: var(--primary);
}

.btn-secondary:disabled {
    opacity: 0.5;
    cursor: not-allowed;
}

.btn-primary {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.625rem 1.25rem;
    border: none;
    border-radius: 0.5rem;
    background: var(--primary);
    color: white;
    font-size: 0.9375rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
}

.btn-primary:hover:not(:disabled) {
    background: var(--primary-hover);
}

.btn-primary:disabled {
    opacity: 0.5;
    cursor: not-allowed;
}

.error-message {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 1rem 1.5rem;
    background: var(--error-bg);
    color: var(--error);
    border-bottom: 1px solid var(--border-color);
}

.error-message .btn-text {
    margin-left: auto;
    padding: 0.25rem 0.5rem;
    border: none;
    background: transparent;
    color: var(--error);
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    text-decoration: underline;
}

.editor-content {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1px;
    flex: 1;
    overflow: hidden;
    background: var(--border-color);
}

.editor-pane,
.preview-pane {
    display: flex;
    flex-direction: column;
    background: var(--bg-primary);
    overflow: hidden;
}

.pane-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1rem 1.5rem;
    border-bottom: 1px solid var(--border-color);
    background: var(--bg-secondary);
}

.pane-header h3 {
    font-size: 1rem;
    font-weight: 600;
    color: var(--text-primary);
    margin: 0;
}

.editor-tools {
    display: flex;
    gap: 0.25rem;
}

.tool-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 2rem;
    height: 2rem;
    border: none;
    border-radius: 0.375rem;
    background: transparent;
    color: var(--text-secondary);
    cursor: pointer;
    transition: all 0.2s;
}

.tool-btn:hover {
    background: var(--bg-tertiary);
    color: var(--text-primary);
}

.editor-textarea {
    flex: 1;
    padding: 1.5rem;
    border: none;
    background: var(--bg-primary);
    color: var(--text-primary);
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.9375rem;
    line-height: 1.7;
    resize: none;
    outline: none;
}

.editor-textarea::placeholder {
    color: var(--text-tertiary);
}

.editor-footer {
    display: flex;
    align-items: center;
    gap: 1.5rem;
    padding: 0.75rem 1.5rem;
    border-top: 1px solid var(--border-color);
    background: var(--bg-secondary);
    font-size: 0.8125rem;
    color: var(--text-secondary);
}

.preview-content {
    flex: 1;
    padding: 1.5rem;
    overflow-y: auto;
    color: var(--text-primary);
    line-height: 1.7;
}

.empty-preview {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: var(--text-tertiary);
    font-style: italic;
}

.preview-content :deep(h1),
.preview-content :deep(h2),
.preview-content :deep(h3) {
    margin-top: 1.5rem;
    margin-bottom: 0.75rem;
    font-weight: 600;
    color: var(--text-primary);
}

.preview-content :deep(h1) {
    font-size: 1.5rem;
}

.preview-content :deep(h2) {
    font-size: 1.25rem;
}

.preview-content :deep(h3) {
    font-size: 1.125rem;
}

.preview-content :deep(p) {
    margin: 0.75rem 0;
}

.preview-content :deep(ul),
.preview-content :deep(ol) {
    margin: 0.75rem 0;
    padding-left: 1.5rem;
}

.preview-content :deep(li) {
    margin: 0.25rem 0;
}

.preview-content :deep(code) {
    padding: 0.125rem 0.375rem;
    background: var(--bg-tertiary);
    border-radius: 0.25rem;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.875em;
}

.preview-content :deep(pre) {
    margin: 1rem 0;
    padding: 1rem;
    background: var(--bg-tertiary);
    border-radius: 0.5rem;
    overflow-x: auto;
}

.preview-content :deep(pre code) {
    padding: 0;
    background: transparent;
}

.preview-content :deep(blockquote) {
    margin: 1rem 0;
    padding-left: 1rem;
    border-left: 3px solid var(--primary);
    color: var(--text-secondary);
}

.preview-content :deep(table) {
    width: 100%;
    margin: 1rem 0;
    border-collapse: collapse;
}

.preview-content :deep(th),
.preview-content :deep(td) {
    padding: 0.5rem;
    border: 1px solid var(--border-color);
    text-align: left;
}

.preview-content :deep(th) {
    background: var(--bg-secondary);
    font-weight: 600;
}
</style>
