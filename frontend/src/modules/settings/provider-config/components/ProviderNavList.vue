<template>
  <div class="provider-nav-column" :class="{ 'is-expanded': expanded }">
    <div class="provider-nav-head">
      <template v-if="expanded">
        <span class="provider-nav-title">{{ title }}</span>
        <button
          type="button"
          class="provider-nav-add-btn"
          :title="addLabel"
          :aria-label="addLabel"
          @click="emit('add')"
        >
          <PlusIcon :size="14" />
          <span class="provider-nav-add-label">{{ addLabel }}</span>
        </button>
      </template>

      <button
        v-else
        type="button"
        class="provider-nav-add-btn is-icon-only"
        :title="addLabel"
        :aria-label="addLabel"
        @click="emit('add')"
      >
        <PlusIcon :size="16" />
      </button>
    </div>

    <div v-if="expanded" class="provider-nav-search">
      <SearchIcon :size="14" class="provider-nav-search-icon" />
      <input
        ref="searchInputRef"
        v-model="keyword"
        type="search"
        class="provider-nav-search-input"
        :placeholder="$t('settings.providers.sidebar.searchPlaceholder')"
        :aria-label="$t('settings.providers.sidebar.searchPlaceholder')"
      >
      <button
        v-if="keyword"
        type="button"
        class="provider-nav-search-clear"
        :aria-label="$t('common.clear')"
        @click="keyword = ''"
      >
        <XIcon :size="12" />
      </button>
    </div>

    <button
      v-else
      type="button"
      class="provider-nav-search-trigger"
      :title="$t('settings.providers.sidebar.searchPlaceholder')"
      :aria-label="$t('settings.providers.sidebar.searchPlaceholder')"
      @click="requestSearch"
    >
      <SearchIcon :size="16" />
    </button>

    <div class="provider-nav-scroll">
      <p v-if="expanded" class="provider-nav-group-label">
        <span>{{ $t('settings.providers.sidebar.configured') }}</span>
        <span class="provider-nav-group-count">{{ filteredItems.length }}</span>
      </p>

      <div v-if="filteredItems.length === 0" class="provider-nav-empty">
        <template v-if="keyword">
          {{ $t('settings.providers.sidebar.noMatch') }}
        </template>
        <template v-else>
          <p class="provider-nav-empty-title">{{ $t('settings.providers.sidebar.empty') }}</p>
          <p class="provider-nav-empty-hint">{{ $t('settings.providers.sidebar.emptyHint') }}</p>
        </template>
      </div>

      <div
        v-for="item in filteredItems"
        :key="item.id"
        class="provider-nav-item"
        :class="{ 'is-selected': item.id === selectedId }"
        role="button"
        tabindex="0"
        :title="`${item.name} · ${item.modelSummary} · ${item.statusText}`"
        :aria-label="item.name"
        :aria-current="item.id === selectedId ? 'true' : undefined"
        @click="emit('select', item.id)"
        @keydown.enter.prevent="emit('select', item.id)"
        @keydown.space.prevent="emit('select', item.id)"
      >
        <span class="provider-nav-logo">
          <ProviderIcon :provider-id="item.id" :size="18" />
          <span class="provider-nav-dot" :class="item.statusClass" />
        </span>

        <span v-if="expanded" class="provider-nav-copy">
          <span class="provider-nav-name">{{ item.name }}</span>
          <span class="provider-nav-meta">{{ item.modelSummary }} · {{ item.statusText }}</span>
        </span>

        <span v-if="expanded" class="provider-nav-trailing">
          <span v-if="item.isCurrent" class="provider-nav-current">{{ currentLabel }}</span>
          <span v-if="item.pendingSave" class="provider-nav-draft">
            {{ $t('settings.providers.unsavedBadge') }}
          </span>
          <span
            v-else-if="item.dirty"
            class="provider-nav-dirty"
            :title="$t('settings.providers.saveBar.unsaved')"
            :aria-label="$t('settings.providers.saveBar.unsaved')"
          />
        </span>

        <!-- 删除入口：清空密钥与模型，让它从左栏和对话窗口的模型下拉里一起消失 -->
        <button
          type="button"
          class="provider-nav-remove"
          :title="removeLabel"
          :aria-label="`${removeLabel} ${item.name}`"
          @click.stop="emit('remove', item.id)"
        >
          <Trash2Icon :size="13" />
        </button>
      </div>
    </div>

    <div class="provider-nav-foot">
      <button
        type="button"
        class="provider-nav-toggle"
        :title="expanded
          ? $t('settings.providers.sidebar.collapse')
          : $t('settings.providers.sidebar.expand')"
        :aria-label="expanded
          ? $t('settings.providers.sidebar.collapse')
          : $t('settings.providers.sidebar.expand')"
        :aria-expanded="expanded"
        @click="emit('toggle-expanded')"
      >
        <component :is="expanded ? PanelLeftCloseIcon : PanelLeftOpenIcon" :size="16" />
        <span v-if="expanded" class="provider-nav-toggle-label">
          {{ $t('settings.providers.sidebar.collapse') }}
        </span>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import {
  PanelLeftClose as PanelLeftCloseIcon,
  PanelLeftOpen as PanelLeftOpenIcon,
  Plus as PlusIcon,
  Search as SearchIcon,
  Trash2 as Trash2Icon,
  X as XIcon,
} from 'lucide-vue-next'
import ProviderIcon from '@/components/ui/ProviderIcon.vue'
import type { ProviderNavItem } from '../types'

interface Props {
  items: ProviderNavItem[]
  selectedId: string
  title: string
  addLabel: string
  removeLabel: string
  currentLabel: string
  /** 展开显示名称与搜索；收起时只保留图标轨道 */
  expanded: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'select', providerId: string): void
  (e: 'add'): void
  (e: 'remove', providerId: string): void
  (e: 'toggle-expanded'): void
}>()

const keyword = ref('')
const searchInputRef = ref<HTMLInputElement | null>(null)
const focusSearchAfterExpand = ref(false)

const filteredItems = computed(() => {
  const query = keyword.value.trim().toLowerCase()
  if (!query) {
    return props.items
  }
  return props.items.filter(
    item =>
      item.name.toLowerCase().includes(query)
      || item.id.toLowerCase().includes(query),
  )
})

function requestSearch(): void {
  focusSearchAfterExpand.value = true
  emit('toggle-expanded')
}

watch(
  () => props.expanded,
  async expanded => {
    if (!expanded || !focusSearchAfterExpand.value) {
      return
    }
    focusSearchAfterExpand.value = false
    await nextTick()
    searchInputRef.value?.focus()
  },
)
</script>

<style scoped>
@import '../styles/ProviderNavList.css';
</style>
