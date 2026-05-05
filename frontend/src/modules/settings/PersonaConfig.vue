<template>
  <div class="persona-config">
    <div class="section-header">
      <h3 class="section-title">
        {{ $t('settings.persona.title') }}
      </h3>
      <p class="section-desc">
        {{ $t('settings.persona.description') }}
      </p>
    </div>

    <!-- 基础信息 -->
    <div class="config-section">
      <div class="section-label">
        <component :is="UserIcon" :size="18" class="label-icon" />
        <span>{{ $t('settings.persona.basicInfo') }}</span>
      </div>
      
      <div class="form-grid">
        <div class="form-group">
          <label class="label">{{ $t('settings.persona.aiName') }}</label>
          <input
            v-model="localPersona.ai_name"
            type="text"
            class="input"
            :placeholder="$t('settings.persona.aiNamePlaceholder')"
            maxlength="50"
          />
          <p class="hint">{{ $t('settings.persona.aiNameHint') }}</p>
        </div>

        <div class="form-group">
          <label class="label">{{ $t('settings.persona.userName') }}</label>
          <input
            v-model="localPersona.user_name"
            type="text"
            class="input"
            :placeholder="$t('settings.persona.userNamePlaceholder')"
            maxlength="50"
          />
          <p class="hint">{{ $t('settings.persona.userNameHint') }}</p>
        </div>
      </div>

      <div class="form-group full-width">
        <label class="label">
          {{ $t('settings.persona.userAddress') }}
          <span class="optional-badge">{{ $t('common.optional') }}</span>
        </label>
        <input
          v-model="localPersona.user_address"
          type="text"
          class="input"
          :placeholder="$t('settings.persona.userAddressPlaceholder')"
          maxlength="200"
        />
        <p class="hint">{{ $t('settings.persona.userAddressHint') }}</p>
      </div>

      <div class="form-group full-width">
        <label class="label">{{ $t('settings.general.outputLanguage') }}</label>
        <input
          v-model="localPersona.output_language"
          type="text"
          class="input"
          :placeholder="$t('settings.general.outputLanguagePlaceholder')"
          maxlength="50"
        />
        <p class="hint">{{ $t('settings.general.outputLanguageDesc') }}</p>
      </div>
    </div>

    <!-- AI性格配置 -->
    <div class="config-section">
      <div class="section-label">
        <component :is="SparklesIcon" :size="18" class="label-icon" />
        <span>{{ $t('settings.persona.personalityTitle') }}</span>
      </div>
      <p class="section-hint">{{ $t('settings.persona.personalityHint') }}</p>

      <div v-if="loadingPersonalities" class="loading-personalities">
        <div class="spinner"></div>
        <p>{{ $t('common.loading') }}</p>
      </div>
      <div v-else class="personality-grid">
        <button
          v-for="p in personalities"
          :key="p.id"
          class="personality-btn"
          :class="{ active: localPersona.personality === p.id }"
          @click="selectPersonality(p.id)"
        >
          <component :is="p.icon" :size="20" class="personality-icon" />
          <div class="personality-content">
            <div class="personality-name">{{ $t(`settings.persona.personalities.${p.id}`, p.name) }}</div>
            <div class="personality-desc">{{ $t(`settings.persona.personalityDesc.${p.id}`, '') }}</div>
          </div>
          <div v-if="localPersona.personality === p.id" class="check-icon">
            <component :is="CheckIcon" :size="16" />
          </div>
        </button>
      </div>

      <!-- 自定义性格 -->
      <transition name="expand">
        <div v-if="localPersona.personality === 'custom'" class="custom-personality">
          <label class="label">{{ $t('settings.persona.customPersonality') }}</label>
          <textarea
            v-model="localPersona.custom_personality"
            class="textarea"
            :placeholder="$t('settings.persona.customPersonalityPlaceholder')"
            rows="4"
            maxlength="500"
          />
          <div class="textarea-footer">
            <p class="hint">{{ $t('settings.persona.customPersonalityHint') }}</p>
            <span class="char-count">{{ localPersona.custom_personality?.length || 0 }}/500</span>
          </div>
        </div>
      </transition>
    </div>

    <!-- 对话历史设置 -->
    <div class="config-section">
      <div class="section-label">
        <component :is="MessageSquareIcon" :size="18" class="label-icon" />
        <span>{{ $t('settings.persona.historyTitle') }}</span>
      </div>
      <p class="section-hint">{{ $t('settings.persona.historyHint') }}</p>

      <div class="slider-container">
        <div class="slider-header">
          <label class="label">{{ $t('settings.persona.maxHistoryMessages') }}</label>
          <div class="slider-value">
            {{ historyDisplayValue }}
          </div>
        </div>
        <input
          v-if="!isUnlimitedHistory"
          v-model.number="localPersona.max_history_messages"
          type="range"
          min="5"
          max="200"
          step="5"
          class="slider"
        />
        <div v-if="!isUnlimitedHistory" class="slider-marks">
          <span>5</span>
          <span>50</span>
          <span>100</span>
          <span>200</span>
        </div>
        <div v-else class="unlimited-notice">
          <component :is="Infinity" :size="20" />
          <span>{{ $t('settings.persona.unlimitedNotice') }}</span>
        </div>
      </div>

      <!-- 快速预设 -->
      <div class="presets-container">
        <label class="label">{{ $t('settings.persona.quickPresets') }}</label>
        <div class="preset-buttons">
          <button
            v-for="preset in presets"
            :key="preset.value"
            class="preset-btn"
            :class="{ active: localPersona.max_history_messages === preset.value }"
            @click="applyPreset(preset.value)"
          >
            <component :is="preset.icon" :size="16" />
            <span>{{ $t(`settings.persona.preset.${preset.label}`) }}</span>
            <span class="preset-value">{{ formatPresetValue(preset.value) }}</span>
          </button>
        </div>
      </div>

      <div class="form-group toggle-group">
        <label class="toggle-label">
          <div class="toggle-content">
            <span class="toggle-text">{{ $t('settings.persona.enableShortContextSummary') }}</span>
            <span class="toggle-hint">{{ $t('settings.persona.enableShortContextSummaryHint') }}</span>
            <span v-if="isUnlimitedHistory" class="toggle-hint">
              {{ $t('settings.persona.enableShortContextSummaryUnlimitedHint') }}
            </span>
          </div>
          <SwitchToggle
            v-model="localPersona.enable_short_context_summary"
            :width="48"
            :height="28"
            :aria-label="$t('settings.persona.enableShortContextSummary')"
          />
        </label>
      </div>

      <!-- Token估算 -->
      <div class="token-estimate">
        <div class="estimate-header">
          <component :is="ZapIcon" :size="18" />
          <span>{{ $t('settings.persona.tokenEstimate') }}</span>
        </div>
        <div class="estimate-grid">
          <div class="estimate-item">
            <span class="estimate-label">{{ $t('settings.persona.estimatedTokens') }}</span>
            <span class="estimate-value">{{ typeof estimatedTokens === 'number' ? `~${estimatedTokens.toLocaleString()}` : estimatedTokens }}</span>
          </div>
          <div class="estimate-item">
            <span class="estimate-label">{{ $t('settings.persona.savingsVs100') }}</span>
            <span class="estimate-value" :class="savingsClass">{{ savingsText }}</span>
          </div>
        </div>
      </div>
    </div>
    <!-- 主动问候设置 -->
    <div class="config-section">
      <div class="section-label">
        <component :is="BellIcon" :size="18" class="label-icon" />
        <span>{{ $t('settings.persona.heartbeat.title') }}</span>
      </div>
      <p class="section-hint">{{ $t('settings.persona.heartbeat.description') }}</p>

      <!-- 启用开关 -->
      <div class="form-group toggle-group">
        <label class="toggle-label">
          <div class="toggle-content">
            <span class="toggle-text">{{ $t('settings.persona.heartbeat.enabled') }}</span>
            <span class="toggle-hint">{{ $t('settings.persona.heartbeat.enabledHint') }}</span>
          </div>
          <SwitchToggle
            v-model="localPersona.heartbeat.enabled"
            :width="48"
            :height="28"
            :aria-label="$t('settings.persona.heartbeat.enabled')"
          />
        </label>
      </div>

      <!-- 启用后显示详细配置 -->
      <transition name="expand">
        <div v-if="localPersona.heartbeat.enabled" class="heartbeat-details">
          <!-- 渠道选择 -->
          <div class="form-grid">
            <div class="form-group">
              <label class="label">{{ $t('settings.persona.heartbeat.channel') }}</label>
              <select v-model="localPersona.heartbeat.channel" class="input">
                <option value="">{{ $t('settings.persona.heartbeat.channelPlaceholder') }}</option>
                <option value="feishu">{{ $t('settings.persona.heartbeat.channelNames.feishu') }}</option>
                <option value="telegram">{{ $t('settings.persona.heartbeat.channelNames.telegram') }}</option>
                <option value="dingtalk">{{ $t('settings.persona.heartbeat.channelNames.dingtalk') }}</option>
                <option value="wecom">{{ $t('settings.persona.heartbeat.channelNames.wecom') }}</option>
                <option value="wechat">{{ $t('settings.persona.heartbeat.channelNames.wechat') }}</option>
                <option value="qq">{{ $t('settings.persona.heartbeat.channelNames.qq') }}</option>
              </select>
            </div>

            <div v-if="showHeartbeatAccountId" class="form-group">
              <label class="label">{{ $t('settings.persona.heartbeat.accountId') }}</label>
              <input
                v-model="localPersona.heartbeat.account_id"
                type="text"
                class="input"
                :placeholder="$t('settings.persona.heartbeat.accountIdPlaceholder')"
              />
              <p class="hint">{{ $t('settings.persona.heartbeat.accountIdHint') }}</p>
            </div>

            <div v-else-if="localPersona.heartbeat.channel" class="form-group">
              <label class="label">{{ $t('settings.persona.heartbeat.accountId') }}</label>
              <div class="auto-account-notice">
                <span class="auto-account-value">default</span>
                <p class="hint">{{ $t('settings.persona.heartbeat.accountIdAutoHint') }}</p>
              </div>
            </div>

            <div class="form-group">
              <label class="label">{{ $t('settings.persona.heartbeat.chatId') }}</label>
              <input
                v-model="localPersona.heartbeat.chat_id"
                type="text"
                class="input"
                :placeholder="$t('settings.persona.heartbeat.chatIdPlaceholder')"
              />
              <p class="hint">{{ $t('settings.persona.heartbeat.chatIdHint') }}</p>
            </div>
          </div>

          <!-- 空闲阈值 -->
          <div class="form-group">
            <label class="label">{{ $t('settings.persona.heartbeat.idleThreshold') }}</label>
            <div class="inline-field">
              <input
                v-model.number="localPersona.heartbeat.idle_threshold_hours"
                type="number"
                class="input narrow-input"
                min="1"
                max="24"
              />
              <span class="field-suffix">{{ $t('settings.persona.heartbeat.hours') }}</span>
            </div>
            <p class="hint">{{ $t('settings.persona.heartbeat.idleThresholdHint') }}</p>
          </div>

          <!-- 每日问候次数 -->
          <div class="form-group">
            <label class="label">{{ $t('settings.persona.heartbeat.maxGreetsPerDay') }}</label>
            <div class="inline-field">
              <input
                v-model.number="localPersona.heartbeat.max_greets_per_day"
                type="number"
                class="input narrow-input"
                min="1"
                max="5"
              />
              <span class="field-suffix">{{ $t('settings.persona.heartbeat.timesPerDay') }}</span>
            </div>
            <p class="hint">{{ $t('settings.persona.heartbeat.maxGreetsPerDayHint') }}</p>
          </div>

          <!-- 免打扰时段 -->
          <div class="form-group">
            <label class="label">{{ $t('settings.persona.heartbeat.quietTime') }}</label>
            <div class="inline-field">
              <span class="field-suffix">{{ $t('settings.persona.heartbeat.quietStart') }}</span>
              <select v-model.number="localPersona.heartbeat.quiet_start" class="input narrow-input">
                <option v-for="h in 24" :key="h - 1" :value="h - 1">{{ String(h - 1).padStart(2, '0') }}:00</option>
              </select>
              <span class="field-suffix">{{ $t('settings.persona.heartbeat.quietEnd') }}</span>
              <select v-model.number="localPersona.heartbeat.quiet_end" class="input narrow-input">
                <option v-for="h in 24" :key="h - 1" :value="h - 1">{{ String(h - 1).padStart(2, '0') }}:00</option>
              </select>
            </div>
            <p class="hint">{{ $t('settings.persona.heartbeat.quietTimeHint') }}</p>
          </div>

          <!-- 未配置渠道提示 -->
          <div v-if="!localPersona.heartbeat.channel || !localPersona.heartbeat.chat_id" class="warning-notice">
            <component :is="AlertCircleIcon" :size="16" />
            <span>{{ $t('settings.persona.heartbeat.notConfigured') }}</span>
          </div>
        </div>
      </transition>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import SwitchToggle from '@/components/ui/SwitchToggle.vue'
import { 
  User as UserIcon,
  Sparkles as SparklesIcon,
  MessageSquare as MessageSquareIcon,
  Zap as ZapIcon,
  Check as CheckIcon,
  Bell as BellIcon,
  AlertCircle as AlertCircleIcon,
  Briefcase,
  Smile,
  Laugh,
  Snowflake,
  TrendingUp,
  Frown,
  Clock,
  Target,
  Gamepad2,
  BookOpen,
  Edit3,
  Heart,
  CloudLightning,
  Infinity
} from 'lucide-vue-next'
import { useSettingsStore } from '@/store/settings'
import { useChannelsStore } from '@/store/channels'
import { personalitiesApi } from '@/api/personalities'

const { t } = useI18n()
const settingsStore = useSettingsStore()
const channelsStore = useChannelsStore()

interface HeartbeatConfig {
  enabled: boolean
  channel: string
  account_id: string
  chat_id: string
  schedule: string
  idle_threshold_hours: number
  quiet_start: number
  quiet_end: number
  max_greets_per_day?: number
}

interface PersonaConfig {
  ai_name: string
  user_name: string
  user_address: string
  output_language: string
  personality: string
  custom_personality: string
  max_history_messages: number
  enable_short_context_summary: boolean
  heartbeat: HeartbeatConfig
}

type PersonaConfigInput = Omit<Partial<PersonaConfig>, 'heartbeat'> & {
  heartbeat?: Partial<HeartbeatConfig>
}

const defaultHeartbeat = {
  enabled: false,
  channel: '',
  account_id: 'default',
  chat_id: '',
  schedule: '0 * * * *',
  idle_threshold_hours: 4,
  quiet_start: 21,
  quiet_end: 8,
  max_greets_per_day: 2,
}

const normalizeHistoryLimit = (value?: number | null) => {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return 0
  }
  return value <= 0 ? 0 : value
}

const createLocalPersonaState = (persona?: PersonaConfigInput): PersonaConfig => ({
  ai_name: persona?.ai_name ?? '',
  user_name: persona?.user_name ?? '',
  user_address: persona?.user_address || '',
  output_language: persona?.output_language || '中文',
  personality: persona?.personality ?? 'grumpy',
  custom_personality: persona?.custom_personality ?? '',
  max_history_messages: normalizeHistoryLimit(persona?.max_history_messages),
  enable_short_context_summary: persona?.enable_short_context_summary ?? false,
  heartbeat: {
    ...defaultHeartbeat,
    ...(persona?.heartbeat || {}),
  },
})

const localPersona = ref<PersonaConfig>(createLocalPersonaState(settingsStore.settings?.persona))

// 图标映射
const iconMap: Record<string, any> = {
  CloudLightning,
  Frown,
  Heart,
  Target,
  Snowflake,
  MessageSquare: MessageSquareIcon,
  BookOpen,
  Smile,
  Laugh,
  TrendingUp,
  Gamepad2,
  Clock,
  Edit3,
}

// 动态加载的性格列表
const personalities = ref<Array<{ id: string; icon: any; name: string }>>([])
const loadingPersonalities = ref(false)

// 加载性格列表
const loadPersonalities = async () => {
  loadingPersonalities.value = true
  try {
    const { personalities: data } = await personalitiesApi.list(true)
    personalities.value = data
      .filter(p => p.is_active)
      .map(p => ({
        id: p.id,
        icon: iconMap[p.icon] || Smile,
        name: p.name,
      }))
    // 添加自定义选项
    personalities.value.push({ id: 'custom', icon: Edit3, name: 'Custom' })
  } catch (error) {
    console.error('Failed to load personalities:', error)
    // 降级到默认列表
    personalities.value = [
      { id: 'grumpy', icon: CloudLightning, name: '暴躁' },
      { id: 'roast', icon: Frown, name: '吐槽' },
      { id: 'gentle', icon: Heart, name: '温柔' },
      { id: 'blunt', icon: Target, name: '直率' },
      { id: 'toxic', icon: Snowflake, name: '毒舌' },
      { id: 'chatty', icon: MessageSquareIcon, name: '话痨' },
      { id: 'philosopher', icon: BookOpen, name: '哲学' },
      { id: 'cute', icon: Smile, name: '可爱' },
      { id: 'humorous', icon: Laugh, name: '幽默' },
      { id: 'hyper', icon: TrendingUp, name: '兴奋' },
      { id: 'chuuni', icon: Gamepad2, name: '中二' },
      { id: 'zen', icon: Clock, name: '佛系' },
      { id: 'custom', icon: Edit3, name: '自定义' },
    ]
  } finally {
    loadingPersonalities.value = false
  }
}

onMounted(() => {
  loadPersonalities()
})

const hasConfiguredFields = (account: Record<string, any>) =>
  Object.entries(account || {}).some(([key, value]) => {
    if (['enabled', 'allow_from', 'account_id', 'draft_account_id', 'accounts'].includes(key)) {
      return false
    }
    if (Array.isArray(value)) {
      return value.length > 0
    }
    return Boolean(value)
  })

const getHeartbeatChannelAccountIds = (channelId: string) => {
  const normalizedChannelId = String(channelId || '').trim()
  if (!normalizedChannelId) {
    return []
  }

  const config = channelsStore.channels[normalizedChannelId]?.config || {}
  const statusInstances = channelsStore.status[normalizedChannelId]?.instances || {}
  const accountIds = new Set<string>()

  const addAccount = (accountId: string, account: Record<string, any> = {}, fromStatus = false) => {
    const normalizedAccountId = String(accountId || 'default').trim() || 'default'
    const configured = hasConfiguredFields(account)
    if (!configured && !account.enabled && !fromStatus) {
      return
    }
    accountIds.add(normalizedAccountId)
  }

  addAccount(String(config.account_id || 'default'), config)

  Object.entries(config.accounts || {}).forEach(([accountId, account]) => {
    addAccount(accountId, account as Record<string, any>)
  })

  Object.entries(statusInstances).forEach(([accountId, account]) => {
    addAccount(accountId, account as Record<string, any>, true)
  })

  return Array.from(accountIds).sort((left, right) => {
    if (left === 'default') return -1
    if (right === 'default') return 1
    return left.localeCompare(right)
  })
}

const heartbeatChannelAccountIds = computed(() =>
  getHeartbeatChannelAccountIds(localPersona.value.heartbeat.channel)
)

const showHeartbeatAccountId = computed(() => heartbeatChannelAccountIds.value.length > 1)

watch(
  [() => localPersona.value.heartbeat.channel, showHeartbeatAccountId],
  () => {
    if (!showHeartbeatAccountId.value && localPersona.value.heartbeat.account_id !== 'default') {
      localPersona.value.heartbeat.account_id = 'default'
    }
  },
  { immediate: true }
)

onMounted(async () => {
  try {
    if (!Object.keys(channelsStore.channels).length) {
      await channelsStore.fetchChannels()
    }
    if (!Object.keys(channelsStore.status).length) {
      await channelsStore.fetchStatus()
    }
  } catch (error) {
    console.warn('Failed to load channel metadata for heartbeat settings:', error)
  }
})

// 对话条数预设
const presets = [
  { label: 'minimal', value: 10, icon: Smile },
  { label: 'short', value: 30, icon: Briefcase },
  { label: 'medium', value: 50, icon: MessageSquareIcon },
  { label: 'long', value: 100, icon: Laugh },
  { label: 'extended', value: 200, icon: TrendingUp },
  { label: 'unlimited', value: 0, icon: Infinity }
]

const isUnlimitedHistory = computed(() => localPersona.value.max_history_messages <= 0)

const historyDisplayValue = computed(() =>
  isUnlimitedHistory.value
    ? t('settings.persona.unlimited')
    : localPersona.value.max_history_messages
)

// Token消耗估算（假设每条消息200 tokens）
const estimatedTokens = computed(() => {
  if (isUnlimitedHistory.value) {
    return '∞'
  }
  return localPersona.value.max_history_messages * 200
})

// 节省百分比
const savingsPercentage = computed(() => {
  if (isUnlimitedHistory.value) {
    return 'unlimited'
  }
  const baseline = 100 * 200
  const current = typeof estimatedTokens.value === 'number' ? estimatedTokens.value : 0
  return ((baseline - current) / baseline * 100).toFixed(0)
})

const savingsText = computed(() => {
  if (savingsPercentage.value === 'unlimited') {
    return '∞'
  }
  const savings = parseInt(savingsPercentage.value as string)
  if (savings > 0) {
    return `↓ ${savings}%`
  } else if (savings < 0) {
    return `↑ ${Math.abs(savings)}%`
  }
  return '0%'
})

const savingsClass = computed(() => {
  if (savingsPercentage.value === 'unlimited') {
    return 'unlimited'
  }
  const savings = parseInt(savingsPercentage.value as string)
  if (savings > 0) return 'positive'
  if (savings < 0) return 'negative'
  return 'neutral'
})

// 选择性格
const selectPersonality = (id: string) => {
  localPersona.value.personality = id
}

// 应用预设
const applyPreset = (value: number) => {
  localPersona.value.max_history_messages = normalizeHistoryLimit(value)
}

const formatPresetValue = (value: number) => (value <= 0 ? '∞' : String(value))

// 监听store变化
watch(
  () => settingsStore.settings?.persona,
  (newPersona) => {
    if (newPersona) {
      localPersona.value = createLocalPersonaState(newPersona)
    }
  },
  { immediate: true, deep: true }
)

// 监听本地变化并更新store（使用immediate: false避免递归）
let isUpdating = false
watch(
  localPersona,
  (newValue) => {
    if (!isUpdating && settingsStore.settings) {
      isUpdating = true
      settingsStore.settings.persona = {
        ...newValue,
        max_history_messages: normalizeHistoryLimit(newValue.max_history_messages),
        output_language: newValue.output_language || settingsStore.settings.persona.output_language || '中文'
      }
      setTimeout(() => {
        isUpdating = false
      }, 0)
    }
  },
  { deep: true }
)
</script>
<style scoped>
@import './styles/PersonaConfig.css';
</style>
