<template>
  <nav class="nc-rail">
    <div class="nc-rail-brand">
      <img class="nc-rail-logo" src="@/assets/countbot-logo.svg" alt="CountBot" />
    </div>

    <button
      v-for="item in contentItems"
      :key="item.id"
      class="nc-rail-item"
      :class="{ 'is-active': item.id === activeSection }"
      :data-tip="item.label"
      :aria-label="item.label"
      :aria-pressed="item.id === activeSection"
      @click="$emit('select-section', item.id)"
    >
      <component :is="item.icon" :size="18" />
    </button>

    <div class="nc-rail-divider" aria-hidden="true" />

    <button
      v-for="item in configItems"
      :key="item.id"
      class="nc-rail-item"
      :class="{ 'is-active': item.id === activeSection }"
      :data-tip="item.label"
      :aria-label="item.label"
      :aria-pressed="item.id === activeSection"
      @click="$emit('select-section', item.id)"
    >
      <component :is="item.icon" :size="18" />
    </button>

    <div class="nc-rail-spacer" />

    <button
      class="nc-rail-item"
      :data-tip="$t('settings.title')"
      :aria-label="$t('settings.title')"
      @click="$emit('open-settings', 'general')"
    >
      <component :is="SettingsIcon" :size="18" />
    </button>

    <button
      v-if="showLogout"
      class="nc-rail-item nc-rail-item--danger"
      :data-tip="$t('sidebar.logout') || '注销'"
      :aria-label="$t('sidebar.logout') || '注销'"
      @click="$emit('logout')"
    >
      <component :is="LogOutIcon" :size="18" />
    </button>
  </nav>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  AlarmClock as AlarmClockIcon,
  Blocks as BlocksIcon,
  BookOpen as BookOpenIcon,
  LogOut as LogOutIcon,
  MessageSquare as MessageSquareIcon,
  Radio as RadioIcon,
  Settings as SettingsIcon,
  Sparkles as SparklesIcon,
  Users as UsersIcon,
  type Icon as LucideIcon,
} from 'lucide-vue-next'
import type { ChatSection } from './types'
import type { SettingsTab } from '@/types/settings'

interface RailItem {
  id: ChatSection
  label: string
  icon: LucideIcon
}

defineProps<{
  activeSection: ChatSection
  showLogout?: boolean
}>()

defineEmits<{
  'select-section': [section: ChatSection]
  'open-settings': [tab: SettingsTab]
  logout: []
}>()

const { t } = useI18n()

/** 内容型入口：直接产出业务内容 */
const contentItems = computed<RailItem[]>(() => [
  { id: 'sessions', label: t('nav.chat'), icon: MessageSquareIcon },
  { id: 'cron', label: t('nav.cron'), icon: AlarmClockIcon },
  { id: 'skills', label: t('nav.skills'), icon: BlocksIcon },
  { id: 'wiki', label: t('nav.wiki'), icon: BookOpenIcon },
])

/** 配置型入口：人设、团队与渠道 */
const configItems = computed<RailItem[]>(() => [
  { id: 'persona', label: t('nav.persona'), icon: SparklesIcon },
  { id: 'multiagent', label: t('nav.multiagent'), icon: UsersIcon },
  { id: 'channels', label: t('nav.remoteConnection'), icon: RadioIcon },
])
</script>

<style scoped>
@import './styles/NextRail.css';
</style>
