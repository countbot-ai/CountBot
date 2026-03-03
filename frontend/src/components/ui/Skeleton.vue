<template>
  <div
    :class="[
      'skeleton',
      `skeleton--${variant}`,
      { 'skeleton--animated': animated }
    ]"
    :style="customStyle"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  variant?: 'text' | 'circular' | 'rectangular' | 'rounded'
  width?: string | number
  height?: string | number
  animated?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'text',
  animated: true
})

const customStyle = computed(() => {
  const style: Record<string, string> = {}
  
  if (props.width) {
    style.width = typeof props.width === 'number' ? `${props.width}px` : props.width
  }
  
  if (props.height) {
    style.height = typeof props.height === 'number' ? `${props.height}px` : props.height
  }
  
  return style
})
</script>

<style scoped>
.skeleton {
  background: var(--color-skeleton-base, #e0e0e0);
  display: block;
}

.skeleton--animated {
  animation: skeleton-pulse 1.5s ease-in-out infinite;
}

@keyframes skeleton-pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}

.skeleton--text {
  height: 1em;
  border-radius: 4px;
  margin-bottom: 0.5em;
}

.skeleton--circular {
  border-radius: 50%;
}

.skeleton--rectangular {
  border-radius: 0;
}

.skeleton--rounded {
  border-radius: 8px;
}

/* 深色模式 */
:root[data-theme="dark"] .skeleton {
  background: var(--color-skeleton-base-dark, #2a2a2a);
}
</style>
