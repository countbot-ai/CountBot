<template>
  <Modal
    :model-value="show"
    :title="$t('settings.providers.addProvider')"
    size="medium"
    @update:model-value="(value) => emit('update:show', value)"
  >
    <div class="add-provider">
      <div class="add-provider-search">
        <SearchIcon :size="14" class="add-provider-search-icon" />
        <input
          v-model="keyword"
          type="search"
          class="add-provider-search-input"
          :placeholder="$t('settings.providers.addDialog.searchPlaceholder')"
          :aria-label="$t('settings.providers.addDialog.searchPlaceholder')"
        >
      </div>

      <p v-if="providers.length === 0" class="add-provider-empty">
        {{ $t('settings.providers.addProviderEmpty') }}
      </p>

      <p v-else-if="groups.length === 0" class="add-provider-empty">
        {{ $t('settings.providers.addDialog.noMatch') }}
      </p>

      <div v-else class="add-provider-groups">
        <section v-for="group in groups" :key="group.id" class="add-provider-group">
          <p class="add-provider-group-label">
            {{ group.label }}
          </p>
          <div class="add-provider-grid">
            <button
              v-for="provider in group.providers"
              :key="provider.id"
              type="button"
              class="add-provider-item"
              :title="providerLabel(provider)"
              @click="emit('select', provider.id)"
            >
              <span class="add-provider-logo">
                <ProviderIcon :provider-id="provider.id" :size="20" />
              </span>
              <span class="add-provider-copy">
                <span class="add-provider-name">{{ providerLabel(provider) }}</span>
                <span class="add-provider-meta">{{ provider.id }}</span>
              </span>
              <PlusIcon :size="15" class="add-provider-action" />
            </button>
          </div>
        </section>
      </div>
    </div>
  </Modal>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Plus as PlusIcon, Search as SearchIcon } from 'lucide-vue-next'
import Modal from '@/components/ui/Modal.vue'
import ProviderIcon from '@/components/ui/ProviderIcon.vue'
import { resolveProviderGroup } from '@/utils/providerRuntime'
import { resolveProviderLabel } from '../constants'
import type { ProviderMetadata } from '@/api'

interface Props {
  show: boolean
  providers: ProviderMetadata[]
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'update:show', value: boolean): void
  (e: 'select', providerId: string): void
}>()

const { t, te } = useI18n()

function providerLabel(provider: ProviderMetadata): string {
  return resolveProviderLabel(provider.id, t, te, provider.name || provider.id)
}

const GROUP_ORDER = ['recommended', 'experimental', 'local', 'advanced'] as const
const KNOWN_GROUPS = new Set<string>(GROUP_ORDER)

const keyword = ref('')

function groupLabel(groupId: string): string {
  return KNOWN_GROUPS.has(groupId)
    ? t(`settings.providers.thinkingControl.groups.${groupId}`)
    : groupId
}

const groups = computed(() => {
  const query = keyword.value.trim().toLowerCase()
  const buckets = new Map<string, ProviderMetadata[]>()

  for (const provider of props.providers) {
    const name = providerLabel(provider).toLowerCase()
    if (query && !name.includes(query) && !provider.id.toLowerCase().includes(query)) {
      continue
    }
    const groupId = resolveProviderGroup(provider)
    const list = buckets.get(groupId) || []
    list.push(provider)
    buckets.set(groupId, list)
  }

  const ordered = GROUP_ORDER
    .filter(groupId => buckets.has(groupId))
    .map(groupId => ({
      id: groupId,
      label: groupLabel(groupId),
      providers: buckets.get(groupId) || [],
    }))
  const extra = [...buckets.keys()]
    .filter(groupId => !KNOWN_GROUPS.has(groupId))
    .sort()
    .map(groupId => ({
      id: groupId,
      label: groupLabel(groupId),
      providers: buckets.get(groupId) || [],
    }))

  return [...ordered, ...extra]
})

// 每次打开都清空搜索，避免上次的关键词把可选列表藏起来
watch(
  () => props.show,
  visible => {
    if (visible) {
      keyword.value = ''
    }
  },
)
</script>

<style scoped>
@import '../styles/AddProviderDialog.css';
</style>
