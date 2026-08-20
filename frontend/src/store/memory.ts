/**
 * Memory state management.
 * Long-term memory + self-improving memory.
 */

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { memoryAPI } from '@/api'

export interface MemorySearchResult {
  line: number
  content: string
  type: 'long-term' | 'self-improving' | 'self-improving-corrections'
  date?: string
}

export const useMemoryStore = defineStore('memory', () => {
  const longTermMemory = ref('')
  const selfImprovingMemory = ref('')
  const selfImprovingCorrections = ref('')
  const selfImprovingIndex = ref('')
  const selfImprovingHeartbeatState = ref('')
  const selfImprovingProjects = ref<string[]>([])
  const selfImprovingDomains = ref<string[]>([])
  const selfImprovingArchive = ref<string[]>([])
  const isLoading = ref(false)
  const isSaving = ref(false)
  const error = ref<string | null>(null)

  const hasLongTermMemory = computed(() => longTermMemory.value.trim().length > 0)
  const hasSelfImprovingMemory = computed(() => selfImprovingMemory.value.trim().length > 0)

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

  async function loadSelfImprovingMemory() {
    isLoading.value = true
    error.value = null
    try {
      const response = await memoryAPI.getSelfImproving()
      selfImprovingMemory.value = response.memory || ''
      selfImprovingCorrections.value = response.corrections || ''
      selfImprovingIndex.value = response.index || ''
      selfImprovingHeartbeatState.value = response.heartbeat_state || ''
      selfImprovingProjects.value = response.projects || []
      selfImprovingDomains.value = response.domains || []
      selfImprovingArchive.value = response.archive || []
    } catch (err: any) {
      error.value = err.message || 'Failed to load self-improving memory'
      console.error('Failed to load self-improving memory:', err)
    } finally {
      isLoading.value = false
    }
  }

  async function saveSelfImprovingMemory(memory: string) {
    isSaving.value = true
    error.value = null
    try {
      await memoryAPI.updateSelfImproving({ memory })
      selfImprovingMemory.value = memory
      await loadSelfImprovingMemory()
    } catch (err: any) {
      error.value = err.message || 'Failed to save self-improving memory'
      throw err
    } finally {
      isSaving.value = false
    }
  }

  async function loadAllMemory() {
    await Promise.all([loadLongTermMemory(), loadSelfImprovingMemory()])
  }

  function searchMemory(query: string): MemorySearchResult[] {
    if (!query.trim()) return []

    const keywords = query.trim().toLowerCase().split(/\s+/)
    const results: MemorySearchResult[] = []

    const searchText = (
      content: string,
      type: MemorySearchResult['type'],
    ) => {
      const lines = content.split('\n').filter(line => line.trim())
      for (let i = 0; i < lines.length; i += 1) {
        const lineLower = lines[i].toLowerCase()
        if (keywords.every(keyword => lineLower.includes(keyword))) {
          const parts = lines[i].split('|', 4)
          results.push({
            line: i + 1,
            content: lines[i],
            type,
            date: parts.length >= 1 ? parts[0] : undefined,
          })
        }
      }
    }

    searchText(longTermMemory.value, 'long-term')
    searchText(selfImprovingMemory.value, 'self-improving')
    searchText(selfImprovingCorrections.value, 'self-improving-corrections')

    return results
  }

  function clearError() {
    error.value = null
  }

  return {
    longTermMemory,
    selfImprovingMemory,
    selfImprovingCorrections,
    selfImprovingIndex,
    selfImprovingHeartbeatState,
    selfImprovingProjects,
    selfImprovingDomains,
    selfImprovingArchive,
    isLoading,
    isSaving,
    error,
    hasLongTermMemory,
    hasSelfImprovingMemory,
    loadLongTermMemory,
    saveLongTermMemory,
    loadSelfImprovingMemory,
    saveSelfImprovingMemory,
    loadAllMemory,
    searchMemory,
    clearError,
  }
})
