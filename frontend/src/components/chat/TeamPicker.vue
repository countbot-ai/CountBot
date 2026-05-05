<template>
  <Transition name="team-picker-fade">
    <div v-if="show" class="team-picker">
      <div class="team-picker-header">
        <component :is="UsersIcon" :size="13" />
        选择团队
      </div>
      <div v-if="filteredTeams.length === 0" class="team-picker-empty">
        无匹配团队
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

const modeLabelMap: Record<string, string> = {
  pipeline: '流水线',
  graph: '依赖图',
  council: '多视角评审',
}
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
  background: var(--bg-primary, #ffffff);
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: var(--radius-lg, 12px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.10), 0 2px 6px rgba(0, 0, 0, 0.06);
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
  color: var(--text-tertiary, #9ca3af);
  text-transform: uppercase;
  border-bottom: 1px solid var(--border-color, #f3f4f6);
  margin-bottom: 4px;
}

.team-picker-empty {
  padding: 20px 12px;
  text-align: center;
  font-size: 13px;
  color: var(--text-tertiary, #9ca3af);
}

.team-picker-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 8px 12px;
  border: none;
  border-radius: var(--radius-md, 8px);
  background: transparent;
  color: var(--text-primary, #111827);
  font-size: 14px;
  text-align: left;
  cursor: pointer;
  transition: background 0.12s ease;
}

.team-picker-item:hover,
.team-picker-item.active {
  background: var(--hover-bg, #f3f4f6);
}

.team-picker-name {
  font-weight: 500;
  color: var(--text-primary, #111827);
}

.team-picker-badge {
  font-size: 11px;
  font-weight: 500;
  color: var(--text-secondary, #6b7280);
  background: var(--bg-secondary, #f9fafb);
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: var(--radius-sm, 4px);
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
