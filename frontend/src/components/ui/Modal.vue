<template>
  <Teleport to="body">
    <Transition name="modal">
      <div
        v-if="modelValue"
        class="modal-overlay"
        :class="{ 'is-closing': isClosing }"
        @click="handleOverlayClick"
      >
        <div
          ref="modalRef"
          class="modal-container"
          :class="[`modal-${size}`, { 'is-closing': isClosing }]"
          role="dialog"
          :aria-modal="true"
          :aria-labelledby="titleId"
          :aria-describedby="descriptionId"
          @click.stop
        >
          <div
            v-if="showHeader"
            class="modal-header"
          >
            <h2
              :id="titleId"
              class="modal-title"
            >
              <slot name="title">
                {{ title }}
              </slot>
            </h2>
            
            <button
              v-if="closable"
              type="button"
              class="modal-close"
              :aria-label="$t('common.close')"
              @click="handleClose"
            >
              <component
                :is="XIcon"
                :size="20"
              />
            </button>
          </div>
          
          <div
            :id="descriptionId"
            class="modal-body"
          >
            <slot />
          </div>
          
          <div
            v-if="$slots.footer || showFooter"
            class="modal-footer"
          >
            <slot name="footer">
              <Button
                variant="ghost"
                @click="handleCancel"
              >
                {{ cancelText || $t('common.cancel') }}
              </Button>
              <Button
                variant="primary"
                :loading="confirmLoading"
                @click="handleConfirm"
              >
                {{ confirmText || $t('common.confirm') }}
              </Button>
            </slot>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { X as XIcon } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import Button from './Button.vue'

interface Props {
  modelValue: boolean
  title?: string
  size?: 'small' | 'medium' | 'large' | 'full'
  closable?: boolean
  maskClosable?: boolean
  showHeader?: boolean
  showFooter?: boolean
  confirmText?: string
  cancelText?: string
  confirmLoading?: boolean
}

interface Emits {
  (e: 'update:modelValue', value: boolean): void
  (e: 'confirm'): void
  (e: 'cancel'): void
  (e: 'close'): void
}

const props = withDefaults(defineProps<Props>(), {
  title: '',
  size: 'medium',
  closable: true,
  maskClosable: true,
  showHeader: true,
  showFooter: false,
  confirmLoading: false
})

const emit = defineEmits<Emits>()
// const { t: _t } = useI18n()

const modalRef = ref<HTMLElement>()
const isClosing = ref(false)
const titleId = computed(() => `modal-title-${Math.random().toString(36).substr(2, 9)}`)
const descriptionId = computed(() => `modal-desc-${Math.random().toString(36).substr(2, 9)}`)

const handleClose = () => {
  isClosing.value = true
  setTimeout(() => {
    emit('update:modelValue', false)
    emit('close')
    isClosing.value = false
  }, 200)
}

const handleOverlayClick = () => {
  if (props.maskClosable) {
    handleClose()
  }
}

const handleConfirm = () => {
  emit('confirm')
}

const handleCancel = () => {
  emit('cancel')
  handleClose()
}

const handleEscape = (event: KeyboardEvent) => {
  if (event.key === 'Escape' && props.modelValue && props.closable) {
    handleClose()
  }
}

const trapFocus = (event: KeyboardEvent) => {
  if (event.key !== 'Tab' || !props.modelValue) return
  
  const focusableElements = modalRef.value?.querySelectorAll(
    'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
  )
  
  if (!focusableElements || focusableElements.length === 0) return
  
  const firstElement = focusableElements[0] as HTMLElement
  const lastElement = focusableElements[focusableElements.length - 1] as HTMLElement
  
  if (event.shiftKey) {
    if (document.activeElement === firstElement) {
      event.preventDefault()
      lastElement.focus()
    }
  } else {
    if (document.activeElement === lastElement) {
      event.preventDefault()
      firstElement.focus()
    }
  }
}

watch(() => props.modelValue, (newValue) => {
  if (newValue) {
    document.body.style.overflow = 'hidden'
    setTimeout(() => {
      const firstFocusable = modalRef.value?.querySelector(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      ) as HTMLElement
      firstFocusable?.focus()
    }, 100)
  } else {
    document.body.style.overflow = ''
  }
})

onMounted(() => {
  document.addEventListener('keydown', handleEscape)
  document.addEventListener('keydown', trapFocus)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', handleEscape)
  document.removeEventListener('keydown', trapFocus)
  document.body.style.overflow = ''
})
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10000;
  padding: var(--spacing-lg);
  overflow-y: auto;
}

.modal-container {
  position: relative;
  background: var(--bg-primary, #ffffff);
  border-radius: var(--radius-lg);
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.3), 0 10px 10px -5px rgba(0, 0, 0, 0.2);
  display: flex;
  flex-direction: column;
  max-height: calc(100vh - var(--spacing-3xl));
  width: 100%;
  z-index: 10001;
}

.modal-small {
  max-width: 400px;
}

.modal-medium {
  max-width: 600px;
}

.modal-large {
  max-width: 900px;
}

.modal-full {
  max-width: calc(100vw - var(--spacing-3xl));
  max-height: calc(100vh - var(--spacing-3xl));
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-lg);
  border-bottom: 1px solid var(--border-color, #e5e7eb);
  background: var(--bg-primary, #ffffff);
  border-radius: var(--radius-lg) var(--radius-lg) 0 0;
}

.modal-title {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary, #1f2937);
  margin: 0;
}

.modal-close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--text-secondary, #6b7280);
  cursor: pointer;
  transition: all var(--transition-base);
}

.modal-close:hover {
  background: var(--hover-bg, #f3f4f6);
  color: var(--text-primary, #1f2937);
  border-color: var(--color-error, #ef4444);
}

.modal-body {
  flex: 1;
  padding: var(--spacing-lg);
  overflow-y: auto;
  color: var(--text-primary, #1f2937);
  background: var(--bg-primary, #ffffff);
}

.modal-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--spacing-sm);
  padding: var(--spacing-lg);
  border-top: 1px solid var(--border-color, #e5e7eb);
  background: var(--bg-secondary, #f9fafb);
  border-radius: 0 0 var(--radius-lg) var(--radius-lg);
}

/* 深色模式 */
:root[data-theme="dark"] .modal-overlay {
  background: rgba(0, 0, 0, 0.8);
}

:root[data-theme="dark"] .modal-container {
  background: var(--bg-primary, #1f2937);
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5), 0 10px 10px -5px rgba(0, 0, 0, 0.4);
}

:root[data-theme="dark"] .modal-header {
  background: var(--bg-primary, #1f2937);
}

:root[data-theme="dark"] .modal-body {
  background: var(--bg-primary, #1f2937);
}

:root[data-theme="dark"] .modal-footer {
  background: var(--bg-secondary, #111827);
}

/* Modal transitions */
.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.2s ease;
}

.modal-enter-active .modal-container,
.modal-leave-active .modal-container {
  transition: transform 0.2s ease, opacity 0.2s ease;
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}

.modal-enter-from .modal-container,
.modal-leave-to .modal-container {
  transform: scale(0.95);
  opacity: 0;
}

/* Closing animation */
.modal-overlay.is-closing {
  animation: fadeOut 0.2s ease;
}

.modal-container.is-closing {
  animation: scaleOut 0.2s ease;
}

@keyframes fadeOut {
  from {
    opacity: 1;
  }
  to {
    opacity: 0;
  }
}

@keyframes scaleOut {
  from {
    transform: scale(1);
    opacity: 1;
  }
  to {
    transform: scale(0.95);
    opacity: 0;
  }
}

/* Scrollbar styling for modal body */
.modal-body::-webkit-scrollbar {
  width: 6px;
}

.modal-body::-webkit-scrollbar-track {
  background: transparent;
}

.modal-body::-webkit-scrollbar-thumb {
  background: var(--border-color, #e5e7eb);
  border-radius: var(--radius-sm);
}

.modal-body::-webkit-scrollbar-thumb:hover {
  background: var(--text-tertiary, #9ca3af);
}
</style>
