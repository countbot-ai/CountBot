<template>
  <div class="cron-builder">
    <!-- Mode Toggle -->
    <div class="mode-toggle">
      <button
        class="mode-btn"
        :class="{ active: mode === 'simple' }"
        @click="mode = 'simple'"
      >
        <component :is="SlidersIcon" :size="14" />
        {{ $t('cron.builder.simpleMode') }}
      </button>
      <button
        class="mode-btn"
        :class="{ active: mode === 'advanced' }"
        @click="mode = 'advanced'"
      >
        <component :is="CodeIcon" :size="14" />
        {{ $t('cron.builder.advancedMode') }}
      </button>
    </div>

    <!-- Simple Mode -->
    <div v-if="mode === 'simple'" class="simple-mode">
      <!-- Frequency Type -->
      <div class="field-row">
        <label class="field-label">{{ $t('cron.builder.frequency') }}</label>
        <select v-model="frequency" class="field-select" @change="onFrequencyChange">
          <option value="minute">{{ $t('cron.builder.freqMinute') }}</option>
          <option value="hour">{{ $t('cron.builder.freqHour') }}</option>
          <option value="day">{{ $t('cron.builder.freqDay') }}</option>
          <option value="week">{{ $t('cron.builder.freqWeek') }}</option>
          <option value="month">{{ $t('cron.builder.freqMonth') }}</option>
        </select>
      </div>

      <!-- Every N minutes -->
      <div v-if="frequency === 'minute'" class="field-row">
        <label class="field-label">{{ $t('cron.builder.every') }}</label>
        <select v-model="minuteInterval" class="field-select narrow" @change="buildExpression">
          <option v-for="n in [1, 2, 3, 5, 10, 15, 20, 30]" :key="n" :value="n">{{ n }}</option>
        </select>
        <span class="field-suffix">{{ $t('cron.builder.minutes') }}</span>
      </div>

      <!-- Every N hours, at minute -->
      <template v-if="frequency === 'hour'">
        <div class="field-row">
          <label class="field-label">{{ $t('cron.builder.every') }}</label>
          <select v-model="hourInterval" class="field-select narrow" @change="buildExpression">
            <option v-for="n in [1, 2, 3, 4, 6, 8, 12]" :key="n" :value="n">{{ n }}</option>
          </select>
          <span class="field-suffix">{{ $t('cron.builder.hours') }}</span>
        </div>
        <div class="field-row">
          <label class="field-label">{{ $t('cron.builder.atMinute') }}</label>
          <select v-model="atMinute" class="field-select narrow" @change="buildExpression">
            <option v-for="n in 60" :key="n - 1" :value="n - 1">{{ String(n - 1).padStart(2, '0') }}</option>
          </select>
        </div>
      </template>

      <!-- Every day at HH:MM -->
      <template v-if="frequency === 'day'">
        <div class="field-row">
          <label class="field-label">{{ $t('cron.builder.atTime') }}</label>
          <div class="time-picker">
            <select v-model="atHour" class="field-select narrow" @change="buildExpression">
              <option v-for="n in 24" :key="n - 1" :value="n - 1">{{ String(n - 1).padStart(2, '0') }}</option>
            </select>
            <span class="time-sep">:</span>
            <select v-model="atMinute" class="field-select narrow" @change="buildExpression">
              <option v-for="n in 60" :key="n - 1" :value="n - 1">{{ String(n - 1).padStart(2, '0') }}</option>
            </select>
          </div>
        </div>
      </template>

      <!-- Every week on weekday at HH:MM -->
      <template v-if="frequency === 'week'">
        <div class="field-row">
          <label class="field-label">{{ $t('cron.builder.onDay') }}</label>
          <div class="weekday-picker">
            <button
              v-for="(label, idx) in weekdayLabels"
              :key="idx"
              class="weekday-btn"
              :class="{ active: selectedWeekdays.includes(idx) }"
              @click="toggleWeekday(idx)"
            >
              {{ label }}
            </button>
          </div>
        </div>
        <div class="field-row">
          <label class="field-label">{{ $t('cron.builder.atTime') }}</label>
          <div class="time-picker">
            <select v-model="atHour" class="field-select narrow" @change="buildExpression">
              <option v-for="n in 24" :key="n - 1" :value="n - 1">{{ String(n - 1).padStart(2, '0') }}</option>
            </select>
            <span class="time-sep">:</span>
            <select v-model="atMinute" class="field-select narrow" @change="buildExpression">
              <option v-for="n in 60" :key="n - 1" :value="n - 1">{{ String(n - 1).padStart(2, '0') }}</option>
            </select>
          </div>
        </div>
      </template>

      <!-- Every month on day at HH:MM -->
      <template v-if="frequency === 'month'">
        <div class="field-row">
          <label class="field-label">{{ $t('cron.builder.onDate') }}</label>
          <select v-model="monthDay" class="field-select narrow" @change="buildExpression">
            <option v-for="n in 31" :key="n" :value="n">{{ n }}</option>
          </select>
          <span class="field-suffix">{{ $t('cron.builder.th') }}</span>
        </div>
        <div class="field-row">
          <label class="field-label">{{ $t('cron.builder.atTime') }}</label>
          <div class="time-picker">
            <select v-model="atHour" class="field-select narrow" @change="buildExpression">
              <option v-for="n in 24" :key="n - 1" :value="n - 1">{{ String(n - 1).padStart(2, '0') }}</option>
            </select>
            <span class="time-sep">:</span>
            <select v-model="atMinute" class="field-select narrow" @change="buildExpression">
              <option v-for="n in 60" :key="n - 1" :value="n - 1">{{ String(n - 1).padStart(2, '0') }}</option>
            </select>
          </div>
        </div>
      </template>
    </div>

    <!-- Advanced Mode -->
    <div v-else class="advanced-mode">
      <div class="cron-input-row">
        <input
          v-model="rawExpression"
          class="cron-raw-input"
          :placeholder="$t('cron.schedulePlaceholder')"
          @input="onRawInput"
        />
      </div>
      <p class="cron-hint">{{ $t('cron.scheduleHint') }}</p>
      <!-- Quick Presets -->
      <div class="quick-presets">
        <button
          v-for="preset in presets"
          :key="preset.value"
          class="preset-chip"
          :class="{ active: rawExpression === preset.value }"
          @click="applyPreset(preset.value)"
        >
          {{ preset.label }}
        </button>
      </div>
    </div>

    <!-- Expression Preview -->
    <div class="expression-preview" :class="{ error: !!parseError }">
      <div class="preview-header">
        <component :is="parseError ? AlertCircleIcon : ClockIcon" :size="14" />
        <span class="preview-label">{{ parseError ? $t('cron.builder.invalidExpr') : $t('cron.builder.preview') }}</span>
        <code class="preview-expr">{{ modelValue || '—' }}</code>
      </div>
      <p v-if="!parseError && description" class="preview-desc">{{ description }}</p>
      <p v-if="parseError" class="preview-error">{{ parseError }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  Sliders as SlidersIcon,
  Code as CodeIcon,
  Clock as ClockIcon,
  AlertCircle as AlertCircleIcon,
} from 'lucide-vue-next'

interface Props {
  modelValue: string
}

interface Emits {
  (e: 'update:modelValue', value: string): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()
const { t } = useI18n()

// State
const mode = ref<'simple' | 'advanced'>('simple')
const frequency = ref('day')
const minuteInterval = ref(5)
const hourInterval = ref(1)
const atMinute = ref(0)
const atHour = ref(9)
const selectedWeekdays = ref<number[]>([1]) // Monday
const monthDay = ref(1)
const rawExpression = ref(props.modelValue || '')
const parseError = ref('')

const weekdayLabels = computed(() => [
  t('cron.builder.sun'),
  t('cron.builder.mon'),
  t('cron.builder.tue'),
  t('cron.builder.wed'),
  t('cron.builder.thu'),
  t('cron.builder.fri'),
  t('cron.builder.sat'),
])

const presets = computed(() => [
  { label: t('cron.presets.everyMinute'), value: '* * * * *' },
  { label: t('cron.presets.every5Minutes'), value: '*/5 * * * *' },
  { label: t('cron.presets.every15Minutes'), value: '*/15 * * * *' },
  { label: t('cron.presets.everyHour'), value: '0 * * * *' },
  { label: t('cron.presets.everyDay'), value: '0 9 * * *' },
  { label: t('cron.presets.everyWeek'), value: '0 9 * * 1' },
  { label: t('cron.presets.everyMonth'), value: '0 9 1 * *' },
])

// Human-readable description
const description = computed(() => {
  const expr = props.modelValue
  if (!expr) return ''
  return describeCron(expr)
})

function describeCron(expr: string): string {
  const parts = expr.trim().split(/\s+/)
  if (parts.length !== 5) return ''
  const [min, hour, day, month, weekday] = parts

  // Common patterns
  if (expr === '* * * * *') return t('cron.patterns.everyMinute')
  if (min.startsWith('*/') && hour === '*' && day === '*' && month === '*' && weekday === '*') {
    return t('cron.patterns.everyNMinutes', { n: min.slice(2) })
  }
  if (min !== '*' && hour === '*' && day === '*' && month === '*' && weekday === '*') {
    if (hour === '*') {
      return t('cron.builder.descEveryHourAt', { minute: min.padStart(2, '0') })
    }
  }
  if (hour.startsWith('*/') && day === '*' && month === '*' && weekday === '*') {
    return t('cron.patterns.everyNHours', { n: hour.slice(2) }) + ` ${t('cron.builder.descAtMinute', { minute: min.padStart(2, '0') })}`
  }

  let desc = ''
  // Day/week/month
  if (day !== '*' && month === '*' && weekday === '*') {
    desc = t('cron.builder.descMonthlyOn', { day })
  } else if (weekday !== '*' && day === '*') {
    const names = [t('cron.builder.sun'), t('cron.builder.mon'), t('cron.builder.tue'), t('cron.builder.wed'), t('cron.builder.thu'), t('cron.builder.fri'), t('cron.builder.sat')]
    const days = weekday.split(',').map(d => names[parseInt(d)] || d).join(', ')
    desc = t('cron.builder.descWeeklyOn', { days })
  } else if (day === '*' && month === '*' && weekday === '*') {
    desc = t('cron.builder.descDaily')
  }

  // Time
  if (hour !== '*' && !hour.startsWith('*/') && min !== '*') {
    desc += ` ${hour.padStart(2, '0')}:${min.padStart(2, '0')}`
  }

  return desc.trim() || expr
}

// Toggle weekday
function toggleWeekday(idx: number) {
  const i = selectedWeekdays.value.indexOf(idx)
  if (i >= 0) {
    if (selectedWeekdays.value.length > 1) {
      selectedWeekdays.value.splice(i, 1)
    }
  } else {
    selectedWeekdays.value.push(idx)
    selectedWeekdays.value.sort()
  }
  buildExpression()
}

// Build cron expression from simple mode fields
function buildExpression() {
  let expr = ''
  switch (frequency.value) {
    case 'minute':
      expr = minuteInterval.value === 1 ? '* * * * *' : `*/${minuteInterval.value} * * * *`
      break
    case 'hour':
      expr = hourInterval.value === 1
        ? `${atMinute.value} * * * *`
        : `${atMinute.value} */${hourInterval.value} * * *`
      break
    case 'day':
      expr = `${atMinute.value} ${atHour.value} * * *`
      break
    case 'week':
      expr = `${atMinute.value} ${atHour.value} * * ${selectedWeekdays.value.join(',')}`
      break
    case 'month':
      expr = `${atMinute.value} ${atHour.value} ${monthDay.value} * *`
      break
  }
  parseError.value = ''
  emit('update:modelValue', expr)
  rawExpression.value = expr
}

// Parse existing expression into simple mode fields
function parseExpression(expr: string) {
  if (!expr) return
  const parts = expr.trim().split(/\s+/)
  if (parts.length !== 5) {
    parseError.value = t('cron.errors.scheduleInvalid')
    return
  }
  parseError.value = ''
  const [min, hour, day, month, weekday] = parts

  // Try to detect frequency
  if (min.startsWith('*/') && hour === '*' && day === '*' && weekday === '*') {
    frequency.value = 'minute'
    minuteInterval.value = parseInt(min.slice(2)) || 5
  } else if (min === '*' && hour === '*' && day === '*' && weekday === '*') {
    frequency.value = 'minute'
    minuteInterval.value = 1
  } else if (hour === '*' || hour.startsWith('*/')) {
    frequency.value = 'hour'
    atMinute.value = min === '*' ? 0 : parseInt(min) || 0
    hourInterval.value = hour.startsWith('*/') ? (parseInt(hour.slice(2)) || 1) : 1
  } else if (day === '*' && weekday !== '*') {
    frequency.value = 'week'
    atMinute.value = parseInt(min) || 0
    atHour.value = parseInt(hour) || 9
    selectedWeekdays.value = weekday.split(',').map(d => parseInt(d)).filter(d => !isNaN(d))
    if (selectedWeekdays.value.length === 0) selectedWeekdays.value = [1]
  } else if (day !== '*' && weekday === '*') {
    frequency.value = 'month'
    atMinute.value = parseInt(min) || 0
    atHour.value = parseInt(hour) || 9
    monthDay.value = parseInt(day) || 1
  } else {
    frequency.value = 'day'
    atMinute.value = parseInt(min) || 0
    atHour.value = parseInt(hour) || 9
  }
}

function onFrequencyChange() {
  buildExpression()
}

function onRawInput() {
  const parts = rawExpression.value.trim().split(/\s+/)
  if (parts.length === 5) {
    parseError.value = ''
    emit('update:modelValue', rawExpression.value.trim())
    parseExpression(rawExpression.value.trim())
  } else if (rawExpression.value.trim()) {
    parseError.value = t('cron.errors.scheduleInvalid')
  }
}

function applyPreset(value: string) {
  rawExpression.value = value
  emit('update:modelValue', value)
  parseExpression(value)
}

// Watch for external changes
watch(() => props.modelValue, (val) => {
  if (val && val !== rawExpression.value) {
    rawExpression.value = val
    parseExpression(val)
  }
})

// Init
onMounted(() => {
  if (props.modelValue) {
    rawExpression.value = props.modelValue
    parseExpression(props.modelValue)
  } else {
    buildExpression()
  }
})
</script>

<style scoped>
.cron-builder {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* Mode Toggle */
.mode-toggle {
  display: flex !important;
  gap: 2px !important;
  padding: 3px !important;
  background: var(--color-bg-tertiary, #f3f4f6) !important;
  border-radius: 8px !important;
  border: 1px solid var(--color-border-primary, #e5e7eb) !important;
}

.mode-btn {
  flex: 1 !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  gap: 6px !important;
  padding: 7px 12px !important;
  border: none !important;
  border-radius: 6px !important;
  background: transparent !important;
  color: var(--color-text-secondary, #6b7280) !important;
  font-size: 12px !important;
  font-weight: 500 !important;
  cursor: pointer !important;
  transition: all 0.2s !important;
  min-width: auto !important;
  box-shadow: none !important;
  line-height: 1.4 !important;
}

.mode-btn:hover {
  color: var(--color-text-primary, #111827) !important;
  background: transparent !important;
  transform: none !important;
}

.mode-btn.active {
  background: var(--color-bg-primary, #fff) !important;
  color: var(--color-primary, #3b82f6) !important;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1) !important;
}

/* Simple Mode */
.simple-mode {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.field-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.field-label {
  font-size: 13px !important;
  font-weight: 500 !important;
  color: var(--color-text-secondary, #6b7280) !important;
  min-width: 70px;
  flex-shrink: 0;
}

.field-select {
  padding: 7px 28px 7px 10px !important;
  border: 1px solid var(--color-border-primary, #e5e7eb) !important;
  border-radius: 6px !important;
  background-color: var(--color-bg-primary, #fff) !important;
  color: var(--color-text-primary, #111827) !important;
  font-size: 13px !important;
  cursor: pointer !important;
  transition: border-color 0.2s, box-shadow 0.2s !important;
  -webkit-appearance: none !important;
  -moz-appearance: none !important;
  appearance: none !important;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%236b7280' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E") !important;
  background-repeat: no-repeat !important;
  background-position: right 8px center !important;
  min-width: auto !important;
  box-shadow: none !important;
  line-height: 1.4 !important;
}

.field-select:focus {
  outline: none !important;
  border-color: var(--color-primary, #3b82f6) !important;
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.15) !important;
}

.field-select.narrow {
  width: 80px !important;
}

.field-suffix {
  font-size: 13px;
  color: var(--color-text-secondary, #6b7280);
}

/* Time Picker */
.time-picker {
  display: flex;
  align-items: center;
  gap: 4px;
}

.time-sep {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-secondary, #6b7280);
  line-height: 1;
}

/* Weekday Picker */
.weekday-picker {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.weekday-btn {
  width: 34px !important;
  height: 34px !important;
  min-width: 34px !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  border: 1px solid var(--color-border-primary, #e5e7eb) !important;
  border-radius: 50% !important;
  background: var(--color-bg-primary, #fff) !important;
  color: var(--color-text-secondary, #6b7280) !important;
  font-size: 11px !important;
  font-weight: 600 !important;
  cursor: pointer !important;
  transition: all 0.2s !important;
  padding: 0 !important;
  box-shadow: none !important;
  line-height: 1 !important;
}

.weekday-btn:hover {
  border-color: var(--color-primary, #3b82f6) !important;
  color: var(--color-primary, #3b82f6) !important;
  background: var(--color-bg-primary, #fff) !important;
  transform: none !important;
}

.weekday-btn.active {
  background: var(--color-primary, #3b82f6) !important;
  border-color: var(--color-primary, #3b82f6) !important;
  color: #fff !important;
}

/* Advanced Mode */
.advanced-mode {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.cron-raw-input {
  width: 100% !important;
  padding: 9px 12px !important;
  border: 1px solid var(--color-border-primary, #e5e7eb) !important;
  border-radius: 6px !important;
  background: var(--color-bg-primary, #fff) !important;
  color: var(--color-text-primary, #111827) !important;
  font-size: 14px !important;
  font-family: var(--font-mono, 'SF Mono', 'Fira Code', monospace) !important;
  letter-spacing: 1px !important;
  transition: border-color 0.2s, box-shadow 0.2s !important;
  box-sizing: border-box !important;
}

.cron-raw-input:focus {
  outline: none !important;
  border-color: var(--color-primary, #3b82f6) !important;
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.15) !important;
}

.cron-hint {
  font-size: 11px;
  color: var(--color-text-tertiary, #9ca3af);
  margin: 0;
}

.quick-presets {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.preset-chip {
  padding: 4px 10px !important;
  border: 1px solid var(--color-border-primary, #e5e7eb) !important;
  border-radius: 20px !important;
  background: var(--color-bg-tertiary, #f3f4f6) !important;
  color: var(--color-text-secondary, #6b7280) !important;
  font-size: 11px !important;
  font-weight: 500 !important;
  cursor: pointer !important;
  transition: all 0.2s !important;
  min-width: auto !important;
  box-shadow: none !important;
  line-height: 1.4 !important;
}

.preset-chip:hover {
  border-color: var(--color-primary, #3b82f6) !important;
  color: var(--color-primary, #3b82f6) !important;
  background: var(--color-bg-tertiary, #f3f4f6) !important;
  transform: none !important;
}

.preset-chip.active {
  background: var(--color-primary, #3b82f6) !important;
  border-color: var(--color-primary, #3b82f6) !important;
  color: #fff !important;
}

/* Expression Preview */
.expression-preview {
  padding: 10px 12px;
  border-radius: 6px;
  background: rgba(59, 130, 246, 0.06);
  border: 1px solid rgba(59, 130, 246, 0.2);
}

.expression-preview.error {
  background: rgba(239, 68, 68, 0.06);
  border-color: rgba(239, 68, 68, 0.3);
}

.preview-header {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--color-primary, #3b82f6);
  font-size: 12px;
  font-weight: 500;
}

.expression-preview.error .preview-header {
  color: var(--color-error, #ef4444);
}

.preview-label {
  flex-shrink: 0;
}

.preview-expr {
  margin-left: auto;
  font-family: var(--font-mono, monospace);
  font-size: 12px;
  padding: 2px 8px;
  background: rgba(59, 130, 246, 0.1);
  border-radius: 4px;
  letter-spacing: 1px;
  color: inherit;
}

.expression-preview.error .preview-expr {
  background: rgba(239, 68, 68, 0.1);
}

.preview-desc {
  margin: 6px 0 0;
  font-size: 13px;
  color: var(--color-text-primary, #111827);
  font-weight: 500;
}

.preview-error {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--color-error, #ef4444);
}

/* ===== Dark mode (cyberpunk theme) ===== */
:root[data-theme="dark"] .mode-toggle {
  background: rgba(255, 255, 255, 0.04) !important;
  border-color: #152035 !important;
}

:root[data-theme="dark"] .mode-btn {
  color: #7a9ab0 !important;
}

:root[data-theme="dark"] .mode-btn:hover {
  color: #d0e8f0 !important;
}

:root[data-theme="dark"] .mode-btn.active {
  background: rgba(0, 240, 255, 0.08) !important;
  color: #00f0ff !important;
  box-shadow: 0 0 6px rgba(0, 240, 255, 0.1) !important;
}

:root[data-theme="dark"] .field-label {
  color: #7a9ab0 !important;
}

:root[data-theme="dark"] .field-select {
  background-color: #0a0e1a !important;
  border-color: #152035 !important;
  color: #d0e8f0 !important;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%237a9ab0' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E") !important;
}

:root[data-theme="dark"] .field-select:focus {
  border-color: #00f0ff !important;
  box-shadow: 0 0 0 2px rgba(0, 240, 255, 0.1) !important;
}

:root[data-theme="dark"] .field-suffix {
  color: #7a9ab0;
}

:root[data-theme="dark"] .time-sep {
  color: #7a9ab0;
}

:root[data-theme="dark"] .weekday-btn {
  background: #0a0e1a !important;
  border-color: #152035 !important;
  color: #7a9ab0 !important;
}

:root[data-theme="dark"] .weekday-btn:hover {
  border-color: rgba(0, 240, 255, 0.4) !important;
  color: #00f0ff !important;
  background: #0a0e1a !important;
}

:root[data-theme="dark"] .weekday-btn.active {
  background: rgba(0, 240, 255, 0.15) !important;
  border-color: #00f0ff !important;
  color: #00f0ff !important;
}

:root[data-theme="dark"] .cron-raw-input {
  background: #0a0e1a !important;
  border-color: #152035 !important;
  color: #d0e8f0 !important;
}

:root[data-theme="dark"] .cron-raw-input:focus {
  border-color: #00f0ff !important;
  box-shadow: 0 0 0 2px rgba(0, 240, 255, 0.1) !important;
}

:root[data-theme="dark"] .cron-hint {
  color: #4a6578;
}

:root[data-theme="dark"] .preset-chip {
  background: rgba(255, 255, 255, 0.04) !important;
  border-color: #152035 !important;
  color: #7a9ab0 !important;
}

:root[data-theme="dark"] .preset-chip:hover {
  border-color: rgba(0, 240, 255, 0.4) !important;
  color: #00f0ff !important;
  background: rgba(0, 240, 255, 0.05) !important;
}

:root[data-theme="dark"] .preset-chip.active {
  background: rgba(0, 240, 255, 0.15) !important;
  border-color: #00f0ff !important;
  color: #00f0ff !important;
}

:root[data-theme="dark"] .expression-preview {
  background: rgba(0, 240, 255, 0.04);
  border-color: rgba(0, 240, 255, 0.12);
}

:root[data-theme="dark"] .expression-preview.error {
  background: rgba(255, 45, 111, 0.06);
  border-color: rgba(255, 45, 111, 0.2);
}

:root[data-theme="dark"] .preview-header {
  color: #00f0ff;
}

:root[data-theme="dark"] .expression-preview.error .preview-header {
  color: #ff2d6f;
}

:root[data-theme="dark"] .preview-expr {
  background: rgba(0, 240, 255, 0.08);
  color: #00f0ff;
}

:root[data-theme="dark"] .expression-preview.error .preview-expr {
  background: rgba(255, 45, 111, 0.1);
  color: #ff2d6f;
}

:root[data-theme="dark"] .preview-desc {
  color: #d0e8f0;
}

:root[data-theme="dark"] .preview-error {
  color: #ff2d6f;
}
</style>
