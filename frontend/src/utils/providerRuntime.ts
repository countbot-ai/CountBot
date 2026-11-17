import type { ProviderConfig, ProviderMetadata } from '@/api'

const LOCAL_PROVIDER_IDS = new Set(['ollama', 'vllm', 'lm_studio'])
const NO_API_KEY_PROVIDER_IDS = new Set(['custom_openai', 'custom_anthropic'])
const PROVIDER_GROUP_ORDER: Record<string, number> = {
  recommended: 0,
  experimental: 1,
  local: 2,
  advanced: 3,
}
const THINKING_CONTROL_TIER_ORDER: Record<string, number> = {
  native: 0,
  limited: 1,
  response_only: 2,
  experimental: 3,
  compat: 4,
  unsupported: 5,
}
const THINKING_CONTROL_NOTE_KEYS: Record<string, string> = {
  anthropic: 'settings.providers.thinkingControl.notes.anthropic',
  openai: 'settings.providers.thinkingControl.notes.openai',
  openrouter: 'settings.providers.thinkingControl.notes.openrouter',
  deepseek: 'settings.providers.thinkingControl.notes.deepseek',
  moonshot: 'settings.providers.thinkingControl.notes.moonshot',
  zhipu: 'settings.providers.thinkingControl.notes.zhipu',
  groq: 'settings.providers.thinkingControl.notes.groq',
  qwen: 'settings.providers.thinkingControl.notes.qwen',
  minimax: 'settings.providers.thinkingControl.notes.minimax',
  vllm: 'settings.providers.thinkingControl.notes.compat',
  ollama: 'settings.providers.thinkingControl.notes.compat',
  lm_studio: 'settings.providers.thinkingControl.notes.compat',
  custom_openai: 'settings.providers.thinkingControl.notes.compat',
  custom_anthropic: 'settings.providers.thinkingControl.notes.compat',
}

export interface ProviderRuntimeView {
  enabled: boolean
  configured: boolean
  selectable: boolean
  requiresApiKey: boolean
  requiresApiBase: boolean
  reason: string
}

export function getProviderLabel(provider: ProviderMetadata): string {
  return provider.name || provider.id
}

export function resolveProviderGroup(provider?: ProviderMetadata | null): string {
  return provider?.providerGroup || provider?.provider_group || 'experimental'
}

export function resolveThinkingControlTier(provider?: ProviderMetadata | null): string {
  return provider?.thinkingControlTier || provider?.thinking_control_tier || 'unsupported'
}

export function resolveThinkingControlNoteKey(provider?: ProviderMetadata | null): string {
  if (!provider) {
    return 'settings.providers.thinkingControl.notes.unsupported'
  }

  return (
    THINKING_CONTROL_NOTE_KEYS[provider.id]
    || `settings.providers.thinkingControl.notes.${resolveThinkingControlTier(provider)}`
  )
}

export function sortProvidersForDisplay<T extends ProviderMetadata>(providers: T[]): T[] {
  return [...providers].sort((left, right) => {
    const leftGroupOrder = PROVIDER_GROUP_ORDER[resolveProviderGroup(left)] ?? 99
    const rightGroupOrder = PROVIDER_GROUP_ORDER[resolveProviderGroup(right)] ?? 99
    if (leftGroupOrder !== rightGroupOrder) {
      return leftGroupOrder - rightGroupOrder
    }

    const leftTierOrder = THINKING_CONTROL_TIER_ORDER[resolveThinkingControlTier(left)] ?? 99
    const rightTierOrder = THINKING_CONTROL_TIER_ORDER[resolveThinkingControlTier(right)] ?? 99
    if (leftTierOrder !== rightTierOrder) {
      return leftTierOrder - rightTierOrder
    }

    return getProviderLabel(left).localeCompare(getProviderLabel(right), 'zh-CN')
  })
}

export function isProviderSelectable(provider: ProviderMetadata): boolean {
  return provider.selectable ?? true
}

export function computeProviderRuntimeState(
  provider: ProviderMetadata,
  providerConfig?: ProviderConfig | null,
): ProviderRuntimeView {
  const enabled = providerConfig?.enabled ?? provider.enabled ?? false
  const requiresApiKey = !LOCAL_PROVIDER_IDS.has(provider.id) && !NO_API_KEY_PROVIDER_IDS.has(provider.id)
  const defaultApiBase = resolveProviderDefaultApiBase(provider)
  const requiresApiBase = !defaultApiBase
  const apiKeyCandidates = Array.isArray(providerConfig?.api_keys)
    ? providerConfig!.api_keys
    : []
  const apiKey = (
    apiKeyCandidates.find(value => String(value || '').trim())
    || providerConfig?.api_key
    || ''
  ).trim()
  const apiBase = (providerConfig?.api_base || defaultApiBase || '').trim()
  const configured = (!requiresApiKey || !!apiKey) && (!requiresApiBase || !!apiBase)
  let reason = provider.reason || 'ready'

  if (!enabled) {
    reason = 'disabled'
  } else if (requiresApiKey && !apiKey) {
    reason = 'missing_api_key'
  } else if (requiresApiBase && !apiBase) {
    reason = 'missing_api_base'
  } else {
    reason = 'ready'
  }

  return {
    enabled,
    configured,
    selectable: enabled && configured,
    requiresApiKey,
    requiresApiBase,
    reason,
  }
}

export function getSelectableProviders<T extends ProviderMetadata>(providers: T[]): T[] {
  return providers.filter(isProviderSelectable)
}

export function isProviderSelectableWithConfig(
  provider: ProviderMetadata,
  providerConfig?: ProviderConfig | null,
): boolean {
  return computeProviderRuntimeState(provider, providerConfig).selectable
}

export function findFirstSelectableProviderWithConfig<T extends ProviderMetadata>(
  providers: T[],
  providerConfigs?: Record<string, ProviderConfig | undefined>,
): T | undefined {
  return providers.find(provider =>
    computeProviderRuntimeState(provider, providerConfigs?.[provider.id]).selectable
  )
}

export function findProviderById<T extends ProviderMetadata>(providers: T[], providerId?: string | null): T | undefined {
  if (!providerId) {
    return undefined
  }
  return providers.find(provider => provider.id === providerId)
}

export function findFirstSelectableProvider<T extends ProviderMetadata>(providers: T[]): T | undefined {
  return getSelectableProviders(providers)[0]
}

export function resolveProviderDefaultApiBase(provider?: ProviderMetadata): string {
  return provider?.defaultApiBase || provider?.default_api_base || ''
}

export function resolveProviderDefaultModel(provider?: ProviderMetadata): string {
  return provider?.defaultModel || provider?.default_model || ''
}
