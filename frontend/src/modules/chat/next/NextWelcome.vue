<template>
  <section class="nc-welcome">
    <div class="nc-welcome-inner">
      <img class="nc-welcome-mark" src="@/assets/countbot-logo.svg" alt="" aria-hidden="true" />

      <h1 class="nc-welcome-greeting">{{ greeting }}</h1>

      <div class="nc-welcome-composer">
        <slot name="composer" />
      </div>

      <div v-if="userStore.loaded" class="nc-welcome-chips">
        <button
          v-for="action in quickActions"
          :key="action.id"
          class="nc-welcome-chip"
          @click="$emit('quick-action', action)"
        >
          <component :is="action.icon" :size="14" class="nc-welcome-chip-icon" />
          <span>{{ action.label }}</span>
        </button>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  Blocks as BlocksIcon,
  Cpu as CpuIcon,
  Plug as PlugIcon,
  SlidersHorizontal as SlidersIcon,
  UserRound as PersonIcon,
  Users as UsersIcon,
} from 'lucide-vue-next'
import type { WelcomeQuickAction } from './types'
import { useUserStore } from '@/store/user'

defineEmits<{
  (e: 'quick-action', action: WelcomeQuickAction): void
}>()

const { t } = useI18n()
const userStore = useUserStore()

const greeting = computed(() => {
  const hour = new Date().getHours()
  const period = hour < 12 ? 'Morning' : hour < 18 ? 'Afternoon' : 'Evening'
  const baseKey = `chat.next.greeting${period}`
  const userKey = `chat.next.greeting${period}User`
  const name = userStore.displayName.trim()

  // 未登录或身份未就绪时沿用通用问候
  if (!userStore.isAuthenticated || !name) {
    return t(baseKey)
  }
  return t(userKey, { name })
})

/** 管理员入口指向全局配置，普通用户入口指向 /api/me/* 的用户级配置。 */
const quickActions = computed<WelcomeQuickAction[]>(() => {
  const adminActions: WelcomeQuickAction[] = [
    {
      id: 'provider',
      label: t('chat.welcome.setupProvider'),
      icon: CpuIcon,
      kind: 'settings',
      value: 'provider',
    },
    {
      id: 'channels',
      label: t('chat.welcome.setupChannels'),
      icon: PlugIcon,
      kind: 'settings',
      value: 'channels',
    },
    {
      id: 'teams',
      label: t('chat.welcome.setupTeams'),
      icon: UsersIcon,
      kind: 'settings',
      value: 'teams',
    },
  ]

  const userActions: WelcomeQuickAction[] = [
    {
      id: 'model',
      label: t('settings.tabs.model'),
      icon: SlidersIcon,
      kind: 'settings',
      value: 'model',
    },
    {
      id: 'persona',
      label: t('settings.tabs.persona'),
      icon: PersonIcon,
      kind: 'settings',
      value: 'persona',
    },
    {
      id: 'sharedskills',
      label: t('settings.tabs.sharedskills'),
      icon: UsersIcon,
      kind: 'settings',
      value: 'sharedskills',
    },
  ]

  return [
    ...(userStore.isAdmin ? adminActions : userActions),
    {
      id: 'skills',
      label: t('nav.skills'),
      icon: BlocksIcon,
      kind: 'panel',
      value: 'skills',
    },
  ]
})
</script>

<style scoped>
@import './styles/NextWelcome.css';
</style>
