<template>
  <div
    class="spinner-wrapper"
    :class="{ 'spinner-fullscreen': fullscreen }"
  >
    <div
      class="spinner"
      :class="[`spinner-${size}`, `spinner-${variant}`]"
      role="status"
      :aria-label="ariaLabel || $t('common.loading')"
    >
      <svg
        class="spinner-svg"
        viewBox="0 0 50 50"
      >
        <circle
          class="spinner-track"
          cx="25"
          cy="25"
          r="20"
          fill="none"
          :stroke-width="strokeWidth"
        />
        <circle
          class="spinner-path"
          cx="25"
          cy="25"
          r="20"
          fill="none"
          :stroke-width="strokeWidth"
        />
      </svg>
    </div>
    
    <div
      v-if="text"
      class="spinner-text"
      :class="`spinner-text-${size}`"
    >
      {{ text }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

type Size = 'small' | 'medium' | 'large'
type Variant = 'primary' | 'secondary' | 'white'

interface Props {
  size?: Size
  variant?: Variant
  text?: string
  fullscreen?: boolean
  ariaLabel?: string
}

const props = withDefaults(defineProps<Props>(), {
  size: 'medium',
  variant: 'primary',
  text: '',
  fullscreen: false
})

// const { t: _t } = useI18n()

const strokeWidth = computed(() => {
  const widths = {
    small: 4,
    medium: 3,
    large: 2.5
  }
  return widths[props.size]
})
</script>

<style scoped>
.spinner-wrapper {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-sm);
}

.spinner-wrapper.spinner-fullscreen {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.9);
  z-index: 9998;
}

[data-theme='dark'] .spinner-wrapper.spinner-fullscreen {
  background: rgba(15, 23, 42, 0.9);
}

.spinner {
  display: inline-block;
  animation: rotate 1.5s linear infinite;
}

.spinner-small {
  width: 16px;
  height: 16px;
}

.spinner-medium {
  width: 24px;
  height: 24px;
}

.spinner-large {
  width: 40px;
  height: 40px;
}

.spinner-svg {
  width: 100%;
  height: 100%;
}

.spinner-track {
  stroke: var(--border-color);
  opacity: 0.3;
}

.spinner-path {
  stroke-dasharray: 90, 150;
  stroke-dashoffset: 0;
  stroke-linecap: round;
  animation: dash 1.5s ease-in-out infinite;
}

.spinner-primary .spinner-path {
  stroke: var(--color-primary);
}

.spinner-secondary .spinner-path {
  stroke: var(--text-secondary);
}

.spinner-white .spinner-path {
  stroke: #ffffff;
}

.spinner-text {
  color: var(--text-secondary);
  font-weight: var(--font-weight-medium);
}

.spinner-text-small {
  font-size: var(--font-size-xs);
}

.spinner-text-medium {
  font-size: var(--font-size-sm);
}

.spinner-text-large {
  font-size: var(--font-size-base);
}

@keyframes rotate {
  100% {
    transform: rotate(360deg);
  }
}

@keyframes dash {
  0% {
    stroke-dasharray: 1, 150;
    stroke-dashoffset: 0;
  }
  50% {
    stroke-dasharray: 90, 150;
    stroke-dashoffset: -35;
  }
  100% {
    stroke-dasharray: 90, 150;
    stroke-dashoffset: -124;
  }
}
</style>
