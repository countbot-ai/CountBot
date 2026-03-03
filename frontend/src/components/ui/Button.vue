<template>
  <button
    :class="buttonClasses"
    :disabled="disabled || loading"
    :type="type"
    @click="handleClick"
  >
    <component
      :is="LoaderIcon"
      v-if="loading"
      :size="iconSize"
      class="button-icon button-icon-loading"
    />
    <component
      :is="icon"
      v-else-if="icon"
      :size="iconSize"
      class="button-icon"
    />
    <span
      v-if="$slots.default"
      class="button-text"
    >
      <slot />
    </span>
  </button>
</template>

<script setup lang="ts">
import { computed, type Component } from 'vue'
import { Loader2 as LoaderIcon } from 'lucide-vue-next'

export interface ButtonProps {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: 'sm' | 'md' | 'lg'
  icon?: Component
  loading?: boolean
  disabled?: boolean
  type?: 'button' | 'submit' | 'reset'
  block?: boolean
}

const props = withDefaults(defineProps<ButtonProps>(), {
  variant: 'primary',
  size: 'md',
  type: 'button',
  loading: false,
  disabled: false,
  block: false
})

const emit = defineEmits<{
  click: [event: MouseEvent]
}>()

const buttonClasses = computed(() => [
  'button',
  `button-${props.variant}`,
  `button-${props.size}`,
  {
    'button-loading': props.loading,
    'button-disabled': props.disabled,
    'button-block': props.block,
    'button-icon-only': !props.$slots?.default
  }
])

const iconSize = computed(() => {
  const sizes = {
    sm: 16,
    md: 18,
    lg: 20
  }
  return sizes[props.size]
})

const handleClick = (event: MouseEvent) => {
  if (!props.disabled && !props.loading) {
    emit('click', event)
  }
}
</script>

<style scoped>
.button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-sm);
  font-family: var(--font-sans);
  font-weight: var(--font-weight-medium);
  line-height: var(--line-height-tight);
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-base);
  white-space: nowrap;
  user-select: none;
  outline: none;
}

.button:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

/* Sizes */
.button-sm {
  height: 32px;
  padding: 0 var(--spacing-md);
  font-size: var(--font-size-sm);
}

.button-md {
  height: 40px;
  padding: 0 var(--spacing-lg);
  font-size: var(--font-size-base);
}

.button-lg {
  height: 48px;
  padding: 0 var(--spacing-xl);
  font-size: var(--font-size-lg);
}

/* Icon only */
.button-icon-only.button-sm {
  width: 32px;
  padding: 0;
}

.button-icon-only.button-md {
  width: 40px;
  padding: 0;
}

.button-icon-only.button-lg {
  width: 48px;
  padding: 0;
}

/* Variants */
.button-primary {
  background-color: var(--color-primary);
  color: #ffffff;
}

.button-primary:hover:not(.button-disabled):not(.button-loading) {
  background-color: #1d4ed8;
  transform: translateY(-1px);
  box-shadow: var(--shadow-md);
}

.button-primary:active:not(.button-disabled):not(.button-loading) {
  transform: translateY(0);
}

.button-secondary {
  background-color: var(--bg-secondary);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
}

.button-secondary:hover:not(.button-disabled):not(.button-loading) {
  background-color: var(--hover-bg);
  border-color: var(--text-tertiary);
}

.button-ghost {
  background-color: transparent;
  color: var(--text-secondary);
}

.button-ghost:hover:not(.button-disabled):not(.button-loading) {
  background-color: var(--hover-bg);
  color: var(--text-primary);
}

.button-danger {
  background-color: var(--color-error);
  color: #ffffff;
}

.button-danger:hover:not(.button-disabled):not(.button-loading) {
  background-color: #dc2626;
  transform: translateY(-1px);
  box-shadow: var(--shadow-md);
}

/* States */
.button-disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.button-loading {
  cursor: wait;
}

.button-block {
  width: 100%;
}

/* Icon */
.button-icon {
  flex-shrink: 0;
}

.button-icon-loading {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.button-text {
  flex: 1;
}
</style>
