/**
 * API 端点定义
 * 
 * 包含所有后端 API 的类型定义和调用方法
 */

import apiClient from './client'

// ============================================================================
// 类型定义
// ============================================================================

// Chat API Types
export interface SendMessageRequest {
    session_id: string
    message: string
    attachments?: string[]
}

export interface SendMessageResponse {
    message_id: string
    streaming: boolean
}

export interface Session {
    id: string
    name: string
    created_at: string
    updated_at: string
    summary?: string | null
    summary_updated_at?: string | null
}

export interface ToolCall {
    id: string
    name: string
    arguments: Record<string, any>
    result?: string | null
    error?: string | null
    status: string
    duration?: number | null
}

export interface Message {
    id: number
    session_id: string
    role: 'user' | 'assistant' | 'system'
    content: string
    created_at: string
    tool_calls?: ToolCall[]
}

export interface CreateSessionRequest {
    name: string
}

export interface UpdateSessionRequest {
    name: string
}

// Settings API Types
export interface ProviderMetadata {
    id: string
    name: string
    defaultApiBase?: string
    defaultModel?: string
    default_api_base?: string
    default_model?: string
}

export interface ProviderConfig {
    enabled: boolean
    api_key?: string
    api_base?: string
}

export interface ModelConfig {
    provider: string
    model: string
    temperature: number
    max_tokens: number
    max_iterations: number
}

export interface SecurityConfig {
    api_key_encryption_enabled: boolean
    dangerous_commands_blocked: boolean
    custom_deny_patterns: string[]
    command_whitelist_enabled: boolean
    custom_allow_patterns: string[]
    audit_log_enabled: boolean
    command_timeout: number
    max_output_length: number
    restrict_to_workspace: boolean
}

export interface HeartbeatConfig {
    enabled: boolean
    channel: string
    chat_id: string
    schedule: string
    idle_threshold_hours: number
    quiet_start: number
    quiet_end: number
}

export interface PersonaConfig {
    ai_name: string
    user_name: string
    personality: string
    custom_personality: string
    max_history_messages: number
    heartbeat?: HeartbeatConfig
}

export interface WorkspaceConfig {
    path: string
}

export interface UpdateSettingsRequest {
    providers?: Record<string, Partial<ProviderConfig>>
    model?: Partial<ModelConfig>
    workspace?: Partial<WorkspaceConfig>
    security?: Partial<SecurityConfig>
    persona?: Partial<PersonaConfig>
}

export interface Settings {
    providers: Record<string, ProviderConfig>
    model: ModelConfig
    workspace: WorkspaceConfig
    security: SecurityConfig
    persona: PersonaConfig
}

export interface TestConnectionRequest {
    provider: string
    api_key: string
    api_base?: string
    model?: string
}

export interface TestConnectionResponse {
    success: boolean
    message?: string
    error?: string
}

// Tools API Types
export interface ToolDefinition {
    name: string
    description: string
    parameters: Record<string, any>
}

export interface ExecuteToolRequest {
    tool: string
    arguments: Record<string, any>
}

export interface ExecuteToolResponse {
    result: string
    success: boolean
    error?: string
}

// Memory API Types
export interface MemoryContent {
    content: string
}

export interface UpdateMemoryRequest {
    content: string
}

export interface UpdateMemoryResponse {
    success: boolean
    message?: string
}

export interface SearchRequest {
    keywords: string
    max_results?: number
}

export interface SearchResponse {
    results: string
    total: number
}

// Skills API Types
export interface SkillInfo {
    name: string
    description: string
    enabled: boolean
    autoLoad: boolean
    requirements: string[]
    source?: 'workspace' | 'builtin'
}

export interface SkillDetail extends SkillInfo {
    content: string
}

export interface ToggleSkillRequest {
    enabled: boolean
}

export interface ToggleSkillResponse {
    success: boolean
    message?: string
}

export interface CreateSkillRequest {
    name: string
    description: string
    content: string
    autoLoad: boolean
    requirements: string[]
}

export interface UpdateSkillRequest {
    description: string
    content: string
    autoLoad: boolean
    requirements: string[]
}

export interface DeleteSkillResponse {
    success: boolean
    message: string
}

// Cron API Types
export interface CronJob {
    id: string
    name: string
    schedule: string
    message: string
    enabled: boolean
    channel?: string | null
    chat_id?: string | null
    deliver_response: boolean
    last_run?: string | null
    next_run?: string | null
    last_status?: string | null
    last_error?: string | null
    run_count: number
    error_count: number
    created_at: string
}

export interface CronJobDetail extends CronJob {
    last_response?: string | null
    last_error?: string | null
}

export interface CreateCronJobRequest {
    name: string
    schedule: string
    message: string
    enabled?: boolean
    channel?: string | null
    chat_id?: string | null
    deliver_response?: boolean
}

export interface UpdateCronJobRequest {
    name?: string
    schedule?: string
    message?: string
    enabled?: boolean
    channel?: string | null
    chat_id?: string | null
    deliver_response?: boolean
}

export interface ExecuteCronJobResponse {
    success: boolean
    message?: string
}

// Tasks API Types
export interface Task {
    id: string
    label: string
    status: 'running' | 'completed' | 'failed'
    progress: number
    result?: string
    created_at: string
    completed_at?: string
}

export interface CreateTaskRequest {
    task: string
    label: string
}

export interface CreateTaskResponse {
    task_id: string
}

// ============================================================================
// API 端点
// ============================================================================

// System Info Types
export interface SystemInfo {
    api_url: string
    version: string
    python_version: string
    os: string
    arch: string
    pid: number
    uptime_start: string
}

/**
 * Health Check API
 */
export const healthAPI = {
    check: (): Promise<{ status: string }> =>
        apiClient.get('/health'),
}

/**
 * Auth API
 */
export const authAPI = {
    status: (): Promise<{ is_local: boolean; auth_enabled: boolean; authenticated: boolean; remote_access_enabled: boolean }> =>
        apiClient.get('/auth/status'),

    setup: (data: { username: string; password: string }): Promise<{ success: boolean; token: string }> =>
        apiClient.post('/auth/setup', data),

    login: (data: { username: string; password: string }): Promise<{ success: boolean; token: string }> =>
        apiClient.post('/auth/login', data),

    logout: (): Promise<{ success: boolean }> =>
        apiClient.post('/auth/logout'),

    changePassword: (data: { old_password: string; new_password: string }): Promise<{ success: boolean }> =>
        apiClient.post('/auth/change-password', data),
}

/**
 * System Info API
 */
export const systemAPI = {
    getInfo: (): Promise<SystemInfo> =>
        apiClient.get('/system/info'),
}

/**
 * Chat API
 */
export const chatAPI = {
    sendMessage: (data: SendMessageRequest): Promise<SendMessageResponse> =>
        apiClient.post('/chat/send', data),

    getSessions: (params?: { limit?: number; offset?: number }): Promise<Session[]> =>
        apiClient.get('/chat/sessions', { params }),

    createSession: (name: string): Promise<Session> =>
        apiClient.post('/chat/sessions', null, { params: { name } }),

    updateSession: (id: string, name: string): Promise<Session> =>
        apiClient.put(`/chat/sessions/${id}`, { name }),

    deleteSession: (id: string): Promise<{ success: boolean }> =>
        apiClient.delete(`/chat/sessions/${id}`),

    getMessages: (sessionId: string, params?: { limit?: number; offset?: number }): Promise<Message[]> =>
        apiClient.get(`/chat/sessions/${sessionId}/messages`, { params }),

    deleteMessage: (sessionId: string, messageId: number): Promise<{ success: boolean; message: string }> =>
        apiClient.delete(`/chat/sessions/${sessionId}/messages/${messageId}`),

    clearMessages: (sessionId: string): Promise<{ success: boolean }> =>
        apiClient.delete(`/chat/sessions/${sessionId}/messages`),

    // 会话总结 API
    getSession: (sessionId: string): Promise<Session> =>
        apiClient.get(`/chat/sessions/${sessionId}`),

    updateSessionSummary: (sessionId: string, summary: string): Promise<{
        success: boolean
        session_id: string
        summary: string
        updated_at: string
    }> =>
        apiClient.put(`/chat/sessions/${sessionId}/summary`, { summary }),

    deleteSessionSummary: (sessionId: string): Promise<{
        success: boolean
        session_id: string
    }> =>
        apiClient.delete(`/chat/sessions/${sessionId}/summary`),

    // 自动总结会话并保存到记忆
    summarizeSessionToMemory: (sessionId: string): Promise<{
        success: boolean
        summary: string
        message?: string
    }> =>
        apiClient.post(`/chat/sessions/${sessionId}/summarize`),

    exportSessionContext: (sessionId: string): Promise<{
        session_id: string
        session_name: string
        system_prompt: string
        messages: Array<{
            id: number
            role: string
            content: string
            created_at: string
        }>
        tool_history?: Array<{
            tool: string
            arguments: Record<string, any>
            result?: string
            error?: string
            success: boolean
            duration?: number
            timestamp?: string
        }>
        exported_at: string
        note?: string
    }> =>
        apiClient.get(`/chat/sessions/${sessionId}/export`),
}

/**
 * Settings API
 */
export const settingsAPI = {
    get: (): Promise<Settings> =>
        apiClient.get('/settings'),

    update: (data: UpdateSettingsRequest): Promise<Settings> =>
        apiClient.put('/settings', data),

    testConnection: (data: TestConnectionRequest): Promise<TestConnectionResponse> =>
        apiClient.post('/settings/test-connection', data),

    getProviders: (): Promise<ProviderMetadata[]> =>
        apiClient.get('/settings/providers'),
}

/**
 * Tools API
 */
export const toolsAPI = {
    execute: (data: ExecuteToolRequest): Promise<ExecuteToolResponse> =>
        apiClient.post('/tools/execute', data),

    list: (): Promise<{ tools: ToolDefinition[] }> =>
        apiClient.get('/tools/list'),

    // 工具调用对话历史
    getConversations: (params?: {
        session_id?: string
        tool_name?: string
        limit?: number
        offset?: number
    }): Promise<{
        conversations: Array<{
            id: string
            session_id: string
            message_id?: number
            timestamp: string
            tool_name: string
            arguments: Record<string, any>
            user_message?: string
            result?: string
            error?: string
            duration_ms?: number
        }>
        total: number
    }> =>
        apiClient.get('/tools/conversations', { params }),

    getConversationStats: (): Promise<{
        total: number
        by_tool: Record<string, number>
        by_session: Record<string, number>
        success_rate: number
    }> =>
        apiClient.get('/tools/conversations/stats'),

    clearConversations: (): Promise<{ success: boolean; message: string }> =>
        apiClient.delete('/tools/conversations'),
}

/**
 * Memory API - 简化版
 * 只保留长期记忆功能
 */
export const memoryAPI = {
    getLongTerm: (): Promise<MemoryContent> =>
        apiClient.get('/memory/long-term'),

    updateLongTerm: (data: UpdateMemoryRequest): Promise<UpdateMemoryResponse> =>
        apiClient.put('/memory/long-term', data),

    getStats: (): Promise<{ total: number; sources: Record<string, number>; date_range: string }> =>
        apiClient.get('/memory/stats'),

    getRecent: (count: number = 10): Promise<MemoryContent> =>
        apiClient.get(`/memory/recent?count=${count}`),

    search: (data: { keywords: string; max_results?: number }): Promise<{ results: string; total: number }> =>
        apiClient.post('/memory/search', data),
}

/**
 * Skills API
 */
export const skillsAPI = {
    list: (): Promise<{ skills: SkillInfo[] }> =>
        apiClient.get('/skills'),

    get: (name: string): Promise<SkillDetail> =>
        apiClient.get(`/skills/${name}`),

    create: (data: CreateSkillRequest): Promise<SkillDetail> =>
        apiClient.post('/skills', data),

    update: (name: string, data: UpdateSkillRequest): Promise<SkillDetail> =>
        apiClient.put(`/skills/${name}`, data),

    delete: (name: string): Promise<DeleteSkillResponse> =>
        apiClient.delete(`/skills/${name}`),

    toggle: (name: string, enabled: boolean): Promise<ToggleSkillResponse> =>
        apiClient.post(`/skills/${name}/toggle`, { enabled }),
}

/**
 * Cron API
 */
export const cronAPI = {
    list: (): Promise<{ jobs: CronJob[] }> =>
        apiClient.get('/cron/jobs'),

    getDetail: (id: string): Promise<{ job: CronJobDetail; last_response?: string | null; last_error?: string | null }> =>
        apiClient.get(`/cron/jobs/${id}`),

    create: (data: CreateCronJobRequest): Promise<{ job: CronJob }> =>
        apiClient.post('/cron/jobs', data),

    update: (id: string, data: UpdateCronJobRequest): Promise<{ job: CronJob }> =>
        apiClient.put(`/cron/jobs/${id}`, data),

    delete: (id: string): Promise<{ success: boolean }> =>
        apiClient.delete(`/cron/jobs/${id}`),

    execute: (id: string): Promise<ExecuteCronJobResponse> =>
        apiClient.post(`/cron/jobs/${id}/run`),
}

/**
 * Tasks API
 */
export const tasksAPI = {
    list: (): Promise<{ tasks: Task[] }> =>
        apiClient.get('/tasks'),

    create: (data: CreateTaskRequest): Promise<CreateTaskResponse> =>
        apiClient.post('/tasks', data),

    delete: (id: string): Promise<{ success: boolean }> =>
        apiClient.delete(`/tasks/${id}`),
}

/**
 * Queue & Task API - 队列和任务管理
 */
export const queueAPI = {
    getStats: (): Promise<{
        inbound_size: number
        outbound_size: number
        active_tasks: number
        rate_limiter: { active_users: number; rate: number; per: number } | null
    }> =>
        apiClient.get('/queue/stats'),

    cancelTask: (sessionId: string): Promise<{ success: boolean; message: string }> =>
        apiClient.post('/queue/cancel', { session_id: sessionId }),

    getActiveTasks: (): Promise<{ active_tasks: string[]; count: number }> =>
        apiClient.get('/queue/active-tasks'),
}

/** @deprecated Use queueAPI.cancelTask instead */
export const stopAPI = {
    stopTask: (sessionId: string): Promise<{ success: boolean; message: string }> =>
        queueAPI.cancelTask(sessionId),

    getActiveTasks: (): Promise<{ active_tasks: string[]; count: number }> =>
        queueAPI.getActiveTasks(),
}
