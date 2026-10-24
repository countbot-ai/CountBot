<template>
  <div v-if="visible" class="security-warning-banner">
    <div class="security-warning-icon">
      <component :is="ShieldAlertIcon" :size="16" />
    </div>
    <span class="security-warning-text">{{ $t('security.remoteWarning') }}</span>
    <button
      class="security-warning-action"
      @click="$emit('setup-password')"
    >
      {{ $t('security.setupPassword') }}
    </button>
    <button
      class="security-warning-dismiss"
      :title="$t('common.close')"
      @click="$emit('dismiss')"
    >
      <component :is="XIcon" :size="14" />
    </button>
  </div>
</template>

<script setup lang="ts">
import { ShieldAlert as ShieldAlertIcon, X as XIcon } from 'lucide-vue-next'

interface Props {
  visible: boolean
}

defineProps<Props>()

interface Emits {
  (e: 'setup-password'): void
  (e: 'dismiss'): void
}

defineEmits<Emits>()
</script>

<style scoped>
.security-warning-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px var(--spacing-lg);
  background: linear-gradient(135deg, var(--color-warning-light) 0%, var(--color-warning-light) 100%);
  border-bottom: 1px solid var(--color-warning);
  color: var(--color-warning);
  font-size: 13px;
  line-height: 1.4;
  z-index: 10;
}



.security-warning-icon {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--color-warning-light);
  color: var(--color-warning);
}



.security-warning-text {
  flex: 1;
}

.security-warning-action {
  flex-shrink: 0;
  padding: 5px 14px;
  border: none;
  border-radius: var(--radius-md);
  background: var(--color-warning);
  color: var(--color-text-inverse);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
}

.security-warning-action:hover {
  background: var(--color-warning);
}





.security-warning-dismiss {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-warning);
  cursor: pointer;
  opacity: 0.6;
  transition: all 0.15s ease;
}

.security-warning-dismiss:hover {
  opacity: 1;
  background: var(--color-bg-overlay);
}




</style>
