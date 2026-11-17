<template>
  <Transition name="team-picker-fade">
    <div v-if="show" class="team-picker">
      <div class="team-picker-header">
        <component :is="UsersIcon" :size="13" />
        {{ $t('chat.teamPicker.title') }}
      </div>
      <div v-if="filteredTeams.length === 0" class="team-picker-empty">
        {{ $t('chat.teamPicker.empty') }}
      </div>
      <button
        v-for="(team, i) in filteredTeams"
        :key="team.id"
        class="team-picker-item"
        :class="{ active: i === activeIndex }"
        @mousedown.prevent="$emit('select', team)"
      >
        <span class="team-picker-name">{{ team.name }}</span>
        <span class="team-picker-badge">{{ modeLabelMap[team.mode] ?? team.mode }}</span>
      </button>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Users as UsersIcon } from 'lucide-vue-next'
import type { AgentTeam } from '@/store/agentTeams'

interface Props {
  show: boolean
  filteredTeams: AgentTeam[]
  activeIndex: number
}

defineProps<Props>()

interface Emits {
  (e: 'select', team: AgentTeam): void
}

defineEmits<Emits>()

const { t } = useI18n()

/**
 * 模式徽标文案：复用工作流面板的模式词表，避免两处维护同一组中文标签。
 */
const modeLabelMap = computed<Record<string, string>>(() => ({
  pipeline: t('chat.workflowPanel.modes.pipeline'),
  graph: t('chat.workflowPanel.modes.graph'),
  council: t('chat.workflowPanel.modes.council'),
}))
</script>

<style scoped>
.team-picker {
  position: absolute;
  bottom: calc(100% - 12px);
  left: 50%;
  transform: translateX(-50%);
  width: min(480px, calc(100% - 48px));
  max-height: 260px;
  overflow-y: auto;
  background: var(--bg-primary);
  border: 1px solid var(--border-color, var(--color-border-primary));
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  z-index: 100;
  padding: 6px;
}

.team-picker-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px 8px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: var(--text-tertiary);
  text-transform: uppercase;
  border-bottom: 1px solid var(--border-color, var(--color-border-primary));
  margin-bottom: 4px;
}

.team-picker-empty {
  padding: 20px 12px;
  text-align: center;
  font-size: 13px;
  color: var(--text-tertiary);
}

.team-picker-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 8px 12px;
  border: none;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--text-primary);
  font-size: 14px;
  text-align: left;
  cursor: pointer;
  transition: background 0.12s ease;
}

.team-picker-item:hover,
.team-picker-item.active {
  background: var(--hover-bg);
}

.team-picker-name {
  font-weight: 500;
  color: var(--text-primary);
}

.team-picker-badge {
  font-size: 11px;
  font-weight: 500;
  color: var(--text-secondary);
  background: var(--bg-secondary);
  border: 1px solid var(--border-color, var(--color-border-primary));
  border-radius: var(--radius-sm);
  padding: 1px 7px;
  white-space: nowrap;
  flex-shrink: 0;
  margin-left: 8px;
}

.team-picker-fade-enter-active,
.team-picker-fade-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.team-picker-fade-enter-from,
.team-picker-fade-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(6px);
}
</style>
