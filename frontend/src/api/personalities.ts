/**
 * 性格管理 API
 */

export interface Personality {
    id: string
    name: string
    description: string
    traits: string[]
    speaking_style: string
    icon: string
    is_builtin: boolean
    is_active: boolean
    created_at: string
    updated_at: string
}

export interface PersonalityCreate {
    id: string
    name: string
    description: string
    traits: string[]
    speaking_style: string
    icon?: string
}

export interface PersonalityUpdate {
    name?: string
    description?: string
    traits?: string[]
    speaking_style?: string
    icon?: string
    is_active?: boolean
}

const API_BASE = '/api/personalities'

export const personalitiesApi = {
    /**
     * 获取所有性格列表
     */
    async list(activeOnly = false): Promise<{ personalities: Personality[]; total: number }> {
        const response = await fetch(`${API_BASE}?active_only=${activeOnly}`)
        if (!response.ok) {
            throw new Error(`Failed to fetch personalities: ${response.statusText}`)
        }
        return response.json()
    },

    /**
     * 获取单个性格详情
     */
    async get(id: string): Promise<Personality> {
        const response = await fetch(`${API_BASE}/${id}`)
        if (!response.ok) {
            throw new Error(`Failed to fetch personality: ${response.statusText}`)
        }
        return response.json()
    },

    /**
     * 创建自定义性格
     */
    async create(data: PersonalityCreate): Promise<Personality> {
        const response = await fetch(API_BASE, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data),
        })
        if (!response.ok) {
            const error = await response.json()
            throw new Error(error.detail || 'Failed to create personality')
        }
        return response.json()
    },

    /**
     * 更新性格
     */
    async update(id: string, data: PersonalityUpdate): Promise<Personality> {
        const response = await fetch(`${API_BASE}/${id}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data),
        })
        if (!response.ok) {
            const error = await response.json()
            throw new Error(error.detail || 'Failed to update personality')
        }
        return response.json()
    },

    /**
     * 删除性格（仅限自定义性格）
     */
    async delete(id: string): Promise<void> {
        const response = await fetch(`${API_BASE}/${id}`, {
            method: 'DELETE',
        })
        if (!response.ok) {
            const error = await response.json()
            throw new Error(error.detail || 'Failed to delete personality')
        }
    },

    /**
     * 复制性格
     */
    async duplicate(id: string, newId: string, newName?: string): Promise<Personality> {
        const response = await fetch(`${API_BASE}/${id}/duplicate`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                new_id: newId,
                new_name: newName,
            }),
        })
        if (!response.ok) {
            const error = await response.json()
            throw new Error(error.detail || 'Failed to duplicate personality')
        }
        return response.json()
    },
}
