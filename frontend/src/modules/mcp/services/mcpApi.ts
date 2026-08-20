import apiClient from '@/api/client'
import type { McpRegistryData, McpServerConfig, McpServerTestResult, McpOverviewData } from '@/modules/mcp/types'

export const mcpApi = {
    getOverview: async (): Promise<McpOverviewData> => {
        const res = await apiClient.get('/mcp/overview')
        return res.data ?? res
    },

    getRegistry: async (): Promise<McpRegistryData> => {
        const res = await apiClient.get('/mcp/registry')
        return res.data ?? res
    },

    updateRegistry: async (data: McpRegistryData): Promise<McpRegistryData> => {
        const res = await apiClient.put('/mcp/registry', data)
        return res.data ?? res
    },

    testServer: async (server: McpServerConfig): Promise<McpServerTestResult> => {
        const res = await apiClient.post('/mcp/test', { server })
        return res.data ?? res
    },

    toggle: async (enabled: boolean): Promise<{ success: boolean; enabled: boolean }> => {
        const res = await apiClient.post('/mcp/toggle', { enabled })
        return res.data ?? res
    },

    importConfig: async (data: any, format: string = 'claude_desktop', merge: boolean = true): Promise<any> => {
        const res = await apiClient.post('/mcp/import', { data, format, merge })
        return res.data ?? res
    },

    exportConfig: async (format: string = 'claude_desktop'): Promise<any> => {
        const res = await apiClient.get('/mcp/export', { params: { format } })
        return res.data ?? res
    },

    reconnect: async (serverId?: string): Promise<{ success: boolean; server_id?: string }> => {
        const res = await apiClient.post('/mcp/reconnect', { server_id: serverId || null })
        return res.data ?? res
    },

    startServer: async (serverId: string): Promise<{ success: boolean; server_id?: string; message?: string }> => {
        const res = await apiClient.post('/mcp/start', { server_id: serverId })
        return res.data ?? res
    },

    stopServer: async (serverId: string): Promise<{ success: boolean; server_id?: string; message?: string }> => {
        const res = await apiClient.post('/mcp/stop', { server_id: serverId })
        return res.data ?? res
    },

    getServerStatus: async (serverId: string): Promise<{ success: boolean; server_id?: string; connected?: boolean; transport?: string; tool_count?: number; message?: string }> => {
        const res = await apiClient.get(`/mcp/status/${serverId}`)
        return res.data ?? res
    },
}
