/**
 * 供应商连接草稿（名称 / Base URL / 协议 / 密钥）与连接测试。
 *
 * 唯一所有者：`providerConfig` 与 `modelName`（当前选中的模型名）。
 * 草稿落地到 store 的唯一入口是 `syncProviderDraftToStore`，
 * 落库（写后端）的唯一入口是 `saveProviderConnection`——
 * 模型清单接口读的是已保存配置，所以拉取/测试前必须先保存。
 */

import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { ProviderApiType, ProviderConfig, ProviderMetadata } from '@/api'
import { settingsAPI } from '@/api'
import { useSettingsStore } from '@/store/settings'
import { buildSendableModelConfig } from '@/utils/modelConfig'
import { useToast } from '@/composables/useToast'
import {
  computeProviderRuntimeState,
  resolveProviderDefaultApiBase,
  resolveProviderDefaultModel,
  resolveThinkingControlNoteKey,
  findProviderById,
} from '@/utils/providerRuntime'
import {
  CUSTOM_PROVIDERS,
  DEFAULT_API_TYPE,
  LOCAL_PROVIDERS,
  NO_API_KEY_PROVIDERS,
  buildEditableApiKeys,
  normalizeApiKeys,
  resolveDefaultApiType,
} from './constants'
import type {
  AppliedSource,
  ApplyDraftPayload,
  ConnectionTestResult,
  ProviderDraft,
  ProviderDraftConfig,
} from './types'

export interface ProviderDraftState {
  providerConfig: Ref<ProviderDraft>
  modelName: Ref<string>
  testing: Ref<boolean>
  testResult: Ref<ConnectionTestResult | null>
  isHydrating: Ref<boolean>
  isApplyingExternalConfig: Ref<boolean>
  appliedSource: Ref<AppliedSource | null>
  isApiKeyOptional: ComputedRef<boolean>
  isCustomProvider: ComputedRef<boolean>
  currentDefaultBaseUrl: ComputedRef<string | undefined>
  selectedProviderSelectable: ComputedRef<boolean>
  selectedProviderStatusText: ComputedRef<string>
  selectedProviderThinkingNote: ComputedRef<string>
  currentDraftConfig: ComputedRef<ProviderDraftConfig>
  savedSnapshot: ComputedRef<{ provider: string; model: string }>
  draftSnapshot: ComputedRef<{ provider: string; model: string }>
  appliedSourceText: ComputedRef<string>
  draftStateHint: ComputedRef<string>
  hasDraftChanges: ComputedRef<boolean>
  canTestConnection: ComputedRef<boolean>
  getPrimaryApiKey: () => string
  addApiKeyField: () => void
  removeApiKeyField: (index: number) => void
  hydrateDraft: (providerId: string) => void
  initializeProvider: () => void
  /** 默认写回当前选中的供应商；切换供应商时要显式传入「旧」供应商，避免把旧草稿写进新供应商 */
  syncProviderDraftToStore: (providerId?: string) => void
  syncModelDraftToStore: () => void
  saveProviderConnection: () => Promise<void>
  testConnection: () => Promise<void>
  applyExternalConfig: (payload: ApplyDraftPayload) => void
  createProvider: (providerId: string) => boolean
  deleteProvider: (providerId: string) => Promise<boolean>
}

/** 草稿里这个供应商算不算「已经接过了」。 */
function hasCredentialsOrModels(config: unknown): boolean {
  if (!config || typeof config !== 'object') {
    return false
  }
  const record = config as Record<string, unknown>
  const keys: unknown[] = [record.api_key, ...((record.api_keys as unknown[]) || [])]
  if (keys.some(key => String(key || '').trim())) {
    return true
  }
  return ((record.models as unknown[]) || []).length > 0
}

export interface ProviderDraftDeps {
  selectedProvider: Ref<string>
  selectedProviderMeta: ComputedRef<ProviderMetadata | undefined>
  availableProviders: Ref<ProviderMetadata[]>
}

export function useProviderDraft(deps: ProviderDraftDeps): ProviderDraftState {
  const { t } = useI18n()
  const toast = useToast()
  const settingsStore = useSettingsStore()

  const providerConfig = ref<ProviderDraft>({
    apiKey: '',
    apiKeys: [''],
    baseUrl: '',
    enabled: true,
    name: '',
    apiType: DEFAULT_API_TYPE,
  })
  const modelName = ref('')
  const testing = ref(false)
  const testResult = ref<ConnectionTestResult | null>(null)
  const isHydrating = ref(false)
  const isApplyingExternalConfig = ref(false)
  const appliedSource = ref<AppliedSource | null>(null)

  /* ---------------- 派生状态 ---------------- */

  const isLocalProvider = computed(() => LOCAL_PROVIDERS.includes(deps.selectedProvider.value))
  const isApiKeyOptional = computed(
    () => isLocalProvider.value || NO_API_KEY_PROVIDERS.includes(deps.selectedProvider.value),
  )
  const isCustomProvider = computed(() => CUSTOM_PROVIDERS.includes(deps.selectedProvider.value))
  const currentDefaultBaseUrl = computed(() =>
    resolveProviderDefaultApiBase(deps.selectedProviderMeta.value),
  )

  function getPrimaryApiKey(): string {
    return normalizeApiKeys(providerConfig.value.apiKeys)[0] || ''
  }

  const selectedProviderRuntime = computed(() => {
    if (!deps.selectedProviderMeta.value) {
      return null
    }
    return computeProviderRuntimeState(deps.selectedProviderMeta.value, {
      enabled: providerConfig.value.enabled,
      api_key: getPrimaryApiKey(),
      api_keys: normalizeApiKeys(providerConfig.value.apiKeys),
      api_base: providerConfig.value.baseUrl,
    })
  })

  const selectedProviderSelectable = computed(
    () => selectedProviderRuntime.value?.selectable ?? false,
  )

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

  const selectedProviderThinkingNote = computed(() => {
    if (!deps.selectedProviderMeta.value) {
      return ''
    }
    return t(resolveThinkingControlNoteKey(deps.selectedProviderMeta.value))
  })

  const currentDraftConfig = computed<ProviderDraftConfig>(() => ({
    provider: deps.selectedProvider.value,
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
      return { provider: t('common.loading'), model: '' }
    }
    const providerLabel =
      findProviderById(deps.availableProviders.value, savedModel.provider)?.name
      || savedModel.provider
    return {
      provider: providerLabel,
      model: savedModel.model || t('common.default'),
    }
  })

  const draftSnapshot = computed(() => ({
    provider:
      deps.selectedProviderMeta.value?.name
      || deps.selectedProvider.value
      || t('common.unknown'),
    model: modelName.value || t('common.default'),
  }))

  const appliedSourceText = computed(() => {
    if (!appliedSource.value) {
      return ''
    }
    const prefix =
      appliedSource.value.type === 'codingplan'
        ? t('settings.providers.presetPanel.sourceCodingPlan')
        : t('settings.providers.presetPanel.sourcePreset')
    return `${prefix} · ${appliedSource.value.label}`
  })

  const canTestConnection = computed(
    () =>
      Boolean(deps.selectedProvider.value)
      && Boolean(modelName.value.trim())
      && (isApiKeyOptional.value || Boolean(getPrimaryApiKey())),
  )

  /** 与已保存配置逐字段比对，用于「当前草稿」卡片是否高亮。 */
  const hasDraftChanges = computed(() => {
    const saved = settingsStore.persistedSettings
    if (!saved) {
      return false
    }

    const savedProviderConfig = saved.providers?.[deps.selectedProvider.value]
    const savedApiKeys = normalizeApiKeys(
      savedProviderConfig?.api_keys,
      savedProviderConfig?.api_key || '',
    )
    const savedProjection = {
      provider: saved.model.provider,
      model: saved.model.model,
      apiKey: savedApiKeys[0] || '',
      apiKeys: savedApiKeys,
      baseUrl: savedProviderConfig?.api_base || currentDefaultBaseUrl.value || '',
      enabled: savedProviderConfig?.enabled ?? true,
      name: savedProviderConfig?.name || '',
      apiType: savedProviderConfig?.api_type || DEFAULT_API_TYPE,
    }

    const draftProjection = {
      provider: deps.selectedProvider.value,
      model: modelName.value,
      apiKey: getPrimaryApiKey(),
      apiKeys: normalizeApiKeys(providerConfig.value.apiKeys),
      baseUrl: providerConfig.value.baseUrl || currentDefaultBaseUrl.value || '',
      enabled: providerConfig.value.enabled,
      name: providerConfig.value.name || '',
      apiType: providerConfig.value.apiType,
    }

    return JSON.stringify(savedProjection) !== JSON.stringify(draftProjection)
  })

  const draftStateHint = computed(() =>
    hasDraftChanges.value ? t('settings.providers.presetPanel.draftChanged') : '',
  )

  /* ---------------- 密钥行 ---------------- */

  function addApiKeyField(): void {
    providerConfig.value.apiKeys.push('')
  }

  function removeApiKeyField(index: number): void {
    providerConfig.value.apiKeys.splice(index, 1)
    if (providerConfig.value.apiKeys.length === 0) {
      providerConfig.value.apiKeys = ['']
    }
  }

  /* ---------------- 草稿 <-> store ---------------- */

  function hydrateDraft(providerId: string): void {
    const settings = settingsStore.settings
    if (!settings?.providers || !settings.model) {
      return
    }

    const existing = settings.providers[providerId]
    const providerMeta = findProviderById(deps.availableProviders.value, providerId)
    const defaultBaseUrl = resolveProviderDefaultApiBase(providerMeta)
    const defaultModel = resolveProviderDefaultModel(providerMeta)
    const apiKeys = buildEditableApiKeys(existing?.api_keys, existing?.api_key || '')

    providerConfig.value = {
      apiKey: apiKeys[0] || '',
      apiKeys,
      baseUrl: existing?.api_base || defaultBaseUrl || '',
      enabled: existing?.enabled ?? true,
      name: existing?.name || '',
      apiType: (existing?.api_type as ProviderApiType) || DEFAULT_API_TYPE,
    }

    if (settings.model.provider === providerId) {
      modelName.value = settings.model.model || defaultModel
    } else {
      const firstEnabled = (existing?.models || []).find(model => model.enabled !== false)
      modelName.value = firstEnabled?.id || defaultModel
    }
  }

  function initializeProvider(): void {
    const settings = settingsStore.settings
    if (!settings?.model) {
      return
    }

    const fallbackProvider =
      settings.model.provider
      || Object.keys(settings.providers || {})[0]
      || deps.availableProviders.value[0]?.id
      || ''

    if (!fallbackProvider) {
      return
    }

    isHydrating.value = true
    deps.selectedProvider.value = fallbackProvider
    hydrateDraft(fallbackProvider)
    isHydrating.value = false
  }

  /**
   * 草稿 -> settings store（只改内存，不落库）。
   *
   * `providerId` 默认取当前选中的供应商；切换供应商时必须传入旧 id——
   * watch 回调执行时选中项已经变成新的了，不传就会把旧供应商的草稿写进新供应商。
   */
  function syncProviderDraftToStore(providerId: string = deps.selectedProvider.value): void {
    const providers = settingsStore.settings?.providers
    if (!providerId || !providers) {
      return
    }

    const apiKeys = normalizeApiKeys(providerConfig.value.apiKeys)
    const primaryApiKey = apiKeys[0] || ''
    const existing = providers[providerId] || { enabled: true, models: [] }

    providers[providerId] = {
      ...existing,
      enabled: providerConfig.value.enabled,
      api_key: primaryApiKey,
      api_keys: apiKeys,
      api_base: providerConfig.value.baseUrl || undefined,
      name: providerConfig.value.name.trim() || null,
      api_type: providerConfig.value.apiType,
      models: existing.models || [],
    }
  }

  /** 把当前选中的模型写回全局默认（仅在供应商可用时）。 */
  function syncModelDraftToStore(): void {
    const settings = settingsStore.settings
    if (!settings?.model || !deps.selectedProvider.value || !selectedProviderSelectable.value) {
      return
    }

    const models = settings.providers?.[deps.selectedProvider.value]?.models || []
    const firstEnabled = models.find(model => model.enabled !== false)
    // 全部模型被隐藏时不允许把隐藏模型写进「当前选择」
    if (!firstEnabled && models.length > 0) {
      return
    }
    if (!modelName.value.trim()) {
      return
    }

    settings.model.provider = deps.selectedProvider.value
    settings.model.model = modelName.value
  }

  /* ---------------- 落库与测试 ---------------- */

  async function saveProviderConnection(): Promise<void> {
    const providers = settingsStore.settings?.providers
    if (!providers?.[deps.selectedProvider.value]) {
      return
    }

    try {
      const response = await settingsAPI.update({
        providers: { [deps.selectedProvider.value]: providers[deps.selectedProvider.value] },
      })
      settingsStore.settings = response
      settingsStore.persistedSettings = JSON.parse(JSON.stringify(response))
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || t('common.saveFailed'))
    }
  }

  async function testConnection(): Promise<void> {
    if (!deps.selectedProvider.value || !canTestConnection.value) {
      return
    }

    testing.value = true
    testResult.value = null

    try {
      const response = await settingsAPI.testConnection({
        provider: deps.selectedProvider.value,
        api_key: getPrimaryApiKey(),
        api_base: providerConfig.value.baseUrl,
        api_type: providerConfig.value.apiType,
        model: modelName.value,
        ...buildSendableModelConfig(settingsStore.settings?.model),
      })

      testResult.value = {
        success: response.success,
        message: response.success
          ? response.message || t('settings.providers.testSuccess')
          : response.error || response.message || t('settings.providers.testFailed'),
      }
    } catch (error: any) {
      testResult.value = {
        success: false,
        message:
          error.response?.data?.error || error.message || t('settings.providers.testFailed'),
      }
    } finally {
      testing.value = false
    }
  }

  /* ---------------- 预设回填 / 新建供应商 ---------------- */

  function applyExternalConfig(payload: ApplyDraftPayload): void {
    isApplyingExternalConfig.value = true
    deps.selectedProvider.value = payload.provider
    const apiKeys = buildEditableApiKeys([payload.apiKey], payload.apiKey)
    providerConfig.value = {
      apiKey: apiKeys[0] || '',
      apiKeys,
      baseUrl: payload.baseUrl || '',
      enabled: payload.enabled,
      name: providerConfig.value.name,
      apiType: providerConfig.value.apiType,
    }
    modelName.value = payload.model

    const settings = settingsStore.settings
    if (settings?.model) {
      if (payload.temperature !== undefined) {
        settings.model.temperature = payload.temperature
      }
      if (payload.maxTokens !== undefined) {
        settings.model.max_tokens = payload.maxTokens
      }
      if (payload.maxIterations !== undefined) {
        settings.model.max_iterations = payload.maxIterations
      }
    }

    syncProviderDraftToStore()
    syncModelDraftToStore()
    appliedSource.value = { type: payload.source, label: payload.label }
    testResult.value = null
    isApplyingExternalConfig.value = false
  }

  /**
   * 「添加供应商」选中某个供应商。
   *
   * 注意：后端启动时会为目录里的每个供应商都预建一条空配置，
   * 所以不能拿「配置里有没有这个 id」判断是否已添加——那会永远命中、点了没反应。
   * 这里以「有没有密钥或模型」判断是否已经真正接过，没接过就补上默认值并选中。
   * 只写草稿、不落库：落库由「保存」触发（加模型前会先自动落库）。
   *
   * @returns 是否真的执行了添加（已配置过的返回 false）
   */
  function createProvider(providerId: string): boolean {
    const providers = settingsStore.settings?.providers
    if (!providers) {
      return false
    }

    const existing = providers[providerId]
    if (existing && hasCredentialsOrModels(existing)) {
      deps.selectedProvider.value = providerId
      return false
    }

    const meta = findProviderById(deps.availableProviders.value, providerId)
    providers[providerId] = {
      ...(existing || {}),
      enabled: existing?.enabled ?? true,
      api_key: existing?.api_key || '',
      api_keys: existing?.api_keys || [],
      api_base: existing?.api_base || resolveProviderDefaultApiBase(meta),
      name: existing?.name ?? null,
      api_type: (existing?.api_type as ProviderApiType) || resolveDefaultApiType(meta?.id),
      models: existing?.models || [],
    }

    deps.selectedProvider.value = providerId
    return true
  }

  /**
   * 从左侧栏删掉一个供应商。
   *
   * 后端启动时就为目录里每个供应商预建了空配置，也没有单独的删除接口，
   * 所以「删除」= 清空它的密钥与模型清单，并立即落库：
   * 清空后它不再出现在左栏，也从对话窗口的模型下拉里消失。
   * 立即落库是因为延迟到「保存」才生效的话，用户不点保存、刷新后它又冒出来了。
   *
   * @returns 是否删除成功（供应商不存在或落库失败返回 false）
   */
  async function deleteProvider(providerId: string): Promise<boolean> {
    const providers = settingsStore.settings?.providers
    if (!providerId || !providers?.[providerId]) {
      return false
    }

    const meta = findProviderById(deps.availableProviders.value, providerId)
    const cleared: ProviderConfig = {
      enabled: true,
      api_key: '',
      api_keys: [],
      api_base: resolveProviderDefaultApiBase(meta),
      name: null,
      api_type: resolveDefaultApiType(meta?.id),
      models: [],
    }

    providers[providerId] = { ...cleared }
    // 删的正是在编辑的这个：表单一起清空，别把旧密钥留在输入框里
    if (deps.selectedProvider.value === providerId) {
      providerConfig.value = {
        apiKey: '',
        apiKeys: [''],
        baseUrl: cleared.api_base || '',
        enabled: true,
        name: '',
        apiType: cleared.api_type as ProviderApiType,
      }
      modelName.value = ''
      testResult.value = null
    }

    try {
      const response = await settingsAPI.update({ providers: { [providerId]: cleared } })
      const saved = response.providers?.[providerId]
      if (saved) {
        providers[providerId] = { ...saved }
        // 只回写这一个供应商：用整份响应覆盖会把其他供应商还没保存的草稿冲掉。
        // 整份替换 persistedSettings 而不是改它的字段，是为了触发订阅者（对话窗口的模型下拉）刷新
        const persisted = settingsStore.persistedSettings
        if (persisted) {
          settingsStore.persistedSettings = {
            ...persisted,
            providers: {
              ...persisted.providers,
              [providerId]: JSON.parse(JSON.stringify(saved)),
            },
          }
        }
      }
      return true
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || t('common.saveFailed'))
      return false
    }
  }

  return {
    providerConfig,
    modelName,
    testing,
    testResult,
    isHydrating,
    isApplyingExternalConfig,
    appliedSource,
    isApiKeyOptional,
    isCustomProvider,
    currentDefaultBaseUrl,
    selectedProviderSelectable,
    selectedProviderStatusText,
    selectedProviderThinkingNote,
    currentDraftConfig,
    savedSnapshot,
    draftSnapshot,
    appliedSourceText,
    draftStateHint,
    hasDraftChanges,
    canTestConnection,
    getPrimaryApiKey,
    addApiKeyField,
    removeApiKeyField,
    hydrateDraft,
    initializeProvider,
    syncProviderDraftToStore,
    syncModelDraftToStore,
    saveProviderConnection,
    testConnection,
    applyExternalConfig,
    createProvider,
    deleteProvider,
  }
}
