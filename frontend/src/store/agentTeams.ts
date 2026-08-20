/**
 * Agent Teams — Pinia store for user-defined multi-agent workflow templates.
 */

import { defineStore } from 'pinia'
import { ref } from 'vue'
import { agentTeamsApi, type AgentTeam, type AgentTeamCreate, type AgentTeamUpdate } from '@/api/agentTeams'

export { type AgentTeam } from '@/api/agentTeams'

export const useAgentTeamsStore = defineStore('agentTeams', () => {
    // ── State ────────────────────────────────────────────────────────────────
    const teams = ref<AgentTeam[]>([])
    const loading = ref(false)
    const error = ref<string | null>(null)

    // ── Actions ──────────────────────────────────────────────────────────────

    async function loadTeams() {
        loading.value = true
        error.value = null
        try {
            teams.value = await agentTeamsApi.list()
        } catch (err: any) {
            error.value = err.message || 'Failed to load agent teams'
        } finally {
            loading.value = false
        }
    }

    async function createTeam(data: AgentTeamCreate): Promise<AgentTeam> {
        try {
            const team = await agentTeamsApi.create(data)
            teams.value.unshift(team)
            return team
        } catch (err: any) {
            // 处理重复名称错误
            if (err.message && err.message.includes('已存在')) {
                error.value = `团队名称 "${data.name}" 已存在，请使用其他名称`
                throw new Error(error.value)
            }
            error.value = err.message || 'Failed to create agent team'
            throw err
        }
    }

    async function updateTeam(id: string, data: AgentTeamUpdate): Promise<AgentTeam> {
        try {
            const updated = await agentTeamsApi.update(id, data)
            const idx = teams.value.findIndex(t => t.id === id)
            if (idx !== -1) teams.value[idx] = updated
            return updated
        } catch (err: any) {
            // 处理重复名称错误
            if (err.message && err.message.includes('已存在')) {
                error.value = `团队名称 "${data.name}" 已存在，请使用其他名称`
                throw new Error(error.value)
            }
            error.value = err.message || 'Failed to update agent team'
            throw err
        }
    }

    async function deleteTeam(id: string): Promise<void> {
        try {
            await agentTeamsApi.delete(id)
            const idx = teams.value.findIndex(t => t.id === id)
            if (idx !== -1) teams.value.splice(idx, 1)
        } catch (err: any) {
            error.value = err.message || 'Failed to delete agent team'
            throw err
        }
    }

    return {
        // State
        teams,
        loading,
        error,

        // Actions
        loadTeams,
        createTeam,
        updateTeam,
        deleteTeam,
    }
})

