/**
 * Chat 状态管理
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { chatAPI, stopAPI, type Session as ApiSession, type Message as ApiMessage } from '@/api'

export interface Session {
    id: string
    name: string
    createdAt: string
    updatedAt: string
}

export interface Message {
    id: number
    sessionId: string
    role: 'user' | 'assistant' | 'system'
    content: string
    createdAt: string
    toolCalls?: Array<{
        id: string
        name: string
        arguments: Record<string, any>
        result?: string | null
        error?: string | null
        status: string
        duration?: number | null
    }>
}

export const useChatStore = defineStore('chat', () => {
    // State
    const sessions = ref<Session[]>([])
    const currentSessionId = ref<string | null>(null)
    const isLoadingSessions = ref(false)
    const isCreatingSession = ref(false)
    const isDeletingSession = ref(false)
    const isRenamingSession = ref(false)
    const isStoppingTask = ref(false)

    // Computed
    const currentSession = computed(() => {
        if (!currentSessionId.value) return null
        return sessions.value.find(s => s.id === currentSessionId.value) || null
    })

    const sortedSessions = computed(() => [...sessions.value].sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()))

    // Actions

    /**
     * 加载会话列表
     */
    async function loadSessions() {
        isLoadingSessions.value = true
        try {
            const response = await chatAPI.getSessions()
            sessions.value = response.map((s: ApiSession) => ({
                id: s.id,
                name: s.name,
                createdAt: s.created_at,
                updatedAt: s.updated_at
            }))
        } catch (error) {
            console.error('Failed to load sessions:', error)
            throw error
        } finally {
            isLoadingSessions.value = false
        }
    }

    /**
     * 创建新会话
     */
    async function createSession(name?: string) {
        isCreatingSession.value = true
        try {
            const sessionName = name || `New Chat ${new Date().toLocaleString()}`
            const response = await chatAPI.createSession(sessionName)

            const newSession: Session = {
                id: response.id,
                name: response.name,
                createdAt: response.created_at,
                updatedAt: response.updated_at
            }

            sessions.value.unshift(newSession)
            currentSessionId.value = newSession.id

            return newSession
        } catch (error) {
            console.error('Failed to create session:', error)
            throw error
        } finally {
            isCreatingSession.value = false
        }
    }

    /**
     * 删除会话
     */
    async function deleteSession(sessionId: string) {
        isDeletingSession.value = true
        try {
            await chatAPI.deleteSession(sessionId)

            const index = sessions.value.findIndex(s => s.id === sessionId)
            if (index !== -1) {
                sessions.value.splice(index, 1)
            }

            // If deleted session was current, switch to another
            if (currentSessionId.value === sessionId) {
                if (sessions.value.length > 0) {
                    currentSessionId.value = sessions.value[0].id
                } else {
                    currentSessionId.value = null
                }
            }
        } catch (error) {
            console.error('Failed to delete session:', error)
            throw error
        } finally {
            isDeletingSession.value = false
        }
    }

    /**
     * 重命名会话
     */
    async function renameSession(sessionId: string, newName: string) {
        isRenamingSession.value = true
        try {
            const response = await chatAPI.updateSession(sessionId, newName)

            const index = sessions.value.findIndex(s => s.id === sessionId)
            if (index !== -1) {
                sessions.value[index] = {
                    id: response.id,
                    name: response.name,
                    createdAt: response.created_at,
                    updatedAt: response.updated_at
                }
            }
        } catch (error) {
            console.error('Failed to rename session:', error)
            throw error
        } finally {
            isRenamingSession.value = false
        }
    }

    /**
     * 切换当前会话
     */
    function switchSession(sessionId: string) {
        const session = sessions.value.find(s => s.id === sessionId)
        if (session) {
            currentSessionId.value = sessionId
        }
    }

    /**
     * 加载会话消息
     */
    async function loadMessages(sessionId: string, limit?: number, offset?: number): Promise<Message[]> {
        try {
            const response = await chatAPI.getMessages(sessionId, { limit, offset })

            return response.map((m: ApiMessage) => ({
                id: m.id,
                sessionId: m.session_id,
                role: m.role,
                content: m.content,
                createdAt: m.created_at,
                toolCalls: m.tool_calls  // 传递 tool_calls
            }))
        } catch (error) {
            console.error('Failed to load messages:', error)
            throw error
        }
    }

    /**
     * 清空会话消息
     */
    async function clearMessages(sessionId: string) {
        try {
            await chatAPI.clearMessages(sessionId)
        } catch (error) {
            console.error('Failed to clear messages:', error)
            throw error
        }
    }

    /**
     * 删除单条消息
     */
    async function deleteMessage(sessionId: string, messageId: number) {
        try {
            await chatAPI.deleteMessage(sessionId, messageId)
        } catch (error) {
            console.error('Failed to delete message:', error)
            throw error
        }
    }

    /**
     * 停止当前会话的任务
     */
    async function stopCurrentTask() {
        if (!currentSessionId.value) {
            throw new Error('No active session')
        }

        isStoppingTask.value = true
        try {
            const response = await stopAPI.stopTask(currentSessionId.value)
            return response
        } catch (error) {
            console.error('Failed to stop task:', error)
            throw error
        } finally {
            isStoppingTask.value = false
        }
    }

    return {
        // State
        sessions,
        currentSessionId,
        isLoadingSessions,
        isCreatingSession,
        isDeletingSession,
        isRenamingSession,
        isStoppingTask,

        // Computed
        currentSession,
        sortedSessions,

        // Actions
        loadSessions,
        createSession,
        deleteSession,
        renameSession,
        switchSession,
        loadMessages,
        clearMessages,
        deleteMessage,
        stopCurrentTask
    }
})
