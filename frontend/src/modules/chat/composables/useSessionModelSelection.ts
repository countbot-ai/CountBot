/**
 * 对话输入框的模型切换。
 *
 * 选中模型后写入并持久化「全局默认模型」，所有没有自定义模型的地方都用它，
 * 下次进入对话默认也是它。
 * 会话级自定义配置（会话设置面板）与团队级自定义模型优先级更高：会话本来
 * 就有自定义时才同步更新该会话，避免留下与全局默认冲突的旧值，也不会凭空
 * 给会话/团队加上自定义模型。
 */

import { computed, ref } from 'vue'
import { chatAPI, settingsAPI } from '@/api'
import type { ProviderMetadata, SessionModelConfig } from '@/api'
import { useSettingsStore } from '@/store/settings'
import { buildSelectableModelGroups, type ProviderOption } from '@/composables/useProviderModelCatalog'

export function useSessionModelSelection() {
  const settingsStore = useSettingsStore()
  const providerOptions = ref<ProviderOption[]>([])
  const providerMetadata = ref<ProviderMetadata[]>([])
  const currentProviderId = ref('')
  const currentModelId = ref('')
  const isSessionOverride = ref(false)
  const switching = ref(false)
  const reasoningLevels = ref<string[]>([])
  const currentReasoningLevel = ref<string | null>(null)
  /** 内置建议按模型缓存，避免每次切换都打接口 */
  const builtinLevelsCache = new Map<string, string[]>()

  const groups = computed(() => buildSelectableModelGroups(providerOptions.value))

  /** 当前生效的模型条目（含它自己的思考档位设置）。 */
  const modelEntry = computed(() => {
    const option = providerOptions.value.find(item => item.id === currentProviderId.value)
    return option?.models.find(model => model.id === currentModelId.value) || null
  })

  function normalizeLevel(value?: string | null): string {
    return String(value || '').trim().toLowerCase()
  }

  /**
   * 当前模型的思考档位：模型条目的自定义档位优先，为空才用内置建议。
   * 两处都取不到时不展示档位下拉。
   */
  async function refreshReasoningLevels(): Promise<void> {
    const custom = modelEntry.value?.reasoning_levels || []
    if (custom.length > 0) {
      reasoningLevels.value = [...custom]
      return
    }

    const modelId = currentModelId.value
    if (!modelId) {
      reasoningLevels.value = []
      return
    }

    const cached = builtinLevelsCache.get(modelId)
    if (cached) {
      reasoningLevels.value = [...cached]
      return
    }

    try {
      const response = await settingsAPI.getReasoningLevels(modelId)
      builtinLevelsCache.set(modelId, response.levels || [])
      // 请求返回时模型可能已切换，丢弃过期结果
      if (modelId === currentModelId.value) {
        reasoningLevels.value = [...(response.levels || [])]
      }
    } catch {
      if (modelId === currentModelId.value) {
        reasoningLevels.value = []
      }
    }
  }

  /** 优先级：会话覆盖 > 模型条目默认 > 档位列表首项。 */
  function resolveReasoningLevel(candidate?: string | null): string | null {
    const levels = reasoningLevels.value
    if (levels.length === 0) {
      return null
    }
    const normalized = normalizeLevel(candidate)
    if (normalized && levels.includes(normalized)) {
      return normalized
    }
    return levels[0]
  }

  async function loadGlobalDefaults() {
    const [settings, providers] = await Promise.all([
      settingsAPI.get(),
      settingsAPI.getProviders().catch(() => [] as ProviderMetadata[]),
    ])

    providerMetadata.value = providers
    providerOptions.value = buildProviderOptionsFromSettings(settings.providers)
    currentProviderId.value = settings.model.provider
    currentModelId.value = settings.model.model
    ensureModelPresent(currentProviderId.value, currentModelId.value)
    await refreshReasoningLevels()
    currentReasoningLevel.value = resolveReasoningLevel(modelEntry.value?.reasoning_level)
    return settings
  }

  /**
   * 保证「当前生效的模型」一定出现在下拉里。
   *
   * 只在 Model Parameters 里填了模型名、却没把它加进供应商模型清单时，
   * 清单接口不会返回它，下拉就会整组消失——用户看到的是「刚配置的模型不见了」。
   * 这里把它补进分组，同时设置页保存时还会给出一条提示。
   */
  function ensureModelPresent(providerId: string, modelId: string): void {
    if (!providerId || !modelId) {
      return
    }
    const option = providerOptions.value.find(item => item.id === providerId)
    if (!option || option.models.some(model => model.id === modelId)) {
      return
    }
    option.models = [
      {
        id: modelId,
        display_name: null,
        enabled: true,
        context_window: null,
        supports_image: null,
        source: 'manual',
      },
      ...option.models,
    ]
  }

  function buildProviderOptionsFromSettings(
    providers: Record<string, any> | undefined,
  ): ProviderOption[] {
    if (!providers) {
      return []
    }
    return Object.entries(providers)
      .filter(([, config]) => config?.enabled !== false)
      .map(([providerId, config]) => ({
        id: providerId,
        name: config?.name || providerId,
        apiType: config?.api_type || 'openai-chat-completions',
        enabled: true,
        models: (config?.models || []).filter((model: any) => model?.id),
      }))
  }

  /** 读取会话当前生效的模型（含会话级覆盖）。 */
  async function loadSessionSelection(sessionId: string) {
    if (!sessionId) {
      return
    }

    try {
      const response = await chatAPI.getSessionConfig(sessionId)
      const effective = response.model_config
      isSessionOverride.value = response.use_custom_config
      currentProviderId.value = effective.provider || currentProviderId.value
      currentModelId.value = effective.model || currentModelId.value
      ensureModelPresent(currentProviderId.value, currentModelId.value)

      await refreshReasoningLevels()
      // 会话覆盖只在它确实不同于全局默认时才算「本会话的选择」，
      // 否则优先用模型条目自己的默认档位。
      const sessionLevel = normalizeLevel(effective.reasoning_level)
      const globalLevel = normalizeLevel(response.global_defaults?.model?.reasoning_level)
      const hasSessionLevel = !!sessionLevel && sessionLevel !== globalLevel
      currentReasoningLevel.value = resolveReasoningLevel(
        hasSessionLevel ? sessionLevel : modelEntry.value?.reasoning_level,
      )
    } catch {
      // 会话配置读取失败时保持全局默认显示，不影响输入
      isSessionOverride.value = false
    }
  }

  /** 切换模型：写入全局默认；会话/团队自定义优先，仅在会话已有自定义时同步。 */
  async function selectModel(sessionId: string, providerId: string, modelId: string) {
    if (!providerId || !modelId) {
      return false
    }

    const previousProvider = currentProviderId.value
    const previousModel = currentModelId.value
    currentProviderId.value = providerId
    currentModelId.value = modelId
    switching.value = true

    try {
      await settingsStore.setGlobalDefaultModel(providerId, modelId)
      // 会话本来就有自定义模型时，同步它，避免会话继续用旧模型与全局默认冲突；
      // 没有自定义的会话不加覆盖，直接跟随新的全局默认。
      if (sessionId && isSessionOverride.value) {
        await chatAPI.updateSessionConfig(sessionId, {
          model_config: { provider: providerId, model: modelId },
        })
      }
      // 换了模型就把上一个模型的档位清掉，按新模型重新取默认值
      await refreshReasoningLevels()
      currentReasoningLevel.value = resolveReasoningLevel(modelEntry.value?.reasoning_level)
      return true
    } catch (error) {
      currentProviderId.value = previousProvider
      currentModelId.value = previousModel
      throw error
    } finally {
      switching.value = false
    }
  }

  /**
   * 会话级覆盖思考强度：写进会话自定义模型配置（后端会打上 session_panel 来源标记），
   * 不改模型条目的默认档位。
   */
  async function selectReasoningLevel(sessionId: string, level: string): Promise<boolean> {
    const next = normalizeLevel(level)
    if (!next || !reasoningLevels.value.includes(next)) {
      return false
    }
    const previous = currentReasoningLevel.value
    if (previous === next) {
      return true
    }

    currentReasoningLevel.value = next
    if (!sessionId) {
      return true
    }

    try {
      const modelConfig: Partial<SessionModelConfig> = { reasoning_level: next }
      // 会话已有自定义模型时一并带上 provider/model：该接口是整体覆盖写入，
      // 漏掉就会把会话已绑定的模型清掉。
      if (isSessionOverride.value && currentProviderId.value && currentModelId.value) {
        modelConfig.provider = currentProviderId.value
        modelConfig.model = currentModelId.value
      }
      await chatAPI.updateSessionConfig(sessionId, { model_config: modelConfig })
      isSessionOverride.value = true
      return true
    } catch (error) {
      currentReasoningLevel.value = previous
      throw error
    }
  }

  /** 供应商清单在设置页被改动后，刷新下拉数据。 */
  async function refreshOptions() {
    const settings = await settingsAPI.get()
    providerOptions.value = buildProviderOptionsFromSettings(settings.providers)

    // 只在供应商本身消失时回落全局默认；模型被移出清单不该清掉用户当前的会话选择
    const providerStillExists = providerOptions.value.some(
      provider => provider.id === currentProviderId.value,
    )
    if (!providerStillExists) {
      currentProviderId.value = settings.model.provider
      currentModelId.value = settings.model.model
    }
    ensureModelPresent(currentProviderId.value, currentModelId.value)

    await refreshReasoningLevels()
    if (!currentReasoningLevel.value || !reasoningLevels.value.includes(currentReasoningLevel.value)) {
      currentReasoningLevel.value = resolveReasoningLevel(modelEntry.value?.reasoning_level)
    }
  }

  return {
    groups,
    providerOptions,
    providerMetadata,
    currentProviderId,
    currentModelId,
    isSessionOverride,
    switching,
    reasoningLevels,
    currentReasoningLevel,
    loadGlobalDefaults,
    loadSessionSelection,
    selectModel,
    selectReasoningLevel,
    refreshOptions,
  }
}

export type { SessionModelConfig }
