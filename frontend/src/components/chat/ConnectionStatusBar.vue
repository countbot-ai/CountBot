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
        正在重连...（第 {{ reconnectAttemptsDisplay }}/10 次）
      </span>
      <span v-else class="status-bar-content">
        连接已断开
        <button class="status-bar-action" @click="$emit('reconnect')">立即重连</button>
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
  background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%);
  border-bottom: 1px solid #fbbf24;
  color: #92400e;
}

:root[data-theme="dark"] .status-reconnecting {
  background: linear-gradient(180deg, rgba(51, 40, 23, 0.96) 0%, rgba(40, 31, 18, 0.98) 100%);
  border-bottom-color: rgba(196, 160, 110, 0.42);
  color: #f0d7a8;
}

.status-disconnected {
  background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%);
  border-bottom: 1px solid #fca5a5;
  color: #991b1b;
}

:root[data-theme="dark"] .status-disconnected {
  background: linear-gradient(180deg, rgba(49, 24, 29, 0.96) 0%, rgba(38, 20, 24, 0.98) 100%);
  border-bottom-color: rgba(207, 134, 150, 0.38);
  color: #e6b6c1;
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
  border: 2px solid rgba(146, 64, 14, 0.3);
  border-top-color: #d97706;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

:root[data-theme="dark"] .status-spinner {
  border-color: rgba(240, 215, 168, 0.24);
  border-top-color: #c4a06e;
}

.status-bar-action {
  padding: 2px 12px;
  border: 1px solid currentColor;
  border-radius: var(--radius-md, 8px);
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
  background: rgba(0, 0, 0, 0.05);
}

:root[data-theme="dark"] .status-bar-action:hover {
  background: rgba(255, 255, 255, 0.06);
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
