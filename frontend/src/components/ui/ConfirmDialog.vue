<template>
  <Modal
    v-model="internalShow"
    :title="title"
    :size="size"
    :mask-closable="false"
    :closable="!loading"
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
          :disabled="loading"
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

// 使用计算属性来同步 show prop 和 Modal 的 v-model
const internalShow = computed({
  get: () => props.show,
  set: (value: boolean) => {
    // loading 期间禁止任何关闭路径
    if (!value && !props.loading) {
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
  if (props.loading) return
  emit('cancel')
  emit('close')
}
</script>

<style scoped>
.confirm-dialog {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-4);
  padding: var(--spacing-4, 1rem) 0;
}

.confirm-dialog-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 64px;
  height: 64px;
  border-radius: 50%;
  background: var(--color-bg-secondary);
}

.confirm-dialog-icon--danger {
  color: var(--color-error);
  background: var(--color-error-bg);
}

.confirm-dialog-icon--warning {
  color: var(--color-warning);
  background: var(--color-warning-bg);
}

.confirm-dialog-icon--info {
  color: var(--color-info);
  background: var(--color-info-bg);
}

.confirm-dialog-icon--success {
  color: var(--color-success);
  background: var(--color-success-bg);
}

.confirm-dialog-content {
  text-align: center;
  max-width: 400px;
}

.confirm-dialog-message {
  margin: 0;
  font-size: var(--font-size-base);
  line-height: 1.6;
  color: var(--color-text-primary);
}

.confirm-dialog-actions {
  display: flex;
  gap: var(--spacing-2);
  justify-content: flex-end;
}

/* 深色模式 */









</style>
