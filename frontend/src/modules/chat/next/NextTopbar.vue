<template>
  <header class="nc-topbar">
    <div class="nc-topbar-left">
      <button
        class="nc-topbar-button"
        :title="$t('chat.next.toggleSidebar')"
        :aria-label="$t('chat.next.toggleSidebar')"
        @click="$emit('toggle-sidebar')"
      >
        <component :is="PanelLeftIcon" :size="16" />
      </button>
      <span v-if="isStreaming" class="nc-topbar-status-dot" aria-hidden="true" />
      <span class="nc-topbar-title" :class="{ 'is-muted': !title }">
        {{ title || $t('chat.title') }}
      </span>
    </div>

    <div class="nc-topbar-right">
      <span
        v-if="userName"
        class="nc-topbar-user"
        :title="$t('settings.account.signedInAs', { name: userName })"
      >
        {{ userName }}
      </span>
      <button
        v-if="hasMessages"
        class="nc-topbar-button"
        :title="$t('chat.next.timeline')"
        :aria-label="$t('chat.next.timeline')"
        @click="$emit('open-panel', 'timeline')"
      >
        <component :is="RouteIcon" :size="16" />
      </button>
      <button
        v-if="hasMessages"
        class="nc-topbar-button"
        :title="$t('chat.clearCurrentChat')"
        :aria-label="$t('chat.clearCurrentChat')"
        @click="$emit('clear-chat')"
      >
        <component :is="Trash2Icon" :size="16" />
      </button>
      <button
        class="nc-topbar-button"
        :title="$t('chat.newSession')"
        :aria-label="$t('chat.newSession')"
        @click="$emit('new-session')"
      >
        <component :is="PlusIcon" :size="16" />
      </button>
      <button
        class="nc-topbar-button"
        :title="$t('sidebar.title')"
        :aria-label="$t('sidebar.title')"
        @click="$emit('open-system')"
      >
        <component :is="InfoIcon" :size="16" />
      </button>
      <button
        class="nc-topbar-button"
        :title="$t('settings.title')"
        :aria-label="$t('settings.title')"
        @click="$emit('open-settings')"
      >
        <component :is="SettingsIcon" :size="16" />
      </button>
      <!-- 远程登录时在设置旁提供注销入口：退出是会话级操作，需与常用按钮同级可达 -->
      <button
        v-if="showLogout"
        class="nc-topbar-button nc-topbar-button-danger"
        :title="$t('sidebar.logout') || '注销'"
        :aria-label="$t('sidebar.logout') || '注销'"
        @click="$emit('logout')"
      >
        <component :is="LogOutIcon" :size="16" />
      </button>
    </div>
  </header>
</template>

<script setup lang="ts">
import {
  Info as InfoIcon,
  LogOut as LogOutIcon,
  PanelLeft as PanelLeftIcon,
  Plus as PlusIcon,
  Route as RouteIcon,
  Settings as SettingsIcon,
  Trash2 as Trash2Icon,
} from 'lucide-vue-next'

interface Props {
  title?: string
  userName?: string
  hasMessages?: boolean
  isStreaming?: boolean
  /** 有登录会话才显示注销：本机免登录时没有会话可注销 */
  showLogout?: boolean
}

withDefaults(defineProps<Props>(), {
  title: '',
  hasMessages: false,
  isStreaming: false,
  showLogout: false,
})

defineEmits<{
  (e: 'toggle-sidebar'): void
  (e: 'new-session'): void
  (e: 'clear-chat'): void
  (e: 'open-panel', panel: 'timeline'): void
  (e: 'open-settings'): void
  (e: 'open-system'): void
  (e: 'logout'): void
}>()
</script>

<style scoped>
@import './styles/NextTopbar.css';
</style>
