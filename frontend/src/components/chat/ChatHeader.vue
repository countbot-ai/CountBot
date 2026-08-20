<template>
  <header class="chat-header">
    <div class="header-left">
      <div
        class="header-brand"
        role="button"
        tabindex="0"
        :title="t('sidebar.title')"
        @click="emit('toggle-sidebar')"
        @keydown.enter.prevent="emit('toggle-sidebar')"
        @keydown.space.prevent="emit('toggle-sidebar')"
      >
        <h1 class="header-title">
          <span class="header-title-main">Count</span>
          <span class="header-title-accent">Bot</span>
        </h1>
      </div>
    </div>

    <div class="header-workspace" aria-hidden="true">
      <span class="header-workspace-line" />
      <span class="header-workspace-label">AI Workspace</span>
    </div>

    <div class="header-actions">
      <button
        v-for="action in actions"
        :key="action.id"
        type="button"
        class="header-btn"
        :class="{ 'is-emphasis': action.emphasis }"
        :title="t(action.tooltip || action.label)"
        @click="action.onClick"
      >
        <component :is="action.icon" :size="17" :stroke-width="1.85" class="header-btn-icon" />
        <span v-if="action.shortLabel && action.emphasis" class="header-btn-label">{{ action.shortLabel }}</span>
      </button>

      <button
        type="button"
        class="header-btn header-btn-danger"
        :title="t('chat.clearCurrentChat')"
        @click="emit('clear-chat')"
      >
        <component :is="Trash2Icon" :size="17" :stroke-width="1.85" class="header-btn-icon" />
      </button>
    </div>
  </header>
</template>

<script setup lang="ts">
import type { Component } from 'vue'
import { Trash2 as Trash2Icon } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'

interface HeaderAction {
  id: string
  icon: Component
  label: string
  tooltip?: string
  emphasis?: boolean
  shortLabel?: string
  onClick: () => void
}

defineProps<{
  actions: HeaderAction[]
}>()

const emit = defineEmits<{
  'toggle-sidebar': []
  'clear-chat': []
}>()

const { t } = useI18n()
</script>
<style scoped>
@import './styles/ChatHeader.css';
</style>
