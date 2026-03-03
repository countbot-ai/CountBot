/**
 * Memory 状态管理
 * 长期记忆 + 搜索 + 统计
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { memoryAPI } from '@/api'

export interface MemorySearchResult {
    line: number
    content: string
    type: 'long-term'
    date?: string
}

export const useMemoryStore = defineStore('memory', () => {
    // State
    const longTermMemory = ref<string>('')
    const isLoading = ref(false)
    const isSaving = ref(false)
    const error = ref<string | null>(null)

    // Computed
    const hasLongTermMemory = computed(() => {
        return longTermMemory.value.trim().length > 0
    })

    // Actions
    async function loadLongTermMemory() {
        isLoading.value = true
        error.value = null
        try {
            const response = await memoryAPI.getLongTerm()
            longTermMemory.value = response.content || ''
        } catch (err: any) {
            error.value = err.message || 'Failed to load long-term memory'
            console.error('Failed to load long-term memory:', err)
        } finally {
            isLoading.value = false
        }
    }

    async function saveLongTermMemory(content: string) {
        isSaving.value = true
        error.value = null
        try {
            await memoryAPI.updateLongTerm({ content })
            longTermMemory.value = content
        } catch (err: any) {
            error.value = err.message || 'Failed to save long-term memory'
            throw err
        } finally {
            isSaving.value = false
        }
    }

    /**
     * 搜索记忆（本地 + 远程）
     * 先尝试本地搜索已加载的内容，如果没有则调用后端 API
     */
    function searchMemory(query: string): MemorySearchResult[] {
        if (!query.trim()) return []

        const keywords = query.trim().toLowerCase().split(/\s+/)
        const lines = longTermMemory.value.split('\n').filter(l => l.trim())
        const results: MemorySearchResult[] = []

        for (let i = 0; i < lines.length; i++) {
            const lineLower = lines[i].toLowerCase()
            if (keywords.every(kw => lineLower.includes(kw))) {
                // 从行格式 "日期|来源|内容" 中提取日期
                const parts = lines[i].split('|', 3)
                const date = parts.length >= 1 ? parts[0] : undefined
                results.push({
                    line: i + 1,
                    content: lines[i],
                    type: 'long-term',
                    date,
                })
            }
        }

        return results
    }

    function clearError() {
        error.value = null
    }

    return {
        // State
        longTermMemory,
        isLoading,
        isSaving,
        error,

        // Computed
        hasLongTermMemory,

        // Actions
        loadLongTermMemory,
        saveLongTermMemory,
        searchMemory,
        clearError,
    }
})
