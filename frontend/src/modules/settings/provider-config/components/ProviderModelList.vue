<template>
  <section class="provider-models">
    <header class="provider-models-header">
      <div class="provider-models-title">
        <span>{{ $t('settings.providers.models.title') }}</span>
        <span class="provider-models-count">
          {{ $t('settings.providers.models.count', { count: models.length }) }}
        </span>
        <span v-if="disabledCount > 0" class="provider-models-disabled">
          {{ $t('settings.providers.models.disabledCount', { count: disabledCount }) }}
        </span>
      </div>

      <div class="provider-models-actions">
        <div v-if="models.length > 3" class="model-search">
          <SearchIcon :size="13" class="model-search-icon" />
          <input
            v-model="keyword"
            type="search"
            class="model-search-input"
            :placeholder="$t('settings.providers.models.searchPlaceholder')"
            :aria-label="$t('settings.providers.models.searchPlaceholder')"
          >
        </div>
        <Button
          variant="ghost"
          size="sm"
          :icon="RefreshCwIcon"
          :loading="catalogLoading"
          :disabled="catalogLoading"
          @click="emit('fetch-models')"
        >
          {{ catalogLoading
            ? $t('settings.providers.models.fetching')
            : $t('settings.providers.models.fetch') }}
        </Button>
        <Button variant="primary" size="sm" :icon="PlusIcon" @click="emit('request-add')">
          {{ $t('settings.providers.models.add') }}
        </Button>
      </div>
    </header>

    <div v-if="models.length === 0" class="provider-models-empty">
      <span class="provider-models-empty-icon">
        <BoxIcon :size="20" />
      </span>
      <div class="provider-models-empty-copy">
        <p class="provider-models-empty-title">
          {{ $t('settings.providers.models.emptyTitle') }}
        </p>
        <p class="provider-models-empty-desc">
          {{ $t('settings.providers.models.emptyDesc') }}
        </p>
      </div>
      <div class="provider-models-empty-actions">
        <Button
          variant="ghost"
          size="sm"
          :icon="RefreshCwIcon"
          :loading="catalogLoading"
          :disabled="catalogLoading"
          @click="emit('fetch-models')"
        >
          {{ $t('settings.providers.models.fetchAction') }}
        </Button>
        <Button variant="ghost" size="sm" :icon="PlusIcon" @click="emit('request-add')">
          {{ $t('settings.providers.models.manualAdd') }}
        </Button>
      </div>
    </div>

    <p v-else-if="visibleModels.length === 0" class="provider-models-nomatch">
      {{ $t('settings.providers.models.noMatch') }}
    </p>

    <ul v-else class="provider-model-list">
      <li
        v-for="model in visibleModels"
        :key="model.id"
        class="provider-model-row"
        :class="{
          'is-hidden': model.enabled === false,
          'is-dragging': draggingId === model.id,
          'is-drag-over': dragOverId === model.id && draggingId !== model.id,
        }"
        draggable="true"
        @dragstart="onDragStart($event, model)"
        @dragover.prevent="dragOverId = model.id"
        @dragleave="onDragLeave(model)"
        @drop.prevent="onDrop(model)"
        @dragend="onDragEnd"
      >
        <button
          type="button"
          class="model-drag-handle"
          :title="$t('settings.providers.models.dragHint')"
          :aria-label="$t('settings.providers.models.dragHint')"
          @keydown.up.prevent="moveBy(model, -1)"
          @keydown.down.prevent="moveBy(model, 1)"
        >
          <GripVerticalIcon :size="14" />
        </button>

        <div class="provider-model-main">
          <span
            class="provider-model-title"
            :class="{ 'is-id': !model.display_name || model.display_name === model.id }"
            :title="model.id"
          >
            {{ model.display_name || model.id }}
          </span>
          <span
            v-if="model.display_name && model.display_name !== model.id"
            class="provider-model-id"
            :title="model.id"
          >
            {{ model.id }}
          </span>
          <span v-if="model.context_window" class="provider-model-pill">
            {{ contextLabel(model.context_window) }}
          </span>
          <span class="provider-model-pill is-muted provider-model-source">
            {{ sourceLabel(model.source) }}
          </span>
          <span v-if="model.shared" class="provider-model-pill is-shared">
            {{ $t('settings.providers.models.sharedBadge') }}
          </span>
          <span v-if="model.supports_image === true" class="provider-model-pill is-vision">
            {{ $t('settings.providers.models.supportsImageOn') }}
          </span>
          <span v-if="model.stream_enabled === false" class="provider-model-pill is-muted">
            {{ $t('settings.providers.models.streamModeNonStreaming') }}
          </span>
          <span v-if="nativeCapabilityCount(model)" class="provider-model-pill is-native">
            {{ $t('settings.providers.models.native.badge', { count: nativeCapabilityCount(model) }) }}
          </span>
          <span v-if="model.enabled === false" class="provider-model-pill is-off">
            {{ $t('settings.providers.models.disabled') }}
          </span>
        </div>

        <div class="provider-model-actions">
          <button
            type="button"
            class="provider-model-action"
            :disabled="testingModelId === model.id"
            :title="testingModelId === model.id
              ? $t('settings.providers.models.testingModel')
              : $t('settings.providers.models.test')"
            :aria-label="$t('settings.providers.models.test')"
            @click="emit('test-model', model.id)"
          >
            <Loader2Icon v-if="testingModelId === model.id" :size="14" class="model-action-spin" />
            <UnplugIcon v-else :size="14" />
          </button>
          <button
            type="button"
            class="provider-model-action"
            :title="$t('settings.providers.models.configure')"
            :aria-label="$t('settings.providers.models.configure')"
            @click="emit('edit-model', model)"
          >
            <PencilIcon :size="14" />
          </button>
          <button
            type="button"
            class="provider-model-action is-danger"
            :title="$t('common.delete')"
            :aria-label="$t('common.delete')"
            @click="emit('delete-model', model.id)"
          >
            <TrashIcon :size="14" />
          </button>
          <SwitchToggle
            :model-value="model.enabled !== false"
            :width="36"
            :height="20"
            :aria-label="$t('settings.providers.models.enabled')"
            @update:model-value="(value) => emit('toggle-model', model.id, value)"
          />
        </div>
      </li>
    </ul>

    <p v-if="models.length > 1" class="hint provider-models-reorder-hint">
      {{ $t('settings.providers.models.reorderHint') }}
    </p>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  Box as BoxIcon,
  GripVertical as GripVerticalIcon,
  Loader2 as Loader2Icon,
  Pencil as PencilIcon,
  Plus as PlusIcon,
  RefreshCw as RefreshCwIcon,
  Search as SearchIcon,
  Trash2 as TrashIcon,
  Unplug as UnplugIcon,
} from 'lucide-vue-next'
import Button from '@/components/ui/Button.vue'
import SwitchToggle from '@/components/ui/SwitchToggle.vue'
import { normalizeNativeCapabilities } from '@/types/nativeCaps'
import type { ProviderModel } from '../types'

function nativeCapabilityCount(model: ProviderModel): number {
  const caps = normalizeNativeCapabilities(model.native_capabilities)
  return [
    caps.web_search,
    caps.read_url,
    caps.safety_check,
    caps.asr,
    caps.tts,
    caps.document_parsing !== 'off',
  ].filter(Boolean).length
}

interface Props {
  models: ProviderModel[]
  testingModelId: string
  catalogLoading: boolean
  sourceLabel: (source: ProviderModel['source']) => string
  contextLabel: (value: number) => string
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'request-add'): void
  (e: 'fetch-models'): void
  (e: 'test-model', modelId: string): void
  (e: 'edit-model', model: ProviderModel): void
  (e: 'delete-model', modelId: string): void
  (e: 'toggle-model', modelId: string, enabled: boolean): void
  (e: 'reorder-model', fromIndex: number, toIndex: number): void
}>()

const keyword = ref('')
const draggingId = ref('')
const dragOverId = ref('')

const disabledCount = computed(
  () => props.models.filter(model => model.enabled === false).length,
)

const visibleModels = computed(() => {
  const query = keyword.value.trim().toLowerCase()
  if (!query) {
    return props.models
  }
  return props.models.filter(
    model =>
      model.id.toLowerCase().includes(query)
      || (model.display_name || '').toLowerCase().includes(query),
  )
})

function sourceIndex(model: ProviderModel): number {
  return props.models.findIndex(item => item.id === model.id)
}

function moveBy(model: ProviderModel, offset: number): void {
  const from = sourceIndex(model)
  const to = from + offset
  if (from < 0 || to < 0 || to >= props.models.length) {
    return
  }
  emit('reorder-model', from, to)
}

function onDragStart(event: DragEvent, model: ProviderModel): void {
  draggingId.value = model.id
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', model.id)
  }
}

function onDragLeave(model: ProviderModel): void {
  if (dragOverId.value === model.id) {
    dragOverId.value = ''
  }
}

function onDrop(model: ProviderModel): void {
  const draggedId = draggingId.value || dragOverId.value
  if (!draggedId) {
    onDragEnd()
    return
  }
  const from = props.models.findIndex(item => item.id === draggedId)
  const to = sourceIndex(model)
  if (from >= 0 && to >= 0 && from !== to) {
    emit('reorder-model', from, to)
  }
  onDragEnd()
}

function onDragEnd(): void {
  draggingId.value = ''
  dragOverId.value = ''
}
</script>

<style scoped>
@import '../styles/ProviderModelList.css';
</style>
