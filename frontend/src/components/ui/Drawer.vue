<template>
  <Teleport to="body">
    <Transition name="drawer">
      <div v-if="modelValue" class="drawer-overlay" @click="handleOverlayClick">
        <aside
          ref="panelRef"
          class="drawer-panel"
          :class="[`drawer-${size}`, `drawer-${placement}`]"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="titleId"
          @click.stop
        >
          <header v-if="showHeader" class="drawer-header">
            <h2 :id="titleId" class="drawer-title">
              <slot name="title">{{ title }}</slot>
            </h2>
            <button
              v-if="closable"
              type="button"
              class="drawer-close"
              :aria-label="$t('common.close')"
              @click="close"
            >
              <component :is="XIcon" :size="18" />
            </button>
          </header>

          <div class="drawer-body">
            <slot />
          </div>

          <footer v-if="$slots.footer" class="drawer-footer">
            <slot name="footer" />
          </footer>
        </aside>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { X as XIcon } from 'lucide-vue-next'

interface Props {
  modelValue: boolean
  title?: string
  size?: 'narrow' | 'medium' | 'wide'
  placement?: 'right' | 'left'
  closable?: boolean
  maskClosable?: boolean
  showHeader?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  title: '',
  size: 'medium',
  placement: 'right',
  closable: true,
  // 抽屉里通常承载表单/详情，默认不允许点遮罩关闭，避免误触丢内容
  maskClosable: false,
  showHeader: true
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'close'): void
}>()

const titleId = computed(() => `drawer-title-${Math.random().toString(36).slice(2, 9)}`)
const panelRef = ref<HTMLElement>()

const close = () => {
  emit('update:modelValue', false)
  emit('close')
}

const handleOverlayClick = () => {
  if (props.maskClosable) close()
}

const handleEscape = (event: KeyboardEvent) => {
  if (event.key === 'Escape' && props.modelValue && props.closable) {
    close()
  }
}

watch(
  () => props.modelValue,
  (open) => {
    document.body.style.overflow = open ? 'hidden' : ''
    if (open) {
      document.addEventListener('keydown', handleEscape)
      setTimeout(() => {
        const first = panelRef.value?.querySelector(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        ) as HTMLElement | null
        first?.focus()
      }, 60)
    } else {
      document.removeEventListener('keydown', handleEscape)
    }
  },
  { immediate: true }
)

onBeforeUnmount(() => {
  document.removeEventListener('keydown', handleEscape)
  document.body.style.overflow = ''
})
</script>

<style scoped>
.drawer-overlay {
  position: fixed;
  inset: 0;
  z-index: 9500;
  background: var(--color-bg-overlay);
  backdrop-filter: blur(2px);
  display: flex;
}

.drawer-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  max-width: 100vw;
  background: var(--color-bg-primary);
  box-shadow: var(--shadow-lg);
}

.drawer-right {
  margin-left: auto;
}

.drawer-narrow {
  width: 400px;
}

.drawer-medium {
  width: 600px;
}

.drawer-wide {
  width: 800px;
}

.drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-shrink: 0;
  padding: 16px 20px;
  border-bottom: 1px solid var(--color-border-primary);
}

.drawer-title {
  margin: 0;
  font-size: 15px;
  font-weight: 550;
  color: var(--color-text-primary);
}

.drawer-close {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--color-text-tertiary);
  cursor: pointer;
  transition: background 140ms ease, color 140ms ease;
}

.drawer-close:hover {
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
}

.drawer-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 20px;
  color: var(--color-text-primary);
}

.drawer-footer {
  flex-shrink: 0;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 20px;
  border-top: 1px solid var(--color-border-primary);
  background: var(--color-bg-secondary);
}

.drawer-enter-active,
.drawer-leave-active {
  transition: opacity 200ms cubic-bezier(0.215, 0.61, 0.355, 1);
}

.drawer-enter-active .drawer-panel,
.drawer-leave-active .drawer-panel {
  transition: transform 220ms cubic-bezier(0.215, 0.61, 0.355, 1);
}

.drawer-enter-from,
.drawer-leave-to {
  opacity: 0;
}

.drawer-enter-from .drawer-right,
.drawer-leave-to .drawer-right {
  transform: translateX(24px);
}

.drawer-enter-from .drawer-left,
.drawer-leave-to .drawer-left {
  transform: translateX(-24px);
}

@media (max-width: 860px) {
  .drawer-narrow,
  .drawer-medium,
  .drawer-wide {
    width: 100%;
  }
}
</style>
