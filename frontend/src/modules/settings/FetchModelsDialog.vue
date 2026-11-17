<template>
  <Modal
    :model-value="show"
    :title="$t('settings.providers.fetchDialog.title')"
    size="medium"
    @update:model-value="handleClose"
  >
    <div class="fetch-models">
      <div class="fetch-models-toolbar">
        <Input
          v-model="search"
          type="text"
          :placeholder="$t('settings.providers.fetchDialog.searchPlaceholder')"
        />
        <div class="fetch-models-toolbar-actions">
          <Button
            variant="ghost"
            size="sm"
            :disabled="loading || selectableIds.length === 0"
            @click="selectAll"
          >
            {{ $t('settings.providers.fetchDialog.selectAll') }}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            :disabled="loading || selected.size === 0"
            @click="clearSelection"
          >
            {{ $t('settings.providers.fetchDialog.clear') }}
          </Button>
        </div>
      </div>

      <div v-if="loading" class="fetch-models-state">
        <Spinner size="small" />
        <span>{{ $t('settings.providers.fetchDialog.loading') }}</span>
      </div>

      <div v-else-if="error" class="fetch-models-state is-error">
        <component :is="XCircleIcon" :size="16" />
        <span>{{ error }}</span>
        <Button variant="outline" size="sm" @click="emit('retry')">
          {{ $t('settings.providers.fetchDialog.retry') }}
        </Button>
      </div>

      <div v-else-if="models.length === 0" class="fetch-models-state">
        <span>{{ $t('settings.providers.fetchDialog.empty') }}</span>
      </div>

      <div v-else-if="filteredModels.length === 0" class="fetch-models-state">
        <span>{{ $t('settings.providers.fetchDialog.noMatch') }}</span>
      </div>

      <ul v-else class="fetch-models-list">
        <li
          v-for="model in filteredModels"
          :key="model.id"
          class="fetch-models-item"
          :class="{ 'is-disabled': isAlreadyAdded(model.id) }"
        >
          <label class="fetch-models-check">
            <input
              type="checkbox"
              :checked="selected.has(model.id)"
              :disabled="isAlreadyAdded(model.id)"
              @change="toggle(model.id)"
            />
            <span class="fetch-models-name">{{ model.display_name || model.id }}</span>
            <span class="fetch-models-id">{{ model.id }}</span>
            <span v-if="isAlreadyAdded(model.id)" class="fetch-models-badge">
              {{ $t('settings.providers.fetchDialog.alreadyAdded') }}
            </span>
          </label>
        </li>
      </ul>

      <p v-if="selectionSummary" class="fetch-models-summary">{{ selectionSummary }}</p>
    </div>

    <template #footer>
      <Button variant="ghost" @click="handleClose(false)">
        {{ $t('settings.providers.fetchDialog.close') }}
      </Button>
      <Button
        variant="primary"
        :disabled="selected.size === 0"
        @click="handleConfirm"
      >
        {{ $t('settings.providers.fetchDialog.confirm') }}
      </Button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { XCircle as XCircleIcon } from 'lucide-vue-next'
import Modal from '@/components/ui/Modal.vue'
import Input from '@/components/ui/Input.vue'
import Button from '@/components/ui/Button.vue'
import Spinner from '@/components/ui/Spinner.vue'
import type { ProviderModelCatalogEntry } from '@/api'

interface Props {
  loading?: boolean
  error?: string | null
  models: ProviderModelCatalogEntry[]
  /** 已经在供应商清单里的模型 ID，置灰不可重复添加 */
  existingModelIds?: string[]
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  error: null,
  existingModelIds: () => [],
})

const emit = defineEmits<{
  (e: 'confirm', modelIds: string[]): void
  (e: 'retry'): void
}>()

// 显隐由父组件通过 v-model:show 控制
const show = defineModel<boolean>('show', { default: false })

const { t } = useI18n()
const search = ref('')
const selected = ref<Set<string>>(new Set())

const existingSet = computed(() => new Set(props.existingModelIds || []))

const filteredModels = computed(() => {
  const keyword = search.value.trim().toLowerCase()
  if (!keyword) {
    return props.models
  }
  return props.models.filter(
    model =>
      model.id.toLowerCase().includes(keyword) ||
      (model.display_name || '').toLowerCase().includes(keyword),
  )
})

const selectableIds = computed(() =>
  filteredModels.value
    .map(model => model.id)
    .filter(id => !existingSet.value.has(id)),
)

const selectionSummary = computed(() =>
  selected.value.size > 0
    ? t('settings.providers.fetchDialog.selected', { count: selected.value.size })
    : '',
)

function isAlreadyAdded(modelId: string): boolean {
  return existingSet.value.has(modelId)
}

function toggle(modelId: string) {
  if (isAlreadyAdded(modelId)) {
    return
  }
  const next = new Set(selected.value)
  if (next.has(modelId)) {
    next.delete(modelId)
  } else {
    next.add(modelId)
  }
  selected.value = next
}

function selectAll() {
  selected.value = new Set(selectableIds.value)
}

function clearSelection() {
  selected.value = new Set()
}

function handleClose(value = false) {
  show.value = value
}

function handleConfirm() {
  emit('confirm', Array.from(selected.value))
}

// 每次重新打开都清空上次的搜索与勾选，避免误提交
watch(
  () => show.value,
  visible => {
    if (visible) {
      search.value = ''
      selected.value = new Set()
    }
  },
)
</script>

<style scoped>
@import './styles/FetchModelsDialog.css';
</style>
