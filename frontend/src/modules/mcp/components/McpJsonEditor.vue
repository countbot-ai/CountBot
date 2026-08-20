<template>
  <div class="mcp-json-editor">
    <div class="mcp-json-header">
      <span class="mcp-json-hint">{{ $t('settings.mcp.jsonHint') }}</span>
      <div class="json-actions">
        <button class="mcp-btn mcp-btn-primary" @click="$emit('apply', jsonText)" :disabled="!!jsonError">
          {{ $t('settings.mcp.applyJson') }}
        </button>
        <button class="mcp-btn" @click="$emit('cancel')">
          {{ $t('settings.mcp.cancel') }}
        </button>
      </div>
    </div>
    <div v-if="jsonError" class="mcp-json-error">{{ jsonError }}</div>
    <textarea
      :value="jsonText"
      @input="onInput"
      class="mcp-textarea"
      spellcheck="false"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const props = defineProps<{
  jsonText: string
}>()

const emit = defineEmits<{
  'update:jsonText': [value: string]
  apply: [json: string]
  cancel: []
}>()

const jsonError = ref('')

function validate(s: string): string {
  try {
    const parsed = JSON.parse(s)
    const mcpServers = parsed.mcpServers || parsed
    if (typeof mcpServers !== 'object' || mcpServers === null || Array.isArray(mcpServers)) {
      return t('settings.mcp.jsonInvalidFormat')
    }
    return ''
  } catch (e: any) {
    return e.message
  }
}

function onInput(e: Event) {
  const val = (e.target as HTMLTextAreaElement).value
  emit('update:jsonText', val)
  jsonError.value = validate(val)
}

watch(() => props.jsonText, () => {
  jsonError.value = validate(props.jsonText)
}, { immediate: true })
</script>

<style>
@import '../styles/mcp.css';
</style>
