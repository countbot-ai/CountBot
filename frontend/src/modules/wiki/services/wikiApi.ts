/**
 * Wiki API 服务层
 * 封装所有与后端 Wiki API 的交互
 */

const API_BASE = '/api/wiki'

export interface WikiEntry {
  slug: string
  title: string
  content: string
  tags: string[]
  summary?: string
  created_at?: string
  updated_at?: string
}

export interface WikiSearchResult {
  slug: string
  title: string
  summary: string
  tags: string[]
}

export interface WikiStats {
  articles: number
  indexed_count: number
  unique_terms: number
}

export interface CompileRequest {
  content: string
  source_type: string
  title_hint?: string
}

export interface CompileResult {
  success: boolean
  title?: string
  content?: string
  tags?: string[]
}

class WikiApiService {
  private async fetchWithRetry(url: string, options?: RequestInit, retries = 2): Promise<Response> {
    for (let i = 0; i <= retries; i++) {
      try {
        const res = await fetch(url, options)
        if (res.ok || i === retries) {
          return res
        }
        // 如果是服务器错误且还有重试次数，等待后重试
        if (res.status >= 500 && i < retries) {
          await new Promise(resolve => setTimeout(resolve, 1000 * (i + 1)))
          continue
        }
        return res
      } catch (err) {
        if (i === retries) throw err
        await new Promise(resolve => setTimeout(resolve, 1000 * (i + 1)))
      }
    }
    throw new Error('Request failed after retries')
  }

  // ---------- 条目管理 ----------

  async listEntries(tag?: string): Promise<WikiEntry[]> {
    const url = tag ? `${API_BASE}?tag=${encodeURIComponent(tag)}` : API_BASE
    const res = await this.fetchWithRetry(url)
    if (!res.ok) throw new Error('加载失败')
    const data = await res.json()
    return data.entries || []
  }

  async getEntry(slug: string): Promise<WikiEntry> {
    const res = await this.fetchWithRetry(`${API_BASE}/${slug}`)
    if (!res.ok) throw new Error('加载失败')
    return res.json()
  }

  async getBacklinks(slug: string): Promise<{ slug: string; title: string; backlinks: any[]; count: number }> {
    const res = await this.fetchWithRetry(`${API_BASE}/${slug}/backlinks`)
    if (!res.ok) throw new Error('加载反向链接失败')
    return res.json()
  }

  async syncIndex(): Promise<{ success: boolean; message: string; stats: any }> {
    const res = await this.fetchWithRetry(`${API_BASE}/sync`, { method: 'POST' })
    if (!res.ok) throw new Error('同步索引失败')
    return res.json()
  }

  async createEntry(entry: Partial<WikiEntry>): Promise<WikiEntry> {
    const res = await this.fetchWithRetry(API_BASE, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(entry),
    })
    if (!res.ok) throw new Error('创建失败')
    return res.json()
  }

  async updateEntry(slug: string, entry: Partial<WikiEntry>): Promise<WikiEntry> {
    const res = await this.fetchWithRetry(`${API_BASE}/${slug}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(entry),
    })
    if (!res.ok) throw new Error('更新失败')
    return res.json()
  }

  async deleteEntry(slug: string): Promise<void> {
    const res = await this.fetchWithRetry(`${API_BASE}/${slug}`, {
      method: 'DELETE',
    })
    if (!res.ok) throw new Error('删除失败')
  }

  // ---------- 搜索 ----------

  async search(query: string, limit: number = 20): Promise<WikiSearchResult[]> {
    const res = await this.fetchWithRetry(
      `${API_BASE}/search?query=${encodeURIComponent(query)}&limit=${limit}`
    )
    if (!res.ok) throw new Error('搜索失败')
    const data = await res.json()
    return data.results || []
  }

  async ask(question: string): Promise<string> {
    const res = await this.fetchWithRetry(`${API_BASE}/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    })
    if (!res.ok) throw new Error('提问失败')
    const data = await res.json()
    return data.answer || ''
  }

  // ---------- 统计 ----------

  async getStats(): Promise<WikiStats> {
    const res = await this.fetchWithRetry(`${API_BASE}/stats`)
    if (!res.ok) throw new Error('获取统计失败')
    return res.json()
  }

  // ---------- AI 编译 ----------

  async compile(request: CompileRequest): Promise<CompileResult> {
    const res = await this.fetchWithRetry(`${API_BASE}/compile`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    })
    if (!res.ok) throw new Error('编译失败')
    return res.json()
  }

  // ---------- 批量操作 ----------

  async batchDelete(slugs: string[]): Promise<any> {
    const res = await this.fetchWithRetry(`${API_BASE}/batch/delete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(slugs),
    })
    if (!res.ok) throw new Error('批量删除失败')
    return res.json()
  }

  async batchUpdateTags(slugs: string[], addTags: string[], removeTags: string[]): Promise<any> {
    const res = await this.fetchWithRetry(`${API_BASE}/batch/tag`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ slugs, add_tags: addTags, remove_tags: removeTags }),
    })
    if (!res.ok) throw new Error('批量更新标签失败')
    return res.json()
  }

  async exportWiki(): Promise<any> {
    const res = await this.fetchWithRetry(`${API_BASE}/export`)
    if (!res.ok) throw new Error('导出失败')
    return res.json()
  }

  async importWiki(entries: any[]): Promise<any> {
    const res = await this.fetchWithRetry(`${API_BASE}/import`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(entries),
    })
    if (!res.ok) throw new Error('导入失败')
    return res.json()
  }
}

export const wikiApi = new WikiApiService()
