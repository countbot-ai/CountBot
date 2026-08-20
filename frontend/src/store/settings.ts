/**
 * Settings 状态管理
 */

import { defineStore } from 'pinia'
import { ref } from 'vue'
import { settingsAPI, type Settings } from '@/api'
import { buildSendableModelConfig } from '@/utils/modelConfig'

export interface ProviderConfig {
    enabled: boolean
    api_key?: string
    api_keys?: string[]
    api_base?: string
}

export interface ModelConfig {
    provider: string
    model: string
    api_mode: 'chat_completions'
    temperature: number
    max_tokens: number
    max_iterations: number
    thinking_enabled: boolean
}

export interface WorkspaceConfig {
    path: string
}

export interface SecurityConfig {
    // 危险命令检测
    dangerous_commands_blocked: boolean
    custom_deny_patterns: string[]

    // 命令白名单
    command_whitelist_enabled: boolean
    custom_allow_patterns: string[]

    // 审计日志
    audit_log_enabled: boolean

    // 其他安全选项
    command_timeout: number
    subagent_timeout: number  // 子代理超时（秒）
    max_output_length: number
    restrict_to_workspace: boolean
}

export const useSettingsStore = defineStore('settings', () => {
    const cloneSettings = <T>(value: T): T => JSON.parse(JSON.stringify(value))

    // State
    const settings = ref<Settings | null>(null)
    const persistedSettings = ref<Settings | null>(null)
    const loading = ref(false)
    const saving = ref(false)
    const testing = ref(false)
    const error = ref<string | null>(null)

    /**
     * 加载设置
     */
    async function loadSettings() {
        loading.value = true
        error.value = null
        try {
            const response = await settingsAPI.get()
            settings.value = response
            persistedSettings.value = cloneSettings(response)
        } catch (err: any) {
            error.value = err.message || 'Failed to load settings'
            throw err
        } finally {
            loading.value = false
        }
    }

    /**
     * 保存设置
     */
    async function saveSettings(
        newSettings: Partial<Settings>,
        options: { includeChannels?: boolean } = {}
    ) {
        saving.value = true
        error.value = null
        try {
            // 1. 保存常规设置
            const response = await settingsAPI.update(newSettings)
            settings.value = response
            persistedSettings.value = cloneSettings(response)

            if (options.includeChannels) {
                const { useChannelsStore } = await import('./channels')
                const channelsStore = useChannelsStore()
                const channelsSaved = await channelsStore.saveAllChannels()

                if (!channelsSaved) {
                    throw new Error('Failed to save channel configurations')
                }
            }

            return true
        } catch (err: any) {
            error.value = err.message || 'Failed to save settings'
            throw err
        } finally {
            saving.value = false
        }
    }

    /**
     * 测试连接
     */
    async function testConnection(
        provider: string,
        apiKey: string,
        apiBase?: string,
        model?: string,
        apiMode?: 'chat_completions',
        temperature?: number,
        maxTokens?: number,
        thinkingEnabled?: boolean
    ) {
        testing.value = true
        error.value = null
        try {
            const response = await settingsAPI.testConnection({
                provider,
                api_key: apiKey,
                api_base: apiBase,
                model,
                api_mode: apiMode,
                ...buildSendableModelConfig({
                    temperature,
                    max_tokens: maxTokens,
                    thinking_enabled: thinkingEnabled,
                }),
            })
            return response.success
        } catch (err: any) {
            error.value = err.message || 'Connection test failed'
            throw err
        } finally {
            testing.value = false
        }
    }

    /**
     * 更新提供商配置
     */
    function updateProvider(provider: string, config: ProviderConfig) {
        if (settings.value) {
            settings.value.providers[provider] = config
        }
    }

    /**
     * 更新模型配置
     */
    function updateModel(config: Partial<ModelConfig>) {
        if (settings.value) {
            settings.value.model = { ...settings.value.model, ...config }
        }
    }

    /**
     * 更新工作空间配置
     */
    function updateWorkspace(config: WorkspaceConfig) {
        if (settings.value) {
            settings.value.workspace = config
        }
    }

    /**
     * 更新安全配置
     */
    function updateSecurity(config: SecurityConfig) {
        if (settings.value) {
            settings.value.security = config
            // 自动保存到后端
            void saveSettings({ security: config }).catch((err: any) => {
                console.error('Failed to auto-save security settings:', err)
            })
        }
    }

    return {
        // State
        settings,
        persistedSettings,
        loading,
        saving,
        testing,
        error,

        // Actions
        loadSettings,
        saveSettings,
        testConnection,
        updateProvider,
        updateModel,
        updateWorkspace,
        updateSecurity
    }
})
