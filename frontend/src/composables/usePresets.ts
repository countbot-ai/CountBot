/**
 * 预设管理 Composable
 */

import { ref, computed } from 'vue'
import type { ProviderPreset, PresetManager } from '@/types/presets'

const STORAGE_KEY = 'provider-presets'

// 检查 localStorage 是否可用
function checkLocalStorageAvailability(): boolean {
    try {
        const testKey = '__localStorage_test__'
        localStorage.setItem(testKey, 'test')
        localStorage.removeItem(testKey)
        return true
    } catch (error) {
        console.error('localStorage is not available:', error)
        return false
    }
}

// 全局状态 - 确保所有组件共享同一个状态
const presets = ref<ProviderPreset[]>([])
const selectedPresetId = ref<string>()

// 计算属性
const selectedPreset = computed(() =>
    presets.value.find(p => p.id === selectedPresetId.value)
)

const presetOptions = computed(() =>
    presets.value.map(preset => ({
        value: preset.id,
        label: preset.name,
        description: preset.description
    }))
)

// 加载预设
function loadPresets() {
    try {
        const stored = localStorage.getItem(STORAGE_KEY)
        if (stored) {
            const data: PresetManager = JSON.parse(stored)
            presets.value = data.presets || []
            selectedPresetId.value = data.selectedPresetId
        } else {
            presets.value = []
        }
    } catch (error) {
        console.error('Failed to load presets:', error)
        presets.value = []
    }
}

// 保存预设到存储
function saveToStorage() {
    if (!checkLocalStorageAvailability()) {
        throw new Error('localStorage is not available')
    }

    try {
        const data: PresetManager = {
            presets: presets.value,
            selectedPresetId: selectedPresetId.value
        }
        localStorage.setItem(STORAGE_KEY, JSON.stringify(data))
    } catch (error) {
        console.error('Failed to save presets:', error)
        throw error
    }
}

// 创建新预设
function createPreset(config: Omit<ProviderPreset, 'id' | 'createdAt' | 'updatedAt'>): string {
    const id = `preset_${Date.now()}_${Math.random().toString(36).substring(2, 11)}`
    const now = new Date().toISOString()

    const preset: ProviderPreset = {
        ...config,
        id,
        createdAt: now,
        updatedAt: now
    }

    presets.value.push(preset)
    saveToStorage()
    return id
}

// 更新预设
function updatePreset(id: string, updates: Partial<Omit<ProviderPreset, 'id' | 'createdAt'>>) {
    const index = presets.value.findIndex(p => p.id === id)
    if (index !== -1) {
        presets.value[index] = {
            ...presets.value[index],
            ...updates,
            updatedAt: new Date().toISOString()
        }
        saveToStorage()
    }
}

// 删除预设
function deletePreset(id: string) {
    const index = presets.value.findIndex(p => p.id === id)
    if (index !== -1) {
        presets.value.splice(index, 1)
        if (selectedPresetId.value === id) {
            selectedPresetId.value = undefined
        }
        saveToStorage()
    }
}

// 选择预设
function selectPreset(id: string) {
    selectedPresetId.value = id
    saveToStorage()
}

// 清除选择
function clearSelection() {
    selectedPresetId.value = undefined
    saveToStorage()
}

// 导出预设
function exportPresets(): string {
    return JSON.stringify({
        presets: presets.value,
        exportedAt: new Date().toISOString(),
        version: '1.0'
    }, null, 2)
}

// 导入预设
function importPresets(jsonData: string): { success: boolean; message: string; imported: number } {
    try {
        const data = JSON.parse(jsonData)

        if (!data.presets || !Array.isArray(data.presets)) {
            return { success: false, message: '无效的预设数据格式', imported: 0 }
        }

        let imported = 0
        for (const preset of data.presets) {
            if (preset.name && preset.provider && preset.model) {
                // 检查是否已存在同名预设
                const existing = presets.value.find(p => p.name === preset.name)
                if (!existing) {
                    createPreset({
                        name: preset.name,
                        description: preset.description,
                        provider: preset.provider,
                        model: preset.model,
                        apiKey: preset.apiKey || '',
                        baseUrl: preset.baseUrl,
                        temperature: preset.temperature,
                        maxTokens: preset.maxTokens,
                        maxIterations: preset.maxIterations
                    })
                    imported++
                }
            }
        }

        return {
            success: true,
            message: `成功导入 ${imported} 个预设`,
            imported
        }
    } catch (error) {
        return {
            success: false,
            message: '解析预设数据失败：' + (error as Error).message,
            imported: 0
        }
    }
}

// 初始化 - 只在第一次导入时执行
let initialized = false
if (!initialized) {
    loadPresets()
    initialized = true
}

export function usePresets() {
    return {
        presets,
        selectedPresetId,
        selectedPreset,
        presetOptions,
        createPreset,
        updatePreset,
        deletePreset,
        selectPreset,
        clearSelection,
        exportPresets,
        importPresets,
        loadPresets
    }
}