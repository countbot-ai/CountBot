<template>
  <SettingsCard :title="$t('settings.model.draftTitle')" flush>
    <SettingsRow :label="$t('settings.providers.savedSnapshot')">
      <span class="co-row-value">{{ savedSummary }}</span>
    </SettingsRow>
    <SettingsRow :label="$t('settings.providers.currentDraft')">
      <span v-if="isDraftChanged" class="co-row-badge">{{ $t('settings.saveState.dirty') }}</span>
      <span class="co-row-value">{{ draftSummary }}</span>
    </SettingsRow>
  </SettingsCard>

  <SettingsCard :title="$t('settings.model.paramsTitle')">
    <SettingsRow :label="$t('settings.model.temperature')" :description="$t('settings.model.temperatureDesc')" layout="block">
      <div class="slider-head">
        <input v-model.number="modelConfig.temperature" class="co-slider" type="range" min="0" max="2" step="0.1">
        <span class="co-row-value">{{ temperatureLabel }}</span>
      </div>
      <div class="co-slider-scale">
        <span>{{ $t('common.default') }}</span>
        <span>1</span>
        <span>2</span>
      </div>
    </SettingsRow>

    <SettingsRow :label="$t('settings.model.maxTokens')" :description="$t('settings.model.maxTokensDesc')" layout="block">
      <div class="slider-head">
        <input
          v-model.number="maxTokensSliderIndex"
          class="co-slider"
          type="range"
          min="0"
          :max="MAX_TOKENS_SLIDER_MAX"
          :step="MAX_TOKENS_SLIDER_STEP"
        >
        <span class="co-row-value">{{ maxTokensLabel }}</span>
        <button
          type="button"
          class="co-btn co-btn--ghost btn-compact"
          :disabled="modelConfig.maxTokens === MODEL_CONFIG_FALLBACK.max_tokens"
          @click="modelConfig.maxTokens = MODEL_CONFIG_FALLBACK.max_tokens"
        >
          {{ $t('settings.model.maxTokensReset') }}
        </button>
      </div>
      <div class="co-slider-scale">
        <span v-for="(label, index) in maxTokensScaleLabels" :key="`scale-${index}`">{{ label }}</span>
      </div>
    </SettingsRow>

    <SettingsRow :label="$t('settings.model.maxIterations')" :description="$t('settings.model.maxIterationsDesc')" layout="block">
      <div class="slider-head">
        <input
          v-model.number="maxIterationsSliderIndex"
          class="co-slider"
          type="range"
          min="0"
          :max="MAX_ITERATIONS_SLIDER_MAX"
          step="1"
        >
        <span class="co-row-value">{{ maxIterationsLabel }}</span>
      </div>
      <div class="co-slider-scale">
        <span>1</span>
        <span>{{ Math.round(MAX_ITERATIONS_LIMIT / 2) }}</span>
        <span>{{ $t('settings.model.maxIterationsUnlimited') }}</span>
      </div>
    </SettingsRow>

    <SettingsRow :label="$t('settings.model.imageInput')" :description="$t('settings.model.imageInputDesc')">
      <Select
        v-model="imageSupportMode"
        class="select-control"
        :options="imageSupportOptions"
        :aria-label="$t('settings.model.imageInput')"
      />
    </SettingsRow>

    <SettingsRow :label="$t('settings.model.thinkingEnabled')" :description="$t('settings.model.thinkingEnabledDesc')">
      <SwitchToggle
        v-model="modelConfig.thinkingEnabled"
        :width="40"
        :height="22"
        :aria-label="$t('settings.model.thinkingEnabled')"
      />
    </SettingsRow>

    <SettingsRow :label="$t('settings.model.streamMode')" :description="$t('settings.model.streamModeDesc')">
      <Select
        v-model="streamMode"
        class="select-control"
        :options="streamModeOptions"
        :aria-label="$t('settings.model.streamMode')"
      />
    </SettingsRow>
  </SettingsCard>
</template>

<script setup lang="ts">
import { computed, ref, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useSettingsStore } from '@/store/settings'
import SwitchToggle from '@/components/ui/SwitchToggle.vue'
import Select from '@/components/ui/Select.vue'
import { SettingsCard, SettingsRow } from './ui'
import {
  MAX_ITERATIONS_LIMIT,
  MAX_ITERATIONS_SLIDER_MAX,
  MAX_TOKENS_PRESET_VALUES,
  MAX_TOKENS_SLIDER_MAX,
  MAX_TOKENS_SLIDER_STEP,
  MODEL_CONFIG_FALLBACK,
  buildEffectiveModelConfig,
  formatMaxIterationsValue,
  formatMaxTokensValue,
  formatModelConfigSummary,
  getMaxIterationsSliderIndex,
  getMaxIterationsValueFromSliderIndex,
  getMaxTokensSliderIndex,
  getMaxTokensValueFromSliderIndex,
} from '@/utils/modelConfig'

const { t } = useI18n()
const settingsStore = useSettingsStore()

const modelConfig = ref({
  temperature: MODEL_CONFIG_FALLBACK.temperature,
  maxTokens: MODEL_CONFIG_FALLBACK.max_tokens,
  maxIterations: MODEL_CONFIG_FALLBACK.max_iterations,
  thinkingEnabled: MODEL_CONFIG_FALLBACK.thinking_enabled,
  streamEnabled: MODEL_CONFIG_FALLBACK.stream_enabled,
  supportsImage: MODEL_CONFIG_FALLBACK.supports_image,
})

const isUpdating = ref(false)

// Initialize from store
onMounted(async () => {
  if (settingsStore.settings?.model) {
    isUpdating.value = true
    const effectiveConfig = buildEffectiveModelConfig(settingsStore.settings.model)
    modelConfig.value = {
      temperature: effectiveConfig.temperature,
      maxTokens: effectiveConfig.max_tokens,
      maxIterations: effectiveConfig.max_iterations,
      thinkingEnabled: effectiveConfig.thinking_enabled,
      streamEnabled: effectiveConfig.stream_enabled,
      supportsImage: effectiveConfig.supports_image ?? null,
    }
    isUpdating.value = false
  }
})

// Watch for settings changes from store (e.g., after reload)
watch(() => settingsStore.settings?.model, (newModel) => {
  if (newModel && !isUpdating.value) {
    isUpdating.value = true
    const effectiveConfig = buildEffectiveModelConfig(newModel)
    modelConfig.value = {
      temperature: effectiveConfig.temperature,
      maxTokens: effectiveConfig.max_tokens,
      maxIterations: effectiveConfig.max_iterations,
      thinkingEnabled: effectiveConfig.thinking_enabled,
      streamEnabled: effectiveConfig.stream_enabled,
      supportsImage: effectiveConfig.supports_image ?? null,
    }
    isUpdating.value = false
  }
}, { deep: true })

// Watch for local changes and sync to store (parent will save)
watch(modelConfig, (newConfig) => {
  if (!isUpdating.value && settingsStore.settings?.model) {
    isUpdating.value = true
    settingsStore.settings.model.api_mode = 'chat_completions'
    settingsStore.settings.model.temperature = newConfig.temperature
    settingsStore.settings.model.max_tokens = newConfig.maxTokens
    settingsStore.settings.model.max_iterations = newConfig.maxIterations
    settingsStore.settings.model.thinking_enabled = newConfig.thinkingEnabled
    settingsStore.settings.model.stream_enabled = newConfig.streamEnabled
    settingsStore.settings.model.supports_image = newConfig.supportsImage
    isUpdating.value = false
  }
}, { deep: true })

const savedSummary = computed(() => {
  const savedModel = settingsStore.persistedSettings?.model
  if (!savedModel) {
    return '...'
  }

  return formatModelConfigSummary(savedModel, {
    defaultLabel: t('common.default'),
    unlimitedLabel: t('settings.model.maxTokensAuto'),
    unlimitedIterationsLabel: t('settings.model.maxIterationsUnlimited'),
  })
})

const draftSummary = computed(() =>
  formatModelConfigSummary(
    {
      temperature: modelConfig.value.temperature,
      max_tokens: modelConfig.value.maxTokens,
      max_iterations: modelConfig.value.maxIterations,
    },
    {
      defaultLabel: t('common.default'),
      unlimitedLabel: t('settings.model.maxTokensAuto'),
    },
  )
)

const imageSupportOptions = computed(() => [
  { value: 'auto', label: t('settings.model.imageInputAuto') },
  { value: 'on', label: t('settings.model.imageInputOn') },
  { value: 'off', label: t('settings.model.imageInputOff') },
])

const streamModeOptions = computed(() => [
  { value: 'stream', label: t('settings.model.streamModeStreaming') },
  { value: 'non-stream', label: t('settings.model.streamModeNonStreaming') },
])

const streamMode = computed({
  get: () => (modelConfig.value.streamEnabled ? 'stream' : 'non-stream'),
  set: (value: string | string[]) => {
    const mode = Array.isArray(value) ? value[0] : value
    modelConfig.value.streamEnabled = mode === 'stream'
  },
})

const imageSupportMode = computed({
  get: () => {
    if (modelConfig.value.supportsImage === true) return 'on'
    if (modelConfig.value.supportsImage === false) return 'off'
    return 'auto'
  },
  set: (value: string | string[]) => {
    const mode = Array.isArray(value) ? value[0] : value
    modelConfig.value.supportsImage = mode === 'on' ? true : mode === 'off' ? false : null
  },
})

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
  get: () => getMaxTokensSliderIndex(modelConfig.value.maxTokens),
  set: (value: number) => {
    modelConfig.value.maxTokens = getMaxTokensValueFromSliderIndex(value)
  },
})

const maxTokensLabel = computed(() =>
  formatMaxTokensValue(modelConfig.value.maxTokens, {
    unlimitedLabel: t('settings.model.maxTokensAuto'),
  })
)

const temperatureLabel = computed(() =>
  modelConfig.value.temperature === MODEL_CONFIG_FALLBACK.temperature
    ? t('common.default')
    : modelConfig.value.temperature,
)

const maxIterationsSliderIndex = computed({
  get: () => getMaxIterationsSliderIndex(modelConfig.value.maxIterations),
  set: (value: number) => {
    modelConfig.value.maxIterations = getMaxIterationsValueFromSliderIndex(value)
  },
})

const maxIterationsLabel = computed(() =>
  formatMaxIterationsValue(modelConfig.value.maxIterations, {
    unlimitedLabel: t('settings.model.maxIterationsUnlimited'),
  })
)

const isDraftChanged = computed(() => {
  const savedModel = settingsStore.persistedSettings?.model
  if (!savedModel) {
    return false
  }

  return JSON.stringify({
    temperature: savedModel.temperature,
    maxTokens: savedModel.max_tokens,
    maxIterations: savedModel.max_iterations,
    thinkingEnabled: savedModel.thinking_enabled,
    streamEnabled: savedModel.stream_enabled,
  }) !== JSON.stringify({
    temperature: modelConfig.value.temperature,
    maxTokens: modelConfig.value.maxTokens,
    maxIterations: modelConfig.value.maxIterations,
    thinkingEnabled: modelConfig.value.thinkingEnabled,
    streamEnabled: modelConfig.value.streamEnabled,
  })
})

</script>

<style scoped>
.slider-head {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
}

.slider-head .co-slider {
  flex: 1;
  min-width: 0;
}

.slider-head .co-row-value {
  min-width: 52px;
  text-align: right;
}

.btn-compact {
  height: 24px;
  padding: 0 8px;
  font-size: var(--font-size-xs);
  flex-shrink: 0;
}

.select-control {
  width: 220px;
}

@media (max-width: 680px) {
  .select-control {
    width: 100%;
  }
}
</style>
