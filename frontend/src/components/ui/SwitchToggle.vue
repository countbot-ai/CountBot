<template>
  <span
    class="switch-toggle"
    :class="{ 'is-disabled': disabled }"
    :style="cssVars"
  >
    <input
      :checked="modelValue"
      :disabled="disabled"
      :aria-label="ariaLabel"
      type="checkbox"
      class="switch-toggle-input"
      @change="handleChange"
    >
    <span class="switch-toggle-track" aria-hidden="true"></span>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  modelValue: boolean
  disabled?: boolean
  ariaLabel?: string
  width?: number
  height?: number
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false,
  ariaLabel: '',
  width: 48,
  height: 28,
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'change', value: boolean): void
}>()

const normalizedWidth = computed(() => Math.max(32, Math.round(props.width)))
const normalizedHeight = computed(() => Math.max(18, Math.round(props.height)))
const padding = computed(() => Math.max(2, Math.round(normalizedHeight.value * 0.14)))
const thumbSize = computed(() =>
  Math.max(12, normalizedHeight.value - padding.value * 2),
)
const thumbShift = computed(() =>
  Math.max(0, normalizedWidth.value - thumbSize.value - padding.value * 2),
)

const cssVars = computed(() => ({
  '--switch-width': `${normalizedWidth.value}px`,
  '--switch-height': `${normalizedHeight.value}px`,
  '--switch-padding': `${padding.value}px`,
  '--switch-thumb-size': `${thumbSize.value}px`,
  '--switch-thumb-shift': `${thumbShift.value}px`,
}))

function handleChange(event: Event) {
  const checked = (event.target as HTMLInputElement).checked
  emit('update:modelValue', checked)
  emit('change', checked)
}
</script>

<style scoped>
.switch-toggle {
  position: relative;
  display: inline-flex;
  width: var(--switch-width);
  height: var(--switch-height);
  flex-shrink: 0;
  vertical-align: middle;
}

.switch-toggle-input {
  position: absolute;
  inset: 0;
  margin: 0;
  opacity: 0;
  cursor: pointer;
  z-index: 1;
}

.switch-toggle-track {
  position: absolute;
  inset: 0;
  pointer-events: none;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 999px;
  background: var(--bg-tertiary, #dbe3ee);
  box-shadow: inset 0 1px 2px rgba(15, 23, 42, 0.06);
  transition:
    background-color 0.2s ease,
    border-color 0.2s ease,
    box-shadow 0.2s ease,
    opacity 0.2s ease;
}

.switch-toggle-track::before {
  content: '';
  position: absolute;
  top: var(--switch-padding);
  left: var(--switch-padding);
  width: var(--switch-thumb-size);
  height: var(--switch-thumb-size);
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 999px;
  background: #ffffff;
  box-shadow: 0 2px 4px rgba(15, 23, 42, 0.16);
  transition:
    transform 0.2s ease,
    background-color 0.2s ease,
    border-color 0.2s ease,
    box-shadow 0.2s ease;
}

.switch-toggle-input:checked + .switch-toggle-track {
  border-color: var(--color-success, #10b981);
  background: var(--color-success, #10b981);
  box-shadow: 0 8px 18px rgba(16, 185, 129, 0.18);
}

.switch-toggle-input:checked + .switch-toggle-track::before {
  transform: translateX(var(--switch-thumb-shift));
}

.switch-toggle-input:focus-visible + .switch-toggle-track {
  box-shadow:
    0 0 0 3px rgba(16, 185, 129, 0.2),
    inset 0 1px 2px rgba(15, 23, 42, 0.06);
}

.switch-toggle:hover .switch-toggle-track {
  opacity: 0.92;
}

.switch-toggle.is-disabled .switch-toggle-track,
.switch-toggle-input:disabled + .switch-toggle-track {
  opacity: 0.55;
  cursor: not-allowed;
}

.switch-toggle.is-disabled .switch-toggle-input,
.switch-toggle-input:disabled {
  cursor: not-allowed;
}

:root[data-theme='dark'] .switch-toggle-track {
  background: rgba(8, 12, 22, 0.96);
  border-color: rgba(48, 67, 92, 0.92);
  box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.38);
}

:root[data-theme='dark'] .switch-toggle-track::before {
  background: #9caec4;
  border-color: rgba(0, 240, 255, 0.16);
  box-shadow: 0 4px 10px rgba(0, 0, 0, 0.35);
}

:root[data-theme='dark'] .switch-toggle-input:checked + .switch-toggle-track {
  border-color: var(--color-success, #10b981);
  background: var(--color-success, #10b981);
  box-shadow: 0 10px 22px rgba(108, 180, 157, 0.24);
}
</style>
