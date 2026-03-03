<template>
  <div class="memory-viewer">
    <div class="memory-header">
      <h2 class="memory-title">
        {{ t('memory.title') }}
      </h2>
      <div class="memory-actions">
        <button
          class="btn-icon"
          :disabled="isLoading"
          :title="t('common.retry')"
          @click="handleRefresh"
        >
          <RefreshCwIcon
            :class="{ spinning: isLoading }"
            :size="20"
          />
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

    <div class="memory-content">
      <!-- 长期记忆视图 -->
      <div class="memory-section">
        <div class="section-header">
          <h3>{{ t('memory.longTermMemory') }}</h3>
          <button
            class="btn-secondary btn-sm"
            @click="handleEditLongTerm"
          >
            <EditIcon :size="16" />
            <span>{{ t('common.edit') }}</span>
          </button>
        </div>

        <div
          v-if="isLoading"
          class="loading-state"
        >
          <div class="spinner" />
          <p>{{ t('common.loading') }}</p>
        </div>

        <div
          v-else-if="!hasLongTermMemory"
          class="empty-state"
        >
          <FileTextIcon :size="48" />
          <h3>{{ t('memory.emptyLongTerm') }}</h3>
          <p>{{ t('memory.emptyLongTermDesc') }}</p>
          <button
            class="btn-primary"
            @click="handleEditLongTerm"
          >
            <PlusIcon :size="18" />
            <span>{{ t('memory.createMemory') }}</span>
          </button>
        </div>

        <div
          v-else
          class="memory-text"
          v-html="renderMarkdown(longTermMemory)"
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
    EditIcon,
    RefreshCwIcon,
    AlertCircleIcon,
    FileTextIcon,
    PlusIcon,
} from 'lucide-vue-next'

const { t } = useI18n()
const memoryStore = useMemoryStore()
const { renderMarkdown } = useMarkdown()

const emit = defineEmits<{
    edit: []
}>()

// 计算属性
const isLoading = computed(() => memoryStore.isLoading)
const error = computed(() => memoryStore.error)
const longTermMemory = computed(() => memoryStore.longTermMemory)
const hasLongTermMemory = computed(() => memoryStore.hasLongTermMemory)

// 方法
const handleRefresh = async () => {
    await memoryStore.loadLongTermMemory()
}

const handleEditLongTerm = () => {
    emit('edit')
}

const clearError = () => {
    memoryStore.clearError()
}

// 初始化
onMounted(async () => {
    await memoryStore.loadLongTermMemory()
})
</script>

<style scoped>
.memory-viewer {
    display: flex;
    flex-direction: column;
    height: 100%;
    background: var(--bg-primary);
}

.memory-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1.5rem;
    border-bottom: 1px solid var(--border-color);
}

.memory-title {
    font-size: 1.5rem;
    font-weight: 600;
    color: var(--text-primary);
    margin: 0;
}

.memory-actions {
    display: flex;
    gap: 0.5rem;
}

.btn-icon {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 2.5rem;
    height: 2.5rem;
    border: none;
    border-radius: 0.5rem;
    background: var(--bg-secondary);
    color: var(--text-secondary);
    cursor: pointer;
    transition: all 0.2s;
}

.btn-icon:hover:not(:disabled) {
    background: var(--bg-tertiary);
    color: var(--text-primary);
}

.btn-icon:disabled {
    opacity: 0.5;
    cursor: not-allowed;
}

.spinning {
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

.memory-content {
    flex: 1;
    overflow-y: auto;
    padding: 1.5rem;
}

.memory-section {
    max-width: 900px;
    margin: 0 auto;
}

.section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 1.5rem;
}

.section-header h3 {
    font-size: 1.125rem;
    font-weight: 600;
    color: var(--text-primary);
    margin: 0;
}

.btn-secondary {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 1rem;
    border: 1px solid var(--border-color);
    border-radius: 0.5rem;
    background: var(--bg-secondary);
    color: var(--text-primary);
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
}

.btn-secondary:hover {
    background: var(--bg-tertiary);
    border-color: var(--primary);
}

.btn-sm {
    padding: 0.375rem 0.75rem;
    font-size: 0.8125rem;
}

.btn-primary {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem 1.5rem;
    border: none;
    border-radius: 0.5rem;
    background: var(--primary);
    color: white;
    font-size: 0.9375rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
}

.btn-primary:hover {
    background: var(--primary-hover);
}

.loading-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 4rem 2rem;
    color: var(--text-secondary);
}

.spinner {
    width: 2.5rem;
    height: 2.5rem;
    border: 3px solid var(--border-color);
    border-top-color: var(--primary);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    margin-bottom: 1rem;
}

.empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 4rem 2rem;
    text-align: center;
}

.empty-state svg {
    color: var(--text-tertiary);
    margin-bottom: 1.5rem;
}

.empty-state h3 {
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--text-primary);
    margin: 0 0 0.5rem;
}

.empty-state p {
    font-size: 0.9375rem;
    color: var(--text-secondary);
    margin: 0 0 1.5rem;
    max-width: 400px;
}

.memory-text {
    padding: 1.5rem;
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: 0.75rem;
    color: var(--text-primary);
    line-height: 1.7;
}

.memory-text :deep(h1),
.memory-text :deep(h2),
.memory-text :deep(h3) {
    margin-top: 1.5rem;
    margin-bottom: 0.75rem;
    font-weight: 600;
    color: var(--text-primary);
}

.memory-text :deep(h1) {
    font-size: 1.5rem;
}

.memory-text :deep(h2) {
    font-size: 1.25rem;
}

.memory-text :deep(h3) {
    font-size: 1.125rem;
}

.memory-text :deep(p) {
    margin: 0.75rem 0;
}

.memory-text :deep(ul),
.memory-text :deep(ol) {
    margin: 0.75rem 0;
    padding-left: 1.5rem;
}

.memory-text :deep(li) {
    margin: 0.25rem 0;
}

.memory-text :deep(code) {
    padding: 0.125rem 0.375rem;
    background: var(--bg-tertiary);
    border-radius: 0.25rem;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.875em;
}

.memory-text :deep(pre) {
    margin: 1rem 0;
    padding: 1rem;
    background: var(--bg-tertiary);
    border-radius: 0.5rem;
    overflow-x: auto;
}

.memory-text :deep(pre code) {
    padding: 0;
    background: transparent;
}

.memory-text :deep(blockquote) {
    margin: 1rem 0;
    padding-left: 1rem;
    border-left: 3px solid var(--primary);
    color: var(--text-secondary);
}
</style>
