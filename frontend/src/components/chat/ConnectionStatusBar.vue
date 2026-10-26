<template>
  <transition name="status-bar">
    <div
      v-if="!isConnected || isConnecting || reconnectingVisible"
      class="connection-status-bar"
      :class="{
        'status-reconnecting': isConnecting || reconnectingVisible,
        'status-disconnected': !isConnected && !isConnecting && !reconnectingVisible
      }"
    >
      <span v-if="isConnecting || reconnectingVisible" class="status-bar-content">
        <span class="status-spinner" />
        {{ $t('chat.connectionStatus.reconnecting', { attempt: reconnectAttemptsDisplay, max: 10 }) }}
      </span>
      <span v-else class="status-bar-content">
        {{ $t('chat.connectionStatus.disconnected') }}
        <button class="status-bar-action" @click="$emit('reconnect')">{{ $t('chat.connectionStatus.reconnectNow') }}</button>
      </span>
    </div>
  </transition>
</template>

<script setup lang="ts">
interface Props {
  isConnected: boolean
  isConnecting: boolean
  reconnectingVisible: boolean
  reconnectAttemptsDisplay: number
}

defineProps<Props>()

interface Emits {
  (e: 'reconnect'): void
}

defineEmits<Emits>()
</script>

<style scoped>
.connection-status-bar {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 6px 16px;
  font-size: 13px;
  font-weight: 500;
  z-index: 10;
  transition: all 0.3s ease;
}

.status-reconnecting {
  background: linear-gradient(135deg, var(--color-warning-light) 0%, var(--color-warning-light) 100%);
  border-bottom: 1px solid var(--color-warning);
  color: var(--color-warning);
}



.status-disconnected {
  background: linear-gradient(135deg, var(--color-error-light) 0%, var(--color-error-light) 100%);
  border-bottom: 1px solid var(--color-error);
  color: var(--color-error);
}



.status-bar-content {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid var(--color-border-primary);
  border-top-color: var(--color-warning);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}



.status-bar-action {
  padding: 2px 12px;
  border: 1px solid currentColor;
  border-radius: var(--radius-md);
  background: transparent;
  color: inherit;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  opacity: 0.8;
}

.status-bar-action:hover {
  opacity: 1;
  background: var(--color-bg-overlay);
}



.status-bar-enter-active,
.status-bar-leave-active {
  transition: all 0.3s ease;
  max-height: 40px;
  overflow: hidden;
}

.status-bar-enter-from,
.status-bar-leave-to {
  max-height: 0;
  padding-top: 0;
  padding-bottom: 0;
  opacity: 0;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>
