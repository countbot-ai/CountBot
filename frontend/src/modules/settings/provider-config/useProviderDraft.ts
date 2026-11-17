/**
 * 供应商连接草稿（名称 / Base URL / 协议 / 密钥）与连接测试。
 *
 * 唯一所有者：`providerConfig` 与 `modelName`（当前选中的模型名）。
 * 草稿落地到 store 的唯一入口是 `syncProviderDraftToStore`，
 * 落库（写后端）的唯一入口是 `saveProviderConnection`——
 * 模型清单接口读的是已保存配置，所以拉取/测试前必须先保存。
 */

import { computed, ref, watch, type ComputedRef, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { ProviderApiType, ProviderConfig, ProviderMetadata } from '@/api'
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
  buildConnectionSignature,
  buildEditableApiKeys,
  normalizeApiKeys,
  resolveApiTypeBaseUrl,
  resolveDefaultApiType,
} from './constants'
import type { ProviderConfigSource } from './source'
import type {
  ConnectionTestResult,
  ProviderDraft,
} from './types'

export interface ProviderDraftState {
  providerConfig: Ref<ProviderDraft>
  modelName: Ref<string>
  testing: Ref<boolean>
  testResult: Ref<ConnectionTestResult | null>
  isHydrating: Ref<boolean>
  /** 当前供应商连接信息是否有未保存的改动 */
  isProviderDirty: ComputedRef<boolean>
  /** 正在保存当前供应商 */
  savingProvider: Ref<boolean>
  isApiKeyOptional: ComputedRef<boolean>
  isCustomProvider: ComputedRef<boolean>
  currentDefaultBaseUrl: ComputedRef<string | undefined>
  selectedProviderSelectable: ComputedRef<boolean>
  selectedProviderStatusText: ComputedRef<string>
  selectedProviderThinkingNote: ComputedRef<string>
  canTestConnection: ComputedRef<boolean>
  getPrimaryApiKey: () => string
  addApiKeyField: () => void
  removeApiKeyField: (index: number) => void
  hydrateDraft: (providerId: string, fromPersisted?: boolean) => void
  initializeProvider: () => void
  /** 默认写回当前选中的供应商；切换供应商时要显式传入「旧」供应商，避免把旧草稿写进新供应商 */
  syncProviderDraftToStore: (providerId?: string) => void
  syncModelDraftToStore: () => void
  /** 保存当前供应商的连接信息（不整卡落库，避免冲掉其他供应商的草稿） */
  saveProviderConnection: () => Promise<boolean>
  /** 丢弃当前供应商的草稿改动，回到最近一次保存的状态 */
  discardDraft: () => void
  testConnection: () => Promise<void>
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
  source: ProviderConfigSource
}

export function useProviderDraft(deps: ProviderDraftDeps): ProviderDraftState {
  const { t } = useI18n()
  const toast = useToast()
  const source = deps.source

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
  const savingProvider = ref(false)

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

  const canTestConnection = computed(
    () =>
      Boolean(deps.selectedProvider.value)
      && Boolean(modelName.value.trim())
      && (isApiKeyOptional.value || Boolean(getPrimaryApiKey())),
  )

  /**
   * 连接信息是否有未保存改动。
   * 只比较名称 / 地址 / 协议 / 启用态 / 密钥；模型清单是即时保存的，不参与脏检查。
   */
  const isProviderDirty = computed(() => {
    const meta = deps.selectedProviderMeta.value
    if (!meta) {
      return false
    }
    const draft = source.settings.value?.providers?.[meta.id]
    const saved = source.persistedSettings.value?.providers?.[meta.id]
    return buildConnectionSignature(meta, draft) !== buildConnectionSignature(meta, saved)
  })

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

  /**
   * 把某个供应商的配置读进表单。
   *
   * @param fromPersisted 为 true 时读最近一次保存成功的状态（用于「撤销」），
   *                      否则读当前草稿，保证切换回来后还能看到刚才的输入。
   */
  function hydrateDraft(providerId: string, fromPersisted = false): void {
    const settings = fromPersisted
      ? source.persistedSettings.value
      : source.settings.value
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
    const settings = source.settings.value
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
   * API 协议切换时同步根地址。
   *
   * DeepSeek 这类供应商的 OpenAI 兼容端点与 Anthropic 兼容端点不同，
   * 只覆盖「空 / 内置默认 / 上一协议专用」的地址，用户手填的保持不变。
   */
  watch(
    () => [deps.selectedProvider.value, providerConfig.value.apiType] as const,
    ([providerId, apiType], previous) => {
      const previousApiType = previous?.[1]
      if (!previousApiType || apiType === previousApiType) {
        return
      }

      const normalize = (value?: string) => String(value || '').trim().replace(/\/+$/, '')
      const nextBaseUrl = resolveApiTypeBaseUrl(providerId, apiType)
      const previousBaseUrl = resolveApiTypeBaseUrl(providerId, previousApiType)
      const currentBaseUrl = normalize(providerConfig.value.baseUrl)
      const defaultBaseUrl = normalize(currentDefaultBaseUrl.value)

      if (nextBaseUrl) {
        const isUntouched =
          !currentBaseUrl || currentBaseUrl === defaultBaseUrl || currentBaseUrl === previousBaseUrl
        if (isUntouched) {
          providerConfig.value.baseUrl = nextBaseUrl
        }
        return
      }

      // 换回默认协议时，把之前自动填的地址还原成默认地址
      if (previousBaseUrl && currentBaseUrl === previousBaseUrl) {
        providerConfig.value.baseUrl = currentDefaultBaseUrl.value || ''
      }
    },
  )

  /**
   * 草稿 -> settings store（只改内存，不落库）。
   *
   * `providerId` 默认取当前选中的供应商；切换供应商时必须传入旧 id——
   * watch 回调执行时选中项已经变成新的了，不传就会把旧供应商的草稿写进新供应商。
   */
  function syncProviderDraftToStore(providerId: string = deps.selectedProvider.value): void {
    const providers = source.settings.value?.providers
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
    const settings = source.settings.value
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

  /**
   * 只保存当前供应商的连接信息。
   *
   * 用「单供应商 updateProviders」而不是整份 settings 覆盖：
   * 一处保存不该冲掉其他供应商还没保存的草稿。
   */
  async function saveProviderConnection(): Promise<boolean> {
    const providerId = deps.selectedProvider.value
    const providers = source.settings.value?.providers
    if (!providerId || !providers?.[providerId]) {
      return false
    }

    if (savingProvider.value) {
      return false
    }

    savingProvider.value = true
    try {
      const response = await source.api.updateProviders({
        providers: { [providerId]: providers[providerId] },
      })

      const saved = response.providers?.[providerId]
      if (!saved) {
        return false
      }

      // 草稿侧只回写这一个供应商，保留其他供应商的未保存编辑
      providers[providerId] = JSON.parse(JSON.stringify(saved)) as ProviderConfig
      // 已保存快照整体替换对象，触发订阅者（对话窗口的模型下拉）刷新
      source.persistedSettings.value = {
        ...(source.persistedSettings.value || response),
        providers: {
          ...(source.persistedSettings.value?.providers || response.providers),
          [providerId]: JSON.parse(JSON.stringify(saved)),
        },
      }
      return true
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || t('common.saveFailed'))
      return false
    } finally {
      savingProvider.value = false
    }
  }

  /** 丢弃草稿改动：把最近一次保存成功的连接信息重新读回表单。 */
  function discardDraft(): void {
    const providerId = deps.selectedProvider.value
    if (!providerId) {
      return
    }
    hydrateDraft(providerId, true)
    // 表单里已是已保存值，再同步一次让 store 中的草稿与之一致
    syncProviderDraftToStore(providerId)
    testResult.value = null
  }

  async function testConnection(): Promise<void> {
    if (!deps.selectedProvider.value || !canTestConnection.value) {
      return
    }

    testing.value = true
    testResult.value = null

    try {
      const response = await source.api.testConnection({
        provider: deps.selectedProvider.value,
        api_key: getPrimaryApiKey(),
        api_base: providerConfig.value.baseUrl,
        api_type: providerConfig.value.apiType,
        model: modelName.value,
        ...buildSendableModelConfig(source.settings.value?.model),
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

  /* ---------------- 新建供应商 ---------------- */

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
    const providers = source.settings.value?.providers
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
   * 管理员侧后端启动时为目录里每个供应商预建了空配置、也没有删除接口，
   * 「删除」= 清空它的密钥与模型清单并立即落库：清空后不再出现在左栏，
   * 也从对话窗口的模型下拉里消失。
   * 用户侧有真实删除端点（source.api.deleteProvider），直接删除自有配置。
   * 立即落库是因为延迟到「保存」才生效的话，用户不点保存、刷新后它又冒出来了。
   *
   * @returns 是否删除成功（供应商不存在或落库失败返回 false）
   */
  async function deleteProvider(providerId: string): Promise<boolean> {
    const providers = source.settings.value?.providers
    if (!providerId || !providers?.[providerId]) {
      return false
    }

    if (source.api.deleteProvider) {
      try {
        await source.api.deleteProvider(providerId)
      } catch (error: any) {
        toast.error(error?.response?.data?.detail || t('common.saveFailed'))
        return false
      }
      if (deps.selectedProvider.value === providerId) {
        providerConfig.value = {
          apiKey: '',
          apiKeys: [''],
          baseUrl: '',
          enabled: true,
          name: '',
          apiType: DEFAULT_API_TYPE,
        }
        modelName.value = ''
        testResult.value = null
      }
      return true
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
      const response = await source.api.updateProviders({ providers: { [providerId]: cleared } })
      const saved = response.providers?.[providerId]
      if (saved) {
        providers[providerId] = { ...saved }
        // 只回写这一个供应商：用整份响应覆盖会把其他供应商还没保存的草稿冲掉。
        // 整份替换 persistedSettings 而不是改它的字段，是为了触发订阅者（对话窗口的模型下拉）刷新
        const persisted = source.persistedSettings.value
        if (persisted) {
          source.persistedSettings.value = {
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
    isProviderDirty,
    savingProvider,
    isApiKeyOptional,
    isCustomProvider,
    currentDefaultBaseUrl,
    selectedProviderSelectable,
    selectedProviderStatusText,
    selectedProviderThinkingNote,
    canTestConnection,
    getPrimaryApiKey,
    addApiKeyField,
    removeApiKeyField,
    hydrateDraft,
    initializeProvider,
    syncProviderDraftToStore,
    syncModelDraftToStore,
    saveProviderConnection,
    discardDraft,
    testConnection,
    createProvider,
    deleteProvider,
  }
}
