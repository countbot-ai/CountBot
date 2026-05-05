<template>
  <div
    ref="comboBoxRef"
    class="combobox-wrapper"
  >
    <label
      v-if="label"
      :for="comboBoxId"
      class="combobox-label"
    >
      {{ label }}
      <span
        v-if="required"
        class="required"
      >*</span>
    </label>
    
    <div class="combobox-container">
      <input
        :id="comboBoxId"
        ref="inputRef"
        v-model="inputValue"
        type="text"
        class="combobox-input"
        :class="{
          'is-open': isOpen,
          'has-error': error
        }"
        :placeholder="placeholder"
        :disabled="disabled"
        :aria-label="ariaLabel || label"
        :aria-invalid="!!error"
        :aria-expanded="isOpen"
        :aria-controls="`${comboBoxId}-listbox`"
        role="combobox"
        @input="handleInput"
        @focus="handleFocus"
        @keydown="handleKeydown"
      >
      
      <button
        type="button"
        class="combobox-toggle"
        :disabled="disabled"
        :aria-label="$t('common.toggleDropdown')"
        @click="toggleDropdown"
      >
        <component
          :is="ChevronDownIcon"
          :size="16"
        />
      </button>
    </div>
    
    <Transition name="dropdown">
      <div
        v-if="isOpen && filteredOptions.length > 0"
        :id="`${comboBoxId}-listbox`"
        class="combobox-dropdown"
        role="listbox"
      >
        <div class="combobox-options">
          <div
            v-for="(option, index) in filteredOptions"
            :key="option.value"
            class="combobox-option"
            :class="{
              'is-selected': inputValue === option.value,
              'is-focused': focusedIndex === index
            }"
            role="option"
            :aria-selected="inputValue === option.value"
            @click="selectOption(option.value)"
            @mouseenter="focusedIndex = index"
          >
            <span class="option-label">{{ option.label }}</span>
          </div>
        </div>
      </div>
    </Transition>
    
    <div
      v-if="error || hint"
      class="combobox-message"
      :class="{ 'is-error': error }"
    >
      <span
        v-if="error"
        role="alert"
      >
        {{ error }}
      </span>
      <span v-else>{{ hint }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ChevronDown as ChevronDownIcon } from 'lucide-vue-next'
import { onClickOutside } from '@vueuse/core'

export interface ComboBoxOption {
  label: string
  value: string
  disabled?: boolean
}

interface Props {
  modelValue?: string
  options: ComboBoxOption[]
  label?: string
  placeholder?: string
  error?: string
  hint?: string
  disabled?: boolean
  required?: boolean
  ariaLabel?: string
}

interface Emits {
  (e: 'update:modelValue', value: string): void
  (e: 'change', value: string): void
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: '',
  placeholder: '',
  disabled: false,
  required: false
})

const emit = defineEmits<Emits>()

const comboBoxRef = ref<HTMLElement>()
const inputRef = ref<HTMLInputElement>()
const isOpen = ref(false)
const inputValue = ref(props.modelValue || '')
const focusedIndex = ref(0)
const comboBoxId = computed(() => `combobox-${Math.random().toString(36).substr(2, 9)}`)

// 过滤选项：根据输入值过滤
const filteredOptions = computed(() => {
  if (!inputValue.value) return props.options
  
  const query = inputValue.value.toLowerCase()
  return props.options.filter(option =>
    option.label.toLowerCase().includes(query) ||
    option.value.toLowerCase().includes(query)
  )
})

// 监听 modelValue 变化，同步到 inputValue
watch(() => props.modelValue, (newValue) => {
  if (newValue !== inputValue.value) {
    inputValue.value = newValue || ''
  }
})

// 监听 inputValue 变化，发出更新事件
watch(inputValue, (newValue) => {
  emit('update:modelValue', newValue)
  emit('change', newValue)
})

const handleInput = () => {
  // 输入时自动打开下拉列表
  if (!isOpen.value && filteredOptions.value.length > 0) {
    isOpen.value = true
  }
  focusedIndex.value = 0
}

const handleFocus = () => {
  // 聚焦时显示所有选项
  if (filteredOptions.value.length > 0) {
    isOpen.value = true
  }
}

const toggleDropdown = () => {
  if (props.disabled) return
  isOpen.value = !isOpen.value
  
  if (isOpen.value) {
    inputRef.value?.focus()
  }
}

const closeDropdown = () => {
  isOpen.value = false
  focusedIndex.value = 0
}

const selectOption = (value: string) => {
  inputValue.value = value
  closeDropdown()
  inputRef.value?.blur()
}

const handleKeydown = (event: KeyboardEvent) => {
  if (props.disabled) return
  
  switch (event.key) {
    case 'Enter':
      event.preventDefault()
      if (isOpen.value && filteredOptions.value[focusedIndex.value]) {
        selectOption(filteredOptions.value[focusedIndex.value].value)
      } else {
        closeDropdown()
      }
      break
      
    case 'Escape':
      event.preventDefault()
      closeDropdown()
      break
      
    case 'ArrowDown':
      event.preventDefault()
      if (!isOpen.value) {
        isOpen.value = true
      } else {
        focusedIndex.value = Math.min(focusedIndex.value + 1, filteredOptions.value.length - 1)
      }
      break
      
    case 'ArrowUp':
      event.preventDefault()
      if (isOpen.value) {
        focusedIndex.value = Math.max(focusedIndex.value - 1, 0)
      }
      break
      
    case 'Tab':
      closeDropdown()
      break
  }
}

onClickOutside(comboBoxRef, () => {
  closeDropdown()
})
</script>
<style scoped>
@import './styles/ComboBox.css';
</style>
