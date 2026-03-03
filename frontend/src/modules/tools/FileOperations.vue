<template>
  <div class="file-operations">
    <div class="operations-tabs">
      <button
        v-for="op in operations"
        :key="op.id"
        class="op-tab"
        :class="{ active: activeOp === op.id }"
        @click="activeOp = op.id"
      >
        <component
          :is="op.icon"
          :size="18"
        />
        <span>{{ $t(`tools.fileOps.${op.id}`) }}</span>
      </button>
    </div>

    <div class="op-content">
      <!-- Read File -->
      <div
        v-if="activeOp === 'read'"
        class="op-panel"
      >
        <h3 class="op-title">
          {{ $t('tools.fileOps.readFile') }}
        </h3>
        <p class="op-desc">
          {{ $t('tools.fileOps.readFileDesc') }}
        </p>
        
        <div class="form-group">
          <label class="form-label">
            {{ $t('tools.fileOps.filePath') }}
            <span class="required">*</span>
          </label>
          <input
            v-model="readForm.path"
            type="text"
            class="form-input"
            :placeholder="$t('tools.fileOps.filePathPlaceholder')"
          >
        </div>

        <button
          class="execute-btn"
          :disabled="!readForm.path || executing"
          @click="executeRead"
        >
          <component
            :is="executing ? LoaderIcon : FileTextIcon"
            :size="16"
            :class="{ 'spin': executing }"
          />
          {{ executing ? $t('tools.executing') : $t('tools.execute') }}
        </button>

        <div
          v-if="readResult"
          class="result-section"
        >
          <h4 class="result-title">
            {{ $t('tools.result') }}
          </h4>
          <div
            class="result-box"
            :class="{ error: readResult.error }"
          >
            <pre>{{ readResult.content }}</pre>
          </div>
        </div>
      </div>

      <!-- Write File -->
      <div
        v-if="activeOp === 'write'"
        class="op-panel"
      >
        <h3 class="op-title">
          {{ $t('tools.fileOps.writeFile') }}
        </h3>
        <p class="op-desc">
          {{ $t('tools.fileOps.writeFileDesc') }}
        </p>
        
        <div class="form-group">
          <label class="form-label">
            {{ $t('tools.fileOps.filePath') }}
            <span class="required">*</span>
          </label>
          <input
            v-model="writeForm.path"
            type="text"
            class="form-input"
            :placeholder="$t('tools.fileOps.filePathPlaceholder')"
          >
        </div>

        <div class="form-group">
          <label class="form-label">
            {{ $t('tools.fileOps.content') }}
            <span class="required">*</span>
          </label>
          <textarea
            v-model="writeForm.content"
            class="form-textarea"
            rows="10"
            :placeholder="$t('tools.fileOps.contentPlaceholder')"
          />
        </div>

        <button
          class="execute-btn"
          :disabled="!writeForm.path || !writeForm.content || executing"
          @click="executeWrite"
        >
          <component
            :is="executing ? LoaderIcon : SaveIcon"
            :size="16"
            :class="{ 'spin': executing }"
          />
          {{ executing ? $t('tools.executing') : $t('tools.execute') }}
        </button>

        <div
          v-if="writeResult"
          class="result-section"
        >
          <h4 class="result-title">
            {{ $t('tools.result') }}
          </h4>
          <div
            class="result-box"
            :class="{ error: writeResult.error }"
          >
            <pre>{{ writeResult.message }}</pre>
          </div>
        </div>
      </div>

      <!-- Edit File -->
      <div
        v-if="activeOp === 'edit'"
        class="op-panel"
      >
        <h3 class="op-title">
          {{ $t('tools.fileOps.editFile') }}
        </h3>
        <p class="op-desc">
          {{ $t('tools.fileOps.editFileDesc') }}
        </p>
        
        <div class="form-group">
          <label class="form-label">
            {{ $t('tools.fileOps.filePath') }}
            <span class="required">*</span>
          </label>
          <input
            v-model="editForm.path"
            type="text"
            class="form-input"
            :placeholder="$t('tools.fileOps.filePathPlaceholder')"
          >
        </div>

        <div class="form-group">
          <label class="form-label">
            {{ $t('tools.fileOps.oldText') }}
            <span class="required">*</span>
          </label>
          <textarea
            v-model="editForm.oldText"
            class="form-textarea"
            rows="5"
            :placeholder="$t('tools.fileOps.oldTextPlaceholder')"
          />
        </div>

        <div class="form-group">
          <label class="form-label">
            {{ $t('tools.fileOps.newText') }}
            <span class="required">*</span>
          </label>
          <textarea
            v-model="editForm.newText"
            class="form-textarea"
            rows="5"
            :placeholder="$t('tools.fileOps.newTextPlaceholder')"
          />
        </div>

        <button
          class="execute-btn"
          :disabled="!editForm.path || !editForm.oldText || executing"
          @click="executeEdit"
        >
          <component
            :is="executing ? LoaderIcon : EditIcon"
            :size="16"
            :class="{ 'spin': executing }"
          />
          {{ executing ? $t('tools.executing') : $t('tools.execute') }}
        </button>

        <div
          v-if="editResult"
          class="result-section"
        >
          <h4 class="result-title">
            {{ $t('tools.result') }}
          </h4>
          <div
            class="result-box"
            :class="{ error: editResult.error }"
          >
            <pre>{{ editResult.message }}</pre>
          </div>
        </div>
      </div>

      <!-- List Directory -->
      <div
        v-if="activeOp === 'list'"
        class="op-panel"
      >
        <h3 class="op-title">
          {{ $t('tools.fileOps.listDir') }}
        </h3>
        <p class="op-desc">
          {{ $t('tools.fileOps.listDirDesc') }}
        </p>
        
        <div class="form-group">
          <label class="form-label">
            {{ $t('tools.fileOps.dirPath') }}
          </label>
          <input
            v-model="listForm.path"
            type="text"
            class="form-input"
            :placeholder="$t('tools.fileOps.dirPathPlaceholder')"
          >
          <span class="form-hint">
            {{ $t('tools.fileOps.dirPathHint') }}
          </span>
        </div>

        <button
          class="execute-btn"
          :disabled="executing"
          @click="executeList"
        >
          <component
            :is="executing ? LoaderIcon : FolderIcon"
            :size="16"
            :class="{ 'spin': executing }"
          />
          {{ executing ? $t('tools.executing') : $t('tools.execute') }}
        </button>

        <div
          v-if="listResult"
          class="result-section"
        >
          <h4 class="result-title">
            {{ $t('tools.result') }}
          </h4>
          <div
            class="result-box"
            :class="{ error: listResult.error }"
          >
            <pre>{{ listResult.content }}</pre>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  FileText as FileTextIcon,
  Save as SaveIcon,
  Edit as EditIcon,
  Folder as FolderIcon,
  Loader2 as LoaderIcon
} from 'lucide-vue-next'
import { toolsAPI } from '@/api/endpoints'
import { useToast } from '@/composables/useToast'

const { t } = useI18n()
const toast = useToast()

type OperationType = 'read' | 'write' | 'edit' | 'list'

const operations = [
  { id: 'read' as OperationType, icon: FileTextIcon },
  { id: 'write' as OperationType, icon: SaveIcon },
  { id: 'edit' as OperationType, icon: EditIcon },
  { id: 'list' as OperationType, icon: FolderIcon }
]

const activeOp = ref<OperationType>('read')
const executing = ref(false)

// Form data
const readForm = ref({ path: '' })
const writeForm = ref({ path: '', content: '' })
const editForm = ref({ path: '', oldText: '', newText: '' })
const listForm = ref({ path: '.' })

// Results
const readResult = ref<{ content: string; error?: boolean } | null>(null)
const writeResult = ref<{ message: string; error?: boolean } | null>(null)
const editResult = ref<{ message: string; error?: boolean } | null>(null)
const listResult = ref<{ content: string; error?: boolean } | null>(null)

const executeRead = async () => {
  executing.value = true
  readResult.value = null
  
  try {
    const result = await toolsAPI.execute({
      tool: 'read_file',
      arguments: { path: readForm.value.path }
    }) as { result: string; success: boolean; error?: string }
    
    if (result.success) {
      readResult.value = { content: result.result }
      toast.success(t('tools.executeSuccess'))
    } else {
      readResult.value = { content: result.error || result.result, error: true }
      toast.error(t('tools.executeError'))
    }
  } catch (err: any) {
    readResult.value = { content: err.message, error: true }
    toast.error(t('tools.executeError'))
  } finally {
    executing.value = false
  }
}

const executeWrite = async () => {
  executing.value = true
  writeResult.value = null
  
  try {
    const result = await toolsAPI.execute({
      tool: 'write_file',
      arguments: {
        path: writeForm.value.path,
        content: writeForm.value.content
      }
    }) as { result: string; success: boolean; error?: string }
    
    if (result.success) {
      writeResult.value = { message: result.result }
      toast.success(t('tools.executeSuccess'))
    } else {
      writeResult.value = { message: result.error || result.result, error: true }
      toast.error(t('tools.executeError'))
    }
  } catch (err: any) {
    writeResult.value = { message: err.message, error: true }
    toast.error(t('tools.executeError'))
  } finally {
    executing.value = false
  }
}

const executeEdit = async () => {
  executing.value = true
  editResult.value = null
  
  try {
    const result = await toolsAPI.execute({
      tool: 'edit_file',
      arguments: {
        path: editForm.value.path,
        old_text: editForm.value.oldText,
        new_text: editForm.value.newText
      }
    }) as { result: string; success: boolean; error?: string }
    
    if (result.success) {
      editResult.value = { message: result.result }
      toast.success(t('tools.executeSuccess'))
    } else {
      editResult.value = { message: result.error || result.result, error: true }
      toast.error(t('tools.executeError'))
    }
  } catch (err: any) {
    editResult.value = { message: err.message, error: true }
    toast.error(t('tools.executeError'))
  } finally {
    executing.value = false
  }
}

const executeList = async () => {
  executing.value = true
  listResult.value = null
  
  try {
    const result = await toolsAPI.execute({
      tool: 'list_dir',
      arguments: { path: listForm.value.path || '.' }
    }) as { result: string; success: boolean; error?: string }
    
    if (result.success) {
      listResult.value = { content: result.result }
      toast.success(t('tools.executeSuccess'))
    } else {
      listResult.value = { content: result.error || result.result, error: true }
      toast.error(t('tools.executeError'))
    }
  } catch (err: any) {
    listResult.value = { content: err.message, error: true }
    toast.error(t('tools.executeError'))
  } finally {
    executing.value = false
  }
}
</script>

<style scoped>
.file-operations {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-secondary, #f9fafb);
}

.operations-tabs {
  display: flex;
  gap: var(--spacing-xs);
  padding: var(--spacing-md);
  border-bottom: 1px solid var(--border-color, #e5e7eb);
  background: var(--bg-primary, #ffffff);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}

.op-tab {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--text-secondary, #6b7280);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: all var(--transition-base);
}

.op-tab:hover {
  background: var(--hover-bg, #f3f4f6);
  color: var(--text-primary, #1f2937);
}

.op-tab.active {
  background: var(--bg-secondary, #f9fafb);
  color: var(--color-primary, #3b82f6);
  border-color: var(--color-primary, #3b82f6);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

.op-content {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-xl);
}

.op-panel {
  max-width: 800px;
  margin: 0 auto;
}

.op-title {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  margin: 0 0 var(--spacing-sm) 0;
}

.op-desc {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  margin: 0 0 var(--spacing-xl) 0;
  line-height: 1.6;
}

.form-group {
  margin-bottom: var(--spacing-lg);
}

.form-label {
  display: block;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--text-primary);
  margin-bottom: var(--spacing-xs);
}

.required {
  color: var(--color-error);
  margin-left: 2px;
}

.form-input,
.form-textarea {
  width: 100%;
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: var(--radius-md);
  background: var(--bg-primary, #ffffff);
  color: var(--text-primary, #1f2937);
  font-size: var(--font-size-sm);
  font-family: var(--font-sans);
  transition: border-color var(--transition-base);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

.form-textarea {
  font-family: var(--font-mono);
  resize: vertical;
}

.form-input:focus,
.form-textarea:focus {
  outline: none;
  border-color: var(--color-primary, #3b82f6);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.form-hint {
  display: block;
  margin-top: var(--spacing-xs);
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
}

.execute-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-lg);
  border: 1px solid var(--color-primary, #3b82f6);
  border-radius: var(--radius-md);
  background: var(--color-primary, #3b82f6);
  color: #ffffff;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: all var(--transition-base);
  box-shadow: 0 2px 4px rgba(59, 130, 246, 0.3);
}

.execute-btn:hover:not(:disabled) {
  background: var(--color-primary-hover, #2563eb);
  box-shadow: 0 4px 6px rgba(59, 130, 246, 0.4);
  transform: translateY(-1px);
}

.execute-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.result-section {
  margin-top: var(--spacing-xl);
}

.result-title {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  margin: 0 0 var(--spacing-md) 0;
}

.result-box {
  padding: var(--spacing-md);
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: var(--radius-md);
  background: var(--bg-primary, #ffffff);
  max-height: 400px;
  overflow-y: auto;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}

.result-box.error {
  border-color: var(--color-error, #ef4444);
  background: rgba(239, 68, 68, 0.1);
}

.result-box pre {
  margin: 0;
  font-size: var(--font-size-sm);
  font-family: var(--font-mono);
  color: var(--text-primary);
  white-space: pre-wrap;
  word-wrap: break-word;
}

.result-box.error pre {
  color: var(--color-error);
}

.spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

/* 深色模式 */
:root[data-theme="dark"] .file-operations {
  background: var(--bg-secondary, #111827);
}

:root[data-theme="dark"] .operations-tabs {
  background: var(--bg-primary, #1f2937);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}

:root[data-theme="dark"] .result-box {
  background: var(--bg-primary, #1f2937);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}
</style>
