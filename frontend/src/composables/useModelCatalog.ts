/** 模型目录：按身份提供可选的供应商/模型及连通性测试 */

import { computed } from 'vue'
import { t } from '@/i18n'
import { meAPI, settingsAPI } from '@/api'
import type {
  MeModelsResponse,
  ProviderMetadata,
  TestConnectionRequest,
  TestConnectionResponse,
} from '@/api'
import { useUserStore } from '@/store/user'

export function useModelCatalog() {
  const userStore = useUserStore()

  /** 身份是否已就绪（isAdmin 在 profile 加载前恒为 false） */
  const identityReady = computed(() => userStore.loaded)
  const isUserScoped = computed(() => identityReady.value && !userStore.isAdmin)

  async function ensureIdentity(): Promise<void> {
    if (!identityReady.value) {
      await userStore.loadProfile()
    }
  }

  /** 本次会话内复用用户模型清单，避免每次开面板都请求一次。 */
  let userModels: MeModelsResponse | null = null

  async function loadUserModels(force = false): Promise<MeModelsResponse> {
    if (!userModels || force) {
      userModels = await meAPI.listModels()
    }
    return userModels
  }

  /** 供应商清单；普通用户由自有模型清单归纳分组 */
  async function listProviders(): Promise<ProviderMetadata[]> {
    await ensureIdentity()
    if (!isUserScoped.value) {
      return settingsAPI.getProviders()
    }

    const data = await loadUserModels()
    const byProvider = new Map<string, ProviderMetadata>()
    for (const item of [...data.shared, ...data.own]) {
      if (!item.provider || item.available === false) continue
      if (byProvider.has(item.provider)) continue
      byProvider.set(item.provider, {
        id: item.provider,
        name: item.provider_name || item.provider,
        defaultModel: item.model,
        enabled: true,
        configured: true,
      })
    }
    return [...byProvider.values()]
  }

  /** 测试模型连通性；普通用户仅限清单内模型 */
  async function testConnection(
    payload: TestConnectionRequest,
  ): Promise<TestConnectionResponse> {
    await ensureIdentity()
    if (!isUserScoped.value) {
      return settingsAPI.testConnection(payload)
    }

    const data = await loadUserModels()
    const target = [...data.shared, ...data.own].find(
      (item) => item.provider === payload.provider && item.model === payload.model,
    )
    if (!target) {
      return { success: false, message: t('settings.models.notInCatalog') }
    }
    const result = await meAPI.testModel({
      source: target.source,
      provider: target.provider,
      model: target.model,
    })
    return { success: result.success, message: result.message }
  }

  return { identityReady, isUserScoped, ensureIdentity, listProviders, testConnection }
}
