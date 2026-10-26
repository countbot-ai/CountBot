/**
 * 供应商清单与选中态。
 *
 * 唯一所有者：`availableProviders`（后端供应商目录）与 `selectedProvider`（当前编辑的供应商）。
 *
 * 左栏只展示「已经保存过、且真的配了密钥或模型」的供应商：
 * 草稿里新加的供应商在保存成功前不会出现，保存成功后才会进入左栏，
 * 同时也就能在对话窗口的模型下拉里选到（下拉读的是同一份已保存配置）。
 */

import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { settingsAPI } from '@/api'
import type { ProviderMetadata } from '@/api'
import { useSettingsStore } from '@/store/settings'
import {
  computeProviderRuntimeState,
  findProviderById,
  sortProvidersForDisplay,
} from '@/utils/providerRuntime'
import type { ProviderNavItem } from './types'

export interface ProviderCatalog {
  availableProviders: Ref<ProviderMetadata[]>
  selectedProvider: Ref<string>
  showAllProviders: Ref<boolean>
  selectedProviderMeta: ComputedRef<ProviderMetadata | undefined>
  navigationProviders: ComputedRef<ProviderNavItem[]>
  hiddenProviderCount: ComputedRef<number>
  addableProviders: ComputedRef<ProviderMetadata[]>
  loadProviders: () => Promise<void>
  selectProvider: (providerId: string) => void
  /** 记录「本次会话刚通过添加入口接过」的供应商，让它立刻出现在左栏 */
  markProviderAdded: (providerId: string) => void
  /** 撤销上面的记录（删除供应商时调用，否则它会被当成「刚添加」继续留在左栏） */
  unmarkProviderAdded: (providerId: string) => void
}

/** 已保存的配置里，这个供应商算不算「配过了」。 */
function isConfigured(config: unknown): boolean {
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

export function useProviderCatalog(): ProviderCatalog {
  const { t } = useI18n()
  const settingsStore = useSettingsStore()

  const availableProviders = ref<ProviderMetadata[]>([])
  const selectedProvider = ref('')
  const showAllProviders = ref(false)
  /**
   * 本次会话里通过「添加供应商」显式接过的供应商。
   * 后端为每个供应商都预建了空配置，光看配置无法区分「用户刚加的」和「一直存在的空壳」，
   * 所以这里显式记一笔：刚加完立刻可见（带「未保存」），配好并保存后标记自动失效。
   */
  const addedProviderIds = ref<string[]>([])

  /**
   * 已保存的供应商配置。
   * 首次渲染时 persistedSettings 可能还没就绪，先退回当前配置避免闪空。
   */
  const savedProviderConfigs = computed(
    () => (settingsStore.persistedSettings || settingsStore.settings)?.providers || {},
  )

  const selectedProviderMeta = computed(() =>
    findProviderById(availableProviders.value, selectedProvider.value),
  )

  /**
   * 左栏全集：后端有目录 + （已保存配过 或 本次刚添加）。
   */
  const allNavItems = computed<ProviderNavItem[]>(() => {
    const savedConfigs = savedProviderConfigs.value
    const draftConfigs = settingsStore.settings?.providers || {}
    const currentProviderId = settingsStore.settings?.model?.provider || ''

    return sortProvidersForDisplay(availableProviders.value)
      .filter(
        meta =>
          Boolean(savedConfigs[meta.id])
          || addedProviderIds.value.includes(meta.id),
      )
      .map(meta => {
        const savedConfig = savedConfigs[meta.id]
        // 刚添加、还没配好的：用草稿数据，界面才能立刻反映刚填的名字
        const config = savedConfig || draftConfigs[meta.id]
        const enabledCount = (config?.models || []).filter(
          model => model.enabled !== false,
        ).length
        const runtime = computeProviderRuntimeState(meta, {
          enabled: config?.enabled !== false,
          api_key: config?.api_key || '',
          api_keys: config?.api_keys || [],
          api_base: config?.api_base || '',
        })
        const name = config?.name || meta.name || meta.id
        const configured = isConfigured(savedConfig)

        return {
          id: meta.id,
          name,
          isCurrent: meta.id === currentProviderId,
          modelSummary: enabledCount
            ? t('settings.providers.models.count', { count: enabledCount })
            : t('settings.providers.models.emptyHint'),
          statusClass: runtime.selectable ? 'is-ready' : 'is-warning',
          configured,
          // 刚添加但还没保存配好：显示「未保存」，保存成功后自动消失
          pendingSave: !configured && addedProviderIds.value.includes(meta.id),
        } as ProviderNavItem
      })
  })

  /** 默认只出「已保存且配过密钥或模型」的，外加刚添加、还没保存的 */
  const navigationProviders = computed(() =>
    showAllProviders.value
      ? allNavItems.value
      : allNavItems.value.filter(item => item.configured || item.pendingSave),
  )

  const hiddenProviderCount = computed(
    () =>
      allNavItems.value.length
      - allNavItems.value.filter(item => item.configured || item.pendingSave).length,
  )

  /** 还没真正接进来的供应商：可以出现在「添加供应商」里 */
  const addableProviders = computed(() =>
    sortProvidersForDisplay(availableProviders.value).filter(
      meta => !isConfigured(savedProviderConfigs.value[meta.id]),
    ),
  )

  async function loadProviders(): Promise<void> {
    availableProviders.value = sortProvidersForDisplay(await settingsAPI.getProviders())
  }

  function selectProvider(providerId: string): void {
    if (providerId === selectedProvider.value) {
      return
    }
    selectedProvider.value = providerId
  }

  function markProviderAdded(providerId: string): void {
    if (!providerId || addedProviderIds.value.includes(providerId)) {
      return
    }
    addedProviderIds.value = [...addedProviderIds.value, providerId]
  }

  function unmarkProviderAdded(providerId: string): void {
    addedProviderIds.value = addedProviderIds.value.filter(id => id !== providerId)
  }

  return {
    availableProviders,
    selectedProvider,
    showAllProviders,
    selectedProviderMeta,
    navigationProviders,
    hiddenProviderCount,
    addableProviders,
    loadProviders,
    selectProvider,
    markProviderAdded,
    unmarkProviderAdded,
  }
}
