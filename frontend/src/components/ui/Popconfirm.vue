<template>
  <span ref="rootRef" class="popconfirm">
    <span class="popconfirm-trigger" @click="toggle">
      <slot />
    </span>

    <Transition name="popconfirm">
      <div
        v-if="isOpen"
        class="popconfirm-panel"
        :class="`popconfirm-panel--${placement}`"
        role="dialog"
        @click.stop
      >
        <p class="popconfirm-title">
          <slot name="title">{{ title }}</slot>
        </p>
        <p v-if="message || $slots.message" class="popconfirm-message">
          <slot name="message">{{ message }}</slot>
        </p>
        <div class="popconfirm-actions">
          <Button variant="ghost" size="sm" :disabled="loading" @click="cancel">
            {{ cancelText || $t('common.cancel') }}
          </Button>
          <Button
            :variant="confirmVariant"
            size="sm"
            :loading="loading"
            @click="confirm"
          >
            {{ confirmText || $t('common.confirm') }}
          </Button>
        </div>
      </div>
    </Transition>
  </span>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import Button from './Button.vue'

interface Props {
  title?: string
  message?: string
  confirmText?: string
  cancelText?: string
  confirmVariant?: 'primary' | 'danger' | 'warning'
  placement?: 'top' | 'bottom'
  disabled?: boolean
  loading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  title: '',
  message: '',
  confirmVariant: 'danger',
  placement: 'top',
  disabled: false,
  loading: false
})

const emit = defineEmits<{
  (e: 'confirm'): void
  (e: 'cancel'): void
  (e: 'update:open', value: boolean): void
}>()

const isOpen = ref(false)
const rootRef = ref<HTMLElement>()

const setOpen = (value: boolean) => {
  isOpen.value = value
  emit('update:open', value)
}

const toggle = () => {
  if (props.disabled) return
  setOpen(!isOpen.value)
}

const confirm = () => {
  if (props.loading) return
  emit('confirm')
  setOpen(false)
}

const cancel = () => {
  if (props.loading) return
  emit('cancel')
  setOpen(false)
}

// 点外部关闭：轻量确认不阻断页面，符合「非模态」定位
const handleOutsideClick = (event: MouseEvent) => {
  if (!isOpen.value) return
  if (rootRef.value && !rootRef.value.contains(event.target as Node)) {
    setOpen(false)
  }
}

const handleEscape = (event: KeyboardEvent) => {
  if (event.key === 'Escape' && isOpen.value && !props.loading) {
    setOpen(false)
  }
}

watch(isOpen, (open) => {
  if (open) {
    document.addEventListener('click', handleOutsideClick)
    document.addEventListener('keydown', handleEscape)
  } else {
    document.removeEventListener('click', handleOutsideClick)
    document.removeEventListener('keydown', handleEscape)
  }
})

onBeforeUnmount(() => {
  document.removeEventListener('click', handleOutsideClick)
  document.removeEventListener('keydown', handleEscape)
})
</script>

<style scoped>
.popconfirm {
  position: relative;
  display: inline-block;
}

.popconfirm-trigger {
  display: inline-flex;
}

.popconfirm-panel {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  z-index: 9000;
  width: 240px;
  padding: 12px;
  border: 1px solid var(--color-border-primary);
  border-radius: 8px;
  background: var(--color-bg-primary);
  box-shadow: var(--shadow-lg);
  text-align: left;
}

.popconfirm-panel--top {
  bottom: calc(100% + 8px);
}

.popconfirm-panel--bottom {
  top: calc(100% + 8px);
}

.popconfirm-title {
  margin: 0;
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-primary);
  line-height: 1.5;
}

.popconfirm-message {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--color-text-secondary);
  line-height: 1.6;
  text-wrap: pretty;
}

.popconfirm-actions {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
  margin-top: 10px;
}

.popconfirm-enter-active,
.popconfirm-leave-active {
  transition: opacity 140ms cubic-bezier(0.215, 0.61, 0.355, 1),
    transform 140ms cubic-bezier(0.215, 0.61, 0.355, 1);
}

.popconfirm-enter-from,
.popconfirm-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(4px);
}
</style>
