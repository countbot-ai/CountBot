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
@import './styles/CronBuilder.css';
</style>
