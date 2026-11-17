<template>
  <div
    ref="triggerRef"
    class="tooltip-wrapper"
    @mouseenter="handleMouseEnter"
    @mouseleave="handleMouseLeave"
    @focusin="handleFocus"
    @focusout="handleBlur"
  >
    <slot />

    <Teleport to="body">
      <div
        v-if="isVisible && (content || $slots.content)"
        ref="tooltipRef"
        class="tooltip"
        :class="[`tooltip-${placement}`, `tooltip-${theme}`]"
        :style="tooltipStyle"
        role="tooltip"
      >
        <div class="tooltip-content">
          <slot name="content">
            {{ content }}
          </slot>
        </div>
        <div class="tooltip-arrow" />
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onBeforeUnmount, nextTick } from 'vue'

type Placement = 'top' | 'bottom' | 'left' | 'right'
type Theme = 'dark' | 'light'

interface Props {
  content?: string
  placement?: Placement
  theme?: Theme
  delay?: number
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  content: '',
  placement: 'top',
  theme: 'dark',
  delay: 200,
  disabled: false
})

const triggerRef = ref<HTMLElement>()
const tooltipRef = ref<HTMLElement>()
const isVisible = ref(false)
const tooltipStyle = ref({})
let showTimer: ReturnType<typeof setTimeout> | null = null
let hideTimer: ReturnType<typeof setTimeout> | null = null

const calculatePosition = () => {
  if (!triggerRef.value || !tooltipRef.value) return
  
  const triggerRect = triggerRef.value.getBoundingClientRect()
  const tooltipRect = tooltipRef.value.getBoundingClientRect()
  const gap = 8
  
  let top = 0
  let left = 0
  
  switch (props.placement) {
    case 'top':
      top = triggerRect.top - tooltipRect.height - gap
      left = triggerRect.left + (triggerRect.width - tooltipRect.width) / 2
      break
      
    case 'bottom':
      top = triggerRect.bottom + gap
      left = triggerRect.left + (triggerRect.width - tooltipRect.width) / 2
      break
      
    case 'left':
      top = triggerRect.top + (triggerRect.height - tooltipRect.height) / 2
      left = triggerRect.left - tooltipRect.width - gap
      break
      
    case 'right':
      top = triggerRect.top + (triggerRect.height - tooltipRect.height) / 2
      left = triggerRect.right + gap
      break
  }
  
  // 保证提示框不超出视口
  const padding = 8
  top = Math.max(padding, Math.min(top, window.innerHeight - tooltipRect.height - padding))
  left = Math.max(padding, Math.min(left, window.innerWidth - tooltipRect.width - padding))
  
  tooltipStyle.value = {
    top: `${top}px`,
    left: `${left}px`
  }
}

const show = () => {
  if (props.disabled) return
  
  if (hideTimer) {
    clearTimeout(hideTimer)
    hideTimer = null
  }
  
  showTimer = setTimeout(() => {
    isVisible.value = true
    nextTick(calculatePosition)
  }, props.delay)
}

const hide = () => {
  if (showTimer) {
    clearTimeout(showTimer)
    showTimer = null
  }
  
  hideTimer = setTimeout(() => {
    isVisible.value = false
  }, 100)
}

const handleMouseEnter = () => {
  show()
}

const handleMouseLeave = () => {
  hide()
}

const handleFocus = () => {
  show()
}

const handleBlur = () => {
  hide()
}

const handleScroll = () => {
  if (isVisible.value) {
    calculatePosition()
  }
}

const handleResize = () => {
  if (isVisible.value) {
    calculatePosition()
  }
}

watch(isVisible, (newValue) => {
  if (newValue) {
    window.addEventListener('scroll', handleScroll, true)
    window.addEventListener('resize', handleResize)
  } else {
    window.removeEventListener('scroll', handleScroll, true)
    window.removeEventListener('resize', handleResize)
  }
})

onBeforeUnmount(() => {
  if (showTimer) clearTimeout(showTimer)
  if (hideTimer) clearTimeout(hideTimer)
  window.removeEventListener('scroll', handleScroll, true)
  window.removeEventListener('resize', handleResize)
})
</script>

<style scoped>
.tooltip-wrapper {
  display: inline-block;
}

.tooltip {
  position: fixed;
  z-index: 10000;
  max-width: 320px;
  padding: 8px 10px;
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-md);
  background: var(--color-bg-elevated);
  color: var(--color-text-primary);
  box-shadow: var(--shadow-lg);
  font-size: 12px;
  line-height: 1.5;
  word-wrap: break-word;
  pointer-events: none;
}

.tooltip-dark,
.tooltip-light {
  background: var(--color-bg-elevated);
  color: var(--color-text-primary);
}

.tooltip-content {
  position: relative;
  z-index: 1;
}

.tooltip-arrow {
  position: absolute;
  width: 8px;
  height: 8px;
  transform: rotate(45deg);
}

.tooltip-dark .tooltip-arrow,
.tooltip-light .tooltip-arrow {
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-primary);
}

/* Arrow positioning */
.tooltip-top .tooltip-arrow {
  bottom: -4px;
  left: 50%;
  margin-left: -4px;
  border-bottom: none;
  border-right: none;
}

.tooltip-bottom .tooltip-arrow {
  top: -4px;
  left: 50%;
  margin-left: -4px;
  border-top: none;
  border-left: none;
}

.tooltip-left .tooltip-arrow {
  right: -4px;
  top: 50%;
  margin-top: -4px;
  border-top: none;
  border-right: none;
}

.tooltip-right .tooltip-arrow {
  left: -4px;
  top: 50%;
  margin-top: -4px;
  border-bottom: none;
  border-left: none;
}

</style>
