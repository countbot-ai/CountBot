<template>
  <div class="native-picker" :class="{ 'is-disabled': !supported }">
    <button type="button" class="native-picker-head" @click="toggleExpanded">
      <span class="native-picker-title">
        <Sparkles :size="14" />
        <span>{{ $t('settings.providers.models.native.title') }}</span>
        <span v-if="enabledCount" class="native-picker-count">{{ enabledCount }}</span>
      </span>
      <span class="native-picker-head-right">
        <span v-if="!supported" class="native-picker-unsupported">
          {{ $t('settings.providers.models.native.unsupported') }}
        </span>
        <ChevronDown :size="14" class="native-picker-chevron" :class="{ expanded }" />
      </span>
    </button>

    <div v-if="expanded" class="native-picker-body">
      <p class="native-picker-hint">{{ $t('settings.providers.models.native.hint') }}</p>
      <p v-if="customEndpoint" class="native-picker-hint native-picker-hint-warn">
        {{ $t('settings.providers.models.native.customEndpointHint') }}
      </p>

      <div
        v-for="item in toggleItems"
        :key="item.key"
        class="native-picker-row"
      >
        <span class="native-picker-icon"><component :is="item.icon" :size="14" /></span>
        <span class="native-picker-copy">
          <span class="native-picker-label">{{ $t(item.labelKey) }}</span>
          <span class="native-picker-desc">{{ $t(item.descKey) }}</span>
        </span>
        <SwitchToggle
          :model-value="Boolean(value[item.key])"
          :disabled="disabled"
          :aria-label="$t(item.labelKey)"
          @update:model-value="(next: boolean) => updateToggle(item.key, next)"
        />
      </div>

      <div class="native-picker-row native-picker-row-stack">
        <span class="native-picker-icon"><FileText :size="14" /></span>
        <span class="native-picker-copy">
          <span class="native-picker-label">{{ $t('settings.providers.models.native.documentParsing') }}</span>
          <span class="native-picker-desc">
            {{ $t('settings.providers.models.native.documentParsingDesc') }}
          </span>
        </span>
        <div class="native-segments">
          <button
            v-for="mode in documentModes"
            :key="mode.value"
            type="button"
            class="native-segment"
            :class="{ 'is-active': value.document_parsing === mode.value }"
            :disabled="disabled"
            @click="updateDocumentMode(mode.value)"
          >
            {{ $t(mode.labelKey) }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  ChevronDown,
  FileText,
  Globe2,
  Link2,
  Mic,
  ShieldCheck,
  Sparkles,
  Volume2,
} from 'lucide-vue-next'
import SwitchToggle from '@/components/ui/SwitchToggle.vue'
import {
  DEFAULT_NATIVE_CAPABILITIES,
  normalizeNativeCapabilities,
  type DocumentParsingMode,
  type NativeCapabilities,
} from '@/types/nativeCaps'

interface Props {
  modelValue?: NativeCapabilities
  supported?: boolean
  /** 非官方地址：能力按 DeepSeek 原生语义发送。 */
  customEndpoint?: boolean
  /** 受控展开状态；不传时组件内部自行维护。 */
  expanded?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: () => ({ ...DEFAULT_NATIVE_CAPABILITIES }),
  supported: true,
  customEndpoint: false,
  expanded: undefined,
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: NativeCapabilities): void
  (e: 'update:expanded', value: boolean): void
}>()

const internalExpanded = ref(false)
const expanded = computed(() => props.expanded ?? internalExpanded.value)

function toggleExpanded(): void {
  const next = !expanded.value
  internalExpanded.value = next
  emit('update:expanded', next)
}

const value = computed(() => normalizeNativeCapabilities(props.modelValue))
const disabled = computed(() => !props.supported)

const enabledCount = computed(() => {
  const caps = value.value
  return [
    caps.web_search,
    caps.read_url,
    caps.safety_check,
    caps.asr,
    caps.tts,
    caps.document_parsing !== 'off',
  ].filter(Boolean).length
})

const toggleItems = [
  {
    key: 'web_search' as const,
    icon: Globe2,
    labelKey: 'settings.providers.models.native.webSearch',
    descKey: 'settings.providers.models.native.webSearchDesc',
  },
  {
    key: 'read_url' as const,
    icon: Link2,
    labelKey: 'settings.providers.models.native.readUrl',
    descKey: 'settings.providers.models.native.readUrlDesc',
  },
  {
    key: 'safety_check' as const,
    icon: ShieldCheck,
    labelKey: 'settings.providers.models.native.safetyCheck',
    descKey: 'settings.providers.models.native.safetyCheckDesc',
  },
  {
    key: 'asr' as const,
    icon: Mic,
    labelKey: 'settings.providers.models.native.asr',
    descKey: 'settings.providers.models.native.asrDesc',
  },
  {
    key: 'tts' as const,
    icon: Volume2,
    labelKey: 'settings.providers.models.native.tts',
    descKey: 'settings.providers.models.native.ttsDesc',
  },
]

const documentModes: Array<{ value: DocumentParsingMode; labelKey: string }> = [
  { value: 'off', labelKey: 'settings.providers.models.native.docOff' },
  { value: 'text', labelKey: 'settings.providers.models.native.docText' },
  { value: 'rich', labelKey: 'settings.providers.models.native.docRich' },
]

function emitValue(next: NativeCapabilities): void {
  emit('update:modelValue', next)
}

function updateToggle(key: keyof NativeCapabilities, next: boolean): void {
  if (disabled.value) return
  emitValue({ ...value.value, [key]: next })
}

function updateDocumentMode(mode: DocumentParsingMode): void {
  if (disabled.value) return
  emitValue({ ...value.value, document_parsing: mode })
}
</script>

<style scoped>
.native-picker {
  border-radius: 10px;
  background: var(--color-bg-secondary);
  overflow: hidden;
}

.native-picker.is-disabled {
  opacity: 0.72;
}

.native-picker-head {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 9px 11px;
  border: 0;
  background: transparent;
  cursor: pointer;
  color: var(--color-text-primary);
}

.native-picker-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12.5px;
  font-weight: 600;
}

.native-picker-count {
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 999px;
  background: var(--color-accent-alpha);
  color: var(--color-accent);
  font-size: 10.5px;
  line-height: 18px;
  text-align: center;
  font-variant-numeric: tabular-nums;
}

.native-picker-head-right {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.native-picker-unsupported {
  font-size: 10.5px;
  color: var(--color-text-tertiary);
}

.native-picker-chevron {
  transition: transform 200ms cubic-bezier(0.215, 0.61, 0.355, 1);
}

.native-picker-chevron.expanded {
  transform: rotate(180deg);
}

.native-picker-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 2px 11px 8px;
  box-shadow: inset 0 1px 0 var(--color-border-primary);
}

.native-picker-hint {
  margin: 8px 0 4px;
  font-size: 11px;
  line-height: 1.6;
  color: var(--color-text-tertiary);
  text-wrap: pretty;
}

.native-picker-hint-warn {
  margin-top: 0;
  color: var(--color-warning);
}

.native-picker-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 0;
  box-shadow: inset 0 -1px 0 var(--color-border-primary);
}

.native-picker-row:last-child {
  box-shadow: none;
}

.native-picker-row-stack {
  align-items: flex-start;
  flex-wrap: wrap;
}

.native-picker-icon {
  display: inline-flex;
  margin-top: 2px;
  color: var(--color-text-tertiary);
}

.native-picker-copy {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 140px;
}

.native-picker-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--color-text-primary);
}

.native-picker-desc {
  font-size: 10.5px;
  line-height: 1.5;
  color: var(--color-text-tertiary);
  text-wrap: pretty;
}

.native-segments {
  display: inline-flex;
  gap: 2px;
  padding: 2px;
  border-radius: 8px;
  background: var(--color-bg-primary);
}

.native-segment {
  border: 0;
  border-radius: 6px;
  padding: 4px 9px;
  background: transparent;
  color: var(--color-text-secondary);
  font-family: inherit;
  font-size: 10.5px;
  cursor: pointer;
  transition:
    background var(--transition-fast),
    color var(--transition-fast);
}

.native-segment.is-active {
  background: var(--color-bg-elevated);
  color: var(--color-text-primary);
  box-shadow: var(--shadow-xs);
}

.native-segment:disabled {
  cursor: not-allowed;
}

@media (prefers-reduced-motion: reduce) {
  .native-picker-chevron,
  .native-segment {
    transition: none;
  }
}
</style>
