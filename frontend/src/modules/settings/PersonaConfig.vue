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
            <div class="personality-name">{{ $t(`settings.persona.personality.${p.id}`, p.name) }}</div>
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
            {{ localPersona.max_history_messages === -1 ? $t('settings.persona.unlimited') : localPersona.max_history_messages }}
          </div>
        </div>
        <input
          v-if="localPersona.max_history_messages !== -1"
          v-model.number="localPersona.max_history_messages"
          type="range"
          min="5"
          max="200"
          step="5"
          class="slider"
        />
        <div v-if="localPersona.max_history_messages !== -1" class="slider-marks">
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
            <span class="preset-value">{{ preset.value }}</span>
          </button>
        </div>
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
      <div class="form-group">
        <label class="heartbeat-toggle">
          <input
            v-model="localPersona.heartbeat.enabled"
            type="checkbox"
            class="form-checkbox"
          />
          <span>{{ $t('settings.persona.heartbeat.enabled') }}</span>
        </label>
        <p class="hint">{{ $t('settings.persona.heartbeat.enabledHint') }}</p>
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
                <option value="wechat">{{ $t('settings.persona.heartbeat.channelNames.wechat') }}</option>
                <option value="qq">{{ $t('settings.persona.heartbeat.channelNames.qq') }}</option>
              </select>
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
import { personalitiesApi, type Personality } from '@/api/personalities'

const { t } = useI18n()
const settingsStore = useSettingsStore()

interface HeartbeatConfig {
  enabled: boolean
  channel: string
  chat_id: string
  schedule: string
  idle_threshold_hours: number
  quiet_start: number
  quiet_end: number
  max_greets_per_day: number
}

interface PersonaConfig {
  ai_name: string
  user_name: string
  personality: string
  custom_personality: string
  max_history_messages: number
  heartbeat: HeartbeatConfig
}

const defaultHeartbeat = {
  enabled: false,
  channel: '',
  chat_id: '',
  schedule: '0 * * * *',
  idle_threshold_hours: 4,
  quiet_start: 21,
  quiet_end: 8,
  max_greets_per_day: 2,
}

const localPersona = ref<PersonaConfig>(
  settingsStore.settings?.persona
    ? { 
        ...settingsStore.settings.persona,
        user_address: settingsStore.settings.persona.user_address || '',
        heartbeat: {
          ...defaultHeartbeat,
          ...(settingsStore.settings.persona.heartbeat || {}),
        }
      }
    : {
        ai_name: '',
        user_name: '',
        user_address: '',
        personality: 'grumpy',
        custom_personality: '',
        max_history_messages: 50,
        heartbeat: { ...defaultHeartbeat }
      }
)

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
      { id: 'grumpy', icon: CloudLightning, name: 'Grumpy' },
      { id: 'roast', icon: Frown, name: 'Roast' },
      { id: 'gentle', icon: Heart, name: 'Gentle' },
      { id: 'blunt', icon: Target, name: 'Blunt' },
      { id: 'toxic', icon: Snowflake, name: 'Toxic' },
      { id: 'chatty', icon: MessageSquareIcon, name: 'Chatty' },
      { id: 'philosopher', icon: BookOpen, name: 'Philosopher' },
      { id: 'cute', icon: Smile, name: 'Cute' },
      { id: 'humorous', icon: Laugh, name: 'Humorous' },
      { id: 'hyper', icon: TrendingUp, name: 'Hyper' },
      { id: 'chuuni', icon: Gamepad2, name: 'Chuuni' },
      { id: 'zen', icon: Clock, name: 'Zen' },
      { id: 'custom', icon: Edit3, name: 'Custom' },
    ]
  } finally {
    loadingPersonalities.value = false
  }
}

onMounted(() => {
  loadPersonalities()
})

// 对话条数预设
const presets = [
  { label: 'minimal', value: 10, icon: Smile },
  { label: 'short', value: 30, icon: Briefcase },
  { label: 'medium', value: 50, icon: MessageSquareIcon },
  { label: 'long', value: 100, icon: Laugh },
  { label: 'extended', value: 200, icon: TrendingUp },
  { label: 'unlimited', value: -1, icon: Infinity }
]

// Token消耗估算（假设每条消息200 tokens）
const estimatedTokens = computed(() => {
  if (localPersona.value.max_history_messages === -1) {
    return '∞'
  }
  return localPersona.value.max_history_messages * 200
})

// 节省百分比
const savingsPercentage = computed(() => {
  if (localPersona.value.max_history_messages === -1) {
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
  localPersona.value.max_history_messages = value
}

// 监听store变化
watch(
  () => settingsStore.settings?.persona,
  (newPersona) => {
    if (newPersona) {
      localPersona.value = { 
        ...newPersona,
        heartbeat: {
          ...defaultHeartbeat,
          ...(newPersona.heartbeat || {}),
        },
      }
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
      settingsStore.settings.persona = { ...newValue }
      setTimeout(() => {
        isUpdating = false
      }, 0)
    }
  },
  { deep: true }
)
</script>


<style scoped>
.persona-config {
  width: 100%;
}

/* Section Header */
.section-header {
  margin-bottom: 32px;
}

.section-title {
  margin: 0 0 8px 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
}

.section-desc {
  margin: 0;
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.6;
}

/* Config Section */
.config-section {
  margin-bottom: 32px;
  padding: 24px;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 12px;
}

.section-label {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.label-icon {
  color: var(--primary-color);
}

.section-hint {
  margin: 0 0 20px 0;
  padding: 12px;
  background: var(--bg-secondary);
  border-left: 3px solid var(--primary-color);
  border-radius: 4px;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
}

/* Form Grid */
.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 20px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-group.full-width {
  grid-column: 1 / -1;
}

.label {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 8px;
}

.optional-badge {
  font-size: 12px;
  color: var(--text-tertiary);
  font-weight: normal;
  padding: 2px 8px;
  background: var(--bg-tertiary);
  border-radius: 4px;
}

.input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: 14px;
  font-family: inherit;
  transition: all 0.2s;
}

.input:focus {
  outline: none;
  border-color: var(--primary-color);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.textarea {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: 14px;
  font-family: inherit;
  resize: vertical;
  min-height: 100px;
  line-height: 1.6;
  transition: all 0.2s;
}

.textarea:focus {
  outline: none;
  border-color: var(--primary-color);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.textarea-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.hint {
  margin: 0;
  font-size: 12px;
  color: var(--text-tertiary);
  line-height: 1.4;
}

.char-count {
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 500;
}

.loading-personalities {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  color: var(--text-secondary);
}

.loading-personalities .spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--border-color);
  border-top-color: var(--primary-color);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin-bottom: 12px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Personality Grid */
.personality-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
  margin-bottom: 20px;
}

.personality-btn {
  position: relative;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-primary);
  cursor: pointer;
  transition: all 0.2s;
  text-align: left;
}

.personality-btn:hover {
  border-color: var(--primary-color);
  background: var(--bg-hover);
}

.personality-btn.active {
  border-color: var(--primary-color);
  background: rgba(59, 130, 246, 0.05);
  box-shadow: 0 0 0 1px var(--primary-color);
}

.personality-icon {
  flex-shrink: 0;
  color: var(--text-secondary);
}

.personality-btn.active .personality-icon {
  color: var(--primary-color);
}

.personality-content {
  flex: 1;
  min-width: 0;
}

.personality-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.personality-desc {
  font-size: 12px;
  color: var(--text-tertiary);
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.check-icon {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--primary-color);
  border-radius: 50%;
  color: white;
}

/* Custom Personality */
.custom-personality {
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid var(--border-color);
}

/* Slider Container */
.slider-container {
  margin-bottom: 24px;
}

.slider-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.slider-value {
  font-size: 16px;
  font-weight: 600;
  color: var(--primary-color);
  padding: 4px 12px;
  background: rgba(59, 130, 246, 0.1);
  border-radius: 6px;
}

.slider {
  width: 100%;
  height: 6px;
  border-radius: 3px;
  background: var(--bg-secondary);
  outline: none;
  -webkit-appearance: none;
  cursor: pointer;
}

.slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--primary-color);
  cursor: pointer;
  transition: all 0.2s;
}

.slider::-webkit-slider-thumb:hover {
  transform: scale(1.2);
  box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.2);
}

.slider::-moz-range-thumb {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--primary-color);
  cursor: pointer;
  border: none;
  transition: all 0.2s;
}

.slider::-moz-range-thumb:hover {
  transform: scale(1.2);
  box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.2);
}

.slider-marks {
  display: flex;
  justify-content: space-between;
  margin-top: 8px;
  padding: 0 4px;
}

.slider-marks span {
  font-size: 11px;
  color: var(--text-tertiary);
}

/* Presets Container */
.presets-container {
  margin-bottom: 24px;
}

.preset-buttons {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 10px;
  margin-top: 12px;
}

.preset-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.preset-btn:hover {
  border-color: var(--primary-color);
  background: var(--bg-hover);
}

.preset-btn.active {
  border-color: var(--primary-color);
  background: rgba(59, 130, 246, 0.05);
  color: var(--primary-color);
}

.preset-value {
  font-size: 11px;
  color: var(--text-tertiary);
  font-weight: 400;
}

.preset-btn.active .preset-value {
  color: var(--primary-color);
}

/* Token Estimate */
.token-estimate {
  padding: 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
}

.estimate-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.estimate-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
}

.estimate-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  background: var(--bg-primary);
  border-radius: 6px;
}

.estimate-label {
  font-size: 13px;
  color: var(--text-secondary);
}

.estimate-value {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.estimate-value.positive {
  color: #10b981;
}

.estimate-value.negative {
  color: #ef4444;
}

.estimate-value.neutral {
  color: var(--text-secondary);
}

/* Heartbeat Section */
.heartbeat-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.heartbeat-details {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--border-color);
}

.inline-field {
  display: flex;
  align-items: center;
  gap: 8px;
}

.narrow-input {
  width: 100px !important;
}

.field-suffix {
  font-size: 13px;
  color: var(--text-secondary);
  white-space: nowrap;
}

.warning-notice {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: rgba(245, 158, 11, 0.08);
  border: 1px solid rgba(245, 158, 11, 0.3);
  border-radius: 6px;
  color: #d97706;
  font-size: 13px;
}

/* Expand Transition */
.expand-enter-active,
.expand-leave-active {
  transition: all 0.3s ease;
  overflow: hidden;
}

.expand-enter-from,
.expand-leave-to {
  opacity: 0;
  max-height: 0;
}

.expand-enter-to,
.expand-leave-from {
  opacity: 1;
  max-height: 800px;
}

/* Responsive */
@media (max-width: 768px) {
  .form-grid {
    grid-template-columns: 1fr;
  }

  .personality-grid {
    grid-template-columns: 1fr;
  }

  .preset-buttons {
    grid-template-columns: 1fr;
  }

  .estimate-grid {
    grid-template-columns: 1fr;
  }
}
</style>


.unlimited-notice {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 16px;
  background: rgba(59, 130, 246, 0.05);
  border: 1px dashed var(--primary-color);
  border-radius: 8px;
  color: var(--primary-color);
  font-size: 14px;
  font-weight: 500;
  margin-top: 12px;
}

.estimate-value.unlimited {
  color: var(--primary-color);
}
