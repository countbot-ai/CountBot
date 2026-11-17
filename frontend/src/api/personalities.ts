/** 性格管理 API */

import i18n from '@/i18n'

const t = (key: string) => i18n.global.t(key)

export interface Personality {
    id: string
    name: string
    description: string
    traits: string[]
    speaking_style: string
    icon: string
    is_builtin: boolean
    is_active: boolean
    is_cloned?: boolean
    mental_models?: MentalModel[]
    heuristics?: Heuristic[]
    expression_dna?: ExpressionDNA
    values?: string[]
    anti_patterns?: string[]
    tensions?: string[]
    honesty_boundaries?: string[]
    memory_anchors?: MemoryAnchor[]
    research_dimensions?: ResearchDimension[]
    response_profile?: Record<string, any>
    source_type?: string
    source_stats?: Record<string, any>
    memory_doc?: string | null
    persona_doc?: string | null
    combined_doc?: string | null
    created_at: string
    updated_at: string
}

export interface MentalModel {
    name: string
    summary?: string
    evidence?: string[]
    application?: string
    limitation?: string
    /** 三层筛选：跨话题复现 / 可外推 / 有区分度 */
    topic_span?: boolean
    extrapolates?: boolean
    distinctive?: boolean
}

export interface Heuristic {
    name: string
    rule?: string
    scenario?: string
    example?: string
}

export interface ExpressionDNA {
    sentence_pattern?: string
    vocabulary?: string
    rhythm?: string
    humor?: string
    certainty?: string
    citation_habit?: string
}

export interface MemoryAnchor {
    title: string
    detail?: string
}

/** 遇到需要事实的问题时优先查证的方向 */
export interface ResearchDimension {
    name: string
    why?: string
    points?: string[]
}

/** 克隆人格的对话记忆 */
export interface PersonaSessionNote {
    id: number
    personality_id: string
    session_id: string
    summary: string
    mood: string
    key_points: string[]
    next_topics: string[]
    message_count: number
    created_at: string | null
}

export interface SceneReply {
    persona_id: string
    name: string
    content: string
    tone?: string
}

export interface PersonalityCreate {
    id: string
    name: string
    description: string
    traits: string[]
    speaking_style: string
    icon?: string
    mental_models?: MentalModel[]
    heuristics?: Heuristic[]
    expression_dna?: ExpressionDNA
    values?: string[]
    anti_patterns?: string[]
    tensions?: string[]
    honesty_boundaries?: string[]
    memory_anchors?: MemoryAnchor[]
    research_dimensions?: ResearchDimension[]
    response_profile?: Record<string, any>
    source_type?: string
    source_stats?: Record<string, any>
    memory_doc?: string
    persona_doc?: string
    combined_doc?: string
}

export interface PersonalityUpdate {
    name?: string
    description?: string
    traits?: string[]
    speaking_style?: string
    icon?: string
    is_active?: boolean
    mental_models?: MentalModel[]
    heuristics?: Heuristic[]
    expression_dna?: ExpressionDNA
    values?: string[]
    anti_patterns?: string[]
    tensions?: string[]
    honesty_boundaries?: string[]
    memory_anchors?: MemoryAnchor[]
    research_dimensions?: ResearchDimension[]
    response_profile?: Record<string, any>
    source_type?: string
    source_stats?: Record<string, any>
    memory_doc?: string
    persona_doc?: string
    combined_doc?: string
}

export interface CorpusStats {
    platform?: string
    message_count?: number
    target_message_count?: number
    user_message_count?: number
    speakers?: string[]
    style_tags?: string[]
    session_count?: number
    top_particles?: string[]
    first_timestamp?: string | null
    last_timestamp?: string | null
    [key: string]: any
}

export interface AnalyzeResult {
    /** 给人看的分析报告 */
    report: string
    /** 给模型看的证据底稿：统计 + 原话 + 会话片段 */
    digest: string
    stats: CorpusStats
    warnings: string[]
}

export interface GenerateResult {
    /** 已映射的人格草稿字段 */
    draft: Record<string, any>
    /** 校验发现的问题；非空时可让用户先修改再保存 */
    problems: string[]
    /** 已映射成性格字段，可直接用于创建 */
    payload: PersonalityCreate
    /** 关系记忆文档 */
    memory_document: string
    /** 五层人格文档 */
    persona_document: string
    /** 拼接后的完整档案 */
    combined_document: string
}

export interface PersonaVersion {
    id: number
    personality_id: string
    version: number
    action: string
    note: string
    created_at: string | null
}

export interface QualityReport {
    total: number
    grade: 'A' | 'B' | 'C' | 'D'
    dimensions: Record<string, number>
    detail: Record<string, number>
    suggestions: string[]
}

const API_BASE = '/api/personalities'
const CLONE_BASE = '/api/persona-clone'

const CJK_PATTERN = /[\u4e00-\u9fff]/

/** 非中文界面不直接展示服务端中文详情，退回当前语言的兜底文案 */
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

async function readError(response: Response, fallback: string): Promise<string> {
    try {
        return extractErrorMessage(await response.json(), fallback)
    } catch {
        return fallback
    }
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

    /** 创建自定义性格 */
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
            const error = await response.json()
            throw new Error(error.detail || 'Failed to update personality')
        }
        return response.json()
    },

    /** 删除性格（仅限自定义性格） */
    async delete(id: string): Promise<void> {
        const response = await fetch(`${API_BASE}/${id}`, {
            method: 'DELETE',
        })
        if (!response.ok) {
            const error = await response.json()
            throw new Error(error.detail || 'Failed to delete personality')
        }
    },

    /** 复制性格 */
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

/** 人格克隆流程 API：上传语料、解析统计、生成草稿三个独立接口 */
export const personaCloneApi = {
    /** 上传语料文件，返回工作区内的相对路径 */
    async upload(file: File): Promise<{ path: string; filename: string; size: number }> {
        const response = await fetch(`${CLONE_BASE}/upload`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/octet-stream',
                'X-File-Name': encodeURIComponent(file.name || 'corpus'),
                'X-File-Size': String(file.size || 0),
            },
            body: file,
        })
        if (!response.ok) {
            const error = await response.json().catch(() => ({}))
            throw new Error(extractErrorMessage(error, t('settings.persona.clone.errors.uploadFailed')))
        }
        return response.json()
    },

    /** 把上传文件或粘贴文本解析成分析报告 */
    async analyze(params: {
        paths?: string[]
        pastedText?: string
        customPattern?: string
        target?: string
        targetAliases?: string
        selfName?: string
        sessionGapMinutes?: number
    }): Promise<AnalyzeResult> {
        const response = await fetch(`${CLONE_BASE}/analyze`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                paths: params.paths || [],
                pasted_text: params.pastedText || '',
                custom_pattern: params.customPattern || '',
                target: params.target || '',
                target_aliases: params.targetAliases || null,
                self_name: params.selfName || null,
                session_gap_minutes: params.sessionGapMinutes || 180,
            }),
        })
        if (!response.ok) {
            throw new Error(await readError(response, t('settings.persona.clone.errors.analyzeFailed')))
        }
        return response.json()
    },

    /** 调用模型生成人格档案 */
    async generate(params: {
        analysis: string
        name: string
        extraNote?: string
        provider?: string
        model?: string
        digest?: string
        stats?: CorpusStats
        intake?: Record<string, string>
    }): Promise<GenerateResult> {
        const response = await fetch(`${CLONE_BASE}/generate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                analysis: params.analysis,
                name: params.name,
                extra_note: params.extraNote || '',
                provider: params.provider || '',
                model: params.model || '',
                digest: params.digest || '',
                stats: params.stats || {},
                intake: params.intake || {},
            }),
        })
        if (!response.ok) {
            throw new Error(await readError(response, t('settings.persona.clone.errors.generateFailed')))
        }
        return response.json()
    },

    /** 列出人格的历史版本 */
    async versions(id: string): Promise<PersonaVersion[]> {
        const response = await fetch(`${CLONE_BASE}/${id}/versions`)
        if (!response.ok) {
            throw new Error(await readError(response, t('settings.persona.clone.errors.loadVersionsFailed')))
        }
        const data = await response.json()
        return Array.isArray(data?.versions) ? data.versions : []
    },

    /** 追加素材并合并进现有档案 */
    async append(id: string, params: {
        paths?: string[]
        pastedText?: string
        customPattern?: string
        target?: string
        selfName?: string
        provider?: string
        model?: string
        note?: string
    }): Promise<{ version: number; changes: string[]; conflicts: string[]; combined_document: string }> {
        const response = await fetch(`${CLONE_BASE}/${id}/append`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                paths: params.paths || [],
                pasted_text: params.pastedText || '',
                custom_pattern: params.customPattern || '',
                target: params.target || '',
                self_name: params.selfName || null,
                provider: params.provider || '',
                model: params.model || '',
                note: params.note || '',
            }),
        })
        if (!response.ok) {
            throw new Error(await readError(response, t('settings.persona.clone.errors.appendFailed')))
        }
        return response.json()
    },

    /** 按用户纠正更新档案 */
    async correct(id: string, params: {
        correction: string
        provider?: string
        model?: string
    }): Promise<{ version: number; layer: string; summary: string; changed_fields: string[] }> {
        const response = await fetch(`${CLONE_BASE}/${id}/correct`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                correction: params.correction,
                provider: params.provider || '',
                model: params.model || '',
            }),
        })
        if (!response.ok) {
            throw new Error(await readError(response, t('settings.persona.clone.errors.correctFailed')))
        }
        return response.json()
    },

    /** 回滚到指定版本 */
    async rollback(id: string, version: number): Promise<{ version: number; rolled_back_to: number }> {
        const response = await fetch(`${CLONE_BASE}/${id}/versions/${version}/rollback`, {
            method: 'POST',
        })
        if (!response.ok) {
            throw new Error(await readError(response, t('settings.persona.clone.errors.rollbackFailed')))
        }
        return response.json()
    },

    /** 静态质检 */
    async quality(id: string): Promise<QualityReport> {
        const response = await fetch(`${CLONE_BASE}/${id}/quality`)
        if (!response.ok) {
            throw new Error(await readError(response, t('settings.persona.clone.errors.qualityFailed')))
        }
        return response.json()
    },

    /** 列出这个人的对话记忆 */
    async sessionNotes(id: string): Promise<PersonaSessionNote[]> {
        const response = await fetch(`${CLONE_BASE}/${id}/session-notes`)
        if (!response.ok) {
            throw new Error(await readError(response, t('settings.persona.clone.errors.loadNotesFailed')))
        }
        const data = await response.json()
        return Array.isArray(data?.notes) ? data.notes : []
    },

    /** 按需总结一个会话 */
    async summarizeSession(id: string, params: {
        sessionId: string
        provider?: string
        model?: string
    }): Promise<{ note: PersonaSessionNote }> {
        const response = await fetch(`${CLONE_BASE}/${id}/session-notes`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: params.sessionId,
                provider: params.provider || '',
                model: params.model || '',
            }),
        })
        if (!response.ok) {
            throw new Error(await readError(response, t('settings.persona.clone.errors.summarizeFailed')))
        }
        return response.json()
    },

    /** 删除一条对话记忆 */
    async deleteSessionNote(id: string, noteId: number): Promise<void> {
        const response = await fetch(`${CLONE_BASE}/${id}/session-notes/${noteId}`, {
            method: 'DELETE',
        })
        if (!response.ok) {
            throw new Error(await readError(response, t('settings.persona.clone.errors.deleteNoteFailed')))
        }
    },

    /** 场景导演：让几个克隆人格轮流说话 */
    async sceneRound(params: {
        personaIds: string[]
        scene?: string
        history?: Array<{ speaker: string; content: string }>
        message?: string
        provider?: string
        model?: string
    }): Promise<{ replies: SceneReply[]; members: Array<{ id: string; name: string }> }> {
        const response = await fetch(`${CLONE_BASE}/scene/round`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                persona_ids: params.personaIds,
                scene: params.scene || '',
                history: params.history || [],
                message: params.message || '',
                provider: params.provider || '',
                model: params.model || '',
            }),
        })
        if (!response.ok) {
            throw new Error(await readError(response, t('settings.persona.clone.errors.sceneFailed')))
        }
        return response.json()
    },
}
