<template>
  <section class="provider-models">
    <div class="provider-models-header">
      <div class="provider-models-title">
        <span>{{ $t('settings.providers.models.title') }}</span>
        <span class="provider-models-count">
          {{ $t('settings.providers.models.count', { count: models.length }) }}
        </span>
      </div>

      <div class="provider-models-actions">
        <Button variant="outline" size="sm" :icon="PlusIcon" @click="emit('request-add')">
          {{ $t('settings.providers.models.add') }}
        </Button>
        <Button
          variant="outline"
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
        <Button
          variant="secondary"
          size="sm"
          :icon="PlugZapIcon"
          :loading="providerTesting"
          :disabled="providerTesting"
          @click="emit('test-provider')"
        >
          {{ providerTesting
            ? $t('settings.providers.models.testingProvider')
            : $t('settings.providers.models.testProvider') }}
        </Button>
      </div>
    </div>

    <div v-if="models.length === 0" class="provider-models-empty">
      <InfoIcon :size="16" />
      <span>{{ $t('settings.providers.models.empty') }}</span>
    </div>

    <ul v-else class="provider-model-list">
      <li
        v-for="(model, index) in models"
        :key="model.id"
        class="provider-model-row"
        :class="{ 'is-hidden': model.enabled === false }"
      >
        <div class="provider-model-order">
          <button
            type="button"
            class="model-order-btn"
            :disabled="index === 0"
            :title="$t('settings.providers.models.moveUp')"
            :aria-label="$t('settings.providers.models.moveUp')"
            @click="emit('move-model', index, -1)"
          >
            <ChevronUpIcon :size="12" />
          </button>
          <button
            type="button"
            class="model-order-btn"
            :disabled="index === models.length - 1"
            :title="$t('settings.providers.models.moveDown')"
            :aria-label="$t('settings.providers.models.moveDown')"
            @click="emit('move-model', index, 1)"
          >
            <ChevronDownIcon :size="12" />
          </button>
        </div>

        <div class="provider-model-main">
          <span class="provider-model-id" :title="model.id">{{ model.id }}</span>
          <span
            v-if="model.display_name && model.display_name !== model.id"
            class="provider-model-name"
            :title="model.display_name"
          >
            {{ model.display_name }}
          </span>
          <span v-if="model.context_window" class="provider-model-pill">
            {{ contextLabel(model.context_window) }}
          </span>
          <span class="provider-model-pill is-muted provider-model-source">
            {{ sourceLabel(model.source) }}
          </span>
          <span v-if="model.supports_image === true" class="provider-model-pill is-vision">
            {{ $t('settings.providers.models.supportsImageOn') }}
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
import {
  ChevronDown as ChevronDownIcon,
  ChevronUp as ChevronUpIcon,
  Info as InfoIcon,
  Loader2 as Loader2Icon,
  Pencil as PencilIcon,
  PlugZap as PlugZapIcon,
  Plus as PlusIcon,
  RefreshCw as RefreshCwIcon,
  Trash2 as TrashIcon,
  Unplug as UnplugIcon,
} from 'lucide-vue-next'
import Button from '@/components/ui/Button.vue'
import SwitchToggle from '@/components/ui/SwitchToggle.vue'
import type { ProviderModel } from '../types'

interface Props {
  models: ProviderModel[]
  testingModelId: string
  providerTesting: boolean
  catalogLoading: boolean
  sourceLabel: (source: ProviderModel['source']) => string
  contextLabel: (value: number) => string
}

defineProps<Props>()

const emit = defineEmits<{
  (e: 'request-add'): void
  (e: 'fetch-models'): void
  (e: 'test-provider'): void
  (e: 'test-model', modelId: string): void
  (e: 'edit-model', model: ProviderModel): void
  (e: 'delete-model', modelId: string): void
  (e: 'toggle-model', modelId: string, enabled: boolean): void
  (e: 'move-model', index: number, offset: number): void
}>()
</script>

<style scoped>
@import '../styles/ProviderModelList.css';
</style>
