/**
 * 供应商模型清单的数据入口。
 *
 * 设置页（左栏供应商 + 右栏模型列表）和对话输入框的模型下拉共用这一份逻辑，
 * 避免两处各写一遍「拉取 -> 写入 -> 刷新」的流程。
 */

import { computed, ref } from 'vue'
import { settingsAPI } from '@/api'
import type {
    MeModelItem,
    ProviderMetadata,
    ProviderModelCatalogEntry,
    ProviderModelEntry,
} from '@/api'
import type { ProviderConfigSource } from '@/modules/settings/provider-config/source'

export interface ProviderOption {
    id: string
    name: string
    apiType: string
    enabled: boolean
    models: ProviderModelEntry[]
}

export function useProviderModelCatalog(source?: ProviderConfigSource) {
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
            // 注入数据源时走对应身份的端点；缺省为管理员全局目录
            const response = source
                ? await source.api.fetchModelCatalog(providerId)
                : await settingsAPI.getProviderModelCatalog(providerId)
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

/** 将 /api/me/models 的分组结果转为下拉选项（普通用户视角）。 */
export function buildProviderOptionsFromMeModels(
    data: { shared?: MeModelItem[]; own?: MeModelItem[] },
): ProviderOption[] {
    // 共享模型合并为一个「内置模型」分组，条目保留真实供应商 ID 供选择时使用
    const builtinGroup: ProviderOption = {
        id: '__builtin_models__',
        name: '',
        apiType: 'openai-chat-completions',
        enabled: true,
        models: [],
    }
    const byProvider = new Map<string, ProviderOption>()
    for (const item of [...(data.shared || []), ...(data.own || [])]) {
        if (!item?.provider || !item?.model || item.available === false) continue
        if (item.source === 'shared') {
            if (!builtinGroup.name) {
                builtinGroup.name = item.provider_name || item.provider
            }
            if (!builtinGroup.models.some(model => model.id === item.model)) {
                builtinGroup.models.push({
                    id: item.model,
                    display_name: item.alias || item.model,
                    enabled: true,
                    context_window: item.context_window ?? null,
                    provider_id: item.provider,
                } as ProviderModelEntry)
            }
            continue
        }
        let option = byProvider.get(item.provider)
        if (!option) {
            option = {
                id: item.provider,
                name: item.provider_name || item.provider,
                apiType: 'openai-chat-completions',
                enabled: true,
                models: [],
            }
            byProvider.set(item.provider, option)
        }
        if (!option.models.some(model => model.id === item.model)) {
            option.models.push({
                id: item.model,
                display_name: item.alias || item.model,
                enabled: true,
                context_window: item.context_window ?? null,
                native_capabilities: item.native_capabilities,
            } as ProviderModelEntry)
        }
    }
    if (builtinGroup.models.length > 0) {
        return [builtinGroup, ...byProvider.values()]
    }
    return [...byProvider.values()]
}

export function useSelectableModelGroups(
    providers: () => Record<string, any> | undefined,
    metadata: () => ProviderMetadata[] | undefined,
) {
    return computed(() =>
        buildSelectableModelGroups(buildProviderOptions(providers(), metadata())),
    )
}
