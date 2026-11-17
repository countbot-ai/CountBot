/** 性格管理 API */

import i18n from '@/i18n'

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

const CJK_PATTERN = /[\u4e00-\u9fff]/

/** 非中文界面使用当前语言的默认提示，不直接展示服务端中文详情 */
function localizeDetail(detail: string, fallback: string): string {
    if (!CJK_PATTERN.test(detail)) {
        return detail
    }
    const locale = String((i18n.global.locale as any)?.value ?? i18n.global.locale ?? '')
    return locale.startsWith('zh') ? detail : fallback
}

/** 从错误响应的 detail（string/object/array）中解析可读文案 */
function extractErrorMessage(payload: any, fallback: string): string {
    const detail = payload?.detail ?? payload?.message

    if (typeof detail === 'string' && detail.trim()) {
        return localizeDetail(detail, fallback)
    }
    if (Array.isArray(detail)) {
        const parts = detail
            .map(item => (typeof item === 'string' ? item : item?.msg))
            .filter((item): item is string => Boolean(item && item.trim()))
        if (parts.length) return localizeDetail(parts.join('；'), fallback)
    }
    if (detail && typeof detail === 'object') {
        if (typeof detail.detail === 'string' && detail.detail.trim()) {
            return localizeDetail(detail.detail, fallback)
        }
        if (typeof detail.message === 'string' && detail.message.trim()) {
            return localizeDetail(detail.message, fallback)
        }
    }
    return fallback
}

export const personalitiesApi = {
    /** 获取所有性格列表 */
    async list(activeOnly = false): Promise<{ personalities: Personality[]; total: number }> {
        const response = await fetch(`${API_BASE}?active_only=${activeOnly}`)
        if (!response.ok) {
            throw new Error(`Failed to fetch personalities: ${response.statusText}`)
        }
        return response.json()
    },

    /** 获取单个性格详情 */
    async get(id: string): Promise<Personality> {
        const response = await fetch(`${API_BASE}/${id}`)
        if (!response.ok) {
            throw new Error(`Failed to fetch personality: ${response.statusText}`)
        }
        return response.json()
    },

    /** 创建性格 */
    async create(data: PersonalityCreate): Promise<Personality> {
        const response = await fetch(API_BASE, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data),
        })
        if (!response.ok) {
            const error = await response.json().catch(() => ({}))
            throw new Error(extractErrorMessage(error, 'Failed to create personality'))
        }
        return response.json()
    },

    /** 更新性格 */
    async update(id: string, data: PersonalityUpdate): Promise<Personality> {
        const response = await fetch(`${API_BASE}/${id}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data),
        })
        if (!response.ok) {
            const error = await response.json().catch(() => ({}))
            throw new Error(extractErrorMessage(error, 'Failed to update personality'))
        }
        return response.json()
    },

    /** 删除性格 */
    async delete(id: string): Promise<void> {
        const response = await fetch(`${API_BASE}/${id}`, {
            method: 'DELETE',
        })
        if (!response.ok) {
            const error = await response.json().catch(() => ({}))
            throw new Error(extractErrorMessage(error, 'Failed to delete personality'))
        }
    },
}

