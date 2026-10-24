<template>
  <div :class="['loading-state', `loading-state--${size}`]">
    <Spinner
      v-if="type === 'spinner'"
      :size="size"
    />
    <div
      v-else-if="type === 'skeleton'"
      class="skeleton-container"
    >
      <slot name="skeleton">
        <Skeleton
          v-for="i in lines"
          :key="i"
          :width="`${100 - Math.random() * 20}%`"
        />
      </slot>
    </div>
    <div
      v-if="message"
      class="loading-message"
    >
      {{ message }}
    </div>
  </div>
</template>

<script setup lang="ts">
import Spinner from './Spinner.vue'
import Skeleton from './Skeleton.vue'

interface Props {
  type?: 'spinner' | 'skeleton'
  size?: 'small' | 'medium' | 'large'
  message?: string
  lines?: number
}

withDefaults(defineProps<Props>(), {
  type: 'spinner',
  size: 'medium',
  lines: 3
})
</script>

<style scoped>
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-4);
}

.loading-state--small {
  padding: var(--spacing-2);
}

.loading-state--large {
  padding: var(--spacing-8);
}

.skeleton-container {
  width: 100%;
  max-width: 600px;
}

.loading-message {
  margin-top: var(--spacing-3);
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  text-align: center;
}
</style>
