/**
 * 供应商模型清单的数据入口。
 *
 * 设置页（左栏供应商 + 右栏模型列表）和对话输入框的模型下拉共用这一份逻辑，
 * 避免两处各写一遍「拉取 -> 写入 -> 刷新」的流程。
 */

import { computed, ref } from 'vue'
import { settingsAPI } from '@/api'
import type {
    ProviderMetadata,
    ProviderModelCatalogEntry,
    ProviderModelEntry,
} from '@/api'

export interface ProviderOption {
    id: string
    name: string
    apiType: string
    enabled: boolean
    models: ProviderModelEntry[]
}

export function useProviderModelCatalog() {
    const catalogLoading = ref(false)
    const catalogError = ref<string | null>(null)
    const fetchedModels = ref<ProviderModelCatalogEntry[]>([])

    async function fetchCatalog(providerId: string): Promise<ProviderModelCatalogEntry[]> {
        if (!providerId) {
            return []
        }

        catalogLoading.value = true
        catalogError.value = null

        try {
            const response = await settingsAPI.getProviderModelCatalog(providerId)
            if (!response.success) {
                catalogError.value = response.error || ''
                fetchedModels.value = []
                return []
            }
            fetchedModels.value = response.models || []
            return fetchedModels.value
        } catch (error: any) {
            catalogError.value = error?.response?.data?.detail || error?.message || ''
            fetchedModels.value = []
            return []
        } finally {
            catalogLoading.value = false
        }
    }

    function reset() {
        fetchedModels.value = []
        catalogError.value = null
        catalogLoading.value = false
    }

    return {
        catalogLoading,
        catalogError,
        fetchedModels,
        fetchCatalog,
        reset,
    }
}

/** 把 settings.providers 投影成下拉需要的「供应商 -> 可用模型」结构。 */
export function buildProviderOptions(
    providers: Record<string, any> | undefined,
    metadata: ProviderMetadata[] | undefined,
): ProviderOption[] {
    if (!providers) {
        return []
    }

    const nameById = new Map((metadata || []).map(item => [item.id, item.name || item.id]))

    return Object.entries(providers)
        .map(([providerId, config]) => {
            const models: ProviderModelEntry[] = (config?.models || []).filter(
                (model: ProviderModelEntry) => model?.id,
            )
            return {
                id: providerId,
                name: config?.name || nameById.get(providerId) || providerId,
                apiType: config?.api_type || 'openai-chat-completions',
                enabled: config?.enabled !== false,
                models,
            }
        })
        .filter(provider => provider.enabled)
}

/** 只保留启用模型的分组，供对话输入框的下拉使用。 */
export function buildSelectableModelGroups(options: ProviderOption[]) {
    return options
        .map(provider => ({
            providerId: provider.id,
            providerName: provider.name,
            models: provider.models.filter(model => model.enabled !== false),
        }))
        .filter(group => group.models.length > 0)
}

export function useSelectableModelGroups(
    providers: () => Record<string, any> | undefined,
    metadata: () => ProviderMetadata[] | undefined,
) {
    return computed(() =>
        buildSelectableModelGroups(buildProviderOptions(providers(), metadata())),
    )
}
