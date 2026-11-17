/**
 * 供应商配置的数据源抽象：同一套组件与 composable 在两种身份下复用。
 *
 * 管理员走全局设置（settingsStore + settingsAPI）；普通用户走 /api/me/providers
 * 的私有配置视图。两侧返回同构的 Settings 形状（providers + model），
 * 写入语义由各自端点保证：管理员整卡保存，用户端点只动自有配置并剥离共享字段。
 */

import { computed, ref, type Ref } from 'vue'
import {
  meProvidersAPI,
  settingsAPI,
  type ProviderConfig,
  type ProviderMetadata,
  type ProviderModelCatalogResponse,
  type ProviderModelEntry,
  type ReasoningLevelsResponse,
  type Settings,
  type TestConnectionRequest,
  type TestConnectionResponse,
  type ProviderConnectionTestResponse,
  type AddProviderModelsRequest,
  type UpdateProviderModelRequest,
} from '@/api'
import { useSettingsStore } from '@/store/settings'

export interface ProviderConfigSource {
  /** 当前草稿态设置（providers + model）；写入口在各 api 方法内 */
  settings: Ref<Settings | null>
  /** 最近一次保存成功的设置，用于脏检查与已保存视图 */
  persistedSettings: Ref<Settings | null>
  api: {
    updateProviders(payload: { providers: Record<string, ProviderConfig> }): Promise<Settings>
    listProviderMetadata(): Promise<ProviderMetadata[]>
    fetchModelCatalog(providerId: string): Promise<ProviderModelCatalogResponse>
    addProviderModels(providerId: string, payload: AddProviderModelsRequest): Promise<ProviderModelEntry[]>
    updateProviderModel(providerId: string, modelId: string, payload: UpdateProviderModelRequest): Promise<ProviderModelEntry[]>
    deleteProviderModel(providerId: string, modelId: string): Promise<ProviderModelEntry[]>
    reorderProviderModels(providerId: string, modelIds: string[]): Promise<ProviderModelEntry[]>
    testConnection(payload: TestConnectionRequest): Promise<TestConnectionResponse>
    testProviderConnection(providerId: string): Promise<ProviderConnectionTestResponse>
    getReasoningLevels(model: string): Promise<ReasoningLevelsResponse>
    /** 真实删除一个自有供应商；管理员侧无此端点，走清空落库 */
    deleteProvider?(providerId: string): Promise<Settings>
  }
  /** 用户视图的首次拉取；管理员视图由全局设置加载流程负责，可为空 */
  refresh?(): Promise<void>
}

/** 管理员数据源：直接代理 settingsStore，保持既有全局行为不变。 */
export function createAdminSource(): ProviderConfigSource {
  const store = useSettingsStore()
  return {
    settings: computed({
      get: () => store.settings,
      set: value => { store.settings = value },
    }) as unknown as Ref<Settings | null>,
    persistedSettings: computed({
      get: () => store.persistedSettings,
      set: value => { store.persistedSettings = value },
    }) as unknown as Ref<Settings | null>,
    api: {
      updateProviders: payload => settingsAPI.update(payload),
      listProviderMetadata: () => settingsAPI.getProviders(),
      fetchModelCatalog: providerId => settingsAPI.getProviderModelCatalog(providerId),
      addProviderModels: (providerId, payload) => settingsAPI.addProviderModels(providerId, payload),
      updateProviderModel: (providerId, modelId, payload) =>
        settingsAPI.updateProviderModel(providerId, modelId, payload),
      deleteProviderModel: (providerId, modelId) =>
        settingsAPI.deleteProviderModel(providerId, modelId),
      reorderProviderModels: (providerId, modelIds) =>
        settingsAPI.reorderProviderModels(providerId, modelIds),
      testConnection: payload => settingsAPI.testConnection(payload),
      testProviderConnection: providerId => settingsAPI.testProviderConnection(providerId),
      getReasoningLevels: model => settingsAPI.getReasoningLevels(model),
    },
  }
}

/** 普通用户数据源：本地持有 /api/me/providers 视图，写接口成功后同步两份快照。 */
export function createUserSource(): ProviderConfigSource {
  const settings = ref<Settings | null>(null)
  const persistedSettings = ref<Settings | null>(null)

  function applyView(view: Settings): Settings {
    // 用户视图里 model.provider 可能指向共享供应商（不可编辑），这里不修正，
    // 由界面按 scope 隐藏「当前选择」相关卡片，避免指向不存在的自有配置。
    settings.value = view
    persistedSettings.value = JSON.parse(JSON.stringify(view))
    return view
  }

  async function refresh(): Promise<void> {
    applyView(await meProvidersAPI.getView())
  }

  async function updateProviders(payload: { providers: Record<string, ProviderConfig> }): Promise<Settings> {
    return applyView(await meProvidersAPI.updateProviders(payload))
  }

  return {
    settings,
    persistedSettings,
    refresh,
    api: {
      updateProviders,
      listProviderMetadata: () => meProvidersAPI.getProviders(),
      fetchModelCatalog: providerId => meProvidersAPI.getProviderModelCatalog(providerId),
      addProviderModels: (providerId, payload) => meProvidersAPI.addProviderModels(providerId, payload),
      updateProviderModel: (providerId, modelId, payload) =>
        meProvidersAPI.updateProviderModel(providerId, modelId, payload),
      deleteProviderModel: (providerId, modelId) =>
        meProvidersAPI.deleteProviderModel(providerId, modelId),
      reorderProviderModels: (providerId, modelIds) =>
        meProvidersAPI.reorderProviderModels(providerId, modelIds),
      testConnection: payload => meProvidersAPI.testConnection(payload),
      testProviderConnection: providerId => meProvidersAPI.testProviderConnection(providerId),
      getReasoningLevels: model => meProvidersAPI.getReasoningLevels(model),
      deleteProvider: async providerId => applyView(await meProvidersAPI.deleteProvider(providerId)),
    },
  }
}
