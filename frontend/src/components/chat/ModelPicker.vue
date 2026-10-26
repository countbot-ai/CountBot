<template>
  <div ref="rootRef" class="model-picker">
    <button
      type="button"
      class="model-picker-trigger"
      :aria-expanded="open"
      :aria-label="$t('chat.modelPicker.title')"
      :title="triggerTitle"
      @click="toggle"
    >
      <ProviderIcon :provider-id="providerId" :size="15" />
      <span class="model-picker-label">{{ triggerLabel }}</span>
      <span v-if="isSessionOverride" class="model-picker-badge">
        {{ $t('chat.modelPicker.sessionBadge') }}
      </span>
      <component :is="ChevronDownIcon" :size="14" class="model-picker-caret" />
    </button>

    <div v-if="open" class="model-picker-popover">
      <p v-if="selectableGroups.length === 0" class="model-picker-empty">
        {{ $t('chat.modelPicker.empty') }}
      </p>

      <template v-else>
        <div class="model-picker-search">
          <component :is="SearchIcon" :size="14" class="model-picker-search-icon" />
          <input
            ref="searchRef"
            v-model="keyword"
            type="text"
            class="model-picker-search-input"
            :placeholder="$t('chat.modelPicker.searchPlaceholder')"
            @keydown.esc.stop="close"
          />
        </div>

        <!-- 供应商 -> 模型 两级：默认先出供应商，命中后右侧出该供应商的模型 -->
        <div v-if="visibleGroups.length === 0" class="model-picker-empty">
          {{ $t('chat.modelPicker.noMatch') }}
        </div>

        <div v-else class="model-picker-body">
          <div class="model-picker-providers" role="listbox">
            <button
              v-for="group in visibleGroups"
              :key="group.providerId"
              type="button"
              role="option"
              class="model-picker-provider"
              :class="{ 'is-active': group.providerId === activeProviderId }"
              :aria-selected="group.providerId === activeProviderId"
              @mouseenter="activeProviderId = group.providerId"
              @focus="activeProviderId = group.providerId"
              @click="activeProviderId = group.providerId"
            >
              <ProviderIcon :provider-id="group.providerId" :size="16" />
              <span class="model-picker-provider-copy">
                <span class="model-picker-provider-name">{{ group.providerName }}</span>
                <span class="model-picker-provider-meta">
                  {{ $t('settings.providers.models.count', { count: group.models.length }) }}
                </span>
              </span>
              <component
                v-if="group.providerId === providerId"
                :is="CheckIcon"
                :size="13"
                class="model-picker-provider-check"
              />
            </button>
          </div>

          <div class="model-picker-models" role="listbox">
            <button
              v-for="model in activeModels"
              :key="model.id"
              type="button"
              role="option"
              class="model-picker-item"
              :class="{ 'is-active': isActive(activeProviderId, model.id) }"
              :aria-selected="isActive(activeProviderId, model.id)"
              @click="selectModel(activeProviderId, model.id)"
            >
              <span class="model-picker-item-icon">
                <BoxIcon :size="13" />
              </span>
              <span class="model-picker-item-main">
                <span class="model-picker-item-name">{{ model.display_name || model.id }}</span>
                <span
                  v-if="model.display_name && model.display_name !== model.id"
                  class="model-picker-item-id"
                >
                  {{ model.id }}
                </span>
              </span>
              <span v-if="model.context_window" class="model-picker-item-pill">
                {{ formatContextLength(model.context_window) }}
              </span>
              <component
                v-if="isActive(activeProviderId, model.id)"
                :is="CheckIcon"
                :size="14"
                class="model-picker-check"
              />
            </button>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  Box as BoxIcon,
  Check as CheckIcon,
  ChevronDown as ChevronDownIcon,
  Search as SearchIcon,
} from 'lucide-vue-next'
import ProviderIcon from '@/components/ui/ProviderIcon.vue'
import { formatContextLength } from '@/utils/modelConfig'
import type { ProviderModelEntry } from '@/api'

export interface ModelPickerGroup {
  providerId: string
  providerName: string
  models: ProviderModelEntry[]
}

interface Props {
  groups: ModelPickerGroup[]
  providerId?: string
  modelId?: string
  /** 当前会话是否覆盖了全局模型 */
  isSessionOverride?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  providerId: '',
  modelId: '',
  isSessionOverride: false,
})

const emit = defineEmits<{
  (e: 'select', providerId: string, modelId: string): void
}>()

const { t } = useI18n()

const rootRef = ref<HTMLElement>()
const searchRef = ref<HTMLInputElement>()
const open = ref(false)
const keyword = ref('')
const activeProviderId = ref('')

/** 下拉只展示真正有可用模型的供应商 */
const selectableGroups = computed(() =>
  props.groups.filter(group => group.models.length > 0),
)

const query = computed(() => keyword.value.trim().toLowerCase())

function matchesModel(model: ProviderModelEntry): boolean {
  if (!query.value) {
    return true
  }
  return (
    model.id.toLowerCase().includes(query.value)
    || (model.display_name || '').toLowerCase().includes(query.value)
  )
}

/** 搜索时按「供应商名命中」或「该供应商下有模型命中」保留供应商 */
const visibleGroups = computed(() =>
  selectableGroups.value.filter((group) => {
    if (!query.value) {
      return true
    }
    return (
      group.providerName.toLowerCase().includes(query.value)
      || group.models.some(matchesModel)
    )
  }),
)

const activeModels = computed(() => {
  const group = visibleGroups.value.find(item => item.providerId === activeProviderId.value)
  return group ? group.models.filter(matchesModel) : []
})

const triggerLabel = computed(() => {
  for (const group of props.groups) {
    const model = group.models.find(item => item.id === props.modelId)
    if (model) {
      return model.display_name || model.id
    }
  }
  return props.modelId || t('chat.modelPicker.placeholder')
})

const triggerTitle = computed(() => `${props.providerId} / ${props.modelId || '-'}`)

function isActive(providerId: string, modelId: string): boolean {
  return providerId === props.providerId && modelId === props.modelId
}

/** 打开时定位到当前供应商；没有命中时退回第一个可选项 */
function syncActiveProvider(): void {
  const groups = visibleGroups.value
  if (!groups.length) {
    activeProviderId.value = ''
    return
  }
  const current = groups.find(group => group.providerId === props.providerId)
  activeProviderId.value = (current || groups[0]).providerId
}

function toggle(): void {
  open.value = !open.value
  if (!open.value) {
    return
  }
  keyword.value = ''
  syncActiveProvider()
  nextTick(() => searchRef.value?.focus())
}

function close(): void {
  open.value = false
}

function selectModel(providerId: string, modelId: string): void {
  emit('select', providerId, modelId)
  close()
}

function handleDocumentPointerDown(event: MouseEvent): void {
  if (!open.value) {
    return
  }
  const target = event.target as Node | null
  if (target && rootRef.value && !rootRef.value.contains(target)) {
    close()
  }
}

/** 搜索结果变化后，若当前高亮的供应商被过滤掉就重新定位 */
watch(visibleGroups, () => {
  if (!open.value) {
    return
  }
  if (!visibleGroups.value.some(group => group.providerId === activeProviderId.value)) {
    syncActiveProvider()
  }
})

onMounted(() => {
  document.addEventListener('mousedown', handleDocumentPointerDown)
})

onBeforeUnmount(() => {
  document.removeEventListener('mousedown', handleDocumentPointerDown)
})
</script>

<style scoped>
@import './styles/ModelPicker.css';
</style>
