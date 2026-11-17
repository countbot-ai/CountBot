<template>
  <div ref="rootEl" class="memory-viewer">
    <SettingsCard :title="t('memory.longTermMemory')" flush>
      <template #actions>
        <span class="co-row-value">{{ longTermLineCount }} {{ t('memory.lines') }}</span>
        <button class="icon-btn" :disabled="isLoading" :title="t('common.retry')" @click="handleRefresh">
          <component :is="RefreshCwIcon" :size="15" :class="{ spinning: isLoading }" />
        </button>
        <button class="co-btn co-btn--secondary btn-compact" @click="emit('edit', 'long-term')">
          <component :is="PencilIcon" :size="14" />
          {{ t('common.edit') }}
        </button>
      </template>

      <p v-if="error" class="error-row">
        <component :is="AlertCircleIcon" :size="14" />
        <span>{{ error }}</span>
        <button class="link-btn" @click="clearError">{{ t('common.close') }}</button>
      </p>

      <div v-if="isLoading" class="state-block">{{ t('common.loading') }}</div>

      <div v-else-if="!hasLongTermMemory" class="state-block">
        <component :is="FileTextIcon" :size="22" class="state-icon" />
        <p class="state-title">{{ t('memory.emptyLongTerm') }}</p>
        <p class="state-desc">{{ t('memory.emptyLongTermDesc') }}</p>
        <button class="co-btn co-btn--primary" @click="emit('edit', 'long-term')">
          {{ t('memory.createMemory') }}
        </button>
      </div>

      <div v-else class="memory-text" v-html="renderMarkdown(longTermMemory)" />
    </SettingsCard>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMemoryStore } from '@/store/memory'
import { useMarkdown } from '@/composables/useMarkdown'
import { useMermaid } from '@/composables/useMermaid'
import {
  AlertCircle as AlertCircleIcon,
  FileText as FileTextIcon,
  Pencil as PencilIcon,
  RefreshCw as RefreshCwIcon,
} from 'lucide-vue-next'
import { SettingsCard } from '@/modules/settings/ui'

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

const isLoading = computed(() => memoryStore.isLoading)
const error = computed(() => memoryStore.error)
const longTermMemory = computed(() => memoryStore.longTermMemory)
const hasLongTermMemory = computed(() => memoryStore.hasLongTermMemory)
const longTermLineCount = computed(
  () => longTermMemory.value.split('\n').filter((line) => line.trim()).length,
)

// 只有一个记忆分区，props.tab 只用于保持外部接口稳定
void props.tab

useMermaid(rootEl, [longTermMemory])

const handleRefresh = async () => {
  await memoryStore.loadLongTermMemory()
}

const clearError = () => {
  memoryStore.clearError()
}

onMounted(async () => {
  await memoryStore.loadLongTermMemory()
})
</script>

<style scoped>
.btn-compact {
  height: 26px;
  padding: 0 10px;
  font-size: var(--font-size-xs);
}

.icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-text-tertiary);
  cursor: pointer;
}

.icon-btn:hover:not(:disabled) {
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
}

.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
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

.state-block {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 56px 16px;
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  text-align: center;
}

.state-icon {
  color: var(--color-text-disabled);
}

.state-title {
  margin: 4px 0 0;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
}

.state-desc {
  margin: 0 0 8px;
  max-width: 52ch;
  font-size: var(--font-size-xs);
  line-height: 1.6;
}

.memory-text {
  padding: 14px var(--co-row-gutter) 18px;
  font-size: var(--font-size-sm);
  line-height: 1.75;
  color: var(--color-text-primary);
}

/* 首个块不留顶部外边距，否则卡片头和正文之间会空出一段 */
.memory-text :deep(> :first-child) {
  margin-top: 0;
}

/* 记忆文件的标题仅作分区标记，字号低于正文标题 */
.memory-text :deep(h1) {
  margin: 16px 0 6px;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
}

.memory-text :deep(h2) {
  margin: 14px 0 6px;
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
}

.memory-text :deep(h3),
.memory-text :deep(h4) {
  margin: 12px 0 4px;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
}

.memory-text :deep(p) {
  margin: 0 0 6px;
}

.memory-text :deep(ul),
.memory-text :deep(ol) {
  margin: 0 0 6px;
  padding-left: 18px;
}
</style>
