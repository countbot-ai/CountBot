<template>
  <div ref="rootEl" class="memory-viewer">
    <div class="memory-shell">
      <div class="memory-header">
        <div class="section-header">
          <h3 class="section-title">{{ t('memory.title') }}</h3>
          <p class="section-desc">{{ t('memory.emptyLongTermDesc') }}</p>
        </div>
      </div>

      <div class="memory-toolbar">
        <div class="memory-tabs">
          <button
            class="memory-tab"
            :class="{ active: activeTab === 'long-term' }"
            @click="changeTab('long-term')"
          >
            {{ t('memory.longTermMemory') }}
          </button>
        </div>

        <div class="memory-actions">
          <div class="memory-stat-line">
            <span>{{ longTermLineCount }} {{ t('memory.lines') }}</span>
          </div>

          <button
            class="btn-icon"
            :disabled="isLoading"
            :title="t('common.retry')"
            @click="handleRefresh"
          >
            <RefreshCwIcon :class="{ spinning: isLoading }" :size="20" />
          </button>
        </div>
      </div>

      <div v-if="error" class="error-message">
        <AlertCircleIcon :size="18" />
        <span>{{ error }}</span>
        <button class="btn-text" @click="clearError">{{ t('common.close') }}</button>
      </div>

      <div class="memory-content">
        <div class="memory-content-actions">
          <button
            class="btn-secondary btn-sm"
            @click="emit('edit', 'long-term')"
          >
            <EditIcon :size="16" />
            <span>{{ t('common.edit') }}</span>
          </button>
        </div>

        <div class="memory-section">
          <div v-if="isLoading" class="loading-state">
            <div class="spinner" />
            <p>{{ t('common.loading') }}</p>
          </div>

          <div v-else-if="!hasLongTermMemory" class="empty-state">
            <FileTextIcon :size="48" />
            <h3>{{ t('memory.emptyLongTerm') }}</h3>
            <p>{{ t('memory.emptyLongTermDesc') }}</p>
            <button class="btn-primary" @click="emit('edit', 'long-term')">
              <PlusIcon :size="18" />
              <span>{{ t('memory.createMemory') }}</span>
            </button>
          </div>

          <div v-else class="document-card">
            <div class="document-card-header">
              <h3>{{ t('memory.longTermMemory') }}</h3>
            </div>
            <div class="memory-text document-card-body" v-html="renderMarkdown(longTermMemory)" />
          </div>
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
import {
  AlertCircleIcon,
  EditIcon,
  FileTextIcon,
  PlusIcon,
  RefreshCwIcon,
} from 'lucide-vue-next'

type MemoryTab = 'long-term'

const props = defineProps<{
  tab: MemoryTab
}>()

const emit = defineEmits<{
  edit: [target: MemoryTab]
  'change-tab': [target: MemoryTab]
}>()

const { t } = useI18n()
const memoryStore = useMemoryStore()
const { renderMarkdown } = useMarkdown()
const rootEl = ref<HTMLElement | null>(null)

const activeTab = computed(() => props.tab)
const isLoading = computed(() => memoryStore.isLoading)
const error = computed(() => memoryStore.error)
const longTermMemory = computed(() => memoryStore.longTermMemory)
const hasLongTermMemory = computed(() => memoryStore.hasLongTermMemory)
const longTermLineCount = computed(() => longTermMemory.value.split('\n').filter(line => line.trim()).length)

useMermaid(rootEl, [longTermMemory])

const handleRefresh = async () => {
  await memoryStore.loadLongTermMemory()
}

const changeTab = (target: MemoryTab) => {
  emit('change-tab', target)
}

const clearError = () => {
  memoryStore.clearError()
}

onMounted(async () => {
  await memoryStore.loadLongTermMemory()
})
</script>
<style scoped>
@import './styles/MemoryViewer.css';
</style>
