/** Settings 展示层类型；后端对齐类型统一维护在 @/api，此处不重复声明 */

export type { ProviderMetadata } from '@/api'

export type SettingsTab = 'general' | 'provider' | 'model' | 'persona' | 'memory' | 'workspace' | 'security' | 'injection' | 'channels' | 'mcp' | 'sharedskills' | 'externaltools' | 'multiagent' | 'importexport' | 'users' | 'notifications'

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
