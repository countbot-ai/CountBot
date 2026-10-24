<template>
  <div :class="['empty-state', `empty-state--${size}`]">
    <div
      v-if="icon || $slots.icon"
      class="empty-state-icon"
    >
      <slot name="icon">
        <Icon
          v-if="icon"
          :name="icon"
          :size="iconSize"
        />
      </slot>
    </div>
    
    <div class="empty-state-content">
      <h3
        v-if="title"
        class="empty-state-title"
      >
        {{ title }}
      </h3>
      
      <p
        v-if="description"
        class="empty-state-description"
      >
        {{ description }}
      </p>
      
      <slot name="description" />
    </div>
    
    <div
      v-if="$slots.action || action"
      class="empty-state-action"
    >
      <slot name="action">
        <Button
          v-if="action"
          :variant="actionVariant"
          @click="$emit('action')"
        >
          {{ action }}
        </Button>
      </slot>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Icon from './Icon.vue'
import Button from './Button.vue'

interface Props {
  icon?: string
  title?: string
  description?: string
  action?: string
  actionVariant?: 'primary' | 'secondary' | 'outline'
  size?: 'small' | 'medium' | 'large'
}

const props = withDefaults(defineProps<Props>(), {
  actionVariant: 'primary',
  size: 'medium'
})

defineEmits<{
  action: []
}>()

const iconSize = computed(() => {
  const sizes = {
    small: 32,
    medium: 48,
    large: 64
  }
  return sizes[props.size]
})
</script>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: var(--spacing-8);
  color: var(--color-text-secondary);
}

.empty-state--small {
  padding: var(--spacing-4);
}

.empty-state--large {
  padding: var(--spacing-12);
}

.empty-state-icon {
  margin-bottom: var(--spacing-4);
  color: var(--color-text-tertiary);
  opacity: 0.6;
}

.empty-state--small .empty-state-icon {
  margin-bottom: var(--spacing-2);
}

.empty-state--large .empty-state-icon {
  margin-bottom: var(--spacing-6);
}

.empty-state-content {
  max-width: 400px;
}

.empty-state-title {
  margin: 0 0 var(--spacing-2, 0.5rem);
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.empty-state--small .empty-state-title {
  font-size: var(--font-size-base);
}

.empty-state--large .empty-state-title {
  font-size: var(--font-size-xl);
}

.empty-state-description {
  margin: 0;
  font-size: var(--font-size-sm);
  line-height: 1.6;
  color: var(--color-text-secondary);
}

.empty-state--small .empty-state-description {
  font-size: var(--font-size-xs);
}

.empty-state-action {
  margin-top: var(--spacing-4);
}

.empty-state--small .empty-state-action {
  margin-top: var(--spacing-2);
}

.empty-state--large .empty-state-action {
  margin-top: var(--spacing-6);
}
</style>
