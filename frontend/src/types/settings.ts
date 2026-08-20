/**
 * Settings 类型定义
 */

export interface ProviderMetadata {
    id: string
    name: string
    defaultApiBase?: string
    defaultModel?: string
    default_api_base?: string
    default_model?: string
    enabled?: boolean
    configured?: boolean
    selectable?: boolean
    requires_api_key?: boolean
    requires_api_base?: boolean
    status?: string
    reason?: string
    providerGroup?: string
    provider_group?: string
    thinkingControlTier?: string
    thinking_control_tier?: string
}

export interface ProviderConfig {
    apiKey: string
    apiKeys: string[]
    baseUrl?: string
    enabled: boolean
}

export interface Settings {
    providers: Record<string, ProviderConfig>
    model: string
    temperature: number
    maxTokens: number
    maxIterations: number
    workspace: string
    theme: 'light' | 'dark' | 'auto'
    language: 'zh-CN' | 'en-US' | 'auto'
    fontSize: 'small' | 'medium' | 'large'
}

export type SettingsTab = 'general' | 'provider' | 'model' | 'persona' | 'memory' | 'workspace' | 'security' | 'channels' | 'mcp' | 'externaltools' | 'multiagent' | 'importexport'

export interface HeartbeatConfig {
    enabled: boolean
    channel: string
    account_id?: string
    chat_id: string
    schedule: string
    idle_threshold_hours: number
    quiet_start: number
    quiet_end: number
    max_greets_per_day?: number
}

export interface PersonaConfig {
    ai_name: string
    user_name: string
    user_address?: string
    output_language?: string
    personality: string
    custom_personality: string
    max_history_messages: number
    enable_short_context_summary?: boolean
    heartbeat?: HeartbeatConfig
}
