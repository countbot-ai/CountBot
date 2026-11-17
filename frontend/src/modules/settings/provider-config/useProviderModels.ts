/**
 * 模型清单：增删改、排序、启用开关与单模型测试。
 *
 * 唯一所有者：模型清单的写入入口 `replaceModelsInStore`（同时刷新
 * 拉取模型清单前必须先落库连接信息，见 useProviderDraft.saveProviderConnection。
 */

import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { ProviderApiType, ProviderModelCatalogEntry, ProviderModelEntry } from '@/api'
import { buildSendableModelConfig, formatContextLength } from '@/utils/modelConfig'
import { useToast } from '@/composables/useToast'
import { useConfirm } from '@/composables/useConfirm'
import { useProviderModelCatalog } from '@/composables/useProviderModelCatalog'
import type { ProviderConfigSource } from './source'
import type { ModelUpdatePayload, ProviderTestResult } from './types'

export interface ProviderModelsState {
  models: ComputedRef<ProviderModelEntry[]>
  existingModelIds: ComputedRef<string[]>
  editingModel: Ref<ProviderModelEntry | null>
  testingModelId: Ref<string>
  providerTesting: Ref<boolean>
  providerTestResult: Ref<ProviderTestResult | null>
  catalogLoading: Ref<boolean>
  catalogError: Ref<string | null>
  fetchedModels: Ref<ProviderModelCatalogEntry[]>
  showFetchDialog: Ref<boolean>
  sourceLabel: (source: ProviderModelEntry['source']) => string
  contextLabel: (value: number) => string
  commitNewModel: (
    modelId: string,
    contextWindow?: number | null,
    nativeCapabilities?: ModelUpdatePayload['native_capabilities'],
  ) => Promise<boolean>
  commitFetchedModels: (modelIds: string[]) => Promise<void>
  openFetchDialog: () => Promise<void>
  deleteModel: (modelId: string) => Promise<void>
  toggleModel: (modelId: string, enabled: boolean) => Promise<void>
  moveModel: (index: number, offset: number) => Promise<void>
  reorderModel: (from: number, to: number) => Promise<void>
  openModelEditor: (model: ProviderModelEntry) => void
  closeModelEditor: () => void
  saveModelEditor: (payload: ModelUpdatePayload) => Promise<void>
  testModel: (modelId: string) => Promise<void>
  testProvider: () => Promise<void>
  clearProviderTestResult: () => void
}

export interface ProviderModelsDeps {
  selectedProvider: Ref<string>
  /** 落库连接信息（模型清单接口读的是已保存配置） */
  saveProviderConnection: () => Promise<boolean>
  syncProviderDraftToStore: () => void
  getPrimaryApiKey: () => string
  apiBase: ComputedRef<string>
  apiType: ComputedRef<ProviderApiType>
  source: ProviderConfigSource
}

export function useProviderModels(deps: ProviderModelsDeps): ProviderModelsState {
  const { t } = useI18n()
  const toast = useToast()
  const { confirm } = useConfirm()
  const source = deps.source
  const catalog = useProviderModelCatalog(source)

  const editingModel = ref<ProviderModelEntry | null>(null)
  const testingModelId = ref('')
  const providerTesting = ref(false)
  const providerTestResult = ref<ProviderTestResult | null>(null)
  const showFetchDialog = ref(false)

  const models = computed<ProviderModelEntry[]>(
    () => source.settings.value?.providers?.[deps.selectedProvider.value]?.models || [],
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
    const providers = source.settings.value?.providers
    if (!providers?.[providerId]) {
      return
    }
    providers[providerId].models = next

    const persisted = source.persistedSettings.value?.providers?.[providerId]
    if (persisted) {
      persisted.models = next
    }
  }

  /**
   * 新增模型前先把供应商连接信息落库。
   * 模型清单接口读的是已保存配置；后端虽然给每个供应商预建了空配置，
   * 但草稿里的 base_url / 密钥还没写进去，直接加模型会写到旧配置上。
   */
  async function ensureProviderSaved(): Promise<boolean> {
    if (!deps.selectedProvider.value) {
      return false
    }
    deps.syncProviderDraftToStore()
    return deps.saveProviderConnection()
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
    nativeCapabilities?: ModelUpdatePayload['native_capabilities'],
  ): Promise<boolean> {
    const providerId = deps.selectedProvider.value
    const trimmed = modelId.trim()
    if (!providerId || !trimmed) {
      return false
    }

    const saved = await ensureProviderSaved()
    if (!saved) {
      return false
    }

    // 窗口随模型一起提交：压缩阈值按窗口派生，缺省会落到兜底值
    const payload: {
      id: string
      context_window?: number
      native_capabilities?: ModelUpdatePayload['native_capabilities']
    } = { id: trimmed }
    if (contextWindow && contextWindow > 0) {
      payload.context_window = contextWindow
    }
    if (nativeCapabilities) {
      payload.native_capabilities = nativeCapabilities
    }

    return runModelMutation(
      () =>
        source.api.addProviderModels(providerId, {
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
    const saved = await deps.saveProviderConnection()
    if (!saved) {
      return
    }

    await catalog.fetchCatalog(providerId)
    showFetchDialog.value = true
  }

  async function commitFetchedModels(modelIds: string[]): Promise<void> {
    const providerId = deps.selectedProvider.value
    if (!providerId || modelIds.length === 0) {
      return
    }

    await runModelMutation(async () => {
      const saved = await source.api.addProviderModels(providerId, {
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
      () => source.api.deleteProviderModel(deps.selectedProvider.value, modelId),
      'settings.providers.models.deleteFailed',
    )
  }

  async function toggleModel(modelId: string, enabled: boolean): Promise<void> {
    await runModelMutation(
      () => source.api.updateProviderModel(deps.selectedProvider.value, modelId, { enabled }),
      'settings.providers.models.saveFailed',
    )
  }

  async function moveModel(index: number, offset: number): Promise<void> {
    await reorderModel(index, index + offset)
  }

  /** 把第 from 个模型移动到 to 位置（拖拽排序用）。 */
  async function reorderModel(from: number, to: number): Promise<void> {
    const providerId = deps.selectedProvider.value
    const list = [...models.value]
    if (
      !providerId
      || from === to
      || from < 0
      || to < 0
      || from >= list.length
      || to >= list.length
    ) {
      return
    }

    const [moved] = list.splice(from, 1)
    list.splice(to, 0, moved)

    await runModelMutation(
      () => source.api.reorderProviderModels(providerId, list.map(model => model.id)),
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

    // 一次保存同时落库连接信息与模型配置：模型接口只读已保存的供应商配置，
    // 先冲掉连接草稿，避免写进旧配置，也避免返回页面后还要再点一次保存。
    const ready = await ensureProviderSaved()
    if (!ready) {
      return
    }

    const saved = await runModelMutation(async () => {
      const next = await source.api.updateProviderModel(
        deps.selectedProvider.value,
        model.id,
        payload,
      )
      closeModelEditor()
      return next
    }, 'settings.providers.models.saveFailed')
    if (saved) {
      toast.success(t('settings.saveSuccess'))
    }
  }

  /* ---------------- 测试 ---------------- */

  async function testModel(modelId: string): Promise<void> {
    const providerId = deps.selectedProvider.value
    if (!providerId) {
      return
    }

    testingModelId.value = modelId
    try {
      const response = await source.api.testConnection({
        provider: providerId,
        api_key: deps.getPrimaryApiKey(),
        api_base: deps.apiBase.value,
        api_type: deps.apiType.value,
        model: modelId,
        ...buildSendableModelConfig(source.settings.value?.model),
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
    if (!providerId || providerTesting.value) {
      return
    }

    providerTesting.value = true
    providerTestResult.value = null
    deps.syncProviderDraftToStore()
    const saved = await deps.saveProviderConnection()

    try {
      if (!saved) {
        providerTestResult.value = {
          success: false,
          latencyMs: null,
          modelCount: null,
          error: t('common.saveFailed'),
        }
        return
      }

      const response = await source.api.testProviderConnection(providerId)
      providerTestResult.value = response.success
        ? {
            success: true,
            latencyMs: response.latency_ms ?? null,
            modelCount: response.model_count ?? null,
            error: '',
          }
        : {
            success: false,
            latencyMs: null,
            modelCount: null,
            error: response.error || t('settings.providers.testFailed'),
          }
    } catch (error: any) {
      providerTestResult.value = {
        success: false,
        latencyMs: null,
        modelCount: null,
        error:
          error?.response?.data?.detail
          || error.message
          || t('settings.providers.testFailed'),
      }
    } finally {
      providerTesting.value = false
    }
  }

  function clearProviderTestResult(): void {
    providerTestResult.value = null
  }

  return {
    models,
    existingModelIds,
    editingModel,
    testingModelId,
    providerTesting,
    providerTestResult,
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
    reorderModel,
    openModelEditor,
    closeModelEditor,
    saveModelEditor,
    testModel,
    testProvider,
    clearProviderTestResult,
  }
}
