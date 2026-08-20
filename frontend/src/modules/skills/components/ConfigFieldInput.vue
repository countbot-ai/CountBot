<template>
  <div
    v-if="field.type === 'object'"
    class="object-field"
    :class="{ nested: isNested, collapsed: canCollapse && !isObjectExpanded }"
  >
    <button
      v-if="canCollapse"
      type="button"
      class="object-header object-toggle"
      @click="toggleObject"
    >
      <div class="object-header-copy">
        <div class="object-title-row">
          <span class="field-label">
            {{ field.label }}
            <span v-if="field.required" class="required">*</span>
            <span v-if="field.sensitive" class="sensitive-badge">
              <ShieldIcon :size="12" />
              敏感
            </span>
          </span>
        </div>
        <p v-if="field.description" class="field-description">
          {{ field.description }}
        </p>
      </div>

      <ChevronDownIcon
        :size="18"
        class="object-chevron"
        :class="{ rotated: isObjectExpanded }"
      />
    </button>

    <div v-else class="object-header">
      <div class="object-title-row">
        <span class="field-label">
          {{ field.label }}
          <span v-if="field.required" class="required">*</span>
          <span v-if="field.sensitive" class="sensitive-badge">
            <ShieldIcon :size="12" />
            敏感
          </span>
        </span>
      </div>
      <p v-if="field.description" class="field-description">
        {{ field.description }}
      </p>
    </div>

    <transition name="collapse">
      <div v-show="isObjectExpanded" class="object-body">
        <ConfigFieldInput
          v-for="subField in field.fields"
          :key="subField.key"
          :field="subField"
          :model-value="getNestedValue(subField.key)"
          :is-nested="true"
          @update:model-value="(val) => handleNestedUpdate(subField.key, val)"
        />

        <a
          v-if="field.help_url"
          :href="field.help_url"
          target="_blank"
          class="help-link"
        >
          <ExternalLinkIcon :size="14" />
          查看帮助
        </a>
      </div>
    </transition>
  </div>

  <div v-else class="config-field" :class="{ nested: isNested }">
    <label class="field-label">
      {{ field.label }}
      <span v-if="field.required" class="required">*</span>
      <span v-if="field.sensitive" class="sensitive-badge">
        <ShieldIcon :size="12" />
        敏感
      </span>
    </label>

    <p v-if="field.description" class="field-description">
      {{ field.description }}
    </p>

    <input
      v-if="field.type === 'string' || field.type === 'email'"
      :type="field.type"
      :value="normalizedValue"
      :placeholder="field.placeholder"
      :required="field.required"
      :readonly="field.readonly"
      @input="handleInput"
      class="field-input"
      :class="{ readonly: field.readonly }"
    />

    <div v-else-if="field.type === 'password'" class="password-field">
      <input
        :type="showPassword ? 'text' : 'password'"
        :value="normalizedValue"
        :placeholder="field.placeholder"
        :required="field.required"
        :readonly="field.readonly"
        @input="handleInput"
        class="field-input"
        :class="{ readonly: field.readonly }"
      />
      <button
        v-if="!field.readonly"
        type="button"
        class="toggle-password"
        @click="showPassword = !showPassword"
        :title="showPassword ? '隐藏' : '显示'"
      >
        <component :is="showPassword ? EyeOffIcon : EyeIcon" :size="16" />
      </button>
    </div>

    <input
      v-else-if="field.type === 'number'"
      type="number"
      :value="normalizedValue"
      :placeholder="field.placeholder"
      :required="field.required"
      :readonly="field.readonly"
      :min="field.min"
      :max="field.max"
      @input="handleInput"
      class="field-input"
      :class="{ readonly: field.readonly }"
    />

    <label v-else-if="field.type === 'boolean'" class="switch-label">
      <input
        type="checkbox"
        :checked="Boolean(modelValue)"
        :disabled="field.readonly"
        @change="handleCheckbox"
        class="switch-input"
      />
      <span class="switch-slider" :class="{ disabled: field.readonly }"></span>
      <span class="switch-text">{{ modelValue ? '启用' : '禁用' }}</span>
    </label>

    <select
      v-else-if="field.type === 'select'"
      :value="normalizedValue"
      :disabled="field.readonly"
      @change="handleSelect"
      class="field-select"
      :class="{ readonly: field.readonly }"
    >
      <option value="">请选择</option>
      <option
        v-for="option in field.options"
        :key="option.value"
        :value="option.value"
      >
        {{ option.label }}
      </option>
    </select>

    <a
      v-if="field.help_url"
      :href="field.help_url"
      target="_blank"
      class="help-link"
    >
      <ExternalLinkIcon :size="14" />
      查看帮助
    </a>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  ChevronDown as ChevronDownIcon,
  ExternalLink as ExternalLinkIcon,
  Eye as EyeIcon,
  EyeOff as EyeOffIcon,
  Shield as ShieldIcon
} from 'lucide-vue-next'
import type { ConfigFieldSchema } from '@/api/endpoints'

interface Props {
  field: ConfigFieldSchema
  modelValue: any
  isNested?: boolean
  forceExpanded?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  isNested: false,
  forceExpanded: false
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: any): void
}>()

const showPassword = ref(false)
const expanded = ref(true)

const normalizedValue = computed(() => props.modelValue ?? '')
const canCollapse = computed(() => props.field.type === 'object' && Boolean(props.field.collapsible) && !props.forceExpanded)
const isObjectExpanded = computed(() => props.forceExpanded || !canCollapse.value || expanded.value)

const toggleObject = () => {
  if (!canCollapse.value) return
  expanded.value = !expanded.value
}

const handleInput = (e: Event) => {
  const target = e.target as HTMLInputElement
  const value = props.field.type === 'number' 
    ? (target.value === '' ? '' : Number(target.value)) 
    : target.value
  emit('update:modelValue', value)
}

const handleCheckbox = (e: Event) => {
  const target = e.target as HTMLInputElement
  emit('update:modelValue', target.checked)
}

const handleSelect = (e: Event) => {
  const target = e.target as HTMLSelectElement
  emit('update:modelValue', target.value)
}

const getNestedValue = (fieldKey: string) => {
  return props.modelValue?.[fieldKey]
}

const handleNestedUpdate = (fieldKey: string, value: any) => {
  emit('update:modelValue', {
    ...props.modelValue,
    [fieldKey]: value
  })
}
</script>
<style scoped>
@import './styles/ConfigFieldInput.css';
</style>
