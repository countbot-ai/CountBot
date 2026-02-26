<template>
  <div
    ref="selectRef"
    class="select-wrapper"
  >
    <label
      v-if="label"
      :for="selectId"
      class="select-label"
    >
      {{ label }}
      <span
        v-if="required"
        class="required"
      >*</span>
    </label>
    
    <div
      :id="selectId"
      class="select-container"
      :class="{
        'is-open': isOpen,
        'is-disabled': disabled,
        'has-error': error,
        'is-multiple': multiple
      }"
      role="combobox"
      :aria-expanded="isOpen"
      :aria-haspopup="true"
      :aria-controls="`${selectId}-listbox`"
      :aria-label="ariaLabel || label"
      :aria-invalid="!!error"
      :tabindex="disabled ? -1 : 0"
      @click="toggleDropdown"
      @keydown="handleKeydown"
    >
      <div class="select-value">
        <template v-if="multiple && Array.isArray(modelValue) && modelValue.length > 0">
          <div class="select-tags">
            <span
              v-for="value in modelValue"
              :key="value"
              class="select-tag"
            >
              {{ getOptionLabel(value) }}
              <button
                type="button"
                class="tag-remove"
                :aria-label="$t('common.remove')"
                @click.stop="removeValue(value)"
              >
                <component
                  :is="XIcon"
                  :size="12"
                />
              </button>
            </span>
          </div>
        </template>
        <template v-else-if="!multiple && modelValue">
          <span class="select-text">{{ getOptionLabel(modelValue as string) }}</span>
        </template>
        <template v-else>
          <span class="select-placeholder">{{ placeholder }}</span>
        </template>
      </div>
      
      <div class="select-arrow">
        <component
          :is="ChevronDownIcon"
          :size="16"
        />
      </div>
    </div>
    
    <Transition name="dropdown">
      <div
        v-if="isOpen"
        :id="`${selectId}-listbox`"
        class="select-dropdown"
        role="listbox"
        :aria-multiselectable="multiple"
      >
        <div
          v-if="searchable"
          class="select-search"
        >
          <input
            ref="searchInputRef"
            v-model="searchQuery"
            type="text"
            class="search-input"
            :placeholder="$t('common.search')"
            @click.stop
            @keydown.stop="handleSearchKeydown"
          >
        </div>
        
        <div class="select-options">
          <div
            v-if="filteredOptions.length === 0"
            class="select-empty"
          >
            {{ $t('common.noResults') }}
          </div>
          
          <div
            v-for="(option, index) in filteredOptions"
            :key="option.value"
            class="select-option"
            :class="{
              'is-selected': isSelected(option.value),
              'is-focused': focusedIndex === index
            }"
            role="option"
            :aria-selected="isSelected(option.value)"
            @click="selectOption(option.value)"
            @mouseenter="focusedIndex = index"
          >
            <component
              :is="CheckIcon"
              v-if="multiple && isSelected(option.value)"
              :size="16"
              class="option-check"
            />
            <span class="option-label">{{ option.label }}</span>
          </div>
        </div>
      </div>
    </Transition>
    
    <div
      v-if="error || hint"
      class="select-message"
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
import { ChevronDown as ChevronDownIcon, X as XIcon, Check as CheckIcon } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { onClickOutside } from '@vueuse/core'

export interface SelectOption {
  label: string
  value: string
  disabled?: boolean
}

interface Props {
  modelValue?: string | string[]
  options: SelectOption[]
  label?: string
  placeholder?: string
  error?: string
  hint?: string
  disabled?: boolean
  required?: boolean
  multiple?: boolean
  searchable?: boolean
  ariaLabel?: string
}

interface Emits {
  (e: 'update:modelValue', value: string | string[]): void
  (e: 'change', value: string | string[]): void
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: undefined,
  placeholder: '',
  disabled: false,
  required: false,
  multiple: false,
  searchable: false
})

const emit = defineEmits<Emits>()
// const { t: _t } = useI18n()

const selectRef = ref<HTMLElement>()
const searchInputRef = ref<HTMLInputElement>()
const isOpen = ref(false)
const searchQuery = ref('')
const focusedIndex = ref(0)
const selectId = computed(() => `select-${Math.random().toString(36).substr(2, 9)}`)

const filteredOptions = computed(() => {
  if (!searchQuery.value) return props.options
  
  const query = searchQuery.value.toLowerCase()
  return props.options.filter(option =>
    option.label.toLowerCase().includes(query)
  )
})

const getOptionLabel = (value: string): string => {
  const option = props.options.find(opt => opt.value === value)
  return option?.label || value
}

const isSelected = (value: string): boolean => {
  if (props.multiple && Array.isArray(props.modelValue)) {
    return props.modelValue.includes(value)
  }
  return props.modelValue === value
}

const toggleDropdown = () => {
  if (props.disabled) return
  
  isOpen.value = !isOpen.value
  
  if (isOpen.value && props.searchable) {
    setTimeout(() => {
      searchInputRef.value?.focus()
    }, 50)
  }
}

const closeDropdown = () => {
  isOpen.value = false
  searchQuery.value = ''
  focusedIndex.value = 0
}

const selectOption = (value: string) => {
  if (props.multiple) {
    const currentValue = Array.isArray(props.modelValue) ? props.modelValue : []
    const newValue = currentValue.includes(value)
      ? currentValue.filter(v => v !== value)
      : [...currentValue, value]
    
    emit('update:modelValue', newValue)
    emit('change', newValue)
  } else {
    emit('update:modelValue', value)
    emit('change', value)
    closeDropdown()
  }
}

const removeValue = (value: string) => {
  if (!props.multiple || !Array.isArray(props.modelValue)) return
  
  const newValue = props.modelValue.filter(v => v !== value)
  emit('update:modelValue', newValue)
  emit('change', newValue)
}

const handleKeydown = (event: KeyboardEvent) => {
  if (props.disabled) return
  
  switch (event.key) {
    case 'Enter':
    case ' ':
      event.preventDefault()
      if (!isOpen.value) {
        toggleDropdown()
      } else if (filteredOptions.value[focusedIndex.value]) {
        selectOption(filteredOptions.value[focusedIndex.value].value)
      }
      break
      
    case 'Escape':
      event.preventDefault()
      closeDropdown()
      break
      
    case 'ArrowDown':
      event.preventDefault()
      if (!isOpen.value) {
        toggleDropdown()
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
  }
}

const handleSearchKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Escape') {
    closeDropdown()
  }
}

watch(isOpen, (newValue) => {
  if (!newValue) {
    focusedIndex.value = 0
  }
})

onClickOutside(selectRef, () => {
  closeDropdown()
})
</script>

<style scoped>
.select-wrapper {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
  width: 100%;
  position: relative;
}

.select-label {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--text-primary);
  display: block;
}

.required {
  color: var(--color-error);
  margin-left: 2px;
}

.select-container {
  position: relative;
  display: flex;
  align-items: center;
  min-height: 40px;
  padding: var(--spacing-xs) var(--spacing-md);
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-base);
  user-select: none;
}

.select-container:hover:not(.is-disabled) {
  border-color: var(--color-primary);
}

.select-container:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
}

.select-container.is-open {
  border-color: var(--color-primary);
}

.select-container.has-error {
  border-color: var(--color-error);
}

.select-container.is-disabled {
  opacity: 0.6;
  cursor: not-allowed;
  background: var(--bg-tertiary);
}

.select-value {
  flex: 1;
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  overflow: hidden;
}

.select-text {
  color: var(--text-primary);
  font-size: var(--font-size-base);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.select-placeholder {
  color: var(--text-tertiary);
  font-size: var(--font-size-base);
}

.select-tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-xs);
}

.select-tag {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: 2px var(--spacing-xs);
  background: var(--color-primary);
  color: #ffffff;
  font-size: var(--font-size-xs);
  border-radius: var(--radius-sm);
}

.tag-remove {
  display: flex;
  align-items: center;
  padding: 0;
  border: none;
  background: transparent;
  color: #ffffff;
  cursor: pointer;
  opacity: 0.8;
  transition: opacity var(--transition-base);
}

.tag-remove:hover {
  opacity: 1;
}

.select-arrow {
  display: flex;
  align-items: center;
  color: var(--text-secondary);
  transition: transform var(--transition-base);
}

.select-container.is-open .select-arrow {
  transform: rotate(180deg);
}

.select-dropdown {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  max-height: 300px;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  z-index: 1000;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.select-search {
  padding: var(--spacing-sm);
  border-bottom: 1px solid var(--border-color);
}

.search-input {
  width: 100%;
  padding: var(--spacing-xs) var(--spacing-sm);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-size: var(--font-size-sm);
  outline: none;
}

.search-input:focus {
  border-color: var(--color-primary);
}

.select-options {
  overflow-y: auto;
  max-height: 250px;
}

.select-option {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  cursor: pointer;
  transition: background var(--transition-base);
}

.select-option:hover,
.select-option.is-focused {
  background: var(--hover-bg);
}

.select-option.is-selected {
  background: rgba(37, 99, 235, 0.1);
  color: var(--color-primary);
}

.option-check {
  flex-shrink: 0;
  color: var(--color-primary);
}

.option-label {
  flex: 1;
  font-size: var(--font-size-base);
  color: var(--text-primary);
}

.select-empty {
  padding: var(--spacing-lg);
  text-align: center;
  color: var(--text-tertiary);
  font-size: var(--font-size-sm);
}

.select-message {
  font-size: var(--font-size-xs);
  color: var(--text-secondary);
  min-height: 18px;
}

.select-message.is-error {
  color: var(--color-error);
}

/* Dropdown transition */
.dropdown-enter-active,
.dropdown-leave-active {
  transition: all 0.2s ease;
}

.dropdown-enter-from,
.dropdown-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
</style>
