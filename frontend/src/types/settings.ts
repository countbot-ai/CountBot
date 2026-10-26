/**
 * Settings 的展示层类型。
 *
 * 与后端对齐的 ProviderConfig / Settings / ProviderMetadata 统一维护在
 * @/api（endpoints.ts），这里不再重复声明，避免两边字段漂移。
 */

export type { ProviderMetadata } from '@/api'

export type SettingsTab = 'general' | 'provider' | 'model' | 'persona' | 'memory' | 'workspace' | 'security' | 'injection' | 'channels' | 'mcp' | 'externaltools' | 'multiagent' | 'importexport'

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
