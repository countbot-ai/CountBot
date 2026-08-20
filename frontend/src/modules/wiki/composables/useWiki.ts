/**
 * Wiki 组合式函数
 * 提供响应式的 Wiki 数据管理和操作
 */

import { ref, computed, onMounted } from 'vue'
import { wikiApi, type WikiEntry, type WikiStats } from '../services/wikiApi'

export function useWiki() {
  // State
  const entries = ref<WikiEntry[]>([])
  const loading = ref(false)
  const saving = ref(false)
  const error = ref<string | null>(null)
  const searchQuery = ref('')
  const filterTag = ref('all')

  // Computed
  const uniqueTags = computed(() => {
    const tags = new Set<string>()
    entries.value.forEach((e) => {
      e.tags?.forEach((tag) => tags.add(tag))
    })
    return Array.from(tags).sort()
  })

  const tagCounts = computed(() => {
    const counts: Record<string, number> = {}
    entries.value.forEach((e) => {
      e.tags?.forEach((tag) => {
        counts[tag] = (counts[tag] || 0) + 1
      })
    })
    return counts
  })

  const hasActiveFilters = computed(() =>
    filterTag.value !== 'all' || searchQuery.value.trim().length > 0
  )

  const filteredEntries = computed(() => {
    let result = entries.value

    // 如果有标签过滤，先按标签过滤
    if (filterTag.value !== 'all') {
      result = result.filter((e) => e.tags?.includes(filterTag.value))
    }

    // 如果有搜索查询，使用客户端简单过滤（BM25 搜索通过 searchEntries 方法单独调用）
    const query = searchQuery.value.trim().toLowerCase()
    if (query) {
      result = result.filter(
        (e) =>
          e.title.toLowerCase().includes(query) ||
          e.content.toLowerCase().includes(query) ||
          e.tags?.some((t) => t.toLowerCase().includes(query))
      )
    }

    return result
  })

  const shouldUseBM25Search = computed(() => {
    // 当搜索查询长度 >= 2 且没有标签过滤时，建议使用 BM25 搜索
    return searchQuery.value.trim().length >= 2 && filterTag.value === 'all'
  })

  const latestUpdate = computed(() => {
    if (entries.value.length === 0) return '-'
    const sorted = [...entries.value].sort(
      (a, b) =>
        new Date(b.updated_at || 0).getTime() -
        new Date(a.updated_at || 0).getTime()
    )
    return formatTime(sorted[0].updated_at)
  })

  // Methods
  async function loadEntries() {
    loading.value = true
    error.value = null
    try {
      entries.value = await wikiApi.listEntries()
    } catch (err: any) {
      error.value = err.message || '加载失败'
    } finally {
      loading.value = false
    }
  }

  async function createEntry(entry: Partial<WikiEntry>) {
    saving.value = true
    try {
      const newEntry = await wikiApi.createEntry(entry)
      await loadEntries()
      return newEntry
    } catch (err: any) {
      error.value = err.message || '创建失败'
      throw err
    } finally {
      saving.value = false
    }
  }

  async function updateEntry(slug: string, entry: Partial<WikiEntry>) {
    saving.value = true
    try {
      const updated = await wikiApi.updateEntry(slug, entry)
      await loadEntries()
      return updated
    } catch (err: any) {
      error.value = err.message || '更新失败'
      throw err
    } finally {
      saving.value = false
    }
  }

  async function deleteEntry(slug: string) {
    try {
      await wikiApi.deleteEntry(slug)
      await loadEntries()
    } catch (err: any) {
      error.value = err.message || '删除失败'
      throw err
    }
  }

  async function searchEntries(query: string) {
    loading.value = true
    try {
      return await wikiApi.search(query)
    } catch (err: any) {
      error.value = err.message || '搜索失败'
      return []
    } finally {
      loading.value = false
    }
  }

  async function getStats(): Promise<WikiStats> {
    return wikiApi.getStats()
  }

  async function compileContent(
    content: string,
    sourceType: string = 'article',
    titleHint?: string
  ) {
    return wikiApi.compile({ content, source_type: sourceType, title_hint: titleHint })
  }

  function resetFilters() {
    filterTag.value = 'all'
    searchQuery.value = ''
  }

  // Utilities
  function formatTime(iso?: string): string {
    if (!iso) return '-'
    const date = new Date(iso)
    const now = new Date()
    const diff = now.getTime() - date.getTime()
    const days = Math.floor(diff / (1000 * 60 * 60 * 24))

    if (days === 0) return '今天'
    if (days === 1) return '昨天'
    if (days < 7) return `${days} 天前`
    return date.toLocaleDateString('zh-CN')
  }

  function generateSlug(title: string): string {
    return title
      .toLowerCase()
      .replace(/[^\w\s-]/g, '')
      .replace(/[\s_-]+/g, '-')
      .substring(0, 100)
  }

  function getPreview(content: string, maxLength: number = 150): string {
    if (!content) return ''
    const clean = content.replace(/[#*`_~\[\]()]/g, '').trim()
    return clean.length > maxLength ? clean.substring(0, maxLength) + '...' : clean
  }

  // Lifecycle
  onMounted(() => {
    loadEntries()
  })

  return {
    // State
    entries,
    loading,
    saving,
    error,
    searchQuery,
    filterTag,

    // Computed
    uniqueTags,
    tagCounts,
    hasActiveFilters,
    filteredEntries,
    latestUpdate,
    shouldUseBM25Search,

    // Methods
    loadEntries,
    createEntry,
    updateEntry,
    deleteEntry,
    searchEntries,
    getStats,
    compileContent,
    resetFilters,

    // Utilities
    formatTime,
    generateSlug,
    getPreview,
  }
}
