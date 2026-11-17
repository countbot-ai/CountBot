<template>
  <section class="nc-welcome">
    <div class="nc-welcome-inner">
      <img class="nc-welcome-mark" src="@/assets/countbot-logo.svg" alt="" aria-hidden="true" />

      <h1 class="nc-welcome-greeting">{{ greeting }}</h1>

      <div class="nc-welcome-composer">
        <slot name="composer" />
      </div>

      <div class="nc-welcome-chips">
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
  Users as UsersIcon,
} from 'lucide-vue-next'
import type { WelcomeQuickAction } from './types'

defineEmits<{
  (e: 'quick-action', action: WelcomeQuickAction): void
}>()

const { t } = useI18n()

const greeting = computed(() => {
  const hour = new Date().getHours()
  if (hour < 12) return t('chat.next.greetingMorning')
  if (hour < 18) return t('chat.next.greetingAfternoon')
  return t('chat.next.greetingEvening')
})

const quickActions = computed<WelcomeQuickAction[]>(() => [
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
  {
    id: 'skills',
    label: t('nav.skills'),
    icon: BlocksIcon,
    kind: 'panel',
    value: 'skills',
  },
])
</script>

<style scoped>
@import './styles/NextWelcome.css';
</style>
