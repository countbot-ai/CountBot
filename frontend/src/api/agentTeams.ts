/**
 * Agent Teams API — CRUD client for user-defined multi-agent workflow templates.
 */

import apiClient from './client'

const API_BASE = '/agent-teams'

// ── Types ────────────────────────────────────────────────────────────────────

export interface AgentDefinition {
    id: string
    role: string
    /** Persistent system-level persona injected as the LLM system message. */
    system_prompt?: string
    task: string
    perspective?: string
    depends_on: string[]
    /** Optional execution condition (graph mode only) */
    condition?: {
        type: 'output_contains' | 'output_not_contains'
        node: string
        text: string
    }
}

export interface AgentTeam {
    id: string
    name: string
    description?: string
    mode: 'pipeline' | 'graph' | 'council'
    agents: AgentDefinition[]
    is_active: boolean
    cross_review: boolean
    enable_skills: boolean
    use_custom_model: boolean
    created_at: string
    updated_at: string
}

export interface TeamModelConfig {
    provider?: string
    model?: string
    api_mode?: 'chat_completions'
    temperature?: number
    max_tokens?: number
    max_iterations?: number
    thinking_enabled?: boolean
    api_key?: string
    api_base?: string
}

export interface TeamModelConfigResponse {
    team_id: string
    use_custom_model: boolean
    model_settings: TeamModelConfig
    global_defaults: TeamModelConfig
}

export interface AgentTeamCreate {
    name: string
    description?: string
    mode: 'pipeline' | 'graph' | 'council'
    agents: AgentDefinition[]
    is_active?: boolean
    cross_review?: boolean
    enable_skills?: boolean
}

export interface AgentTeamUpdate {
    name?: string
    description?: string
    mode?: 'pipeline' | 'graph' | 'council'
    agents?: AgentDefinition[]
    is_active?: boolean
    cross_review?: boolean
    enable_skills?: boolean
}

// ── API object ───────────────────────────────────────────────────────────────

export const agentTeamsApi = {
    list(): Promise<AgentTeam[]> {
        return apiClient.get(`${API_BASE}/`)
    },

    get(id: string): Promise<AgentTeam> {
        return apiClient.get(`${API_BASE}/${id}`)
    },

    create(data: AgentTeamCreate): Promise<AgentTeam> {
        return apiClient.post(`${API_BASE}/`, data)
    },

    update(id: string, data: AgentTeamUpdate): Promise<AgentTeam> {
        return apiClient.put(`${API_BASE}/${id}`, data)
    },

    delete(id: string): Promise<void> {
        return apiClient.delete(`${API_BASE}/${id}`)
    },

    // ── Team Model Configuration ─────────────────────────────────────────────

    getConfig(id: string): Promise<TeamModelConfigResponse> {
        return apiClient.get(`${API_BASE}/${id}/config`)
    },

    updateConfig(id: string, config: TeamModelConfig): Promise<{ success: boolean; team_id: string; message: string }> {
        return apiClient.put(`${API_BASE}/${id}/config`, config)
    },

    resetConfig(id: string): Promise<{ success: boolean; team_id: string; message: string }> {
        return apiClient.delete(`${API_BASE}/${id}/config`)
    },
}
