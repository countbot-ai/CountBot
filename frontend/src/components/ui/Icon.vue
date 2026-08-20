<template>
  <component
    :is="iconComponent"
    :size="normalizedSize"
    :stroke-width="strokeWidth"
    :color="color"
    :class="['icon', `icon-${variant}`, { 'icon-clickable': clickable }]"
    :aria-label="ariaLabel"
    :role="clickable ? 'button' : undefined"
    :tabindex="clickable ? 0 : undefined"
    @click="handleClick"
    @keydown="handleKeydown"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import * as LucideIcons from 'lucide-vue-next'

type Variant = 'default' | 'primary' | 'success' | 'warning' | 'error' | 'muted'

interface Props {
  name: string
  size?: number | string
  strokeWidth?: number
  color?: string
  variant?: Variant
  clickable?: boolean
  ariaLabel?: string
}

interface Emits {
  (e: 'click', event: MouseEvent): void
}

const props = withDefaults(defineProps<Props>(), {
  size: 20,
  strokeWidth: 2,
  variant: 'default',
  clickable: false
})

const emit = defineEmits<Emits>()

const iconComponent = computed(() => {
  return (LucideIcons as Record<string, unknown>)[props.name] || LucideIcons.AlertCircle
})

const normalizedSize = computed(() => {
  return typeof props.size === 'number' ? props.size : Number(props.size)
})

const handleClick = (event: MouseEvent) => {
  if (props.clickable) {
    emit('click', event)
  }
}

const handleKeydown = (event: KeyboardEvent) => {
  if (props.clickable && (event.key === 'Enter' || event.key === ' ')) {
    event.preventDefault()
    emit('click', event as unknown as MouseEvent)
  }
}
</script>

<style scoped>
.icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all var(--transition-base);
}

.icon-default {
  color: currentColor;
}

.icon-primary {
  color: var(--color-primary);
}

.icon-success {
  color: var(--color-success);
}

.icon-warning {
  color: var(--color-warning);
}

.icon-error {
  color: var(--color-error);
}

.icon-muted {
  color: var(--text-tertiary);
}

.icon-clickable {
  cursor: pointer;
  border-radius: var(--radius-sm);
  padding: 2px;
}

.icon-clickable:hover {
  background: var(--hover-bg);
  transform: scale(1.1);
}

.icon-clickable:active {
  transform: scale(0.95);
}

.icon-clickable:focus {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}
</style>
