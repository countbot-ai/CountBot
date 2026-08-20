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
  background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%);
  border-bottom: 1px solid #fbbf24;
  color: #78350f;
  font-size: 13px;
  line-height: 1.4;
  z-index: 10;
}

:root[data-theme="dark"] .security-warning-banner {
  background: linear-gradient(180deg, rgba(51, 40, 23, 0.96) 0%, rgba(40, 31, 18, 0.98) 100%);
  border-bottom-color: rgba(196, 160, 110, 0.38);
  color: #f0d7a8;
}

.security-warning-icon {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: rgba(245, 158, 11, 0.15);
  color: #d97706;
}

:root[data-theme="dark"] .security-warning-icon {
  background: rgba(196, 160, 110, 0.14);
  color: #d4b07e;
}

.security-warning-text {
  flex: 1;
}

.security-warning-action {
  flex-shrink: 0;
  padding: 5px 14px;
  border: none;
  border-radius: var(--radius-md);
  background: #d97706;
  color: #fff;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
}

.security-warning-action:hover {
  background: #b45309;
}

:root[data-theme="dark"] .security-warning-action {
  background: #c4a06e;
  color: #17110a;
}

:root[data-theme="dark"] .security-warning-action:hover {
  background: #d3b184;
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
  color: #92400e;
  cursor: pointer;
  opacity: 0.6;
  transition: all 0.15s ease;
}

.security-warning-dismiss:hover {
  opacity: 1;
  background: rgba(0, 0, 0, 0.08);
}

:root[data-theme="dark"] .security-warning-dismiss {
  color: #f0d7a8;
}

:root[data-theme="dark"] .security-warning-dismiss:hover {
  background: rgba(255, 255, 255, 0.06);
}
</style>
