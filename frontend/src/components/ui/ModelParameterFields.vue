<template>
  <div class="model-parameter-fields">
    <div class="parameter-group">
      <label class="parameter-label">
        <span>{{ $t('settings.model.temperature') }}</span>
        <span class="parameter-value">{{ temperatureLabel }}</span>
      </label>
      <p class="parameter-help">{{ $t('settings.model.temperatureDesc') }}</p>
      <input
        v-model.number="temperatureValue"
        type="range"
        min="0"
        max="2"
        step="0.1"
        class="parameter-slider"
      >
      <div class="parameter-scale">
        <span>{{ $t('common.default') }}</span>
        <span>{{ $t('settings.model.temperatureBalanced') }}</span>
        <span>{{ $t('settings.model.temperatureCreative') }}</span>
      </div>
    </div>

    <div class="parameter-group">
      <label class="parameter-label">
        <span>{{ $t('settings.model.maxTokens') }}</span>
        <span class="parameter-value">{{ maxTokensLabel }}</span>
      </label>
      <p class="parameter-help">{{ $t('settings.model.maxTokensDesc') }}</p>
      <input
        v-model.number="maxTokensSliderIndex"
        type="range"
        min="0"
        :max="MAX_TOKENS_SLIDER_MAX"
        :step="MAX_TOKENS_SLIDER_STEP"
        class="parameter-slider"
      >
      <div class="parameter-scale parameter-scale-tokens">
        <span v-for="(label, index) in maxTokensScaleLabels" :key="`token-scale-${index}`">{{ label }}</span>
      </div>
      <div class="parameter-actions">
        <button
          type="button"
          class="parameter-reset"
          :disabled="maxTokensValue === MODEL_CONFIG_FALLBACK.max_tokens"
          @click="maxTokensValue = MODEL_CONFIG_FALLBACK.max_tokens"
        >
          {{ $t('settings.model.maxTokensReset') }}
        </button>
      </div>
    </div>

    <div v-if="showMaxIterations" class="parameter-group">
      <label class="parameter-label">
        <span>{{ $t('settings.model.maxIterations') }}</span>
        <span class="parameter-value">{{ maxIterationsLabel }}</span>
      </label>
      <p class="parameter-help">{{ $t('settings.model.maxIterationsDesc') }}</p>
      <input
        v-model.number="maxIterationsValue"
        type="range"
        min="1"
        max="150"
        step="1"
        class="parameter-slider"
      >
      <div class="parameter-scale">
        <span>1</span>
        <span>75</span>
        <span>150</span>
      </div>
    </div>

    <div v-if="showThinkingToggle" class="parameter-group parameter-group-toggle">
      <label class="parameter-toggle">
        <div class="parameter-toggle-copy">
          <span class="parameter-toggle-title">{{ $t('settings.model.thinkingEnabled') }}</span>
          <span class="parameter-toggle-help">{{ $t('settings.model.thinkingEnabledDesc') }}</span>
        </div>
        <SwitchToggle
          v-model="thinkingEnabledValue"
          :width="48"
          :height="28"
          :aria-label="$t('settings.model.thinkingEnabled')"
        />
      </label>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import SwitchToggle from '@/components/ui/SwitchToggle.vue'
import {
  MAX_TOKENS_PRESET_VALUES,
  MAX_TOKENS_SLIDER_MAX,
  MAX_TOKENS_SLIDER_STEP,
  MODEL_CONFIG_FALLBACK,
  formatMaxTokensValue,
  getMaxTokensSliderIndex,
  getMaxTokensValueFromSliderIndex,
  normalizeMaxTokensValue,
} from '@/utils/modelConfig'

interface Props {
  temperature: number
  maxTokens: number
  maxIterations?: number
  thinkingEnabled?: boolean
  showMaxIterations?: boolean
  showThinkingToggle?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  maxIterations: MODEL_CONFIG_FALLBACK.max_iterations,
  thinkingEnabled: MODEL_CONFIG_FALLBACK.thinking_enabled,
  showMaxIterations: true,
  showThinkingToggle: true,
})

const emit = defineEmits<{
  (e: 'update:temperature', value: number): void
  (e: 'update:maxTokens', value: number): void
  (e: 'update:maxIterations', value: number): void
  (e: 'update:thinkingEnabled', value: boolean): void
}>()

const { t } = useI18n()

const temperatureValue = computed({
  get: () => props.temperature,
  set: (value: number) => emit('update:temperature', value),
})

const maxTokensValue = computed({
  get: () => props.maxTokens,
  set: (value: number) => emit('update:maxTokens', normalizeMaxTokensValue(value)),
})

const maxIterationsValue = computed({
  get: () => props.maxIterations,
  set: (value: number) => emit('update:maxIterations', value),
})

const thinkingEnabledValue = computed({
  get: () => props.thinkingEnabled,
  set: (value: boolean) => emit('update:thinkingEnabled', value),
})

const temperatureLabel = computed(() =>
  props.temperature === MODEL_CONFIG_FALLBACK.temperature
    ? t('common.default')
    : String(props.temperature)
)

const maxTokensScaleLabels = computed(() =>
  [
    0,
    MAX_TOKENS_PRESET_VALUES[4],
    MAX_TOKENS_PRESET_VALUES[6],
    MAX_TOKENS_PRESET_VALUES[8],
    MAX_TOKENS_PRESET_VALUES[MAX_TOKENS_PRESET_VALUES.length - 1],
  ].map(value =>
    formatMaxTokensValue(value, {
      unlimitedLabel: t('settings.model.maxTokensAuto'),
    }),
  )
)

const maxTokensSliderIndex = computed({
  get: () => getMaxTokensSliderIndex(props.maxTokens),
  set: (value: number) => emit('update:maxTokens', getMaxTokensValueFromSliderIndex(value)),
})

const maxTokensLabel = computed(() =>
  formatMaxTokensValue(props.maxTokens, {
    unlimitedLabel: t('settings.model.maxTokensAuto'),
  })
)

const maxIterationsLabel = computed(() =>
  props.maxIterations === MODEL_CONFIG_FALLBACK.max_iterations
    ? t('common.default')
    : String(props.maxIterations)
)
</script>

<style scoped>
.model-parameter-fields {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.parameter-group {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.parameter-group-toggle {
  padding: 14px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 16px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(248, 250, 252, 0.96));
}

.parameter-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: var(--text-primary);
  font-size: 14px;
  font-weight: 600;
}

.parameter-value {
  color: var(--color-primary);
  font-weight: 700;
}

.parameter-help {
  margin: 0;
  color: var(--text-tertiary);
  font-size: 12px;
  line-height: 1.55;
}

.parameter-slider {
  width: 100%;
  height: 6px;
  border-radius: 999px;
  background: linear-gradient(90deg, rgba(148, 163, 184, 0.3), rgba(148, 163, 184, 0.12));
  outline: none;
  -webkit-appearance: none;
  appearance: none;
}

.parameter-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 18px;
  height: 18px;
  border: 2px solid rgba(255, 255, 255, 0.92);
  border-radius: 999px;
  background: var(--color-primary);
  box-shadow: 0 3px 10px rgba(37, 99, 235, 0.18);
  cursor: pointer;
}

.parameter-slider::-moz-range-thumb {
  width: 18px;
  height: 18px;
  border: 2px solid rgba(255, 255, 255, 0.92);
  border-radius: 999px;
  background: var(--color-primary);
  box-shadow: 0 3px 10px rgba(37, 99, 235, 0.18);
  cursor: pointer;
}

.parameter-scale {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  color: var(--text-tertiary);
  font-size: 12px;
}

.parameter-scale-tokens {
  gap: 14px;
}

.parameter-actions {
  display: flex;
  justify-content: flex-end;
}

.parameter-reset {
  appearance: none;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 999px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font: inherit;
  font-size: 12px;
  font-weight: 600;
  line-height: 1;
  min-height: 34px;
  padding: 0 12px;
  transition:
    border-color 0.2s ease,
    color 0.2s ease,
    background 0.2s ease;
}

.parameter-reset:hover:not(:disabled) {
  border-color: rgba(37, 99, 235, 0.24);
  color: var(--color-primary);
  background: rgba(37, 99, 235, 0.05);
}

.parameter-reset:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.parameter-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  cursor: pointer;
}

.parameter-toggle-copy {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.parameter-toggle-title {
  color: var(--text-primary);
  font-size: 14px;
  font-weight: 600;
}

.parameter-toggle-help {
  color: var(--text-tertiary);
  font-size: 12px;
  line-height: 1.5;
}

:root[data-theme='dark'] .parameter-group-toggle,
:root[data-theme='dark'] .parameter-advanced {
  border-color: rgba(82, 102, 131, 0.34);
  background: linear-gradient(180deg, rgba(15, 23, 42, 0.92), rgba(10, 16, 28, 0.96));
}

@media (max-width: 640px) {
  .parameter-advanced {
    grid-template-columns: 1fr;
    align-items: stretch;
  }

  .parameter-advanced-meta {
    white-space: normal;
  }

  .parameter-toggle {
    align-items: flex-start;
  }
}
</style>
