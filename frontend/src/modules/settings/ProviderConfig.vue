<template>
  <div class="provider-config">
    <div class="section-header">
      <h3 class="section-title">
        {{ $t('settings.providers.title') }}
      </h3>

      <div class="section-actions">
        <Button
          variant="outline"
          size="sm"
          :icon="LayoutGridIcon"
          @click="showPresetPanel = true"
        >
          {{ $t('settings.providers.presetPanel.open') }}
        </Button>
      </div>
    </div>

    <section class="state-grid">
      <div class="state-card">
        <div class="state-head">
          <span class="state-label">{{ $t('settings.providers.presetPanel.savedSnapshot') }}</span>
        </div>
        <div class="state-stack">
          <span class="state-provider">{{ savedSnapshot.provider }}</span>
          <strong class="state-model">{{ savedSnapshot.model }}</strong>
        </div>
      </div>

      <div class="state-card" :class="{ 'is-dirty': hasDraftChanges }">
        <div class="state-head">
          <span class="state-label">{{ $t('settings.providers.presetPanel.currentDraft') }}</span>
          <span v-if="draftStateHint" class="state-flag">{{ draftStateHint }}</span>
        </div>
        <div class="state-stack">
          <span class="state-provider">{{ draftSnapshot.provider }}</span>
          <strong class="state-model">{{ draftSnapshot.model }}</strong>
        </div>
      </div>
    </section>

    <section class="workspace-card">
      <div class="workspace-header">
        <h4>{{ $t('settings.providers.presetPanel.workspaceTitle') }}</h4>

        <div class="workspace-badges">
          <span class="status-pill" :class="selectedProviderSelectable ? 'ready' : 'warning'">
            {{ selectedProviderStatusText }}
          </span>
          <span v-if="appliedSourceText" class="status-pill neutral">
            {{ appliedSourceText }}
          </span>
        </div>
      </div>

      <div class="form-grid">
        <div class="form-group">
          <label class="label">{{ $t('settings.providers.selectProvider') }}</label>
          <Select
            v-model="selectedProviderOption"
            :options="providerOptions"
            :placeholder="$t('settings.providers.selectProvider')"
            searchable
          />
          <div v-if="selectedProviderMeta" class="provider-capability-card">
            <div class="provider-capability-badges">
              <span class="provider-capability-pill capability-group">
                {{ selectedProviderGroupLabel }}
              </span>
              <span
                class="provider-capability-pill"
                :class="`capability-tier-${selectedProviderThinkingTier}`"
              >
                {{ selectedProviderThinkingTierLabel }}
              </span>
            </div>
            <p class="hint provider-capability-note">
              {{ selectedProviderThinkingNote }}
            </p>
          </div>
        </div>

        <div class="form-group" :class="{ 'form-group-wide': isOpenRouterProvider && showOpenRouterFreeModels }">
          <label class="label">{{ $t('settings.providers.model') }}</label>
          <div class="model-field-stack">
            <div class="model-input-row">
              <div class="model-input-main">
                <Input
                  v-model="modelName"
                  type="text"
                  :placeholder="$t('settings.providers.modelPlaceholder')"
                />
              </div>

              <Button
                v-if="isOpenRouterProvider"
                variant="outline"
                :icon="SearchIcon"
                :loading="openRouterFreeModelsLoading"
                :title="openRouterFreeModelsButtonText"
                :aria-label="openRouterFreeModelsButtonText"
                @click="handleOpenRouterFreeModels"
              >
                {{ $t('settings.providers.openrouterFreeModels.button') }}
              </Button>
            </div>

            <p v-if="isOpenRouterProvider" class="hint">
              {{
                openRouterFreeModelsLoaded
                  ? $t('settings.providers.openrouterFreeModels.loadedHint', { count: openRouterFreeModels.length })
                  : $t('settings.providers.openrouterFreeModels.hint')
              }}
            </p>

            <div v-if="isOpenRouterProvider && showOpenRouterFreeModels" class="openrouter-model-panel">
              <div class="openrouter-model-panel-header">
                <span class="openrouter-model-panel-title">
                  {{ $t('settings.providers.openrouterFreeModels.panelTitle', { count: openRouterFreeModels.length }) }}
                </span>

                <Button
                  variant="ghost"
                  size="sm"
                  :icon="RefreshCwIcon"
                  :loading="openRouterFreeModelsLoading"
                  :title="$t('settings.providers.openrouterFreeModels.refresh')"
                  :aria-label="$t('settings.providers.openrouterFreeModels.refresh')"
                  @click="handleRefreshOpenRouterFreeModels"
                />
              </div>

              <div v-if="openRouterFreeModels.length > 0" class="openrouter-model-browser">
                <select
                  class="openrouter-model-select"
                  :value="selectedOpenRouterFreeModel?.id || ''"
                  size="10"
                  @change="handleOpenRouterFreeModelChange"
                >
                  <option
                    v-for="model in openRouterFreeModels"
                    :key="model.id"
                    :value="model.id"
                  >
                    {{ model.id }}
                  </option>
                </select>

                <div v-if="selectedOpenRouterFreeModel" class="openrouter-model-detail">
                  <div class="openrouter-model-card-head">
                    <strong class="openrouter-model-name">{{ selectedOpenRouterFreeModel.name }}</strong>
                    <span class="openrouter-model-id">{{ selectedOpenRouterFreeModel.id }}</span>
                  </div>

                  <p v-if="selectedOpenRouterFreeModel.variantId && selectedOpenRouterFreeModel.variantId !== selectedOpenRouterFreeModel.id" class="openrouter-model-variant">
                    {{
                      $t('settings.providers.openrouterFreeModels.freeVariant', {
                        value: selectedOpenRouterFreeModel.variantId,
                      })
                    }}
                  </p>

                  <p v-if="selectedOpenRouterFreeModel.description" class="openrouter-model-description">
                    {{ selectedOpenRouterFreeModel.description }}
                  </p>

                  <div class="openrouter-model-meta">
                    <span class="openrouter-model-pill">
                      {{
                        selectedOpenRouterFreeModel.contextLength
                          ? $t('settings.providers.openrouterFreeModels.context', { count: formatContextLength(selectedOpenRouterFreeModel.contextLength) })
                          : $t('settings.providers.openrouterFreeModels.contextUnknown')
                      }}
                    </span>
                    <span class="openrouter-model-pill">
                      {{
                        selectedOpenRouterFreeModel.supportsReasoning
                          ? $t('settings.providers.openrouterFreeModels.reasoningOn')
                          : $t('settings.providers.openrouterFreeModels.reasoningOff')
                      }}
                    </span>
                  </div>

                  <p class="openrouter-model-params">
                    {{
                      $t('settings.providers.openrouterFreeModels.params', {
                        value: formatSupportedParameters(selectedOpenRouterFreeModel.supportedParameters),
                      })
                    }}
                  </p>
                </div>
              </div>

              <p v-else class="openrouter-model-empty">
                {{ $t('settings.providers.openrouterFreeModels.empty') }}
              </p>
            </div>
          </div>
        </div>

        <div class="form-group">
          <label class="label">
            {{ $t('settings.providers.apiKey') }}
            <span v-if="isApiKeyOptional" class="label-hint">({{ $t('common.optional') }})</span>
          </label>
          <div class="api-key-list">
            <div
              v-for="(_, index) in providerConfig.apiKeys"
              :key="`api-key-${selectedProvider}-${index}`"
              class="api-key-row"
            >
              <Input
                v-model="providerConfig.apiKeys[index]"
                type="password"
                :placeholder="isApiKeyOptional ? $t('settings.providers.apiKeyOptionalPlaceholder') : $t('settings.providers.apiKeyPlaceholder')"
              />
              <Button
                v-if="providerConfig.apiKeys.length > 1"
                variant="ghost"
                size="sm"
                :icon="TrashIcon"
                :title="$t('common.remove')"
                :aria-label="$t('common.remove')"
                @click="removeApiKeyField(index)"
              />
            </div>
          </div>
          <div class="api-key-actions">
            <Button
              variant="outline"
              size="sm"
              :icon="PlusIcon"
              @click="addApiKeyField"
            >
              {{ $t('common.add') }}
            </Button>
            <p class="hint api-key-hint">
              {{ $t('settings.providers.apiKeysHint') }}
            </p>
          </div>
          <div v-if="isOpenRouterProvider" class="openrouter-access">
            <p class="hint">
              {{ $t('settings.providers.openrouterAccess.message') }}
            </p>
            <div class="openrouter-access-links">
              <a
                class="openrouter-access-link"
                :href="OPENROUTER_LINKS.home"
                target="_blank"
                rel="noreferrer"
              >
                {{ $t('settings.providers.openrouterAccess.home') }}
              </a>
              <a
                class="openrouter-access-link"
                :href="OPENROUTER_LINKS.freeModels"
                target="_blank"
                rel="noreferrer"
              >
                {{ $t('settings.providers.openrouterAccess.freeModels') }}
              </a>
              <a
                class="openrouter-access-link"
                :href="OPENROUTER_LINKS.apiKeys"
                target="_blank"
                rel="noreferrer"
              >
                {{ $t('settings.providers.openrouterAccess.apiKeys') }}
              </a>
            </div>
          </div>
        </div>

        <div class="form-group">
          <label class="label">
            {{ $t('settings.providers.baseUrl') }}
            <span v-if="currentDefaultBaseUrl" class="label-hint">({{ $t('common.optional') }})</span>
            <span v-else-if="isCustomProvider" class="label-hint required-hint">*</span>
          </label>
          <Input
            v-model="providerConfig.baseUrl"
            type="text"
            :placeholder="isCustomProvider ? $t('settings.providers.baseUrlRequiredPlaceholder') : (currentDefaultBaseUrl || $t('settings.providers.baseUrlPlaceholder'))"
          />
          <p class="hint">
            {{ $t('settings.providers.baseUrlHint') }}
          </p>
        </div>
      </div>

      <div class="toggle-card">
        <label class="label">{{ $t('settings.providers.enabled') }}</label>

        <SwitchToggle
          v-model="providerConfig.enabled"
          :width="50"
          :height="30"
          :aria-label="$t('settings.providers.enabled')"
        />
      </div>

      <div class="action-row">
        <Button
          variant="secondary"
          :loading="testing"
          :disabled="!canTestConnection"
          @click="handleTestConnection"
        >
          {{ testing ? $t('settings.providers.testing') : $t('settings.providers.testConnection') }}
        </Button>
      </div>

      <div
        v-if="testResult"
        class="test-result"
        :class="testResult.success ? 'success' : 'error'"
      >
        <component
          :is="testResult.success ? CheckCircleIcon : XCircleIcon"
          :size="16"
        />
        <span>{{ testResult.message }}</span>
      </div>
    </section>

    <ProviderPresetPanel
      v-model="showPresetPanel"
      :current-config="currentDraftConfig"
      :available-providers="availableProviders"
      @apply-config="handleApplyConfig"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  CheckCircle as CheckCircleIcon,
  LayoutGrid as LayoutGridIcon,
  Plus as PlusIcon,
  RefreshCw as RefreshCwIcon,
  Search as SearchIcon,
  Trash2 as TrashIcon,
  XCircle as XCircleIcon,
} from 'lucide-vue-next'
import Input from '@/components/ui/Input.vue'
import Select from '@/components/ui/Select.vue'
import Button from '@/components/ui/Button.vue'
import SwitchToggle from '@/components/ui/SwitchToggle.vue'
import ProviderPresetPanel from './ProviderPresetPanel.vue'
import { useToast } from '@/composables/useToast'
import { useSettingsStore } from '@/store/settings'
import { settingsAPI } from '@/api'
import type { ProviderConfig as ProviderConfigType, ProviderMetadata } from '@/types/settings'
import {
  computeProviderRuntimeState,
  findProviderById,
  resolveProviderGroup,
  resolveThinkingControlNoteKey,
  resolveThinkingControlTier,
  resolveProviderDefaultApiBase,
  resolveProviderDefaultModel,
  sortProvidersForDisplay,
} from '@/utils/providerRuntime'
import { buildSendableModelConfig } from '@/utils/modelConfig'
import { fetchOpenRouterFreeModels, type OpenRouterFreeModelOption } from '@/utils/openrouterModels'

interface AppliedSource {
  type: 'preset' | 'codingplan'
  label: string
}

interface ApplyDraftPayload {
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

const { t } = useI18n()
const toast = useToast()
const settingsStore = useSettingsStore()

const selectedProvider = ref('')
const modelName = ref('')
const providerConfig = ref<ProviderConfigType>({
  apiKey: '',
  apiKeys: [''],
  baseUrl: '',
  enabled: true
})
const testing = ref(false)
const testResult = ref<{ success: boolean; message: string } | null>(null)
const availableProviders = ref<ProviderMetadata[]>([])
const isHydrating = ref(false)
const isApplyingExternalConfig = ref(false)
const showPresetPanel = ref(false)
const appliedSource = ref<AppliedSource | null>(null)
const openRouterFreeModels = ref<OpenRouterFreeModelOption[]>([])
const openRouterFreeModelsLoading = ref(false)
const openRouterFreeModelsLoaded = ref(false)
const showOpenRouterFreeModels = ref(false)

const providerOptions = computed(() =>
  sortProvidersForDisplay(availableProviders.value).map(provider => ({
    value: provider.id,
    label: provider.name || provider.id,
  }))
)

const selectedProviderOption = computed({
  get: () => selectedProvider.value,
  set: (value: string) => {
    selectedProvider.value = value
    if (settingsStore.settings?.model) {
      settingsStore.settings.model.api_mode = 'chat_completions'
    }
  },
})

const selectedProviderMeta = computed(() =>
  findProviderById(availableProviders.value, selectedProvider.value)
)

const selectedProviderGroup = computed(() =>
  resolveProviderGroup(selectedProviderMeta.value)
)

const selectedProviderThinkingTier = computed(() =>
  resolveThinkingControlTier(selectedProviderMeta.value)
)

const selectedProviderGroupLabel = computed(() =>
  t(`settings.providers.thinkingControl.groups.${selectedProviderGroup.value}`)
)

const selectedProviderThinkingTierLabel = computed(() =>
  t(`settings.providers.thinkingControl.tiers.${selectedProviderThinkingTier.value}`)
)

const selectedProviderThinkingNote = computed(() => {
  if (!selectedProviderMeta.value) {
    return ''
  }
  return t(resolveThinkingControlNoteKey(selectedProviderMeta.value))
})

const OPENROUTER_LINKS = {
  home: 'https://openrouter.ai',
  freeModels: 'https://openrouter.ai/collections/free-models',
  apiKeys: 'https://openrouter.ai/settings/keys',
} as const

const LOCAL_PROVIDERS = ['ollama', 'vllm', 'lm_studio']
const NO_API_KEY_PROVIDERS = ['custom_openai', 'custom_anthropic']
const CUSTOM_PROVIDERS = ['custom_openai', 'custom_anthropic']

function normalizeApiKeys(values: string[] | undefined, fallbackApiKey = ''): string[] {
  const normalized: string[] = []
  const seen = new Set<string>()

  const pushValue = (value: string | undefined) => {
    const trimmed = String(value || '').trim()
    if (!trimmed || seen.has(trimmed)) {
      return
    }
    seen.add(trimmed)
    normalized.push(trimmed)
  }

  for (const value of values || []) {
    pushValue(value)
  }
  pushValue(fallbackApiKey)

  return normalized
}

function buildEditableApiKeys(values: string[] | undefined, fallbackApiKey = ''): string[] {
  const normalized = normalizeApiKeys(values, fallbackApiKey)
  return normalized.length ? normalized : ['']
}

function getPrimaryApiKey(): string {
  return normalizeApiKeys(providerConfig.value.apiKeys)[0] || ''
}

function addApiKeyField() {
  providerConfig.value.apiKeys.push('')
}

function removeApiKeyField(index: number) {
  providerConfig.value.apiKeys.splice(index, 1)
  if (providerConfig.value.apiKeys.length === 0) {
    providerConfig.value.apiKeys = ['']
  }
}

const isLocalProvider = computed(() => LOCAL_PROVIDERS.includes(selectedProvider.value))
const isOpenRouterProvider = computed(() => selectedProvider.value === 'openrouter')
const isApiKeyOptional = computed(() =>
  isLocalProvider.value || NO_API_KEY_PROVIDERS.includes(selectedProvider.value)
)
const isCustomProvider = computed(() => CUSTOM_PROVIDERS.includes(selectedProvider.value))
const openRouterFreeModelsButtonText = computed(() => {
  if (showOpenRouterFreeModels.value) {
    return t('settings.providers.openrouterFreeModels.hide')
  }

  if (openRouterFreeModelsLoaded.value) {
    return t('settings.providers.openrouterFreeModels.show')
  }

  return t('settings.providers.openrouterFreeModels.fetch')
})
function findOpenRouterFreeModelByValue(value: string): OpenRouterFreeModelOption | null {
  const normalizedValue = value.trim()
  if (!normalizedValue) {
    return null
  }

  return openRouterFreeModels.value.find(model =>
    model.id === normalizedValue || model.baseId === normalizedValue,
  ) || null
}

const selectedOpenRouterFreeModel = computed(() =>
  findOpenRouterFreeModelByValue(modelName.value)
  || openRouterFreeModels.value[0]
  || null
)

const currentDefaultBaseUrl = computed(() => resolveProviderDefaultApiBase(selectedProviderMeta.value))
const selectedProviderRuntime = computed(() => {
  if (!selectedProviderMeta.value) {
    return null
  }

  return computeProviderRuntimeState(selectedProviderMeta.value, {
    enabled: providerConfig.value.enabled,
    api_key: getPrimaryApiKey(),
    api_keys: normalizeApiKeys(providerConfig.value.apiKeys),
    api_base: providerConfig.value.baseUrl,
  })
})

const selectedProviderSelectable = computed(() => selectedProviderRuntime.value?.selectable ?? false)

const selectedProviderStatusText = computed(() => {
  const runtime = selectedProviderRuntime.value
  if (!runtime) {
    return ''
  }
  if (runtime.selectable) {
    return t('settings.providers.providerReadyHint')
  }
  if (runtime.reason === 'missing_api_key') {
    return t('settings.providers.providerMissingApiKeyHint')
  }
  if (runtime.reason === 'missing_api_base') {
    return t('settings.providers.providerMissingApiBaseHint')
  }
  return t('settings.providers.providerDisabledHint')
})

const currentDraftConfig = computed(() => ({
  provider: selectedProvider.value,
  model: modelName.value,
  apiKey: getPrimaryApiKey(),
  baseUrl: providerConfig.value.baseUrl,
  enabled: providerConfig.value.enabled,
  temperature: settingsStore.settings?.model?.temperature,
  maxTokens: settingsStore.settings?.model?.max_tokens,
  maxIterations: settingsStore.settings?.model?.max_iterations,
}))

const savedSnapshot = computed(() => {
  const savedModel = settingsStore.persistedSettings?.model
  if (!savedModel) {
    return {
      provider: t('common.loading'),
      model: '',
    }
  }

  const providerLabel = findProviderById(availableProviders.value, savedModel.provider)?.name || savedModel.provider
  return {
    provider: providerLabel,
    model: savedModel.model || t('common.default'),
  }
})

const draftSnapshot = computed(() => ({
  provider: selectedProviderMeta.value?.name || selectedProvider.value || t('common.unknown'),
  model: modelName.value || t('common.default'),
}))

const appliedSourceText = computed(() => {
  if (!appliedSource.value) {
    return ''
  }

  const prefix = appliedSource.value.type === 'codingplan'
    ? t('settings.providers.presetPanel.sourceCodingPlan')
    : t('settings.providers.presetPanel.sourcePreset')
  return `${prefix} · ${appliedSource.value.label}`
})

const draftStateHint = computed(() => {
  if (hasDraftChanges.value) {
    return t('settings.providers.presetPanel.draftChanged')
  }
  return ''
})

const canTestConnection = computed(() =>
  Boolean(selectedProvider.value)
  && Boolean(modelName.value.trim())
  && (isApiKeyOptional.value || Boolean(getPrimaryApiKey()))
)

const hasDraftChanges = computed(() => {
  const saved = settingsStore.persistedSettings
  if (!saved) {
    return false
  }

  const selectedProviderSavedConfig = saved.providers?.[selectedProvider.value]
  const savedApiKeys = normalizeApiKeys(
    selectedProviderSavedConfig?.api_keys,
    selectedProviderSavedConfig?.api_key || '',
  )
  const savedProjection = {
    provider: saved.model.provider,
    model: saved.model.model,
    apiKey: savedApiKeys[0] || '',
    apiKeys: savedApiKeys,
    baseUrl: selectedProviderSavedConfig?.api_base || currentDefaultBaseUrl.value || '',
    enabled: selectedProviderSavedConfig?.enabled ?? true,
    temperature: saved.model.temperature,
    maxTokens: saved.model.max_tokens,
    maxIterations: saved.model.max_iterations,
  }

  const draftProjection = {
    provider: selectedProvider.value,
    model: modelName.value,
    apiKey: getPrimaryApiKey(),
    apiKeys: normalizeApiKeys(providerConfig.value.apiKeys),
    baseUrl: providerConfig.value.baseUrl || currentDefaultBaseUrl.value || '',
    enabled: providerConfig.value.enabled,
    temperature: settingsStore.settings?.model?.temperature,
    maxTokens: settingsStore.settings?.model?.max_tokens,
    maxIterations: settingsStore.settings?.model?.max_iterations,
  }

  return JSON.stringify(savedProjection) !== JSON.stringify(draftProjection)
})

function hydrateDraft(providerId: string) {
  if (!settingsStore.settings?.providers || !settingsStore.settings?.model) {
    return
  }

  const existing = settingsStore.settings.providers[providerId]
  const providerMeta = findProviderById(availableProviders.value, providerId)
  const defaultBaseUrl = resolveProviderDefaultApiBase(providerMeta)
  const defaultModel = resolveProviderDefaultModel(providerMeta)
  const apiKeys = buildEditableApiKeys(existing?.api_keys, existing?.api_key || '')

  providerConfig.value = {
    apiKey: apiKeys[0] || '',
    apiKeys,
    baseUrl: existing?.api_base || defaultBaseUrl,
    enabled: existing?.enabled ?? true,
  }

  if (settingsStore.settings.model.provider === providerId) {
    modelName.value = settingsStore.settings.model.model || defaultModel
  } else {
    modelName.value = defaultModel
  }
}

function initializeProvider() {
  if (!settingsStore.settings?.model) {
    return
  }

  const fallbackProvider = settingsStore.settings.model.provider
    || availableProviders.value[0]?.id
    || ''

  if (!fallbackProvider) {
    return
  }

  isHydrating.value = true
  selectedProvider.value = fallbackProvider
  hydrateDraft(fallbackProvider)
  isHydrating.value = false
}

function syncProviderDraftToStore() {
  if (!selectedProvider.value || !settingsStore.settings?.providers) {
    return
  }

  const apiKeys = normalizeApiKeys(providerConfig.value.apiKeys)
  const primaryApiKey = apiKeys[0] || ''

  settingsStore.settings.providers[selectedProvider.value] = {
    enabled: providerConfig.value.enabled,
    api_key: primaryApiKey,
    api_keys: apiKeys,
    api_base: providerConfig.value.baseUrl || undefined,
  }
}

function syncModelDraftToStore() {
  if (!settingsStore.settings?.model || !selectedProvider.value || !selectedProviderSelectable.value) {
    return
  }

  settingsStore.settings.model.api_mode = 'chat_completions'
  settingsStore.settings.model.provider = selectedProvider.value
  settingsStore.settings.model.model = modelName.value
}

async function loadProviders() {
  try {
    availableProviders.value = sortProvidersForDisplay(await settingsAPI.getProviders())
  } catch (error) {
    console.error('Failed to load providers:', error)
    availableProviders.value = sortProvidersForDisplay([
      { id: 'openrouter', name: 'OpenRouter' },
      { id: 'anthropic', name: 'Anthropic' },
      { id: 'openai', name: 'OpenAI' },
      { id: 'deepseek', name: 'DeepSeek' },
      { id: 'moonshot', name: 'Moonshot AI / Kimi' },
      { id: 'zhipu', name: 'Zhipu AI (GLM)' },
      { id: 'groq', name: 'Groq' },
      { id: 'mistral', name: 'Mistral AI' },
      { id: 'cohere', name: 'Cohere' },
      { id: 'together_ai', name: 'Together AI' },
      { id: 'qwen', name: 'Alibaba Cloud Bailian (阿里云百炼)' },
      { id: 'hunyuan', name: 'Tencent Cloud (腾讯云)' },
      { id: 'ernie', name: 'Baidu Qianfan (百度智能云千帆)' },
      { id: 'doubao', name: 'Volcengine (字节火山引擎)' },
      { id: 'yi', name: '01.AI (Yi)' },
      { id: 'baichuan', name: 'Baichuan AI' },
      { id: 'minimax', name: 'MiniMax' },
      { id: 'vllm', name: 'vLLM' },
      { id: 'ollama', name: 'Ollama' },
      { id: 'lm_studio', name: 'LM Studio' },
      { id: 'custom_openai', name: 'Custom API (OpenAI)' },
      { id: 'custom_anthropic', name: 'Custom API (Anthropic)' }
    ])
  }
}

function handleApplyConfig(payload: ApplyDraftPayload) {
  isApplyingExternalConfig.value = true
  selectedProvider.value = payload.provider
  const apiKeys = buildEditableApiKeys([payload.apiKey], payload.apiKey)
  providerConfig.value = {
    apiKey: apiKeys[0] || '',
    apiKeys,
    baseUrl: payload.baseUrl || '',
    enabled: payload.enabled,
  }
  modelName.value = payload.model

  if (settingsStore.settings?.model) {
    if (payload.temperature !== undefined) {
      settingsStore.settings.model.temperature = payload.temperature
    }
    if (payload.maxTokens !== undefined) {
      settingsStore.settings.model.max_tokens = payload.maxTokens
    }
    if (payload.maxIterations !== undefined) {
      settingsStore.settings.model.max_iterations = payload.maxIterations
    }
  }

  syncProviderDraftToStore()
  syncModelDraftToStore()
  appliedSource.value = { type: payload.source, label: payload.label }
  testResult.value = null
  isApplyingExternalConfig.value = false
}

function formatContextLength(value: number): string {
  return new Intl.NumberFormat().format(value)
}

function formatSupportedParameters(parameters: string[]): string {
  if (!parameters.length) {
    return t('settings.providers.openrouterFreeModels.paramsFallback')
  }

  return parameters.join(', ')
}

async function loadOpenRouterFreeModels(force = false) {
  if (openRouterFreeModelsLoading.value) {
    return
  }

  if (!force && openRouterFreeModelsLoaded.value) {
    return
  }

  openRouterFreeModelsLoading.value = true

  try {
    openRouterFreeModels.value = await fetchOpenRouterFreeModels()
    openRouterFreeModelsLoaded.value = true

    const matchedModel = findOpenRouterFreeModelByValue(modelName.value)
    if (matchedModel && modelName.value.trim() !== matchedModel.id) {
      modelName.value = matchedModel.id
    }
  } catch (error) {
    console.error('Failed to load OpenRouter free models:', error)
    toast.error(t('settings.providers.openrouterFreeModels.fetchFailed'))
  } finally {
    openRouterFreeModelsLoading.value = false
  }
}

async function handleOpenRouterFreeModels() {
  if (!isOpenRouterProvider.value) {
    return
  }

  if (!openRouterFreeModelsLoaded.value) {
    await loadOpenRouterFreeModels()

    if (openRouterFreeModels.value.length > 0) {
      showOpenRouterFreeModels.value = true
    }

    return
  }

  showOpenRouterFreeModels.value = !showOpenRouterFreeModels.value
}

async function handleRefreshOpenRouterFreeModels() {
  await loadOpenRouterFreeModels(true)

  if (openRouterFreeModels.value.length > 0) {
    showOpenRouterFreeModels.value = true
  }
}

function handleSelectOpenRouterFreeModel(modelId: string) {
  modelName.value = modelId
}

function handleOpenRouterFreeModelChange(event: Event) {
  handleSelectOpenRouterFreeModel((event.target as HTMLSelectElement).value)
}

async function handleTestConnection() {
  if (!selectedProvider.value || !canTestConnection.value) {
    return
  }

  testing.value = true
  testResult.value = null

  try {
    const response = await settingsAPI.testConnection({
      provider: selectedProvider.value,
      api_key: getPrimaryApiKey(),
      api_base: providerConfig.value.baseUrl,
      model: modelName.value,
      ...buildSendableModelConfig(settingsStore.settings?.model),
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

watch(selectedProvider, (newProvider) => {
  if (!newProvider || isHydrating.value || isApplyingExternalConfig.value) {
    return
  }

  if (newProvider !== 'openrouter') {
    showOpenRouterFreeModels.value = false
  }

  hydrateDraft(newProvider)
  syncProviderDraftToStore()
  syncModelDraftToStore()
  testResult.value = null
})

watch(providerConfig, () => {
  if (isHydrating.value) {
    return
  }
  syncProviderDraftToStore()
  syncModelDraftToStore()
  testResult.value = null
}, { deep: true })

watch(modelName, () => {
  if (isHydrating.value) {
    return
  }
  syncModelDraftToStore()
  testResult.value = null
})

watch(() => settingsStore.settings, (newSettings) => {
  if (newSettings && !selectedProvider.value) {
    initializeProvider()
  }
}, { immediate: true })

watch(availableProviders, () => {
  if (!selectedProvider.value && settingsStore.settings?.model) {
    initializeProvider()
  }
}, { deep: true })

onMounted(async () => {
  await loadProviders()
  initializeProvider()
})
</script>
<style scoped>
@import './styles/ProviderConfig.css';
</style>
