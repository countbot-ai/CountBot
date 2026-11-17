<template>
  <SettingsCard
    :title="$t('settings.persona.historyTitle')"
    :description="$t('settings.persona.historyHint')"
  >
    <SettingsRow layout="block">
      <div class="history-slider">
        <div class="history-slider__header">
          <Tooltip :content="historyTooltip" placement="top" :delay="120">
            <button
              type="button"
              class="history-label"
              :aria-label="$t('settings.persona.maxHistoryTooltipLabel')"
            >
              <span>{{ $t('settings.persona.maxHistoryMessages') }}</span>
              <InfoIcon :size="15" class="history-info-icon" />
            </button>
          </Tooltip>
          <div class="history-value">{{ historyDisplayValue }}</div>
        </div>

        <input
          v-if="!isUnlimitedHistory"
          v-model.number="historyLimit"
          type="range"
          min="5"
          max="200"
          step="5"
          class="history-range"
        />
        <div v-if="!isUnlimitedHistory" class="history-marks">
          <span>5</span>
          <span>50</span>
          <span>100</span>
          <span>200</span>
        </div>
        <div v-else class="history-unlimited">
          <Infinity :size="20" />
          <span>{{ $t('settings.persona.unlimitedNotice') }}</span>
        </div>
      </div>
    </SettingsRow>

    <SettingsRow layout="block">
      <div class="history-presets">
        <label class="history-presets__label">{{ $t('settings.persona.quickPresets') }}</label>
        <div class="history-preset-grid">
          <button
            v-for="preset in presets"
            :key="preset.value"
            type="button"
            class="history-preset"
            :class="{ 'is-active': maxHistoryMessages === preset.value }"
            @click="setPreset(preset.value)"
          >
            <component :is="preset.icon" :size="16" />
            <span>{{ $t(`settings.persona.preset.${preset.label}`) }}</span>
            <span class="history-preset__value">{{ formatPresetValue(preset.value) }}</span>
          </button>
        </div>
      </div>
    </SettingsRow>

    <SettingsRow
      :label="$t('settings.persona.enableShortContextSummary')"
      :description="$t('settings.persona.enableShortContextSummaryHint')"
    >
      <SwitchToggle
        v-model="shortContextSummary"
        :width="48"
        :height="28"
        :aria-label="$t('settings.persona.enableShortContextSummary')"
      />
      <template #below>
        <p v-if="isUnlimitedHistory" class="history-note">
          {{ $t('settings.persona.enableShortContextSummaryUnlimitedHint') }}
        </p>
      </template>
    </SettingsRow>

    <SettingsRow layout="block">
      <div class="history-estimate">
        <div class="history-estimate__header">
          <ZapIcon :size="18" />
          <span>{{ $t('settings.persona.tokenEstimate') }}</span>
        </div>
        <div class="history-estimate__grid">
          <div class="history-estimate__item">
            <span>{{ $t('settings.persona.estimatedTokens') }}</span>
            <strong>{{ estimatedTokens }}</strong>
          </div>
          <div class="history-estimate__item">
            <span>{{ $t('settings.persona.savingsVs100') }}</span>
            <strong :class="savingsClass">{{ savingsText }}</strong>
          </div>
        </div>
      </div>
    </SettingsRow>
  </SettingsCard>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  Smile,
  Briefcase,
  MessageSquare as MessageSquareIcon,
  Laugh,
  TrendingUp,
  Infinity,
  Info as InfoIcon,
  Zap as ZapIcon,
} from 'lucide-vue-next'
import SwitchToggle from '@/components/ui/SwitchToggle.vue'
import Tooltip from '@/components/ui/Tooltip.vue'
import SettingsCard from './SettingsCard.vue'
import SettingsRow from './SettingsRow.vue'

interface Props {
  maxHistoryMessages: number
  enableShortContextSummary: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'update:maxHistoryMessages': [value: number]
  'update:enableShortContextSummary': [value: boolean]
}>()

const { t } = useI18n()

const presets = [
  { label: 'minimal', value: 5, icon: Smile },
  { label: 'short', value: 30, icon: Briefcase },
  { label: 'medium', value: 50, icon: MessageSquareIcon },
  { label: 'long', value: 100, icon: Laugh },
  { label: 'extended', value: 200, icon: TrendingUp },
  { label: 'unlimited', value: 0, icon: Infinity },
]

const normalizeHistoryLimit = (value: number) => (value <= 0 ? 0 : value)

const historyLimit = computed({
  get: () => props.maxHistoryMessages,
  set: (value: number) => emit('update:maxHistoryMessages', normalizeHistoryLimit(value)),
})

const shortContextSummary = computed({
  get: () => props.enableShortContextSummary,
  set: (value: boolean) => emit('update:enableShortContextSummary', value),
})

const isUnlimitedHistory = computed(() => props.maxHistoryMessages <= 0)

const historyDisplayValue = computed(() =>
  isUnlimitedHistory.value
    ? t('settings.persona.unlimited')
    : props.maxHistoryMessages,
)

const historyTooltip = computed(() =>
  isUnlimitedHistory.value
    ? t('settings.persona.maxHistoryTooltipUnlimited')
    : t('settings.persona.maxHistoryTooltip', {
        count: props.maxHistoryMessages,
      }),
)

const estimatedTokens = computed(() => {
  if (isUnlimitedHistory.value) return '∞'
  return `~${(props.maxHistoryMessages * 200).toLocaleString()}`
})

const savingsPercentage = computed(() => {
  if (isUnlimitedHistory.value) return null
  const baseline = 100 * 200
  const current = props.maxHistoryMessages * 200
  return Math.round(((baseline - current) / baseline) * 100)
})

const savingsText = computed(() => {
  if (savingsPercentage.value === null) return '∞'
  if (savingsPercentage.value > 0) return `↓ ${savingsPercentage.value}%`
  if (savingsPercentage.value < 0) return `↑ ${Math.abs(savingsPercentage.value)}%`
  return '0%'
})

const savingsClass = computed(() => {
  if (savingsPercentage.value === null) return 'is-unlimited'
  if (savingsPercentage.value > 0) return 'is-positive'
  if (savingsPercentage.value < 0) return 'is-negative'
  return 'is-neutral'
})

const setPreset = (value: number) => {
  emit('update:maxHistoryMessages', normalizeHistoryLimit(value))
}

const formatPresetValue = (value: number) => (value <= 0 ? '∞' : String(value))
</script>

<style scoped>
.history-slider__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.history-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--color-text-primary);
  font: inherit;
  cursor: help;
}

.history-info-icon {
  color: var(--color-text-secondary);
  transition: color var(--transition-fast);
}

.history-label:hover .history-info-icon,
.history-label:focus-visible .history-info-icon {
  color: var(--color-primary);
}

.history-label:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 3px;
  border-radius: var(--radius-sm);
}

.history-value {
  padding: 4px 12px;
  border-radius: var(--radius-sm);
  background: var(--color-bg-tertiary);
  color: var(--color-primary);
  font-size: 16px;
  font-weight: 600;
}

.history-range {
  width: 100%;
  height: 6px;
  border-radius: 3px;
  background: var(--color-bg-secondary);
  outline: none;
  cursor: pointer;
  -webkit-appearance: none;
}

.history-range::-webkit-slider-thumb {
  width: 18px;
  height: 18px;
  border: 0;
  border-radius: 50%;
  background: var(--color-primary);
  cursor: pointer;
  -webkit-appearance: none;
  appearance: none;
}

.history-range::-moz-range-thumb {
  width: 18px;
  height: 18px;
  border: 0;
  border-radius: 50%;
  background: var(--color-primary);
  cursor: pointer;
}

.history-marks {
  display: flex;
  justify-content: space-between;
  padding: 0 4px;
  margin-top: 8px;
  color: var(--color-text-tertiary);
  font-size: 11px;
}

.history-unlimited {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-top: 12px;
  padding: 16px;
  border: 1px dashed var(--color-border-strong);
  border-radius: var(--radius-md);
  background: var(--color-bg-tertiary);
  color: var(--color-primary);
  font-size: 14px;
  font-weight: 500;
}

.history-presets__label {
  color: var(--color-text-primary);
  font-size: 13px;
  font-weight: 500;
}

.history-preset-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 10px;
  margin-top: 12px;
}

.history-preset {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-md);
  background: var(--color-bg-elevated);
  color: var(--color-text-primary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition:
    border-color var(--transition-fast),
    background var(--transition-fast),
    color var(--transition-fast);
}

.history-preset:hover {
  border-color: var(--color-border-secondary);
  background: var(--color-bg-secondary);
}

.history-preset.is-active {
  border-color: var(--color-border-secondary);
  background: var(--color-bg-tertiary);
  color: var(--color-primary);
}

.history-preset__value {
  color: var(--color-text-tertiary);
  font-size: 11px;
  font-weight: 400;
}

.history-preset.is-active .history-preset__value {
  color: var(--color-primary);
}

.history-note {
  margin: 8px 0 0;
  color: var(--color-text-tertiary);
  font-size: 12px;
}

.history-estimate {
  padding: 16px;
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-md);
  background: var(--color-bg-secondary);
}

.history-estimate__header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  color: var(--color-text-primary);
  font-size: 14px;
  font-weight: 600;
}

.history-estimate__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
}

.history-estimate__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  background: var(--color-bg-primary);
  color: var(--color-text-secondary);
  font-size: 13px;
}

.history-estimate__item strong {
  color: var(--color-text-primary);
  font-size: 16px;
}

.history-estimate__item strong.is-positive {
  color: var(--color-success);
}

.history-estimate__item strong.is-negative {
  color: var(--color-error);
}

.history-estimate__item strong.is-neutral {
  color: var(--color-text-secondary);
}

.history-estimate__item strong.is-unlimited {
  color: var(--color-primary);
}

@media (max-width: 768px) {
  .history-preset-grid,
  .history-estimate__grid {
    grid-template-columns: 1fr;
  }
}
</style>
