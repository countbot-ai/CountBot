<template>
  <Modal
    :model-value="show"
    :title="$t('settings.providers.addProvider')"
    size="medium"
    @update:model-value="(value) => emit('update:show', value)"
  >
    <div class="add-provider">
      <p v-if="providers.length === 0" class="hint">
        {{ $t('settings.providers.addProviderEmpty') }}
      </p>

      <button
        v-for="provider in providers"
        :key="provider.id"
        type="button"
        class="add-provider-item"
        @click="emit('select', provider.id)"
      >
        <ProviderIcon :provider-id="provider.id" :size="22" />
        <span class="add-provider-copy">
          <span class="add-provider-name">{{ provider.name || provider.id }}</span>
          <span class="add-provider-meta">{{ provider.id }}</span>
        </span>
        <PlusIcon :size="16" class="add-provider-action" />
      </button>
    </div>
  </Modal>
</template>

<script setup lang="ts">
import { Plus as PlusIcon } from 'lucide-vue-next'
import Modal from '@/components/ui/Modal.vue'
import ProviderIcon from '@/components/ui/ProviderIcon.vue'
import type { ProviderMetadata } from '@/api'

interface Props {
  show: boolean
  providers: ProviderMetadata[]
}

defineProps<Props>()

const emit = defineEmits<{
  (e: 'update:show', value: boolean): void
  (e: 'select', providerId: string): void
}>()
</script>

<style scoped>
@import '../styles/AddProviderDialog.css';
</style>
