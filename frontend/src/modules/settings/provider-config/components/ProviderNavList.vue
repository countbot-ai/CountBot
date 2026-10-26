<template>
  <!--
    外层列负责铺满整列高度（底纹 + 分隔线），内层 nav 只在滚动时钉住内容；
    否则导航只有内容那么高，下方会留下一大块空白。
  -->
  <div class="provider-nav-column">
    <nav class="provider-nav" :aria-label="title">
      <div class="provider-nav-header">
        <span class="provider-nav-title">{{ title }}</span>
      </div>

      <div class="provider-nav-list">
        <div
          v-for="item in items"
          :key="item.id"
          class="provider-nav-item"
          :class="{ 'is-selected': item.id === selectedId }"
          role="button"
          tabindex="0"
          :title="`${item.name} · ${item.modelSummary}`"
          :aria-label="item.name"
          :aria-current="item.id === selectedId ? 'true' : undefined"
          @click="emit('select', item.id)"
          @keydown.enter.prevent="emit('select', item.id)"
          @keydown.space.prevent="emit('select', item.id)"
        >
          <ProviderIcon class="provider-nav-icon" :provider-id="item.id" :size="20">
            <span class="provider-nav-dot" :class="item.statusClass" />
          </ProviderIcon>
          <span class="provider-nav-copy">
            <span class="provider-nav-name">{{ item.name }}</span>
            <span class="provider-nav-meta">{{ item.modelSummary }}</span>
          </span>
          <span v-if="item.pendingSave" class="provider-nav-draft">{{ $t('settings.providers.unsavedBadge') }}</span>
          <span v-else-if="item.isCurrent" class="provider-nav-current">{{ currentLabel }}</span>

          <!-- 删除入口：清空密钥与模型，让它从左栏和对话窗口的模型下拉里一起消失 -->
          <button
            type="button"
            class="provider-nav-remove"
            :title="removeLabel"
            :aria-label="`${removeLabel} ${item.name}`"
            @click.stop="emit('remove', item.id)"
          >
            <Trash2Icon :size="14" />
          </button>
        </div>

        <!-- 唯一的添加入口：新增后先以「未保存」出现，保存成功才落库 -->
        <button
          type="button"
          class="provider-nav-item provider-nav-add"
          :title="addLabel"
          :aria-label="addLabel"
          @click="emit('add')"
        >
          <span class="provider-nav-icon is-add">
            <PlusIcon :size="15" />
          </span>
          <span class="provider-nav-copy">
            <span class="provider-nav-name">{{ addLabel }}</span>
          </span>
        </button>
      </div>

      <button
        v-if="hiddenCount > 0 || showAll"
        type="button"
        class="provider-nav-toggle"
        :class="{ 'is-active': showAll }"
        :title="showAll ? collapseLabel : expandLabel"
        @click="emit('toggle-show-all')"
      >
        <ChevronDownIcon :size="14" class="provider-nav-toggle-caret" />
        <span class="provider-nav-toggle-label">{{ showAll ? collapseLabel : expandLabel }}</span>
      </button>
    </nav>
  </div>
</template>

<script setup lang="ts">
import { ChevronDown as ChevronDownIcon, Plus as PlusIcon, Trash2 as Trash2Icon } from 'lucide-vue-next'
import ProviderIcon from '@/components/ui/ProviderIcon.vue'
import type { ProviderNavItem } from '../types'

interface Props {
  items: ProviderNavItem[]
  selectedId: string
  title: string
  addLabel: string
  removeLabel: string
  currentLabel: string
  showAll: boolean
  hiddenCount: number
  expandLabel: string
  collapseLabel: string
}

defineProps<Props>()

const emit = defineEmits<{
  (e: 'select', providerId: string): void
  (e: 'add'): void
  (e: 'remove', providerId: string): void
  (e: 'toggle-show-all'): void
}>()
</script>

<style scoped>
@import '../styles/ProviderNavList.css';
</style>
