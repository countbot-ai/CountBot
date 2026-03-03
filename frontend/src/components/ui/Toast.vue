<template>
  <Teleport to="body">
    <div class="toast-container">
      <TransitionGroup name="toast">
        <div
          v-for="toast in toasts"
          :key="toast.id"
          class="toast"
          :class="[`toast-${toast.type}`, { 'toast-closable': toast.closable }]"
          role="alert"
          :aria-live="toast.type === 'error' ? 'assertive' : 'polite'"
        >
          <div class="toast-icon">
            <component
              :is="getIcon(toast.type)"
              :size="20"
            />
          </div>
          
          <div class="toast-content">
            <div
              v-if="toast.title"
              class="toast-title"
            >
              {{ toast.title }}
            </div>
            <div class="toast-message">
              {{ toast.message }}
            </div>
          </div>
          
          <button
            v-if="toast.closable"
            type="button"
            class="toast-close"
            :aria-label="$t('common.close')"
            @click="removeToast(toast.id)"
          >
            <component
              :is="XIcon"
              :size="16"
            />
          </button>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import {
  CheckCircle as CheckCircleIcon,
  AlertCircle as AlertCircleIcon,
  Info as InfoIcon,
  AlertTriangle as AlertTriangleIcon,
  X as XIcon
} from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'

export type ToastType = 'success' | 'error' | 'warning' | 'info'

export interface ToastOptions {
  id?: string
  type?: ToastType
  title?: string
  message: string
  duration?: number
  closable?: boolean
}

interface Toast extends Required<Omit<ToastOptions, 'title'>> {
  title?: string
}

// const { t: _t } = useI18n()
const toasts = ref<Toast[]>([])
let toastId = 0

const getIcon = (type: ToastType) => {
  const icons = {
    success: CheckCircleIcon,
    error: AlertCircleIcon,
    warning: AlertTriangleIcon,
    info: InfoIcon
  }
  return icons[type]
}

const addToast = (options: ToastOptions) => {
  const id = options.id || `toast-${++toastId}`
  
  const toast: Toast = {
    id,
    type: options.type || 'info',
    title: options.title,
    message: options.message,
    duration: options.duration ?? 3000,
    closable: options.closable ?? true
  }
  
  toasts.value.push(toast)
  
  if (toast.duration > 0) {
    setTimeout(() => {
      removeToast(id)
    }, toast.duration)
  }
  
  return id
}

const removeToast = (id: string) => {
  const index = toasts.value.findIndex(t => t.id === id)
  if (index > -1) {
    toasts.value.splice(index, 1)
  }
}

const clearAll = () => {
  toasts.value = []
}

// Convenience methods
const success = (message: string, options?: Partial<ToastOptions>) => addToast({ ...options, type: 'success', message })

const error = (message: string, options?: Partial<ToastOptions>) => addToast({ ...options, type: 'error', message })

const warning = (message: string, options?: Partial<ToastOptions>) => addToast({ ...options, type: 'warning', message })

const info = (message: string, options?: Partial<ToastOptions>) => addToast({ ...options, type: 'info', message })

defineExpose({
  addToast,
  removeToast,
  clearAll,
  success,
  error,
  warning,
  info
})
</script>

<style scoped>
.toast-container {
  position: fixed;
  top: var(--spacing-lg);
  right: var(--spacing-lg);
  z-index: 10001;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
  pointer-events: none;
}

.toast {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-sm);
  min-width: 300px;
  max-width: 400px;
  padding: var(--spacing-md);
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  pointer-events: auto;
}

.toast-icon {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
}

.toast-success {
  border-left: 3px solid var(--color-success);
}

.toast-success .toast-icon {
  color: var(--color-success);
}

.toast-error {
  border-left: 3px solid var(--color-error);
}

.toast-error .toast-icon {
  color: var(--color-error);
}

.toast-warning {
  border-left: 3px solid var(--color-warning);
}

.toast-warning .toast-icon {
  color: var(--color-warning);
}

.toast-info {
  border-left: 3px solid var(--color-primary);
}

.toast-info .toast-icon {
  color: var(--color-primary);
}

.toast-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.toast-title {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.toast-message {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  line-height: 1.5;
}

.toast-close {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: none;
  background: transparent;
  color: var(--text-tertiary);
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition: all var(--transition-base);
}

.toast-close:hover {
  background: var(--hover-bg);
  color: var(--text-primary);
}

/* Toast transitions */
.toast-enter-active,
.toast-leave-active {
  transition: all 0.3s ease;
}

.toast-enter-from {
  opacity: 0;
  transform: translateX(100%);
}

.toast-leave-to {
  opacity: 0;
  transform: translateX(100%) scale(0.8);
}

.toast-move {
  transition: transform 0.3s ease;
}

/* Responsive */
@media (max-width: 768px) {
  .toast-container {
    top: var(--spacing-sm);
    right: var(--spacing-sm);
    left: var(--spacing-sm);
  }
  
  .toast {
    min-width: auto;
    max-width: none;
  }
}
</style>
