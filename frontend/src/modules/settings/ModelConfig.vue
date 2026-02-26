<template>
  <div class="model-config">
    <div class="section-header">
      <h3 class="section-title">
        {{ $t('settings.model.title') }}
      </h3>
      <p class="section-desc">
        {{ $t('settings.model.description') }}
      </p>
    </div>

    <!-- Temperature -->
    <div class="form-group">
      <label class="label">
        {{ $t('settings.model.temperature') }}
        <span class="value">{{ modelConfig.temperature }}</span>
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
        <span>0</span>
        <span>1</span>
        <span>2</span>
      </div>
    </div>

    <!-- Max Tokens -->
    <div class="form-group">
      <label class="label">
        {{ $t('settings.model.maxTokens') }}
        <span class="value">{{ modelConfig.maxTokens === 0 ? $t('settings.model.maxTokensAuto') : modelConfig.maxTokens }}</span>
      </label>
      <p class="help-text">
        {{ $t('settings.model.maxTokensDesc') }}
      </p>
      <input
        v-model.number="modelConfig.maxTokens"
        type="range"
        min="0"
        max="32768"
        step="256"
        class="slider"
      >
      <div class="slider-labels">
        <span>{{ $t('settings.model.maxTokensAuto') }}</span>
        <span>16K</span>
        <span>32K</span>
      </div>
    </div>

    <!-- Max Iterations -->
    <div class="form-group">
      <label class="label">
        {{ $t('settings.model.maxIterations') }}
        <span class="value">{{ modelConfig.maxIterations }}</span>
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
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { useSettingsStore } from '@/store/settings'

const settingsStore = useSettingsStore()

const modelConfig = ref({
  temperature: 0.7,
  maxTokens: 0,
  maxIterations: 25
})

const isUpdating = ref(false)

// Initialize from store
onMounted(() => {
  if (settingsStore.settings?.model) {
    isUpdating.value = true
    modelConfig.value = {
      temperature: settingsStore.settings.model.temperature ?? 0.7,
      maxTokens: settingsStore.settings.model.max_tokens ?? 4096,
      maxIterations: settingsStore.settings.model.max_iterations ?? 25
    }
    isUpdating.value = false
  }
})

// Watch for settings changes from store (e.g., after reload)
watch(() => settingsStore.settings?.model, (newModel) => {
  if (newModel && !isUpdating.value) {
    isUpdating.value = true
    modelConfig.value = {
      temperature: newModel.temperature ?? 0.7,
      maxTokens: newModel.max_tokens ?? 4096,
      maxIterations: newModel.max_iterations ?? 25
    }
    isUpdating.value = false
  }
}, { deep: true })

// Watch for local changes and sync to store (parent will save)
watch(modelConfig, (newConfig) => {
  if (!isUpdating.value && settingsStore.settings?.model) {
    isUpdating.value = true
    settingsStore.settings.model.temperature = newConfig.temperature
    settingsStore.settings.model.max_tokens = newConfig.maxTokens
    settingsStore.settings.model.max_iterations = newConfig.maxIterations
    isUpdating.value = false
  }
}, { deep: true })
</script>

<style scoped>
.model-config {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xl);
}

.section-header {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.section-title {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  margin: 0;
}

.section-desc {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  margin: 0;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--text-primary);
}

.value {
  font-weight: var(--font-weight-semibold);
  color: var(--color-primary);
}

.help-text {
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
  margin: 0;
  line-height: 1.5;
}

.slider {
  width: 100%;
  height: 6px;
  border-radius: 3px;
  background: var(--bg-tertiary);
  outline: none;
  -webkit-appearance: none;
  appearance: none;
}

.slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--color-primary);
  cursor: pointer;
  transition: all var(--transition-base);
}

.slider::-webkit-slider-thumb:hover {
  transform: scale(1.2);
  box-shadow: 0 0 0 4px rgba(37, 99, 235, 0.2);
}

.slider::-moz-range-thumb {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--color-primary);
  cursor: pointer;
  border: none;
  transition: all var(--transition-base);
}

.slider::-moz-range-thumb:hover {
  transform: scale(1.2);
  box-shadow: 0 0 0 4px rgba(37, 99, 235, 0.2);
}

.slider-labels {
  display: flex;
  justify-content: space-between;
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
}
</style>
