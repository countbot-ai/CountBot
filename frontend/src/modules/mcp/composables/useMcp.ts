import { ref, computed } from 'vue'
import { mcpApi } from '@/modules/mcp/services/mcpApi'
import type { McpOverviewData, McpRegistryData, McpServerConfig, McpServerTestResult } from '@/modules/mcp/types'
import { createEmptyServer, cloneServer } from '@/modules/mcp/types'

export function useMcp() {
    const loading = ref(false)
    const saving = ref(false)
    const enabled = ref(false)
    const overview = ref<McpOverviewData | null>(null)
    const registry = ref<McpRegistryData>({ version: 1, servers: [] })
    const testResults = ref<Record<string, McpServerTestResult>>({})

    const editingServerId = ref<string | null>(null)
    const editingDraft = ref<McpServerConfig | null>(null)
    const isNewServer = ref(false)

    const summary = computed(() => overview.value?.summary ?? {
        total_servers: 0,
        enabled_servers: 0,
        connected_servers: 0,
        mcp_tool_count: 0,
    })

    const serverStatusMap = computed(() => {
        const map: Record<string, { running: boolean; transport: string; tool_count: number | null; tools?: string[]; error?: string }> = {}
        if (overview.value?.servers) {
            for (const s of overview.value.servers) {
                map[s.id] = { running: s.running, transport: s.transport, tool_count: s.tool_count, tools: s.tools, error: s.last_error }
            }
        }
        return map
    })

    async function refreshAll() {
        loading.value = true
        try {
            const [overviewData, registryData] = await Promise.all([
                mcpApi.getOverview(),
                mcpApi.getRegistry(),
            ])
            overview.value = overviewData
            enabled.value = overviewData.enabled
            registry.value = registryData
        } catch (e) {
            console.error('Failed to load MCP data:', e)
        } finally {
            loading.value = false
        }
    }

    async function toggleMcp(value: boolean) {
        try {
            const result = await mcpApi.toggle(value)
            if (result.success) {
                enabled.value = value
            }
        } catch (e) {
            console.error('Failed to toggle MCP:', e)
        }
    }

    async function saveRegistry(data: McpRegistryData) {
        saving.value = true
        try {
            registry.value = await mcpApi.updateRegistry(data)
        } catch (e) {
            console.error('Failed to save MCP registry:', e)
            throw e
        } finally {
            saving.value = false
        }
    }

    async function testServer(server: McpServerConfig) {
        const key = server.id || server.name || 'unknown'
        try {
            testResults.value[key] = await mcpApi.testServer(server)
        } catch (e: any) {
            testResults.value[key] = {
                success: false,
                message: e?.message || 'Test failed',
            }
        }
    }

    function addServer() {
        const server = createEmptyServer()
        server.id = `srv_${Date.now()}`
        server.name = ''
        editingServerId.value = server.id
        editingDraft.value = server
        isNewServer.value = true
    }

    function startEdit(server: McpServerConfig) {
        editingServerId.value = server.id
        editingDraft.value = cloneServer(server)
        isNewServer.value = false
    }

    function cancelEdit() {
        editingServerId.value = null
        editingDraft.value = null
        isNewServer.value = false
    }

    function commitEditLocally() {
        if (!editingDraft.value) return
        const draft = editingDraft.value
        const idx = registry.value.servers.findIndex(s => s.id === draft.id)
        if (idx >= 0) {
            registry.value.servers[idx] = cloneServer(draft)
        } else if (isNewServer.value) {
            registry.value.servers.push(cloneServer(draft))
        }
        editingServerId.value = null
        editingDraft.value = null
        isNewServer.value = false
    }

    function removeServer(index: number) {
        const removed = registry.value.servers.splice(index, 1)
        if (removed.length && editingServerId.value === removed[0].id) {
            cancelEdit()
        }
    }

    async function importConfig(jsonStr: string, merge: boolean = true) {
        try {
            const data = JSON.parse(jsonStr)
            const result = await mcpApi.importConfig(data, 'claude_desktop', merge)
            if (result.success) {
                await refreshAll()
            }
            return result
        } catch (e: any) {
            return { success: false, message: e?.message || 'Invalid JSON' }
        }
    }

    async function exportConfig() {
        try {
            const data = await mcpApi.exportConfig('claude_desktop')
            return JSON.stringify(data, null, 2)
        } catch (e) {
            console.error('Failed to export MCP config:', e)
            return null
        }
    }

    async function reconnect(serverId?: string) {
        try {
            return await mcpApi.reconnect(serverId)
        } catch (e) {
            console.error('Failed to reconnect:', e)
            return { success: false }
        }
    }

    async function startServer(serverId: string) {
        try {
            return await mcpApi.startServer(serverId)
        } catch (e) {
            console.error('Failed to start server:', e)
            return { success: false }
        }
    }

    async function stopServer(serverId: string) {
        try {
            return await mcpApi.stopServer(serverId)
        } catch (e) {
            console.error('Failed to stop server:', e)
            return { success: false }
        }
    }

    async function getServerStatus(serverId: string) {
        try {
            return await mcpApi.getServerStatus(serverId)
        } catch (e) {
            console.error('Failed to get server status:', e)
            return { success: false }
        }
    }

    return {
        loading,
        saving,
        enabled,
        overview,
        registry,
        testResults,
        summary,
        serverStatusMap,
        editingServerId,
        editingDraft,
        isNewServer,
        refreshAll,
        toggleMcp,
        saveRegistry,
        testServer,
        addServer,
        startEdit,
        cancelEdit,
        commitEditLocally,
        removeServer,
        importConfig,
        exportConfig,
        reconnect,
        startServer,
        stopServer,
        getServerStatus,
    }
}
