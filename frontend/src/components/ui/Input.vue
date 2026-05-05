<template>
  <div class="input-wrapper">
    <label
      v-if="label"
      :for="inputId"
      class="input-label"
    >
      {{ label }}
      <span
        v-if="required"
        class="required"
      >*</span>
    </label>
    
    <div
      class="input-container"
      :class="{
        'has-error': error,
        'is-disabled': disabled,
        'has-prefix': $slots.prefix,
        'has-suffix': $slots.suffix || type === 'password' || type === 'search'
      }"
    >
      <div
        v-if="$slots.prefix"
        class="input-prefix"
      >
        <slot name="prefix" />
      </div>
      
      <input
        :id="inputId"
        ref="inputRef"
        :type="computedType"
        :value="modelValue"
        :placeholder="placeholder"
        :disabled="disabled"
        :readonly="readonly"
        :required="required"
        :maxlength="maxlength"
        :minlength="minlength"
        :autocomplete="autocomplete"
        :aria-label="ariaLabel || label"
        :aria-invalid="!!error"
        :aria-describedby="error ? `${inputId}-error` : undefined"
        class="input"
        @input="handleInput"
        @change="handleChange"
        @focus="handleFocus"
        @blur="handleBlur"
        @keydown="handleKeydown"
      >
      
      <div
        v-if="$slots.suffix || type === 'password' || (type === 'search' && modelValue)"
        class="input-suffix"
      >
        <slot name="suffix">
          <button
            v-if="type === 'password'"
            type="button"
            class="icon-btn"
            :aria-label="showPassword ? $t('common.hidePassword') : $t('common.showPassword')"
            @click="togglePassword"
          >
            <component
              :is="showPassword ? EyeOffIcon : EyeIcon"
              :size="16"
            />
          </button>
          
          <button
            v-if="type === 'search' && modelValue"
            type="button"
            class="icon-btn"
            :aria-label="$t('common.clear')"
            @click="handleClear"
          >
            <component
              :is="XIcon"
              :size="16"
            />
          </button>
        </slot>
      </div>
    </div>
    
    <div
      v-if="error || hint"
      class="input-message"
      :class="{ 'is-error': error }"
    >
      <span
        v-if="error"
        :id="`${inputId}-error`"
        role="alert"
      >
        {{ error }}
      </span>
      <span v-else>{{ hint }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Eye as EyeIcon, EyeOff as EyeOffIcon, X as XIcon } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'

interface Props {
  modelValue?: string | number
  type?: 'text' | 'password' | 'email' | 'number' | 'tel' | 'url' | 'search'
  label?: string
  placeholder?: string
  error?: string
  hint?: string
  disabled?: boolean
  readonly?: boolean
  required?: boolean
  maxlength?: number
  minlength?: number
  autocomplete?: string
  ariaLabel?: string
}

interface Emits {
  (e: 'update:modelValue', value: string): void
  (e: 'change', value: string): void
  (e: 'focus', event: FocusEvent): void
  (e: 'blur', event: FocusEvent): void
  (e: 'keydown', event: KeyboardEvent): void
  (e: 'clear'): void
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: '',
  type: 'text',
  placeholder: '',
  disabled: false,
  readonly: false,
  required: false,
  autocomplete: 'off'
})

const emit = defineEmits<Emits>()
// const { t: _t } = useI18n()

const inputRef = ref<HTMLInputElement>()
const showPassword = ref(false)
const inputId = computed(() => `input-${Math.random().toString(36).substr(2, 9)}`)

const computedType = computed(() => {
  if (props.type === 'password') {
    return showPassword.value ? 'text' : 'password'
  }
  return props.type
})

const handleInput = (event: Event) => {
  const target = event.target as HTMLInputElement
  emit('update:modelValue', target.value)
}

const handleChange = (event: Event) => {
  const target = event.target as HTMLInputElement
  emit('change', target.value)
}

const handleFocus = (event: FocusEvent) => {
  emit('focus', event)
}

const handleBlur = (event: FocusEvent) => {
  emit('blur', event)
}

const handleKeydown = (event: KeyboardEvent) => {
  emit('keydown', event)
}

const togglePassword = () => {
  showPassword.value = !showPassword.value
}

const handleClear = () => {
  emit('update:modelValue', '')
  emit('clear')
  inputRef.value?.focus()
}

const focus = () => {
  inputRef.value?.focus()
}

const blur = () => {
  inputRef.value?.blur()
}

defineExpose({
  focus,
  blur
})
</script>

<style scoped>
.input-wrapper {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
  width: 100%;
}

.input-label {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--text-primary);
  display: block;
}

.required {
  color: var(--color-error);
  margin-left: 2px;
}

.input-container {
  position: relative;
  display: flex;
  align-items: center;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  transition: all var(--transition-base);
}

.input-container:focus-within {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
}

.input-container.has-error {
  border-color: var(--color-error);
}

.input-container.has-error:focus-within {
  box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.1);
}

.input-container.is-disabled {
  opacity: 0.6;
  cursor: not-allowed;
  background: var(--bg-tertiary);
}

.input {
  flex: 1;
  width: 100%;
  padding: var(--spacing-sm) var(--spacing-md);
  border: none;
  background: transparent;
  color: var(--text-primary);
  font-size: var(--font-size-base);
  font-family: var(--font-sans);
  outline: none;
}

.input::placeholder {
  color: var(--text-tertiary);
}

.input:disabled {
  cursor: not-allowed;
}

.input-container.has-prefix .input {
  padding-left: var(--spacing-xs);
}

.input-container.has-suffix .input {
  padding-right: var(--spacing-xs);
}

.input-prefix,
.input-suffix {
  display: flex;
  align-items: center;
  padding: 0 var(--spacing-sm);
  color: var(--text-secondary);
}

.icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-xs);
  border: none;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition: all var(--transition-base);
}

.icon-btn:hover {
  background: var(--hover-bg);
  color: var(--text-primary);
}

.input-message {
  font-size: var(--font-size-xs);
  color: var(--text-secondary);
  min-height: 18px;
}

.input-message.is-error {
  color: var(--color-error);
}

/* Number input arrows removal */
.input[type='number']::-webkit-inner-spin-button,
.input[type='number']::-webkit-outer-spin-button {
  -webkit-appearance: none;
  margin: 0;
}

.input[type='number'] {
  -moz-appearance: textfield;
}
</style>
