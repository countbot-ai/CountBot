/** 对话输入框的模型切换：默认写入全局模型，会话/团队自定义优先 */

import { computed, ref, watch } from 'vue'
import { chatAPI, meAPI, settingsAPI } from '@/api'
import type { ChatMode, ProviderMetadata, SessionModelConfig } from '@/api'
import { useSettingsStore } from '@/store/settings'
import { useUserStore } from '@/store/user'
import { useChatModePolicy } from '@/composables/useChatModePolicy'
import { normalizeNativeCapabilities } from '@/types/nativeCaps'
import {
  buildProviderOptionsFromMeModels,
  buildSelectableModelGroups,
  type ProviderOption,
} from '@/composables/useProviderModelCatalog'

export function useSessionModelSelection() {
  const settingsStore = useSettingsStore()
  const userStore = useUserStore()
  const {
    allowedChatModes,
    canSwitchChatMode,
    defaultChatMode,
    clampChatMode,
  } = useChatModePolicy()
  const providerOptions = ref<ProviderOption[]>([])
  const providerMetadata = ref<ProviderMetadata[]>([])
  const currentProviderId = ref('')
  const currentModelId = ref('')
  const isSessionOverride = ref(false)
  const switching = ref(false)
  const reasoningLevels = ref<string[]>([])
  const currentReasoningLevel = ref<string | null>(null)
  /** 会话对话模式：agent 完整能力；chat 纯对话，不注入工具与技能 */
  const chatMode = ref<ChatMode>('agent')
  /** 普通用户模型来源：`provider:model` -> shared/own，切换时回传后端校验 */
  const meModelSources = ref<Record<string, 'shared' | 'own'>>({})
  /** 内置建议按模型缓存，避免每次切换都打接口 */
  const builtinLevelsCache = new Map<string, string[]>()

  // 身份异步加载：策略到达后把当前模式收敛到允许范围
  watch(allowedChatModes, () => {
    chatMode.value = clampChatMode(chatMode.value)
  })

  const groups = computed(() => buildSelectableModelGroups(providerOptions.value))

  /** 当前生效的模型条目（含它自己的思考档位设置）。 */
  const modelEntry = computed(() => {
    const option = providerOptions.value.find(item => item.id === currentProviderId.value)
    const direct = option?.models.find(model => model.id === currentModelId.value)
    if (direct) {
      return direct
    }
    // 共享模型合并为单一「内置模型」分组后，真实供应商 ID 保存在条目上，按条目回查
    for (const item of providerOptions.value) {
      const found = item.models.find(
        model => model.id === currentModelId.value
          && (model.provider_id || item.id) === currentProviderId.value,
      )
      if (found) {
        return found
      }
    }
    return null
  })

  /** 当前模型启用的供应商原生能力（未配置时全部关闭）。 */
  const currentCapabilities = computed(() =>
    normalizeNativeCapabilities(modelEntry.value?.native_capabilities),
  )

  function normalizeLevel(value?: string | null): string {
    return String(value || '').trim().toLowerCase()
  }

  /** 「关闭」档位：与后端 REASONING_LEVEL_OFF 对齐，不在模型档位列表里也允许选择 */
  const OFF_LEVEL = 'none'
  const OFF_LEVEL_ALIASES = new Set(['none', 'off', 'disabled', 'false', '0', '关闭'])

  function isOffLevel(value?: string | null): boolean {
    return OFF_LEVEL_ALIASES.has(normalizeLevel(value))
  }

  /** 会话模型配置为整体覆盖写入，每次保存需带上全部覆盖值 */
  function buildModelConfigPayload(
    extra: Partial<SessionModelConfig>,
  ): Partial<SessionModelConfig> {
    const payload: Partial<SessionModelConfig> = { chat_mode: chatMode.value, ...extra }
    if (isSessionOverride.value && currentProviderId.value && currentModelId.value) {
      payload.provider = currentProviderId.value
      payload.model = currentModelId.value
    }
    return payload
  }

  /** 当前模型的思考档位：模型条目自定义值优先，其次内置建议 */
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
      // 档位建议读的是内置表：普通用户走 /api/me，避免打到管理员专属的 /api/settings
      const response = userStore.isAdmin
        ? await settingsAPI.getReasoningLevels(modelId)
        : await meAPI.getReasoningLevels(modelId)
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
    const normalized = normalizeLevel(candidate)
    // 用户显式选择「关闭」时保留关闭语义，不再回落到档位首项
    if (isOffLevel(normalized)) {
      return OFF_LEVEL
    }

    const levels = reasoningLevels.value
    if (levels.length === 0) {
      return null
    }
    if (normalized && levels.includes(normalized)) {
      return normalized
    }
    return levels[0]
  }

  /** 确保身份已加载再判定角色，避免管理员走用户接口拿到空清单 */
  async function ensureIdentity(): Promise<void> {
    if (!userStore.loaded) {
      await userStore.loadProfile()
    }
  }

  async function loadGlobalDefaults() {
    await ensureIdentity()
    // 普通用户无权读取全局配置，必须走 /api/me/models 的脱敏视图
    if (!userStore.isAdmin) {
      const data = await meAPI.listModels()
      providerOptions.value = buildProviderOptionsFromMeModels(data)
      meModelSources.value = Object.fromEntries(
        [...(data.shared || []), ...(data.own || [])]
          .filter(item => item?.provider && item?.model)
          .map(item => [`${item.provider}:${item.model}`, item.source]),
      )
      providerMetadata.value = []
      // selected 形如 "source:provider:model"
      const [, providerId = '', modelId = ''] = String(data.selected || '').split(':')
      currentProviderId.value = providerId
      currentModelId.value = modelId
      chatMode.value = defaultChatMode.value
      ensureModelPresent(currentProviderId.value, currentModelId.value)
      await refreshReasoningLevels().catch(() => {})
      currentReasoningLevel.value = resolveReasoningLevel(modelEntry.value?.reasoning_level)
      return null
    }

    const [settings, providers] = await Promise.all([
      settingsAPI.get(),
      settingsAPI.getProviders().catch(() => [] as ProviderMetadata[]),
    ])

    providerMetadata.value = providers
    providerOptions.value = buildProviderOptionsFromSettings(settings.providers)
    currentProviderId.value = settings.model.provider
    currentModelId.value = settings.model.model
    chatMode.value = defaultChatMode.value
    ensureModelPresent(currentProviderId.value, currentModelId.value)
    await refreshReasoningLevels()
    currentReasoningLevel.value = resolveReasoningLevel(modelEntry.value?.reasoning_level)
    return settings
  }

  /** 确保当前生效的模型出现在下拉中，必要时补进分组 */
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
      chatMode.value = clampChatMode(effective.chat_mode)
      ensureModelPresent(currentProviderId.value, currentModelId.value)

      await refreshReasoningLevels()
      // 会话覆盖仅在不同于全局默认时视为本会话选择，否则用模型默认档位；
      // 「关闭」是显式语义，即使与全局一致也要按会话选择展示
      const sessionLevel = normalizeLevel(effective.reasoning_level)
      const globalLevel = normalizeLevel(response.global_defaults?.model?.reasoning_level)
      const hasSessionLevel = !!sessionLevel
        && (sessionLevel !== globalLevel || isOffLevel(sessionLevel))
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
      if (userStore.isAdmin) {
        await settingsStore.setGlobalDefaultModel(providerId, modelId)
      } else {
        // 普通用户没有全局配置写权限，切模型走 /api/me/model-selection
        const source = meModelSources.value[`${providerId}:${modelId}`] || 'own'
        await meAPI.selectModel({ source, provider: providerId, model: modelId })
      }
      // 会话内实时切换的模型优先级最高：只要当前有会话就写回会话配置。
      // 否则会话里历史遗留的模型覆盖（会话面板写入 / 渠道命令写入）会在
      // 下一轮把切换结果拉回去，表现为「切了没生效」。
      if (sessionId) {
        isSessionOverride.value = true
        await chatAPI.updateSessionConfig(sessionId, {
          model_config: buildModelConfigPayload({ provider: providerId, model: modelId }),
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

  /** 会话级覆盖思考强度：写入会话配置，不改模型条目默认档位 */
  async function selectReasoningLevel(sessionId: string, level: string): Promise<boolean> {
    const next = normalizeLevel(level)
    if (!next || (!isOffLevel(next) && !reasoningLevels.value.includes(next))) {
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
      // 该接口为整体覆盖写入，需一并带上已绑定的 provider/model
      await chatAPI.updateSessionConfig(sessionId, {
        model_config: buildModelConfigPayload({ reasoning_level: next }),
      })
      isSessionOverride.value = true
      return true
    } catch (error) {
      currentReasoningLevel.value = previous
      throw error
    }
  }

  /** 切换对话模式：agent 启用工具/技能，chat 为纯对话 */
  async function selectChatMode(sessionId: string, mode: ChatMode): Promise<boolean> {
    const next = clampChatMode(mode)
    if (!allowedChatModes.value.includes(next)) {
      return false
    }
    if (next === chatMode.value) {
      return true
    }

    const previous = chatMode.value
    chatMode.value = next
    if (!sessionId) {
      return true
    }

    try {
      // 配置接口是整体覆盖写入：带上当前思考档位，切换模式不会把它清掉
      const modelConfig = buildModelConfigPayload({ chat_mode: next })
      if (currentReasoningLevel.value) {
        modelConfig.reasoning_level = currentReasoningLevel.value
      }
      await chatAPI.updateSessionConfig(sessionId, { model_config: modelConfig })
      isSessionOverride.value = true
      return true
    } catch (error) {
      chatMode.value = previous
      throw error
    }
  }

  /** 供应商清单在设置页被改动后，刷新下拉数据。 */
  async function refreshOptions() {
    // 普通用户无权读全局配置，走 /api/me/models；否则此处会 403
    if (!userStore.isAdmin) {
      await loadGlobalDefaults().catch(() => {})
      return
    }

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
    if (
      !currentReasoningLevel.value
      || (!isOffLevel(currentReasoningLevel.value)
        && !reasoningLevels.value.includes(currentReasoningLevel.value))
    ) {
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
    currentCapabilities,
    chatMode,
    allowedChatModes,
    canSwitchChatMode,
    defaultChatMode,
    loadGlobalDefaults,
    loadSessionSelection,
    selectModel,
    selectReasoningLevel,
    selectChatMode,
    refreshOptions,
  }
}

export type { SessionModelConfig }
