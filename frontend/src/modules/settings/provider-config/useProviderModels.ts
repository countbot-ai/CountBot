/**
 * 模型清单：增删改、排序、启用开关与单模型测试。
 *
 * 唯一所有者：模型清单的写入入口 `replaceModelsInStore`（同时刷新
 * 拉取模型清单前必须先落库连接信息，见 useProviderDraft.saveProviderConnection。
 */

import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { settingsAPI } from '@/api'
import type { ProviderApiType, ProviderModelCatalogEntry, ProviderModelEntry } from '@/api'
import { useSettingsStore } from '@/store/settings'
import { buildSendableModelConfig, formatContextLength } from '@/utils/modelConfig'
import { useToast } from '@/composables/useToast'
import { useConfirm } from '@/composables/useConfirm'
import { useProviderModelCatalog } from '@/composables/useProviderModelCatalog'
import type { ModelUpdatePayload } from './types'

export interface ProviderModelsState {
  models: ComputedRef<ProviderModelEntry[]>
  existingModelIds: ComputedRef<string[]>
  editingModel: Ref<ProviderModelEntry | null>
  testingModelId: Ref<string>
  providerTesting: Ref<boolean>
  catalogLoading: Ref<boolean>
  catalogError: Ref<string | null>
  fetchedModels: Ref<ProviderModelCatalogEntry[]>
  showFetchDialog: Ref<boolean>
  sourceLabel: (source: ProviderModelEntry['source']) => string
  contextLabel: (value: number) => string
  commitNewModel: (modelId: string, contextWindow?: number | null) => Promise<boolean>
  commitFetchedModels: (modelIds: string[]) => Promise<void>
  openFetchDialog: () => Promise<void>
  deleteModel: (modelId: string) => Promise<void>
  toggleModel: (modelId: string, enabled: boolean) => Promise<void>
  moveModel: (index: number, offset: number) => Promise<void>
  openModelEditor: (model: ProviderModelEntry) => void
  closeModelEditor: () => void
  saveModelEditor: (payload: ModelUpdatePayload) => Promise<void>
  testModel: (modelId: string) => Promise<void>
  testProvider: () => Promise<void>
}

export interface ProviderModelsDeps {
  selectedProvider: Ref<string>
  /** 落库连接信息（模型清单接口读的是已保存配置） */
  saveProviderConnection: () => Promise<void>
  syncProviderDraftToStore: () => void
  getPrimaryApiKey: () => string
  apiBase: ComputedRef<string>
  apiType: ComputedRef<ProviderApiType>
}

export function useProviderModels(deps: ProviderModelsDeps): ProviderModelsState {
  const { t } = useI18n()
  const toast = useToast()
  const { confirm } = useConfirm()
  const settingsStore = useSettingsStore()
  const catalog = useProviderModelCatalog()

  const editingModel = ref<ProviderModelEntry | null>(null)
  const testingModelId = ref('')
  const providerTesting = ref(false)
  const showFetchDialog = ref(false)

  const models = computed<ProviderModelEntry[]>(
    () => settingsStore.settings?.providers?.[deps.selectedProvider.value]?.models || [],
  )
  const existingModelIds = computed(() => models.value.map(model => model.id))

  /* ---------------- 展示辅助 ---------------- */

  function sourceLabel(source: ProviderModelEntry['source']): string {
    if (source === 'fetched') {
      return t('settings.providers.models.sourceFetched')
    }
    if (source === 'builtin') {
      return t('settings.providers.models.sourceBuiltin')
    }
    return t('settings.providers.models.sourceManual')
  }

  /** 同时刷新草稿与已保存配置，保证两张状态卡一致。 */
  function replaceModelsInStore(providerId: string, next: ProviderModelEntry[]): void {
    const providers = settingsStore.settings?.providers
    if (!providers?.[providerId]) {
      return
    }
    providers[providerId].models = next

    const persisted = settingsStore.persistedSettings?.providers?.[providerId]
    if (persisted) {
      persisted.models = next
    }
  }

  /**
   * 新增模型前先把供应商连接信息落库。
   * 模型清单接口读的是已保存配置；后端虽然给每个供应商预建了空配置，
   * 但草稿里的 base_url / 密钥还没写进去，直接加模型会写到旧配置上。
   */
  async function ensureProviderSaved(): Promise<void> {
    if (!deps.selectedProvider.value) {
      return
    }
    deps.syncProviderDraftToStore()
    await deps.saveProviderConnection()
  }

  /** 统一处理「调接口 -> 写回 store -> 失败提示」，返回是否成功。 */
  async function runModelMutation(
    mutation: () => Promise<ProviderModelEntry[]>,
    fallbackError: string,
  ): Promise<boolean> {
    const providerId = deps.selectedProvider.value
    if (!providerId) {
      return false
    }
    try {
      replaceModelsInStore(providerId, await mutation())
      return true
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || t(fallbackError))
      return false
    }
  }

  /* ---------------- 手工新增 ---------------- */

  async function commitNewModel(
    modelId: string,
    contextWindow?: number | null,
  ): Promise<boolean> {
    const providerId = deps.selectedProvider.value
    const trimmed = modelId.trim()
    if (!providerId || !trimmed) {
      return false
    }

    await ensureProviderSaved()

    // 窗口随模型一起提交：压缩阈值按窗口派生，缺省会落到兜底值
    const payload: { id: string; context_window?: number } = { id: trimmed }
    if (contextWindow && contextWindow > 0) {
      payload.context_window = contextWindow
    }

    return runModelMutation(
      () =>
        settingsAPI.addProviderModels(providerId, {
          models: [payload],
          source: 'manual',
        }),
      'settings.providers.models.saveFailed',
    )
  }

  /* ---------------- 获取模型 ---------------- */

  async function openFetchDialog(): Promise<void> {
    const providerId = deps.selectedProvider.value
    if (!providerId) {
      return
    }

    // 先保存当前草稿，否则后端用的是旧的 base_url / key
    deps.syncProviderDraftToStore()
    await deps.saveProviderConnection()

    await catalog.fetchCatalog(providerId)
    showFetchDialog.value = true
  }

  async function commitFetchedModels(modelIds: string[]): Promise<void> {
    const providerId = deps.selectedProvider.value
    if (!providerId || modelIds.length === 0) {
      return
    }

    await runModelMutation(async () => {
      const saved = await settingsAPI.addProviderModels(providerId, {
        models: modelIds.map(id => ({ id })),
        source: 'fetched',
      })
      showFetchDialog.value = false
      catalog.reset()
      return saved
    }, 'settings.providers.models.saveFailed')
  }

  /* ---------------- 单条操作 ---------------- */

  async function deleteModel(modelId: string): Promise<void> {
    if (!deps.selectedProvider.value) {
      return
    }
    const confirmed = await confirm({
      title: t('common.confirmDelete'),
      message: t('settings.providers.models.deleteConfirm', { model: modelId }),
      type: 'danger',
      confirmText: t('common.delete'),
      confirmVariant: 'danger'
    })
    if (!confirmed) {
      return
    }

    await runModelMutation(
      () => settingsAPI.deleteProviderModel(deps.selectedProvider.value, modelId),
      'settings.providers.models.deleteFailed',
    )
  }

  async function toggleModel(modelId: string, enabled: boolean): Promise<void> {
    await runModelMutation(
      () => settingsAPI.updateProviderModel(deps.selectedProvider.value, modelId, { enabled }),
      'settings.providers.models.saveFailed',
    )
  }

  async function moveModel(index: number, offset: number): Promise<void> {
    const providerId = deps.selectedProvider.value
    const target = index + offset
    const list = [...models.value]
    if (!providerId || target < 0 || target >= list.length) {
      return
    }

    const [moved] = list.splice(index, 1)
    list.splice(target, 0, moved)

    await runModelMutation(
      () => settingsAPI.reorderProviderModels(providerId, list.map(model => model.id)),
      'settings.providers.models.saveFailed',
    )
  }

  /* ---------------- 模型设置弹窗 ---------------- */

  function openModelEditor(model: ProviderModelEntry): void {
    editingModel.value = model
  }

  function closeModelEditor(): void {
    editingModel.value = null
  }

  async function saveModelEditor(payload: ModelUpdatePayload): Promise<void> {
    const model = editingModel.value
    if (!model || !deps.selectedProvider.value) {
      return
    }

    await runModelMutation(async () => {
      const saved = await settingsAPI.updateProviderModel(
        deps.selectedProvider.value,
        model.id,
        payload,
      )
      closeModelEditor()
      return saved
    }, 'settings.providers.models.saveFailed')
  }

  /* ---------------- 测试 ---------------- */

  async function testModel(modelId: string): Promise<void> {
    const providerId = deps.selectedProvider.value
    if (!providerId) {
      return
    }

    testingModelId.value = modelId
    try {
      const response = await settingsAPI.testConnection({
        provider: providerId,
        api_key: deps.getPrimaryApiKey(),
        api_base: deps.apiBase.value,
        api_type: deps.apiType.value,
        model: modelId,
        ...buildSendableModelConfig(settingsStore.settings?.model),
      })

      if (response.success) {
        toast.success(t('settings.providers.models.testModelSuccess', { model: modelId }))
      } else {
        toast.error(
          t('settings.providers.models.testModelFailed', {
            model: modelId,
            error: response.error || response.message || t('settings.providers.testFailed'),
          }),
        )
      }
    } catch (error: any) {
      toast.error(
        t('settings.providers.models.testModelFailed', {
          model: modelId,
          error: error?.response?.data?.detail || error.message || t('settings.providers.testFailed'),
        }),
      )
    } finally {
      testingModelId.value = ''
    }
  }

  async function testProvider(): Promise<void> {
    const providerId = deps.selectedProvider.value
    if (!providerId) {
      return
    }

    providerTesting.value = true
    deps.syncProviderDraftToStore()
    await deps.saveProviderConnection()

    try {
      const response = await settingsAPI.testProviderConnection(providerId)
      if (response.success) {
        toast.success(
          t('settings.providers.models.testProviderSuccess', {
            count: response.model_count ?? 0,
            latency: response.latency_ms ?? 0,
          }),
        )
      } else {
        toast.error(
          t('settings.providers.models.testProviderFailed', {
            error: response.error || t('settings.providers.testFailed'),
          }),
        )
      }
    } catch (error: any) {
      toast.error(
        t('settings.providers.models.testProviderFailed', {
          error: error?.response?.data?.detail || error.message || t('settings.providers.testFailed'),
        }),
      )
    } finally {
      providerTesting.value = false
    }
  }

  return {
    models,
    existingModelIds,
    editingModel,
    testingModelId,
    providerTesting,
    catalogLoading: catalog.catalogLoading,
    catalogError: catalog.catalogError,
    fetchedModels: catalog.fetchedModels,
    showFetchDialog,
    sourceLabel,
    contextLabel: formatContextLength,
    commitNewModel,
    commitFetchedModels,
    openFetchDialog,
    deleteModel,
    toggleModel,
    moveModel,
    openModelEditor,
    closeModelEditor,
    saveModelEditor,
    testModel,
    testProvider,
  }
}
