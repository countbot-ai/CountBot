<template>
  <div class="persona-config">
    <!-- 基础信息 -->
    <SettingsCard :title="$t('settings.persona.basicInfo')">
      <SettingsRow
        :label="$t('settings.persona.aiName')"
        :description="$t('settings.persona.aiNameHint')"
        wide-control
      >
        <input
          v-model="localPersona.ai_name"
          type="text"
          class="co-input"
          :placeholder="$t('settings.persona.aiNamePlaceholder')"
          maxlength="50"
        />
      </SettingsRow>

      <SettingsRow
        :label="$t('settings.persona.userName')"
        :description="$t('settings.persona.userNameHint')"
        wide-control
      >
        <input
          v-model="localPersona.user_name"
          type="text"
          class="co-input"
          :placeholder="$t('settings.persona.userNamePlaceholder')"
          maxlength="50"
        />
      </SettingsRow>

      <SettingsRow
        :description="$t('settings.persona.userAddressHint')"
        wide-control
      >
        <template #label>
          {{ $t('settings.persona.userAddress') }}
          <span class="optional-badge">{{ $t('common.optional') }}</span>
        </template>
        <input
          v-model="localPersona.user_address"
          type="text"
          class="co-input"
          :placeholder="$t('settings.persona.userAddressPlaceholder')"
          maxlength="200"
        />
      </SettingsRow>

      <SettingsRow
        :label="$t('settings.general.outputLanguage')"
        :description="$t('settings.general.outputLanguageDesc')"
        wide-control
      >
        <input
          v-model="localPersona.output_language"
          type="text"
          class="co-input"
          :placeholder="$t('settings.general.outputLanguagePlaceholder')"
          maxlength="50"
        />
      </SettingsRow>
    </SettingsCard>

    <!-- AI性格配置 -->
    <SettingsCard
      :title="$t('settings.persona.personalityTitle')"
      :description="$t('settings.persona.personalityHint')"
    >
      <div v-if="loadingPersonalities" class="loading-personalities">
        <div class="spinner"></div>
        <p>{{ $t('common.loading') }}</p>
      </div>
      <SettingsRow v-else layout="block">
        <div class="personality-grid">
          <div
            v-for="p in personalities"
            :key="p.id"
            class="personality-btn"
            :class="{ active: localPersona.personality === p.id }"
            role="button"
            tabindex="0"
            @click="selectPersonality(p.id)"
            @keydown.enter.prevent="selectPersonality(p.id)"
          >
            <component :is="p.icon" :size="20" class="personality-icon" />
            <div class="personality-content">
              <!-- 内置性格有翻译；用户自建（含克隆出来）的性格只有库里的文案 -->
              <div class="personality-name">
                <span>{{ p.isBuiltin ? $t(`settings.persona.personalities.${p.id}`, p.name) : p.name }}</span>
              </div>
              <div class="personality-desc">
                {{ p.isBuiltin ? $t(`settings.persona.personalityDesc.${p.id}`, p.description) : p.description }}
              </div>
            </div>
            <button
              v-if="!p.isBuiltin && p.id !== 'custom'"
              type="button"
              class="card-edit-btn"
              :title="$t('settings.persona.editPersonality')"
              @click.stop="openPersonalityEditor(p.id)"
            >
              <component :is="Edit3" :size="14" />
            </button>
            <div v-if="localPersona.personality === p.id" class="check-icon">
              <component :is="CheckIcon" :size="16" />
            </div>
          </div>
        </div>
      </SettingsRow>

      <!-- 自定义性格 -->
      <transition name="expand">
        <SettingsRow
          v-if="localPersona.personality === 'custom'"
          layout="block"
          :label="$t('settings.persona.customPersonality')"
        >
          <textarea
            v-model="localPersona.custom_personality"
            class="co-textarea"
            :placeholder="$t('settings.persona.customPersonalityPlaceholder')"
            rows="4"
            maxlength="500"
          />
          <div class="textarea-footer">
            <p class="hint">{{ $t('settings.persona.customPersonalityHint') }}</p>
            <span class="char-count">{{ localPersona.custom_personality?.length || 0 }}/500</span>
          </div>
        </SettingsRow>
      </transition>
    </SettingsCard>

    <!-- 对话历史设置 -->
    <SettingsCard
      :title="$t('settings.persona.historyTitle')"
      :description="$t('settings.persona.historyHint')"
    >
      <SettingsRow layout="block">
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
      </SettingsRow>

      <!-- 快速预设 -->
      <SettingsRow layout="block">
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
      </SettingsRow>

      <SettingsRow
        :label="$t('settings.persona.enableShortContextSummary')"
        :description="$t('settings.persona.enableShortContextSummaryHint')"
      >
        <SwitchToggle
          v-model="localPersona.enable_short_context_summary"
          :width="48"
          :height="28"
          :aria-label="$t('settings.persona.enableShortContextSummary')"
        />
        <template #below>
          <p v-if="isUnlimitedHistory" class="co-row-desc">
            {{ $t('settings.persona.enableShortContextSummaryUnlimitedHint') }}
          </p>
        </template>
      </SettingsRow>

      <!-- Token估算 -->
      <SettingsRow layout="block">
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
      </SettingsRow>
    </SettingsCard>

    <!-- 克隆人格的对话记忆：摘要按会话注入，避免新会话继承别的会话内容 -->
    <SettingsCard
      :title="$t('settings.persona.sessionMemoryTitle')"
      :description="$t('settings.persona.sessionMemoryHint')"
    >
      <SettingsRow
        :label="$t('settings.persona.sessionMemoryEnabled')"
        :description="$t('settings.persona.sessionMemoryEnabledHint')"
      >
        <SwitchToggle
          v-model="localPersona.session_memory.enabled"
          :width="48"
          :height="28"
          :aria-label="$t('settings.persona.sessionMemoryEnabled')"
        />
      </SettingsRow>

      <SettingsRow
        :label="$t('settings.persona.sessionMemoryScope')"
        :description="$t('settings.persona.sessionMemoryScopeHint')"
      >
        <select
          v-model="localPersona.session_memory.scope"
          class="co-select"
          :disabled="!localPersona.session_memory.enabled"
        >
          <option value="session">{{ $t('settings.persona.sessionMemoryScopeSession') }}</option>
          <option value="persona">{{ $t('settings.persona.sessionMemoryScopePersona') }}</option>
        </select>
        <template #below>
          <p v-if="!localPersona.session_memory.enabled" class="co-row-desc">
            {{ $t('settings.persona.sessionMemoryDisabledHint') }}
          </p>
        </template>
      </SettingsRow>
    </SettingsCard>

    <!-- 主动问候设置：推送走全局渠道配置，普通用户改这里不会生效 -->
    <SettingsCard
      v-if="!personaSource.isUserScoped.value"
      :title="$t('settings.persona.heartbeat.title')"
      :description="$t('settings.persona.heartbeat.description')"
    >
      <!-- 启用开关 -->
      <SettingsRow
        :label="$t('settings.persona.heartbeat.enabled')"
        :description="$t('settings.persona.heartbeat.enabledHint')"
      >
        <SwitchToggle
          v-model="localPersona.heartbeat.enabled"
          :width="48"
          :height="28"
          :aria-label="$t('settings.persona.heartbeat.enabled')"
        />
      </SettingsRow>

      <!-- 启用后显示详细配置 -->
      <transition name="expand">
        <div v-if="localPersona.heartbeat.enabled" class="heartbeat-details">
          <!-- 渠道选择 -->
          <SettingsRow
            :label="$t('settings.persona.heartbeat.channel')"
            wide-control
          >
            <select v-model="localPersona.heartbeat.channel" class="co-select">
              <option value="">{{ $t('settings.persona.heartbeat.channelPlaceholder') }}</option>
              <option value="feishu">{{ $t('settings.persona.heartbeat.channelNames.feishu') }}</option>
              <option value="telegram">{{ $t('settings.persona.heartbeat.channelNames.telegram') }}</option>
              <option value="dingtalk">{{ $t('settings.persona.heartbeat.channelNames.dingtalk') }}</option>
              <option value="wecom">{{ $t('settings.persona.heartbeat.channelNames.wecom') }}</option>
              <option value="wechat">{{ $t('settings.persona.heartbeat.channelNames.wechat') }}</option>
              <option value="qq">{{ $t('settings.persona.heartbeat.channelNames.qq') }}</option>
            </select>
          </SettingsRow>

          <SettingsRow
            v-if="showHeartbeatAccountId"
            :label="$t('settings.persona.heartbeat.accountId')"
            :description="$t('settings.persona.heartbeat.accountIdHint')"
            wide-control
          >
            <select v-model="localPersona.heartbeat.account_id" class="co-select">
              <option
                v-for="account in heartbeatAccountOptions"
                :key="account.accountId"
                :value="account.accountId"
              >
                {{ account.label }}
              </option>
            </select>
          </SettingsRow>

          <SettingsRow
            v-else-if="localPersona.heartbeat.channel"
            :label="$t('settings.persona.heartbeat.accountId')"
          >
            <div class="auto-account-notice">
              <span class="auto-account-value">default</span>
              <p class="hint">{{ $t('settings.persona.heartbeat.accountIdAutoHint') }}</p>
            </div>
          </SettingsRow>

          <SettingsRow
            :label="$t('settings.persona.heartbeat.chatId')"
            :description="$t('settings.persona.heartbeat.chatIdHint')"
            wide-control
          >
            <input
              v-model="localPersona.heartbeat.chat_id"
              type="text"
              class="co-input"
              :placeholder="$t('settings.persona.heartbeat.chatIdPlaceholder')"
            />
          </SettingsRow>

          <!-- 空闲阈值 -->
          <SettingsRow
            :label="$t('settings.persona.heartbeat.idleThreshold')"
            :description="$t('settings.persona.heartbeat.idleThresholdHint')"
            wide-control
          >
            <div class="inline-field">
              <input
                v-model.number="localPersona.heartbeat.idle_threshold_hours"
                type="number"
                class="co-input narrow-input"
                min="1"
                max="24"
              />
              <span class="field-suffix">{{ $t('settings.persona.heartbeat.hours') }}</span>
            </div>
          </SettingsRow>

          <!-- 每日问候次数 -->
          <SettingsRow
            :label="$t('settings.persona.heartbeat.maxGreetsPerDay')"
            :description="$t('settings.persona.heartbeat.maxGreetsPerDayHint')"
            wide-control
          >
            <div class="inline-field">
              <input
                v-model.number="localPersona.heartbeat.max_greets_per_day"
                type="number"
                class="co-input narrow-input"
                min="1"
                max="5"
              />
              <span class="field-suffix">{{ $t('settings.persona.heartbeat.timesPerDay') }}</span>
            </div>
          </SettingsRow>

          <!-- 免打扰时段 -->
          <SettingsRow
            :label="$t('settings.persona.heartbeat.quietTime')"
            :description="$t('settings.persona.heartbeat.quietTimeHint')"
            wide-control
          >
            <div class="inline-field">
              <span class="field-suffix">{{ $t('settings.persona.heartbeat.quietStart') }}</span>
              <select v-model.number="localPersona.heartbeat.quiet_start" class="co-select narrow-input">
                <option v-for="h in 24" :key="h - 1" :value="h - 1">{{ String(h - 1).padStart(2, '0') }}:00</option>
              </select>
              <span class="field-suffix">{{ $t('settings.persona.heartbeat.quietEnd') }}</span>
              <select v-model.number="localPersona.heartbeat.quiet_end" class="co-select narrow-input">
                <option v-for="h in 24" :key="h - 1" :value="h - 1">{{ String(h - 1).padStart(2, '0') }}:00</option>
              </select>
            </div>
          </SettingsRow>

          <!-- 未配置渠道提示 -->
          <div v-if="!localPersona.heartbeat.channel || !localPersona.heartbeat.chat_id" class="warning-notice">
            <component :is="AlertCircleIcon" :size="16" />
            <span>{{ $t('settings.persona.heartbeat.notConfigured') }}</span>
          </div>
        </div>
      </transition>
    </SettingsCard>

    <PersonalityEditDialog
      v-if="editingPersonality"
      :personality="editingPersonality"
      :is-new="false"
      @save="saveEditedPersonality"
      @cancel="editingPersonality = null"
    />

  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import SwitchToggle from '@/components/ui/SwitchToggle.vue'
import { SettingsCard, SettingsRow } from './ui'
import { 
  MessageSquare as MessageSquareIcon,
  Zap as ZapIcon,
  Check as CheckIcon,
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
  Infinity,
} from 'lucide-vue-next'
import { useSettingsStore } from '@/store/settings'
import { useChannelsStore } from '@/store/channels'
import { personalitiesApi, type Personality } from '@/api/personalities'
import { usePersonaSource } from '@/composables/usePersonaSource'
import { useToast } from '@/composables/useToast'
import PersonalityEditDialog from './PersonalityEditDialog.vue'

const { t } = useI18n()
const toast = useToast()
const settingsStore = useSettingsStore()
const channelsStore = useChannelsStore()
// 人设读写按身份分流：管理员用全局配置，普通用户用 /api/me/persona
const personaSource = usePersonaSource()

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

interface PersonaSessionMemoryConfig {
  enabled: boolean
  scope: 'session' | 'persona'
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
  session_memory: PersonaSessionMemoryConfig
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
  session_memory: {
    enabled: persona?.session_memory?.enabled ?? true,
    scope: persona?.session_memory?.scope === 'persona' ? 'persona' : 'session',
  },
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
const personalities = ref<
  Array<{ id: string; icon: any; name: string; description: string; isBuiltin: boolean }>
>([])
const loadingPersonalities = ref(false)
/** 保留接口返回的完整对象，编辑弹窗直接复用，避免再次请求 */
const personalityRecords = ref<Record<string, Personality>>({})
const editingPersonality = ref<Personality | null>(null)
// 加载性格列表
const loadPersonalities = async () => {
  loadingPersonalities.value = true
  try {
    const { personalities: data } = await personalitiesApi.list(true)
    personalityRecords.value = Object.fromEntries(
      data.filter(p => p.is_active).map(p => [p.id, p]),
    )
    personalities.value = data
      .filter(p => p.is_active)
      .map(p => ({
        id: p.id,
        icon: iconMap[p.icon] || Smile,
        name: p.name,
        description: p.description || '',
        isBuiltin: p.is_builtin,
      }))
    // 添加自定义选项
    personalities.value.push({
      id: 'custom',
      icon: Edit3,
      name: t('settings.persona.personalities.custom'),
      description: '',
      isBuiltin: false,
    })
  } catch (error) {
    console.error('Failed to load personalities:', error)
    personalityRecords.value = {}
    // 降级到默认列表：全部是内置项，走 i18n
    personalities.value = [
      { id: 'grumpy', icon: CloudLightning, name: '', isBuiltin: true },
      { id: 'roast', icon: Frown, name: '', isBuiltin: true },
      { id: 'gentle', icon: Heart, name: '', isBuiltin: true },
      { id: 'blunt', icon: Target, name: '', isBuiltin: true },
      { id: 'toxic', icon: Snowflake, name: '', isBuiltin: true },
      { id: 'chatty', icon: MessageSquareIcon, name: '', isBuiltin: true },
      { id: 'philosopher', icon: BookOpen, name: '', isBuiltin: true },
      { id: 'cute', icon: Smile, name: '', isBuiltin: true },
      { id: 'humorous', icon: Laugh, name: '', isBuiltin: true },
      { id: 'hyper', icon: TrendingUp, name: '', isBuiltin: true },
      { id: 'chuuni', icon: Gamepad2, name: '', isBuiltin: true },
      { id: 'zen', icon: Clock, name: '', isBuiltin: true },
    ].map(item => ({ ...item, description: '', isBuiltin: true }))
    personalities.value.push({
      id: 'custom',
      icon: Edit3,
      name: t('settings.persona.personalities.custom'),
      description: '',
      isBuiltin: false,
    })
  } finally {
    loadingPersonalities.value = false
  }
}

/** 直接打开当前性格的编辑弹窗，不用切到「性格编辑」标签 */
async function openPersonalityEditor(id: string) {
  try {
    editingPersonality.value = personalityRecords.value[id] || (await personalitiesApi.get(id))
  } catch (error: any) {
    console.error('Failed to load personality:', error)
    toast.error(error.message || t('settings.persona.loadFailed'))
  }
}

/** 保存卡片内编辑结果 */
async function saveEditedPersonality(personality: Personality) {
  try {
    await personalitiesApi.update(personality.id, {
      name: personality.name,
      description: personality.description,
      traits: personality.traits,
      speaking_style: personality.speaking_style,
      icon: personality.icon,
    })
    toast.success(t('settings.persona.updateSuccess'))
    editingPersonality.value = null
    await loadPersonalities()
  } catch (error: any) {
    console.error('Failed to save personality:', error)
    toast.error(error.message || t('settings.persona.saveFailed'))
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

const heartbeatAccountOptions = computed(() => {
  const channelId = localPersona.value.heartbeat.channel
  const config = (channelsStore.channels[channelId]?.config || {}) as Record<string, any>
  const accounts = (config.accounts || {}) as Record<string, Record<string, any>>
  const primaryAccountId = String(config.account_id || 'default')

  return heartbeatChannelAccountIds.value.map((accountId) => {
    const account = accountId === primaryAccountId ? config : (accounts[accountId] || {})
    const displayName = String(account.display_name || '').trim()
    return {
      accountId,
      label: displayName ? `${displayName}（${accountId}）` : accountId,
    }
  })
})

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

// 普通用户自行拉取人设，管理员由 store watch 回填；用 watch 因身份异步到位
watch(
  () => personaSource.isUserScoped.value,
  async (scoped) => {
    if (!scoped) return
    try {
      localPersona.value = createLocalPersonaState(
        (await personaSource.load()) as PersonaConfigInput,
      )
    } catch (error) {
      console.error('Failed to load persona:', error)
    }
  },
  { immediate: true },
)

// 监听store变化（管理员路径：设置页统一提交后回填）
watch(
  () => settingsStore.settings?.persona,
  (newPersona) => {
    if (!personaSource.isUserScoped.value && newPersona) {
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
    if (isUpdating) return
    const normalized = {
      ...newValue,
      max_history_messages: normalizeHistoryLimit(newValue.max_history_messages),
      output_language:
        newValue.output_language || settingsStore.settings?.persona?.output_language || '中文',
    }
    // 普通用户不依赖全局配置，避免写进一个不会被提交的 store
    if (personaSource.isUserScoped.value) {
      return
    }
    if (settingsStore.settings) {
      isUpdating = true
      settingsStore.settings.persona = normalized
      setTimeout(() => {
        isUpdating = false
      }, 0)
    }
  },
  { deep: true }
)

/** 保存人设：管理员已在 store 更新，普通用户需在此落库 */
async function saveConfig(): Promise<boolean> {
  const payload = {
    ...localPersona.value,
    max_history_messages: normalizeHistoryLimit(localPersona.value.max_history_messages),
  }
  await personaSource.save(payload as unknown as Record<string, unknown>)
  return true
}

defineExpose({ saveConfig })

</script>
<style scoped>
@import './styles/PersonaConfig.css';
</style>
