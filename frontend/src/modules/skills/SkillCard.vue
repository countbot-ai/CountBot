<template>
  <div
    class="skill-card"
    :class="{ 'disabled': !skill.enabled, 'unavailable': !available }"
  >
    <!-- 卡片头部 -->
    <div class="card-header">
      <div class="skill-info">
        <component
          :is="BookOpenIcon"
          :size="20"
          class="skill-icon"
        />
        <h3 class="skill-name">
          {{ skill.name }}
        </h3>
      </div>
      <div class="skill-badges">
        <span
          v-if="skill.autoLoad"
          class="badge auto-load"
          :title="$t('skills.autoLoadTooltip')"
        >
          <component
            :is="ZapIcon"
            :size="12"
          />
          {{ $t('skills.autoLoad') }}
        </span>
        <span
          v-if="!available"
          class="badge unavailable"
          :title="$t('skills.requirementsNotMet')"
        >
          <component
            :is="AlertCircleIcon"
            :size="12"
          />
          {{ $t('skills.unavailable') }}
        </span>
      </div>
    </div>

    <!-- 卡片主体 -->
    <div class="card-body">
      <p class="skill-description">
        {{ skill.description || $t('skills.noDescription') }}
      </p>

      <!-- 依赖要求 -->
      <div
        v-if="skill.requirements && skill.requirements.length > 0"
        class="requirements"
      >
        <component
          :is="AlertCircleIcon"
          :size="14"
        />
        <span class="requirements-label">{{ $t('skills.requirements') }}:</span>
        <div class="requirements-list">
          <span
            v-for="req in skill.requirements"
            :key="req"
            class="requirement-tag"
          >
            {{ req }}
          </span>
        </div>
      </div>
    </div>

    <!-- 卡片底部 -->
    <div class="card-footer">
      <button
        class="view-btn"
        @click="handleView"
      >
        <component
          :is="EyeIcon"
          :size="16"
        />
        {{ $t('skills.viewDetails') }}
      </button>
      <button
        class="toggle-btn"
        :class="{ 'enabled': skill.enabled }"
        :disabled="!available"
        @click="handleToggle"
      >
        <component
          :is="skill.enabled ? ToggleRightIcon : ToggleLeftIcon"
          :size="16"
        />
        {{ skill.enabled ? $t('skills.disable') : $t('skills.enable') }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
// import { computed } from 'vue'
import {
  BookOpen as BookOpenIcon,
  Zap as ZapIcon,
  AlertCircle as AlertCircleIcon,
  Eye as EyeIcon,
  ToggleLeft as ToggleLeftIcon,
  ToggleRight as ToggleRightIcon
} from 'lucide-vue-next'
import type { Skill } from '@/store/skills'

interface Props {
  skill: Skill
  available?: boolean
}

interface Emits {
  (e: 'view', skillName: string): void
  (e: 'toggle', skillName: string, enabled: boolean): void
}

const props = withDefaults(defineProps<Props>(), {
  available: true
})

const emit = defineEmits<Emits>()

// 方法
const handleView = () => {
  emit('view', props.skill.name)
}

const handleToggle = () => {
  if (props.available) {
    emit('toggle', props.skill.name, !props.skill.enabled)
  }
}
</script>

<style scoped>
.skill-card {
  display: flex;
  flex-direction: column;
  padding: var(--spacing-md);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-secondary);
  transition: all var(--transition-base);
}

.skill-card:hover {
  border-color: var(--color-primary);
  box-shadow: var(--shadow-sm);
}

.skill-card.disabled {
  opacity: 0.6;
}

.skill-card.unavailable {
  opacity: 0.5;
  border-color: var(--color-warning);
}

.card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: var(--spacing-sm);
}

.skill-info {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  flex: 1;
  min-width: 0;
}

.skill-icon {
  color: var(--color-primary);
  flex-shrink: 0;
}

.skill-name {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  margin: 0;
  word-break: break-word;
}

.skill-badges {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-xs);
  flex-shrink: 0;
}

.badge {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  white-space: nowrap;
}

.badge.auto-load {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.badge.unavailable {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.card-body {
  flex: 1;
  margin-bottom: var(--spacing-md);
}

.skill-description {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  margin: 0 0 var(--spacing-sm) 0;
  line-height: 1.5;
}

.requirements {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm);
  border-radius: var(--radius-sm);
  background: var(--bg-tertiary);
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
}

.requirements svg {
  flex-shrink: 0;
  margin-top: 2px;
}

.requirements-label {
  font-weight: var(--font-weight-medium);
  flex-shrink: 0;
}

.requirements-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.requirement-tag {
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  background: var(--bg-primary);
  color: var(--text-secondary);
  font-size: var(--font-size-xs);
}

.card-footer {
  display: flex;
  gap: var(--spacing-sm);
  padding-top: var(--spacing-sm);
  border-top: 1px solid var(--border-color);
}

.view-btn,
.toggle-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: all var(--transition-base);
}

.view-btn {
  flex: 1;
}

.view-btn:hover {
  background: var(--hover-bg);
  border-color: var(--color-primary);
}

.toggle-btn:hover:not(:disabled) {
  background: var(--hover-bg);
}

.toggle-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.toggle-btn.enabled {
  background: var(--color-success-bg);
  border-color: var(--color-success);
  color: var(--color-success);
}
</style>
