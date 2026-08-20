<template>
  <div class="model-config">
    <div class="section-header">
      <h3 class="section-title">
        {{ $t('settings.model.title') }}
      </h3>
    </div>

    <div class="draft-callout" :class="{ 'is-dirty': isDraftChanged }">
      <div class="draft-item">
        <span class="draft-label">{{ $t('settings.providers.presetPanel.savedSnapshot') }}</span>
        <strong>{{ savedSummary }}</strong>
      </div>
      <div class="draft-item">
        <span class="draft-label">{{ $t('settings.providers.presetPanel.currentDraft') }}</span>
        <strong>{{ draftSummary }}</strong>
      </div>
    </div>

    <div class="form-group">
      <label class="label">
        {{ $t('settings.model.temperature') }}
        <span class="value">{{ temperatureLabel }}</span>
      </label>
      <p class="help-text">
        {{ $t('settings.model.temperatureDesc') }}
      </p>
      <input
        v-model.number="modelConfig.temperature"
        type="range"
        min="0"
        max="2"
        step="0.1"
        class="slider"
      >
      <div class="slider-labels">
        <span>{{ $t('common.default') }}</span>
        <span>1</span>
        <span>2</span>
      </div>
    </div>

    <!-- Max Tokens -->
    <div class="form-group">
      <label class="label">
        {{ $t('settings.model.maxTokens') }}
        <span class="value">{{ maxTokensLabel }}</span>
      </label>
      <p class="help-text">
        {{ $t('settings.model.maxTokensDesc') }}
      </p>
      <input
        v-model.number="maxTokensSliderIndex"
        type="range"
        min="0"
        :max="MAX_TOKENS_SLIDER_MAX"
        :step="MAX_TOKENS_SLIDER_STEP"
        class="slider"
      >
      <div class="slider-labels slider-labels-token">
        <span v-for="(label, index) in maxTokensScaleLabels" :key="`scale-${index}`">{{ label }}</span>
      </div>
      <div class="token-actions">
        <button
          type="button"
          class="token-reset"
          :disabled="modelConfig.maxTokens === MODEL_CONFIG_FALLBACK.max_tokens"
          @click="modelConfig.maxTokens = MODEL_CONFIG_FALLBACK.max_tokens"
        >
          {{ $t('settings.model.maxTokensReset') }}
        </button>
      </div>
    </div>

    <!-- Max Iterations -->
    <div class="form-group">
      <label class="label">
        {{ $t('settings.model.maxIterations') }}
        <span class="value">{{ maxIterationsLabel }}</span>
      </label>
      <p class="help-text">
        {{ $t('settings.model.maxIterationsDesc') }}
      </p>
      <input
        v-model.number="modelConfig.maxIterations"
        type="range"
        min="1"
        max="150"
        step="1"
        class="slider"
      >
      <div class="slider-labels">
        <span>1</span>
        <span>75</span>
        <span>150</span>
      </div>
    </div>

    <div class="form-group toggle-group">
      <label class="toggle-label">
        <div class="toggle-content">
          <span class="toggle-text">{{ $t('settings.model.thinkingEnabled') }}</span>
          <span class="toggle-hint">{{ $t('settings.model.thinkingEnabledDesc') }}</span>
        </div>
        <SwitchToggle
          v-model="modelConfig.thinkingEnabled"
          :width="48"
          :height="28"
          :aria-label="$t('settings.model.thinkingEnabled')"
        />
      </label>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useSettingsStore } from '@/store/settings'
import SwitchToggle from '@/components/ui/SwitchToggle.vue'
import {
  MAX_TOKENS_PRESET_VALUES,
  MAX_TOKENS_SLIDER_MAX,
  MAX_TOKENS_SLIDER_STEP,
  MODEL_CONFIG_FALLBACK,
  buildEffectiveModelConfig,
  formatMaxTokensValue,
  formatModelConfigSummary,
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

const maxIterationsLabel = computed(() =>
  modelConfig.value.maxIterations === MODEL_CONFIG_FALLBACK.max_iterations
    ? t('common.default')
    : modelConfig.value.maxIterations,
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
  }) !== JSON.stringify({
    temperature: modelConfig.value.temperature,
    maxTokens: modelConfig.value.maxTokens,
    maxIterations: modelConfig.value.maxIterations,
    thinkingEnabled: modelConfig.value.thinkingEnabled,
  })
})

</script>
<style scoped>
@import './styles/ModelConfig.css';
</style>
