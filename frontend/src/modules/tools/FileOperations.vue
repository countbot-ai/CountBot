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
@import './styles/FileOperations.css';
</style>
