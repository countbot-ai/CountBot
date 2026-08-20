/**
 * Tools 状态管理
 */

import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import { toolsAPI } from '@/api'

export interface Tool {
    name: string
    description: string
    parameters: Record<string, any>
}

export interface ToolExecution {
    id: string
    tool: string
    arguments: Record<string, any>
    result: string
    success: boolean
    error: string | null
    timestamp: Date | string
    duration: number | null
}

const STORAGE_KEY = 'CountBot_tool_history'
const MAX_HISTORY_SIZE = 100 // 最多保存 100 条记录

// 从 localStorage 加载历史记录
function loadHistoryFromStorage(): ToolExecution[] {
    try {
        const stored = localStorage.getItem(STORAGE_KEY)
        if (stored) {
            const parsed = JSON.parse(stored)
            // 确保 timestamp 是 Date 对象
            return parsed.map((item: any) => ({
                ...item,
                timestamp: new Date(item.timestamp)
            }))
        }
    } catch (error) {
        console.error('Failed to load tool history from storage:', error)
    }
    return []
}

// 保存历史记录到 localStorage
function saveHistoryToStorage(history: ToolExecution[]) {
    try {
        // 只保存最近的记录
        const toSave = history.slice(0, MAX_HISTORY_SIZE)
        localStorage.setItem(STORAGE_KEY, JSON.stringify(toSave))
    } catch (error) {
        console.error('Failed to save tool history to storage:', error)
    }
}

export const useToolsStore = defineStore('tools', () => {
    // State
    const tools = ref<Tool[]>([])
    const history = ref<ToolExecution[]>([]) // 不再从 localStorage 加载
    const loading = ref(false)
    const executing = ref(false)
    const error = ref<string | null>(null)

    // Computed
    const sortedHistory = computed(() => 
        [...history.value].sort((a, b) => {
            const timeA = a.timestamp instanceof Date ? a.timestamp.getTime() : new Date(a.timestamp).getTime()
            const timeB = b.timestamp instanceof Date ? b.timestamp.getTime() : new Date(b.timestamp).getTime()
            return timeB - timeA
        })
    )

    const executionStats = computed(() => {
        const total = history.value.length
        const successful = history.value.filter(h => h.success).length
        const failed = total - successful
        const successRate = total > 0 ? Math.round((successful / total) * 100) : 0
        
        return {
            total,
            successful,
            failed,
            successRate
        }
    })

    // Actions

    /**
     * 加载工具列表
     */
    async function loadTools() {
        loading.value = true
        error.value = null
        try {
            const response = await toolsAPI.list()
            tools.value = response.tools || []
        } catch (err: any) {
            error.value = err.message || 'Failed to load tools'
            throw err
        } finally {
            loading.value = false
        }
    }

    /**
     * 执行工具
     */
    async function executeTool(toolName: string, parameters: Record<string, any>) {
        executing.value = true
        error.value = null
        try {
            const response = await toolsAPI.execute({
                tool: toolName,
                arguments: parameters
            })

            // 添加到历史记录
            const execution: ToolExecution = {
                id: Date.now().toString(),
                tool: toolName,
                arguments: parameters,
                result: response.result,
                success: response.success,
                error: null,
                timestamp: new Date(),
                duration: null
            }
            history.value.unshift(execution)

            return response
        } catch (err: any) {
            error.value = err.message || 'Failed to execute tool'

            // 添加失败记录
            const execution: ToolExecution = {
                id: Date.now().toString(),
                tool: toolName,
                arguments: parameters,
                result: err.message,
                success: false,
                error: err.message,
                timestamp: new Date(),
                duration: null
            }
            history.value.unshift(execution)

            throw err
        } finally {
            executing.value = false
        }
    }

    /**
     * 从数据库加载当前会话的工具调用历史
     */
    async function loadSessionHistory(sessionId: string) {
        loading.value = true
        error.value = null
        try {
            const response = await toolsAPI.getConversations({ session_id: sessionId })
            // 转换为 ToolExecution 格式
            history.value = response.conversations.map(conv => ({
                id: conv.id,
                tool: conv.tool_name,
                arguments: conv.arguments,
                result: conv.result || conv.error || '',
                success: !conv.error,
                error: conv.error || null,
                timestamp: new Date(conv.timestamp),
                duration: conv.duration_ms || null
            }))
        } catch (err: any) {
            error.value = err.message || 'Failed to load session history'
            console.error('Failed to load session history:', err)
        } finally {
            loading.value = false
        }
    }

    /**
     * 清除历史记录（已废弃，保留用于兼容性）
     */
    function clearHistory() {
        history.value = []
    }

    /**
     * 添加工具执行记录（已废弃，保留用于兼容性）
     */
    function addToolExecution(execution: Omit<ToolExecution, 'id'>) {
        // 不再添加到本地，数据库会自动记录
        console.warn('addToolExecution is deprecated, tool calls are now stored in database')
    }

    /**
     * 更新工具执行记录（已废弃，保留用于兼容性）
     */
    function updateToolExecution(id: string, updates: Partial<ToolExecution>) {
        // 不再更新本地，数据库会自动更新
        console.warn('updateToolExecution is deprecated, tool calls are now stored in database')
    }

    /**
     * 删除历史记录项（已废弃，保留用于兼容性）
     */
    function deleteHistoryItem(id: string) {
        console.warn('deleteHistoryItem is deprecated')
    }

    return {
        // State
        tools,
        history,
        loading,
        executing,
        error,

        // Computed
        sortedHistory,
        executionStats,

        // Actions
        loadTools,
        executeTool,
        loadSessionHistory,
        addToolExecution,
        updateToolExecution,
        clearHistory,
        deleteHistoryItem
    }
})
