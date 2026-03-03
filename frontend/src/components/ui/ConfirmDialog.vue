<template>
  <Modal
    v-model="internalShow"
    :title="title"
    :size="size"
    @update:model-value="handleModalUpdate"
  >
    <div class="confirm-dialog">
      <div
        v-if="icon || type"
        class="confirm-dialog-icon"
        :class="`confirm-dialog-icon--${type}`"
      >
        <Icon
          v-if="icon"
          :name="icon"
          :size="48"
        />
        <component
          :is="getTypeIcon()"
          v-else
          :size="48"
        />
      </div>
      
      <div class="confirm-dialog-content">
        <p
          v-if="message"
          class="confirm-dialog-message"
        >
          {{ message }}
        </p>
        <slot />
      </div>
    </div>
    
    <template #footer>
      <div class="confirm-dialog-actions">
        <Button
          variant="outline"
          @click="handleCancel"
        >
          {{ cancelText || $t('common.cancel') }}
        </Button>
        <Button
          :variant="confirmVariant"
          :loading="loading"
          @click="handleConfirm"
        >
          {{ confirmText || $t('common.confirm') }}
        </Button>
      </div>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { AlertTriangle, AlertCircle, Info, CheckCircle } from 'lucide-vue-next'
import Modal from './Modal.vue'
import Button from './Button.vue'
import Icon from './Icon.vue'
import { useI18n } from 'vue-i18n'

interface Props {
  show: boolean
  title?: string
  message?: string
  icon?: string
  type?: 'danger' | 'warning' | 'info' | 'success'
  confirmText?: string
  cancelText?: string
  confirmVariant?: 'primary' | 'danger' | 'warning'
  loading?: boolean
  size?: 'small' | 'medium' | 'large'
}

const props = withDefaults(defineProps<Props>(), {
  type: 'warning',
  confirmVariant: 'primary',
  size: 'small'
})

const emit = defineEmits<{
  confirm: []
  cancel: []
  close: []
}>()

// const { t: _t } = useI18n()

// 使用计算属性来同步 show prop 和 Modal 的 v-model
const internalShow = computed({
  get: () => props.show,
  set: (value: boolean) => {
    if (!value) {
      handleCancel()
    }
  }
})

const getTypeIcon = () => {
  const icons = {
    danger: AlertCircle,
    warning: AlertTriangle,
    info: Info,
    success: CheckCircle
  }
  return icons[props.type || 'warning']
}

const handleConfirm = () => {
  emit('confirm')
}

const handleCancel = () => {
  emit('cancel')
  emit('close')
}

const handleModalUpdate = (value: boolean) => {
  if (!value) {
    handleCancel()
  }
}
</script>

<style scoped>
.confirm-dialog {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-4, 1rem);
  padding: var(--spacing-4, 1rem) 0;
}

.confirm-dialog-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 64px;
  height: 64px;
  border-radius: 50%;
  background: var(--color-bg-secondary, #f5f5f5);
}

.confirm-dialog-icon--danger {
  color: var(--color-error, #ef4444);
  background: var(--color-error-bg, #fee);
}

.confirm-dialog-icon--warning {
  color: var(--color-warning, #f59e0b);
  background: var(--color-warning-bg, #fffbeb);
}

.confirm-dialog-icon--info {
  color: var(--color-info, #3b82f6);
  background: var(--color-info-bg, #eff6ff);
}

.confirm-dialog-icon--success {
  color: var(--color-success, #10b981);
  background: var(--color-success-bg, #f0fdf4);
}

.confirm-dialog-content {
  text-align: center;
  max-width: 400px;
}

.confirm-dialog-message {
  margin: 0;
  font-size: var(--font-size-base, 1rem);
  line-height: 1.6;
  color: var(--color-text-primary, #333);
}

.confirm-dialog-actions {
  display: flex;
  gap: var(--spacing-2, 0.5rem);
  justify-content: flex-end;
}

/* 深色模式 */
:root[data-theme="dark"] .confirm-dialog-icon {
  background: var(--color-bg-tertiary, #2a2a2a);
}

:root[data-theme="dark"] .confirm-dialog-icon--danger {
  background: rgba(239, 68, 68, 0.1);
}

:root[data-theme="dark"] .confirm-dialog-icon--warning {
  background: rgba(245, 158, 11, 0.1);
}

:root[data-theme="dark"] .confirm-dialog-icon--info {
  background: rgba(59, 130, 246, 0.1);
}

:root[data-theme="dark"] .confirm-dialog-icon--success {
  background: rgba(16, 185, 129, 0.1);
}
</style>
