<template>
  <div ref="rootRef" class="reasoning-select">
    <button
      type="button"
      class="reasoning-select-trigger"
      :aria-expanded="open"
      :aria-label="$t('chat.reasoningLevel.title')"
      @click="toggle"
    >
      <component :is="BrainCircuitIcon" :size="13" class="reasoning-select-icon" />
      <span class="reasoning-select-label">{{ currentLabel }}</span>
      <component :is="ChevronDownIcon" :size="13" class="reasoning-select-caret" />
    </button>

    <div v-if="open" class="reasoning-select-popover" role="listbox">
      <button
        v-for="level in options"
        :key="level"
        type="button"
        role="option"
        class="reasoning-select-option"
        :class="{
          'is-active': level === modelValue,
          'is-off': isOffLevel(level),
        }"
        :aria-selected="level === modelValue"
        @click="selectLevel(level)"
      >
        <span class="reasoning-select-option-name">{{ levelLabel(level) }}</span>
        <component
          v-if="level === modelValue"
          :is="CheckIcon"
          :size="13"
          class="reasoning-select-check"
        />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  BrainCircuit as BrainCircuitIcon,
  Check as CheckIcon,
  ChevronDown as ChevronDownIcon,
} from 'lucide-vue-next'

interface Props {
  levels: string[]
  modelValue?: string | null
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: '',
})

const emit = defineEmits<{
  (e: 'change', level: string): void
}>()

const { t } = useI18n()

const rootRef = ref<HTMLElement>()
const open = ref(false)

/** 「关闭」档位的下发值；与后端 REASONING_LEVEL_OFF 保持一致 */
const OFF_LEVEL = 'none'
const OFF_ALIASES = new Set(['none', 'off', 'disabled', 'false', '0', '关闭'])

function isOffLevel(value?: string | null): boolean {
  return OFF_ALIASES.has(String(value || '').trim().toLowerCase())
}

/** 档位列表 + 固定的「关闭」项，避免模型自带 none 时重复出现 */
const options = computed(() => {
  const visible = (props.levels || []).filter(level => !isOffLevel(level))
  return [...visible, OFF_LEVEL]
})

function levelLabel(level: string): string {
  return isOffLevel(level) ? t('chat.reasoningLevel.off') : level
}

const currentLabel = computed(() => {
  if (props.modelValue && isOffLevel(props.modelValue)) {
    return t('chat.reasoningLevel.off')
  }
  return props.modelValue || t('chat.reasoningLevel.placeholder')
})

function toggle(): void {
  open.value = !open.value
}

function close(): void {
  open.value = false
}

function selectLevel(level: string): void {
  if (level !== props.modelValue) {
    emit('change', level)
  }
  close()
}

function handleDocumentPointerDown(event: MouseEvent): void {
  if (!open.value) {
    return
  }
  const target = event.target as Node | null
  if (target && rootRef.value && !rootRef.value.contains(target)) {
    close()
  }
}

onMounted(() => {
  document.addEventListener('mousedown', handleDocumentPointerDown)
})

onBeforeUnmount(() => {
  document.removeEventListener('mousedown', handleDocumentPointerDown)
})
</script>

<style scoped>
@import './styles/ReasoningLevelSelect.css';
</style>
