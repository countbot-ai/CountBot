/**
 * 预设配置类型定义
 */

export interface ProviderPreset {
    id: string
    name: string
    description?: string
    provider: string
    model: string
    apiKey: string
    baseUrl?: string
    temperature?: number
    maxTokens?: number
    maxIterations?: number
    createdAt: string
    updatedAt: string
}

export interface PresetManager {
    presets: ProviderPreset[]
    selectedPresetId?: string
}