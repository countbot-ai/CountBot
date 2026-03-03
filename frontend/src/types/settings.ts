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
}

export interface ProviderConfig {
    apiKey: string
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

export type SettingsTab = 'provider' | 'model' | 'persona' | 'workspace' | 'security' | 'channels'

export interface HeartbeatConfig {
    enabled: boolean
    channel: string
    chat_id: string
    schedule: string
    idle_threshold_hours: number
    quiet_start: number
    quiet_end: number
}

export interface PersonaConfig {
    ai_name: string
    user_name: string
    user_address?: string
    personality: string
    custom_personality: string
    max_history_messages: number
    heartbeat?: HeartbeatConfig
}
