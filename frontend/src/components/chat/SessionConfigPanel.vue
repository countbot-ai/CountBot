<template>
  <!-- 全屏遮罩 -->
  <div class="config-modal-overlay" @click="$emit('close')">
    <div class="config-modal" @click.stop>
      <div class="modal-container">
        <!-- Header -->
        <div class="modal-header">
          <div class="header-content">
            <div class="header-icon">
              <Settings :size="24" />
            </div>
            <div class="header-text">
              <h3>{{ $t('chat.sessionConfig.title') }}</h3>
              <p class="header-subtitle">{{ sessionName }}</p>
            </div>
          </div>
          <button class="close-btn" @click="$emit('close')" :title="$t('common.close')">
            <X :size="20" />
          </button>
        </div>

        <!-- Scrollable Content -->
        <div class="modal-body">
          <!-- 使用自定义配置开关 -->
          <div class="config-toggle" :class="{ active: useCustomConfig }">
            <div class="toggle-header">
              <label class="toggle-label">
                <SwitchToggle
                  v-model="useCustomConfig"
                  :width="48"
                  :height="28"
                  :aria-label="$t('chat.sessionConfig.useCustomConfig')"
                  @change="onToggleCustomConfig"
                />
                <div class="toggle-content">
                  <span class="toggle-text">{{ $t('chat.sessionConfig.useCustomConfig') }}</span>
                  <span class="toggle-hint">{{ $t('chat.sessionConfig.useCustomConfigHint') }}</span>
                </div>
              </label>
              <div v-if="useCustomConfig" class="config-badge">
                <Sparkles :size="14" />
                <span>自定义</span>
              </div>
            </div>
          </div>

          <div v-if="useCustomConfig" class="config-sections">
            <!-- 模型配置 -->
            <section class="config-section">
              <div class="section-header">
                <div class="section-heading">
                  <div class="section-icon">
                    <Cpu :size="20" />
                  </div>
                  <h4>{{ $t('chat.sessionConfig.modelSettings') }}</h4>
                </div>
                <div class="section-header-actions">
                  <Button
                    variant="outline"
                    size="sm"
                    :icon="LayoutGrid"
                    @click="showPresetPanel = true"
                  >
                    {{ $t('settings.providers.presetPanel.entryTitle') }}
                  </Button>
                </div>
              </div>

              <div class="form-grid">
                <div class="form-group">
                  <label>{{ $t('settings.providers.selectProvider') }}</label>
                  <Select
                    v-model="modelConfig.provider"
                    :options="providerOptions"
                    :placeholder="$t('settings.providers.selectProvider')"
                    searchable
                  />
                </div>

                <div class="form-group">
                  <label>{{ $t('settings.providers.model') }}</label>
                  <input v-model="modelConfig.model" type="text" class="text-input" placeholder="glm-5" />
                </div>

              </div>

              <ModelParameterFields
                :temperature="modelConfig.temperature"
                :max-tokens="modelConfig.max_tokens"
                :max-iterations="modelConfig.max_iterations"
                :thinking-enabled="modelConfig.thinking_enabled"
                @update:temperature="modelConfig.temperature = $event"
                @update:maxTokens="modelConfig.max_tokens = $event"
                @update:maxIterations="modelConfig.max_iterations = $event"
                @update:thinkingEnabled="modelConfig.thinking_enabled = $event"
              />

              <!-- 高级 API 设置 -->
              <details class="advanced-config">
                <summary>
                  <Lock :size="16" />
                  <span>{{ $t('chat.sessionConfig.advancedApiSettings') }}</span>
                  <ChevronDown :size="16" class="chevron" />
                </summary>

                <div class="advanced-content">
                  <div class="form-group">
                    <label>{{ $t('settings.providers.apiKey') }}</label>
                    <Input
                      v-model="modelConfig.api_key"
                      type="password"
                      :placeholder="$t('chat.sessionConfig.leaveEmptyForGlobal')"
                      hint="留空将使用全局配置的 API 密钥"
                    />
                  </div>

                  <div class="form-group">
                    <label>{{ $t('settings.providers.baseUrl') }}</label>
                    <Input
                      v-model="modelConfig.api_base"
                      type="text"
                      :placeholder="$t('chat.sessionConfig.leaveEmptyForGlobal')"
                      hint="留空将使用全局配置的 API 地址"
                    />
                  </div>

                  <!-- 测试连接按钮 -->
                  <div class="form-group">
                    <Button
                      variant="secondary"
                      :loading="testing"
                      @click="handleTestConnection"
                    >
                      {{ testing ? $t('settings.providers.testing') : $t('settings.providers.testConnection') }}
                    </Button>
                  </div>

                  <!-- 测试结果 -->
                  <div
                    v-if="testResult"
                    class="test-result"
                    :class="testResult.success ? 'success' : 'error'"
                  >
                    <CheckCircle v-if="testResult.success" :size="16" />
                    <XCircle v-else :size="16" />
                    <span>{{ testResult.message }}</span>
                  </div>
                </div>
              </details>
            </section>

            <!-- 角色配置 -->
            <section class="config-section">
              <div class="section-header">
                <div class="section-heading">
                  <div class="section-icon">
                    <User :size="20" />
                  </div>
                  <h4>{{ $t('chat.sessionConfig.personaSettings') }}</h4>
                </div>
              </div>

              <div class="form-grid">
                <div class="form-group">
                  <label>{{ $t('settings.persona.aiName') }}</label>
                  <input v-model="personaConfig.ai_name" type="text" class="text-input" placeholder="小C" />
                </div>

                <div class="form-group">
                  <label>{{ $t('settings.persona.userName') }}</label>
                  <input v-model="personaConfig.user_name" type="text" class="text-input" placeholder="主人" />
                </div>

                <div class="form-group full-width">
                  <label>{{ $t('settings.persona.userAddress') }}</label>
                  <input v-model="personaConfig.user_address" type="text" class="text-input" />
                </div>
              </div>

              <div class="form-group">
                <label>{{ $t('settings.persona.personalityLabel') }}</label>
                <div v-if="loadingPersonalities" class="loading-personalities">
                  <Loader2 :size="16" class="spin" />
                  <span>{{ $t('common.loading') }}</span>
                </div>
                <div v-else class="personality-grid">
                  <button
                    v-for="p in displayedPersonalities"
                    :key="p.value"
                    @click="selectPersonality(p.value)"
                    class="personality-option"
                    :class="{ selected: personaConfig.personality === p.value }"
                    type="button"
                  >
                    <div class="personality-icon">
                      <component :is="p.icon" :size="20" />
                    </div>
                    <span class="personality-label">{{ p.label }}</span>
                  </button>
                </div>
                <button
                  v-if="canTogglePersonalities && !showAllPersonalities"
                  @click="showAllPersonalities = true"
                  class="expand-btn"
                  type="button"
                >
                  <ChevronDown :size="16" />
                  <span>展开更多性格</span>
                </button>
                <button
                  v-else-if="canTogglePersonalities"
                  @click="showAllPersonalities = false"
                  class="expand-btn"
                  type="button"
                >
                  <ChevronDown :size="16" style="transform: rotate(180deg)" />
                  <span>收起</span>
                </button>
              </div>

              <div class="form-group">
                <label>{{ $t('chat.sessionConfig.customSystemPrompt') }}</label>
                <textarea
                  v-model="personaConfig.custom_personality"
                  @input="onCustomPromptChange"
                  rows="4"
                  :placeholder="$t('chat.sessionConfig.systemPromptPlaceholder')"
                  class="textarea-input"
                />
                <p class="hint">{{ $t('chat.sessionConfig.customSystemPromptHint') }}</p>
                <div v-if="personaConfig.custom_personality && personaConfig.custom_personality.trim()" class="hint warning">
                  {{ $t('chat.sessionConfig.customSystemPromptWarning') }}
                </div>
              </div>

              <div class="history-settings-card">
                <div class="history-settings-header">
                  <h5>{{ $t('settings.persona.historyTitle') }}</h5>
                  <p>{{ $t('settings.persona.historyHint') }}</p>
                </div>

                <div class="history-settings-grid">
                  <div class="form-group">
                    <label>{{ $t('settings.persona.maxHistoryMessages') }}</label>
                    <input
                      v-model.number="personaConfig.max_history_messages"
                      type="number"
                      min="0"
                      step="1"
                      class="text-input"
                      placeholder="0"
                      @change="normalizeSessionHistoryLimitInput"
                    />
                    <p class="hint">
                      {{
                        isUnlimitedSessionHistory
                          ? $t('settings.persona.unlimitedNotice')
                          : `${$t('settings.persona.maxHistoryMessages')}：${personaConfig.max_history_messages}${$t('settings.persona.messages')}`
                      }}
                    </p>
                  </div>

                  <div class="form-group history-toggle-group">
                    <label class="toggle-label history-toggle-label">
                      <div class="toggle-content">
                        <span class="toggle-text">{{ $t('settings.persona.enableShortContextSummary') }}</span>
                        <span class="toggle-hint">{{ $t('settings.persona.enableShortContextSummaryHint') }}</span>
                        <span v-if="isUnlimitedSessionHistory" class="toggle-hint">
                          {{ $t('settings.persona.enableShortContextSummaryUnlimitedHint') }}
                        </span>
                      </div>
                      <SwitchToggle
                        v-model="personaConfig.enable_short_context_summary"
                        :width="48"
                        :height="28"
                        :aria-label="$t('settings.persona.enableShortContextSummary')"
                      />
                    </label>
                  </div>
                </div>
              </div>
            </section>
          </div>

          <div v-else class="empty-state">
            <div class="empty-icon">
              <Globe :size="48" />
            </div>
            <h4>{{ $t('chat.sessionConfig.usingGlobalDefaults') }}</h4>
            <p>启用自定义配置以为此会话设置专属的模型和角色</p>
          </div>
        </div>

        <!-- Fixed Footer -->
        <div v-if="useCustomConfig" class="modal-footer">
          <button @click="saveConfig" class="btn-primary" :disabled="saving">
            <Save :size="16" v-if="!saving" />
            <Loader2 :size="16" class="spin" v-if="saving" />
            <span>{{ saving ? $t('common.saving') : $t('common.save') }}</span>
          </button>
          <button @click="resetToDefaults" class="btn-secondary">
            <RotateCcw :size="16" />
            <span>{{ $t('chat.sessionConfig.resetToDefaults') }}</span>
          </button>
        </div>
      </div>
    </div>

    <ProviderPresetPanel
      v-model="showPresetPanel"
      :current-config="currentDraftConfig"
      :available-providers="providers"
      @apply-config="handleApplyPresetConfig"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue'
import { 
  X, Settings, Sparkles, Cpu, User, ChevronDown, Lock, LayoutGrid,
  Save, RotateCcw, Loader2, Globe, CheckCircle, XCircle,
  Heart, Frown, Laugh, CloudLightning,
  Target, Snowflake, MessageSquare, BookOpen, Smile,
  TrendingUp, Gamepad2, Clock, Edit3
} from 'lucide-vue-next'
import {
  chatAPI,
  settingsAPI,
  type ProviderMetadata,
  type SessionModelConfig,
  type SessionPersonaConfig,
} from '@/api'
import { personalitiesApi, type Personality } from '@/api/personalities'
import { useI18n } from 'vue-i18n'
import Input from '@/components/ui/Input.vue'
import Button from '@/components/ui/Button.vue'
import Select from '@/components/ui/Select.vue'
import SwitchToggle from '@/components/ui/SwitchToggle.vue'
import ModelParameterFields from '@/components/ui/ModelParameterFields.vue'
import ProviderPresetPanel from '@/modules/settings/ProviderPresetPanel.vue'
import { useToast } from '@/composables/useToast'
import {
  findFirstSelectableProvider,
  findProviderById,
  resolveProviderDefaultApiBase,
  resolveProviderDefaultModel,
} from '@/utils/providerRuntime'
import {
  buildCustomModelEditorConfig,
  buildEffectiveModelConfig,
  buildModelConfigOverrides,
  MODEL_CONFIG_FALLBACK,
  buildSendableModelConfig,
} from '@/utils/modelConfig'

const { t } = useI18n()
const toast = useToast()

type SessionConfigUpdateAction = 'saved' | 'reset'
type ProviderOption = Pick<ProviderMetadata, 'id' | 'name'> & {
  defaultApiBase?: string
  defaultModel?: string
}

interface PersonalityOption {
  value: string
  label: string
  icon: any
}

interface PresetApplyPayload {
  provider: string
  model: string
  apiKey: string
  baseUrl?: string
  enabled: boolean
  temperature?: number
  maxTokens?: number
  maxIterations?: number
  source: 'preset' | 'codingplan'
  label: string
}

const createDefaultModelConfig = (): SessionModelConfig =>
  buildCustomModelEditorConfig<SessionModelConfig>()

const createDefaultPersonaConfig = (): SessionPersonaConfig => ({
  ai_name: '小C',
  user_name: '主人',
  user_address: '',
  output_language: '中文',
  personality: 'grumpy',
  custom_personality: '',
  max_history_messages: 0,
  enable_short_context_summary: false,
})

function normalizeHistoryLimit(value?: number): number {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return 0
  }
  return value <= 0 ? 0 : value
}

function normalizeModelConfig(config?: Partial<SessionModelConfig>): SessionModelConfig {
  return buildEffectiveModelConfig<SessionModelConfig>(undefined, config)
}

function normalizePersonaConfig(config?: Partial<SessionPersonaConfig>): SessionPersonaConfig {
  return {
    ...createDefaultPersonaConfig(),
    ...config,
    user_address: config?.user_address ?? '',
    custom_personality: config?.custom_personality ?? '',
    max_history_messages: normalizeHistoryLimit(config?.max_history_messages),
    enable_short_context_summary: config?.enable_short_context_summary ?? false,
  }
}

const props = defineProps<{
  sessionId: string
  sessionName?: string
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'updated', action: SessionConfigUpdateAction): void
}>()

const useCustomConfig = ref(false)
const saving = ref(false)
const testing = ref(false)
const testResult = ref<{ success: boolean; message: string } | null>(null)
const providers = ref<ProviderOption[]>([])
const showPresetPanel = ref(false)
const personalities = ref<PersonalityOption[]>([])
const loadingPersonalities = ref(false)
const showAllPersonalities = ref(false)
const isHydratingConfig = ref(false)
const DEFAULT_PERSONALITY_COUNT = 4

const iconMap: Record<string, any> = {
  CloudLightning,
  Frown,
  Heart,
  Target,
  Snowflake,
  MessageSquare,
  BookOpen,
  Smile,
  Laugh,
  TrendingUp,
  Gamepad2,
  Clock,
  Edit3,
}

function translatePersonalityLabel(id: string, fallback: string) {
  const key = `settings.persona.personalities.${id}`
  const translated = t(key)
  return translated === key ? fallback : translated
}

function createCustomPromptOption(): PersonalityOption {
  return {
    value: 'custom',
    label: t('settings.persona.customPersonality'),
    icon: Edit3,
  }
}

function appendCustomPromptOption(options: PersonalityOption[]) {
  if (options.some(option => option.value === 'custom')) {
    return options
  }
  return [...options, createCustomPromptOption()]
}

function createFallbackPersonalities(): PersonalityOption[] {
  return appendCustomPromptOption([
    { value: 'grumpy', label: translatePersonalityLabel('grumpy', '暴躁'), icon: CloudLightning },
    { value: 'roast', label: translatePersonalityLabel('roast', '吐槽'), icon: Frown },
    { value: 'gentle', label: translatePersonalityLabel('gentle', '温柔'), icon: Heart },
    { value: 'blunt', label: translatePersonalityLabel('blunt', '直率'), icon: Target },
    { value: 'toxic', label: translatePersonalityLabel('toxic', '毒舌'), icon: Snowflake },
    { value: 'chatty', label: translatePersonalityLabel('chatty', '话痨'), icon: MessageSquare },
    { value: 'philosopher', label: translatePersonalityLabel('philosopher', '哲学'), icon: BookOpen },
    { value: 'cute', label: translatePersonalityLabel('cute', '可爱'), icon: Smile },
    { value: 'humorous', label: translatePersonalityLabel('humorous', '幽默'), icon: Laugh },
    { value: 'hyper', label: translatePersonalityLabel('hyper', '兴奋'), icon: TrendingUp },
    { value: 'chuuni', label: translatePersonalityLabel('chuuni', '中二'), icon: Gamepad2 },
    { value: 'zen', label: translatePersonalityLabel('zen', '佛系'), icon: Clock },
  ])
}

function mapPersonalityOption(personality: Personality): PersonalityOption {
  return {
    value: personality.id,
    label: translatePersonalityLabel(personality.id, personality.name),
    icon: iconMap[personality.icon] || Smile,
  }
}

const availablePersonalities = computed(() => {
  const selectedId = personaConfig.value.personality
  if (!selectedId || personalities.value.some(option => option.value === selectedId)) {
    return personalities.value
  }

  return [
    ...personalities.value,
    {
      value: selectedId,
      label: selectedId,
      icon: Edit3,
    },
  ]
})

const defaultPersonalities = computed(() => {
  const base = availablePersonalities.value.slice(0, DEFAULT_PERSONALITY_COUNT)
  const selected = availablePersonalities.value.find(option => option.value === personaConfig.value.personality)

  if (!selected || base.some(option => option.value === selected.value) || base.length < DEFAULT_PERSONALITY_COUNT) {
    return base
  }

  return [...base.slice(0, DEFAULT_PERSONALITY_COUNT - 1), selected]
})

const displayedPersonalities = computed(() =>
  showAllPersonalities.value ? availablePersonalities.value : defaultPersonalities.value
)

const canTogglePersonalities = computed(() => availablePersonalities.value.length > DEFAULT_PERSONALITY_COUNT)
const isUnlimitedSessionHistory = computed(() => personaConfig.value.max_history_messages <= 0)

const globalModelDefaults = ref<SessionModelConfig>(createDefaultModelConfig())
const modelConfig = ref<SessionModelConfig>(createDefaultModelConfig())
const personaConfig = ref<SessionPersonaConfig>(createDefaultPersonaConfig())
const providerOptions = computed(() =>
  providers.value.map(provider => ({
    value: provider.id,
    label: provider.name,
  }))
)
const currentDraftConfig = computed(() => ({
  provider: modelConfig.value.provider,
  model: modelConfig.value.model,
  apiKey: modelConfig.value.api_key,
  baseUrl: modelConfig.value.api_base || '',
  enabled: true,
  temperature: modelConfig.value.temperature,
  maxTokens: modelConfig.value.max_tokens,
  maxIterations: modelConfig.value.max_iterations,
}))

async function loadProviders() {
  try {
    const providersData = await settingsAPI.getProviders()
    providers.value = providersData.map(p => ({
      id: p.id,
      name: p.name,
      defaultApiBase: resolveProviderDefaultApiBase(p),
      defaultModel: resolveProviderDefaultModel(p)
    }))
    ensureValidProviderSelection()
  } catch (error) {
    console.error('Failed to load providers:', error)
    toast.error(t('chat.sessionConfig.loadFailed'))
  }
}

async function loadPersonalities() {
  loadingPersonalities.value = true
  try {
    const { personalities: data } = await personalitiesApi.list(true)
    personalities.value = appendCustomPromptOption(
      data
        .filter(personality => personality.is_active)
        .map(mapPersonalityOption)
    )
  } catch (error) {
    console.error('Failed to load personalities:', error)
    personalities.value = createFallbackPersonalities()
  } finally {
    loadingPersonalities.value = false
  }
}

function applyConfig(model: Partial<SessionModelConfig>, persona: Partial<SessionPersonaConfig>, enabled: boolean) {
  isHydratingConfig.value = true
  try {
    useCustomConfig.value = enabled
    modelConfig.value = buildCustomModelEditorConfig<SessionModelConfig>(
      globalModelDefaults.value,
      enabled ? model : undefined,
    )
    personaConfig.value = normalizePersonaConfig(persona)
    testResult.value = null
    ensureValidProviderSelection()
  } finally {
    isHydratingConfig.value = false
  }
}

function ensureValidProviderSelection() {
  if (providers.value.length === 0) {
    return
  }

  const currentProvider = findProviderById(providers.value, modelConfig.value.provider)
  if (currentProvider) {
    return
  }

  const fallbackProvider = findFirstSelectableProvider(providers.value)
  const nextProvider = fallbackProvider || providers.value[0]
  if (!nextProvider) {
    return
  }

  modelConfig.value.provider = nextProvider.id
  if (!modelConfig.value.api_base) {
    modelConfig.value.api_base = nextProvider.defaultApiBase || ''
  }
  if (
    !modelConfig.value.model
    || modelConfig.value.model === MODEL_CONFIG_FALLBACK.model
  ) {
    modelConfig.value.model = nextProvider.defaultModel || modelConfig.value.model
  }
}

function handleApplyPresetConfig(payload: PresetApplyPayload) {
  isHydratingConfig.value = true
  try {
    modelConfig.value = buildEffectiveModelConfig<SessionModelConfig>(
      globalModelDefaults.value,
      {
        ...modelConfig.value,
        provider: payload.provider,
        model: payload.model,
        api_mode: 'chat_completions',
        api_key: payload.apiKey,
        api_base: payload.baseUrl || '',
        temperature: payload.temperature ?? modelConfig.value.temperature,
        max_tokens: payload.maxTokens ?? modelConfig.value.max_tokens,
        max_iterations: payload.maxIterations ?? modelConfig.value.max_iterations,
      },
    )
    testResult.value = null
    ensureValidProviderSelection()
  } finally {
    isHydratingConfig.value = false
  }
}

onMounted(async () => {
  await Promise.all([loadProviders(), loadPersonalities()])
  await loadConfig()
})

watch(() => props.sessionId, async (newSessionId, oldSessionId) => {
  if (newSessionId && newSessionId !== oldSessionId) {
    await loadConfig()
  }
})

watch(() => modelConfig.value.provider, (newProvider, oldProvider) => {
  if (!newProvider || providers.value.length === 0 || isHydratingConfig.value) {
    return
  }

  const nextProvider = providers.value.find(p => p.id === newProvider)
  const previousProvider = oldProvider ? providers.value.find(p => p.id === oldProvider) : null

  if (!nextProvider) {
    return
  }

  const shouldUpdateApiBase = !modelConfig.value.api_base || (
    !!previousProvider?.defaultApiBase && modelConfig.value.api_base === previousProvider.defaultApiBase
  )
  if (shouldUpdateApiBase) {
    modelConfig.value.api_base = nextProvider.defaultApiBase || ''
  }

  const shouldUpdateModel = !modelConfig.value.model || (
    !!previousProvider?.defaultModel && modelConfig.value.model === previousProvider.defaultModel
  )
  if (shouldUpdateModel && nextProvider.defaultModel) {
    modelConfig.value.model = nextProvider.defaultModel
  }
})

async function loadConfig() {
  if (!props.sessionId) {
    globalModelDefaults.value = createDefaultModelConfig()
    applyConfig(globalModelDefaults.value, createDefaultPersonaConfig(), false)
    return
  }

  try {
    const config = await chatAPI.getSessionConfig(props.sessionId)
    globalModelDefaults.value = normalizeModelConfig(config.global_defaults.model)
    if (config.use_custom_config) {
      applyConfig(config.model_config, config.persona_config, true)
    } else {
      applyConfig(config.global_defaults.model, config.global_defaults.persona, false)
    }
  } catch (error) {
    console.error('Failed to load session config:', error)
    toast.error(t('chat.sessionConfig.loadFailed'))
  }
}

async function saveConfig() {
  // 如果用户点击保存，说明要使用自定义配置
  if (!useCustomConfig.value) {
    useCustomConfig.value = true
  }
  
  saving.value = true
  try {
    normalizeSessionHistoryLimitInput()
    const modelOverrides = buildModelConfigOverrides<SessionModelConfig>(
      modelConfig.value,
      globalModelDefaults.value,
    )
    await chatAPI.updateSessionConfig(props.sessionId, {
      model_config: modelOverrides,
      persona_config: {
        ...personaConfig.value,
        max_history_messages: normalizeHistoryLimit(personaConfig.value.max_history_messages),
      }
    })
    emit('updated', 'saved')
  } catch (error) {
    console.error('Failed to save config:', error)
    toast.error(t('chat.sessionConfig.saveFailed'))
  } finally {
    saving.value = false
  }
}

async function resetToDefaults() {
  if (!confirm(t('chat.sessionConfig.confirmReset'))) {
    return false
  }

  try {
    await chatAPI.resetSessionConfig(props.sessionId)
    await loadConfig()
    emit('updated', 'reset')
    return true
  } catch (error) {
    console.error('Failed to reset config:', error)
    toast.error(t('chat.sessionConfig.resetFailed'))
    return false
  }
}

async function onToggleCustomConfig() {
  if (!useCustomConfig.value) {
    const reset = await resetToDefaults()
    if (!reset) {
      useCustomConfig.value = true
    }
    return
  }

  modelConfig.value = buildCustomModelEditorConfig<SessionModelConfig>(
    globalModelDefaults.value,
    modelConfig.value,
  )
  testResult.value = null
}

async function handleTestConnection() {
  testing.value = true
  testResult.value = null

  try {
    const response = await settingsAPI.testConnection({
      provider: modelConfig.value.provider,
      api_key: modelConfig.value.api_key || undefined,
      api_base: modelConfig.value.api_base || undefined,
      model: modelConfig.value.model,
      ...buildSendableModelConfig(modelConfig.value),
    })
    
    testResult.value = {
      success: response.success,
      message: response.success 
        ? (response.message || t('settings.providers.testSuccess'))
        : (response.error || response.message || t('settings.providers.testFailed'))
    }
  } catch (error: any) {
    testResult.value = {
      success: false,
      message: error.response?.data?.error || error.message || t('settings.providers.testFailed')
    }
  } finally {
    testing.value = false
  }
}

// 选择性格
function selectPersonality(value: string) {
  personaConfig.value.personality = value
  // 如果有自定义提示词，清空它（因为用户选择了预设性格）
  // 注释掉这行，让用户自己决定
  // personaConfig.value.custom_personality = ''
}

// 自定义提示词变化时的处理
function onCustomPromptChange() {
  // 如果填写了自定义提示词，自动将 personality 设置为 'custom'
  if (personaConfig.value.custom_personality && personaConfig.value.custom_personality.trim()) {
    personaConfig.value.personality = 'custom'
  }
}

function normalizeSessionHistoryLimitInput() {
  personaConfig.value.max_history_messages = normalizeHistoryLimit(
    personaConfig.value.max_history_messages,
  )
}
</script>
<style scoped>
@import './styles/SessionConfigPanel.css';
</style>


