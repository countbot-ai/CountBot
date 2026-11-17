<template>
  <Modal
    :model-value="true"
    size="large"
    mask-closable
    @close="$emit('close')"
  >
    <template #title>
      <div class="scm-title">
        <span class="scm-title-icon">
          <Settings :size="16" />
        </span>
        <span class="scm-title-text">{{ $t('chat.sessionConfig.title') }}</span>
        <span v-if="sessionName" class="scm-title-sub">{{ sessionName }}</span>
      </div>
    </template>

    <div class="scm-body">
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
                <span>{{ $t('chat.sessionConfig.customBadge') }}</span>
              </div>
            </div>
          </div>

          <!-- 工作空间：仅管理员可自定义；普通用户由系统按用户自动分配私有目录 -->
          <section v-if="isAdmin" class="config-section workspace-section">
            <div class="section-header">
              <div class="section-heading">
                <div class="section-icon">
                  <Folder :size="20" />
                </div>
                <h4>{{ $t('chat.sessionConfig.workspaceTitle') }}</h4>
              </div>
              <div v-if="workspaceIsCustom" class="config-badge">
                <Sparkles :size="14" />
                <span>{{ $t('chat.sessionConfig.customBadge') }}</span>
              </div>
            </div>

            <div class="form-group">
              <label>{{ $t('chat.sessionConfig.workspacePath') }}</label>
              <div class="workspace-path-row">
                <input
                  v-model="workspacePath"
                  type="text"
                  class="text-input"
                  :placeholder="globalWorkspacePath || $t('chat.sessionConfig.workspacePlaceholder')"
                  @input="workspaceError = ''"
                />
                <Button
                  v-if="canPickDirectory"
                  variant="secondary"
                  :icon="FolderOpen"
                  @click="handleSelectWorkspaceDirectory"
                >
                  {{ $t('chat.sessionConfig.selectWorkspaceDirectory') }}
                </Button>
              </div>
              <p class="hint">{{ $t('chat.sessionConfig.workspaceHint') }}</p>
              <p v-if="!canPickDirectory" class="hint">
                {{ $t('chat.sessionConfig.workspaceRemoteHint') }}
              </p>
              <p v-if="workspaceError" class="hint warning">{{ workspaceError }}</p>
              <div class="workspace-actions">
                <button type="button" class="link-btn" @click="useGlobalWorkspace">
                  {{ $t('chat.sessionConfig.useGlobalWorkspace') }}
                </button>
                <span class="workspace-effective">
                  {{ $t('chat.sessionConfig.workspaceEffective') }}: {{ effectiveWorkspacePath }}
                </span>
              </div>
            </div>
          </section>

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
                  <Select
                    v-model="modelConfig.model"
                    :options="modelOptions"
                    :placeholder="$t('chat.modelPicker.placeholder')"
                    :disabled="modelOptions.length === 0"
                    :prefix-icon="ProviderIcon"
                    :prefix-icon-props="currentProviderIconProps"
                    searchable
                  />
                </div>
              </div>

              <ModelParameterFields
                :temperature="modelConfig.temperature"
                :max-tokens="modelConfig.max_tokens"
                :max-iterations="modelConfig.max_iterations"
                :thinking-enabled="modelConfig.thinking_enabled"
                :stream-enabled="modelConfig.stream_enabled"
                @update:temperature="modelConfig.temperature = $event"
                @update:maxTokens="modelConfig.max_tokens = $event"
                @update:maxIterations="modelConfig.max_iterations = $event"
                @update:thinkingEnabled="modelConfig.thinking_enabled = $event"
                @update:streamEnabled="modelConfig.stream_enabled = $event"
              />
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
                  <input v-model="personaConfig.ai_name" type="text" class="text-input" :placeholder="$t('settings.persona.aiNamePlaceholder')" />
                </div>

                <div class="form-group">
                  <label>{{ $t('settings.persona.userName') }}</label>
                  <input v-model="personaConfig.user_name" type="text" class="text-input" :placeholder="$t('settings.persona.userNamePlaceholder')" />
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
                  <span>{{ $t('chat.sessionConfig.showAllPersonalities') }}</span>
                </button>
                <button
                  v-else-if="canTogglePersonalities"
                  @click="showAllPersonalities = false"
                  class="expand-btn"
                  type="button"
                >
                  <ChevronDown :size="16" style="transform: rotate(180deg)" />
                  <span>{{ $t('chat.sessionConfig.collapse') }}</span>
                </button>
              </div>

              <div class="form-group">
                <label>{{ $t('chat.sessionConfig.customSystemPrompt') }}</label>
                <textarea
                  v-model="personaConfig.custom_personality"
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
            <p>{{ $t('chat.sessionConfig.usingGlobalDefaultsDesc') }}</p>
          </div>
    </div>

    <template #footer>
      <Button variant="secondary" :icon="RotateCcw" @click="resetToDefaults">
        {{ $t('chat.sessionConfig.resetToDefaults') }}
      </Button>
      <Button variant="primary" :icon="Save" :loading="saving" @click="saveConfig">
        {{ saving ? $t('common.saving') : $t('common.save') }}
      </Button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue'
import {
  Settings, Sparkles, Cpu, User, ChevronDown,
  Save, RotateCcw, Loader2, Globe,
  Heart, Frown, Laugh, CloudLightning,
  Target, Snowflake, MessageSquare, BookOpen, Smile,
  TrendingUp, Gamepad2, Clock, Edit3, Folder, FolderOpen
} from 'lucide-vue-next'
import {
  authAPI,
  chatAPI,
  meAPI,
  settingsAPI,
  type ProviderMetadata,
  type ProviderModelEntry,
  type SessionModelConfig,
  type SessionPersonaConfig,
} from '@/api'
import { personalitiesApi, type Personality } from '@/api/personalities'
import {
  buildProviderOptions,
  buildProviderOptionsFromMeModels,
  type ProviderOption as CatalogProviderOption,
} from '@/composables/useProviderModelCatalog'
import { useChatModePolicy } from '@/composables/useChatModePolicy'
import { useI18n } from 'vue-i18n'
import { useUserStore } from '@/store/user'
import Button from '@/components/ui/Button.vue'
import Modal from '@/components/ui/Modal.vue'
import ProviderIcon from '@/components/ui/ProviderIcon.vue'
import Select from '@/components/ui/Select.vue'
import SwitchToggle from '@/components/ui/SwitchToggle.vue'
import ModelParameterFields from '@/components/ui/ModelParameterFields.vue'
import { useToast } from '@/composables/useToast'
import { useConfirm } from '@/composables/useConfirm'
import {
  buildCustomModelEditorConfig,
  buildEffectiveModelConfig,
  buildModelConfigOverrides,
} from '@/utils/modelConfig'

const { t } = useI18n()
const toast = useToast()
const { confirm } = useConfirm()
// 工作空间自定义仅管理员可见/可改；普通用户强制使用各自私有工作区
const userStore = useUserStore()
const isAdmin = computed(() => userStore.isAdmin)

type SessionConfigUpdateAction = 'saved' | 'reset'

interface PersonalityOption {
  value: string
  label: string
  icon: any
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

const useCustomConfig = ref(true)
const saving = ref(false)
// 对话模式不在模型参数表单里，但同样属于会话模型配置；保存时要原样带回
const { clampChatMode } = useChatModePolicy()
const chatMode = ref<'agent' | 'chat'>('agent')
// 工作空间独立于模型/人设开关：留空表示跟随全局
const workspacePath = ref('')
const initialWorkspacePath = ref('')
const globalWorkspacePath = ref('')
const effectiveWorkspacePath = ref('')
const workspaceError = ref('')
const canPickDirectory = ref(false)
const workspaceIsCustom = computed(() => !!workspacePath.value.trim())
const providers = ref<CatalogProviderOption[]>([])
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

function createFallbackPersonalities(): PersonalityOption[] {
  return [
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
  ]
}

function isEditedBuiltin(personality: Personality): boolean {
  if (!personality.is_builtin) return false
  const created = Date.parse(personality.created_at || '')
  const updated = Date.parse(personality.updated_at || '')
  return Number.isFinite(created) && Number.isFinite(updated) && updated - created > 1000
}

function mapPersonalityOption(personality: Personality): PersonalityOption {
  return {
    value: personality.id,
    label: personality.is_builtin && !isEditedBuiltin(personality)
      ? translatePersonalityLabel(personality.id, personality.name)
      : personality.name,
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
    icon: ProviderIcon,
    iconProps: { providerId: provider.id, size: 16 },
  }))
)
// 模型下拉只读出「已配置好」的模型，不再让用户手敲模型名
const modelOptions = computed(() => {
  const provider = providers.value.find(item => item.id === modelConfig.value.provider)
  if (!provider) {
    return []
  }
  return provider.models
    .filter(model => model.enabled !== false)
    .map(model => ({
      value: model.id,
      label: model.display_name || model.id,
    }))
})
// 与对话窗口一致：模型选中值前面展示该供应商的品牌图标
const currentProviderIconProps = computed(() => ({
  providerId: modelConfig.value.provider,
  size: 16,
}))

async function loadProviders() {
  try {
    if (userStore.isAdmin) {
      const [settings, metadata] = await Promise.all([
        settingsAPI.get(),
        settingsAPI.getProviders().catch(() => [] as ProviderMetadata[]),
      ])
      providers.value = buildProviderOptions(settings.providers, metadata)
    } else {
      // 普通用户无权读全局配置，只暴露管理员共享/自有的模型清单
      const data = await meAPI.listModels()
      providers.value = buildProviderOptionsFromMeModels(data)
    }
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
    personalities.value = data
      .filter(personality => personality.is_active)
      .map(mapPersonalityOption)
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
    chatMode.value = clampChatMode(enabled && model.chat_mode === 'chat' ? 'chat' : 'agent')
    modelConfig.value = buildCustomModelEditorConfig<SessionModelConfig>(
      globalModelDefaults.value,
      enabled ? model : undefined,
    )
    personaConfig.value = normalizePersonaConfig(persona)
    ensureValidProviderSelection()
  } finally {
    isHydratingConfig.value = false
  }
}

function ensureValidProviderSelection() {
  if (providers.value.length === 0) {
    return
  }

  if (!providers.value.some(provider => provider.id === modelConfig.value.provider)) {
    modelConfig.value.provider = providers.value[0].id
  }

  ensureCurrentModelPresent()
}

/** 当前模型若不在供应商清单里，补一个条目保住会话已有选择，或回落到首个可用模型。 */
function ensureCurrentModelPresent() {
  const provider = providers.value.find(item => item.id === modelConfig.value.provider)
  if (!provider) {
    return
  }

  const currentModel = String(modelConfig.value.model || '')
  if (currentModel && provider.models.some(model => model.id === currentModel)) {
    return
  }

  if (currentModel) {
    provider.models = [
      {
        id: currentModel,
        display_name: currentModel,
        enabled: true,
        context_window: null,
        supports_image: null,
        source: 'manual',
      } as ProviderModelEntry,
      ...provider.models,
    ]
    return
  }

  const firstModel = provider.models.find(model => model.enabled !== false)
  if (firstModel) {
    modelConfig.value.model = firstModel.id
  }
}

async function loadDirectoryCapability() {
  try {
    const status = await authAPI.status()
    // 远程访问时不弹服务器桌面的目录选择框，改为手输绝对路径
    canPickDirectory.value = status.is_local
  } catch {
    canPickDirectory.value = false
  }
}

onMounted(async () => {
  await Promise.all([loadProviders(), loadPersonalities(), loadDirectoryCapability()])
  await loadConfig()
})

watch(() => props.sessionId, async (newSessionId, oldSessionId) => {
  if (newSessionId && newSessionId !== oldSessionId) {
    await loadConfig()
  }
})

watch(() => modelConfig.value.provider, (newProvider) => {
  if (!newProvider || providers.value.length === 0 || isHydratingConfig.value) {
    return
  }

  const nextProvider = providers.value.find(p => p.id === newProvider)
  if (!nextProvider) {
    return
  }

  // 切供应商后旧模型通常不在新清单里，回落到新供应商的首个可用模型
  const currentModel = String(modelConfig.value.model || '')
  const stillValid = nextProvider.models.some(
    model => model.id === currentModel && model.enabled !== false,
  )
  if (!stillValid) {
    const firstModel = nextProvider.models.find(model => model.enabled !== false)
    modelConfig.value.model = firstModel ? firstModel.id : ''
  }
})

async function loadConfig() {
  if (!props.sessionId) {
    globalModelDefaults.value = createDefaultModelConfig()
    workspacePath.value = ''
    initialWorkspacePath.value = ''
    effectiveWorkspacePath.value = globalWorkspacePath.value
    workspaceError.value = ''
    applyConfig(globalModelDefaults.value, createDefaultPersonaConfig(), false)
    return
  }

  try {
    const config = await chatAPI.getSessionConfig(props.sessionId)
    globalModelDefaults.value = normalizeModelConfig(config.global_defaults.model)
    // 工作空间与会话模型/人设独立回填；普通用户无工作空间自定义，跳过
    if (isAdmin.value) {
      workspacePath.value = config.workspace?.path || ''
      initialWorkspacePath.value = config.workspace?.path || ''
      globalWorkspacePath.value = config.workspace?.global_path || ''
      effectiveWorkspacePath.value = config.workspace?.effective_path || ''
      workspaceError.value = ''
    }
    // 面板打开时默认启用「使用自定义配置」：有保存值则回填，否则预填全局默认
    if (config.use_custom_config) {
      applyConfig(config.model_config, config.persona_config, true)
    } else {
      applyConfig(config.global_defaults.model, config.global_defaults.persona, true)
    }
  } catch (error) {
    console.error('Failed to load session config:', error)
    toast.error(t('chat.sessionConfig.loadFailed'))
  }
}

async function handleSelectWorkspaceDirectory() {
  try {
    const response = await fetch('/api/settings/workspace/select-directory', {
      method: 'POST',
    })
    const data = await response.json()
    if (data.success && data.path) {
      workspacePath.value = data.path
      workspaceError.value = ''
      return
    }
    if (data.message) {
      toast.info(data.message)
    }
  } catch (error) {
    console.error('Failed to select workspace directory:', error)
    toast.error(t('chat.sessionConfig.workspacePickFailed'))
  }
}

function useGlobalWorkspace() {
  workspacePath.value = ''
  workspaceError.value = ''
}

async function saveWorkspaceIfNeeded(): Promise<boolean> {
  if (!props.sessionId || !isAdmin.value) {
    return true
  }

  const nextPath = workspacePath.value.trim()
  if (nextPath === initialWorkspacePath.value.trim()) {
    return true
  }

  try {
    const result = await chatAPI.updateSessionWorkspace(
      props.sessionId,
      nextPath || null,
    )
    initialWorkspacePath.value = result.workspace_path || ''
    workspacePath.value = result.workspace_path || ''
    effectiveWorkspacePath.value = result.effective_workspace_path
    workspaceError.value = ''
    return true
  } catch (error: any) {
    const status = error?.response?.status
    const message = status === 404 || status === 405
      ? t('chat.sessionConfig.workspaceApiNotReady')
      : (error?.response?.data?.detail || t('chat.sessionConfig.workspaceSaveFailed'))
    workspaceError.value = message
    toast.error(message)
    return false
  }
}

async function saveConfig() {
  saving.value = true
  try {
    // 工作空间先独立落库；校验失败时停在面板内提示
    if (!(await saveWorkspaceIfNeeded())) {
      return
    }

    // 开关关闭时点击保存 = 提交「使用全局默认配置」
    if (!useCustomConfig.value) {
      await chatAPI.resetSessionConfig(props.sessionId)
      // 重置会同时清空工作空间；管理员显式填写了目录时再补写回去
      if (isAdmin.value) {
        const nextPath = workspacePath.value.trim()
        if (nextPath) {
          const result = await chatAPI.updateSessionWorkspace(props.sessionId, nextPath)
          initialWorkspacePath.value = result.workspace_path || ''
          effectiveWorkspacePath.value = result.effective_workspace_path
        } else {
          initialWorkspacePath.value = ''
          effectiveWorkspacePath.value = globalWorkspacePath.value
        }
      }
      emit('updated', 'reset')
      return
    }

    normalizeSessionHistoryLimitInput()
    const modelOverrides = buildModelConfigOverrides<SessionModelConfig>(
      modelConfig.value,
      globalModelDefaults.value,
    )
    // 会话不再覆盖密钥/地址：供应商凭据只在设置页维护，避免重复配置
    delete modelOverrides.api_key
    delete modelOverrides.api_base
    await chatAPI.updateSessionConfig(props.sessionId, {
      model_config: { ...modelOverrides, chat_mode: clampChatMode(chatMode.value) },
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
  const confirmed = await confirm({
    title: t('common.confirm'),
    message: t('chat.sessionConfig.confirmReset'),
    type: 'warning',
    confirmText: t('common.confirm'),
    confirmVariant: 'primary'
  })
  if (!confirmed) {
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

function onToggleCustomConfig() {
  if (!useCustomConfig.value) {
    // 关闭开关仅为草稿状态：直接关闭面板会恢复原配置，保存才重置为全局默认
    return
  }

  modelConfig.value = buildCustomModelEditorConfig<SessionModelConfig>(
    globalModelDefaults.value,
    modelConfig.value,
  )
}

// 选择性格
function selectPersonality(value: string) {
  personaConfig.value.personality = value
  // 自定义系统提示词作为补充约束，不改变当前性格选择
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


