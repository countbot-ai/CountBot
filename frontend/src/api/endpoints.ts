/** API 端点定义：包含所有后端 API 的类型定义和调用方法 */

import apiClient from './client'
import type { NativeCapabilities, NativeChatEvent } from '@/types/nativeCaps'

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

export interface AttachmentItem {
    path: string
    name: string
    size: number
    content_type?: string | null
    kind: 'image' | 'audio' | 'video' | 'file' | string
}

export interface Session {
    id: string
    name: string
    created_at: string
    updated_at: string
    summary?: string | null
    summary_updated_at?: string | null
    use_custom_config?: boolean  // 是否使用自定义配置
    workspace_path?: string | null  // 会话自定义工作空间；为空跟随全局
    effective_workspace_path?: string | null  // 实际生效的工作空间
}

export interface SessionSearchHit {
    session_id: string
    session_name: string
    created_at?: string | null
    updated_at?: string | null
    summary?: string | null
    message_count: number
    score: number
    snippets: string[]
    preview: string
}

export interface SessionSearchResponse {
    hits: SessionSearchHit[]
    total: number
}

export interface ToolCall {
    id: string
    name: string
    arguments: Record<string, any>
    result?: string | null
    error?: string | null
    status: string
    duration?: number | null
    spawn_task?: SubagentTaskDetail | null  // 子代理任务详情（仅 spawn 工具调用）
    detail_available?: boolean
    detail_loaded?: boolean
    result_truncated?: boolean
    error_truncated?: boolean
}

export interface Message {
    id: number
    session_id: string
    role: 'user' | 'assistant' | 'system'
    content: string
    reasoning_content?: string | null
    attachment_items?: AttachmentItem[]
    native_events?: NativeChatEvent[]
    created_at: string
    tool_call_count?: number
    special_tool_call_names?: string[]
    tool_calls?: ToolCall[]
}

export interface GetMessagesParams {
    limit?: number
    offset?: number
    tool_mode?: 'full' | 'summary' | 'none'
    tool_preview_limit?: number
}

export interface GetMessageToolCallsParams {
    limit?: number
    offset?: number
    tool_mode?: 'full' | 'summary'
    tool_preview_limit?: number
}

export interface MessageToolCallPageResponse {
    message_id: number
    total: number
    offset: number
    limit: number
    has_more: boolean
    items: ToolCall[]
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
    enabled?: boolean
    configured?: boolean
    selectable?: boolean
    requires_api_key?: boolean
    requires_api_base?: boolean
    status?: string
    reason?: string
    providerGroup?: string
    provider_group?: string
    thinkingControlTier?: string
    thinking_control_tier?: string
}

export type ProviderApiType =
    | 'openai-chat-completions'
    | 'openai-responses'
    | 'anthropic-messages'

export interface ProviderModelEntry {
    id: string
    display_name?: string | null
    enabled: boolean
    context_window?: number | null
    supports_image?: boolean | null
    /** 该模型的输出模式：空=跟随全局，true=流式，false=非流式 */
    stream_enabled?: boolean | null
    /** 真实供应商 ID；共享模型合并为「内置模型」分组时携带，选择时回传后端 */
    provider_id?: string | null
    /** 该模型可选的思考档位（从低到高）；空数组=用内置建议，用户可自由增删 */
    reasoning_levels?: string[]
    /** 该模型默认思考档位；空=取档位列表首项或不下发档位 */
    reasoning_level?: string | null
    /** 供应商原生能力开关；不传则保持默认全关 */
    native_capabilities?: NativeCapabilities
    source: 'builtin' | 'manual' | 'fetched'
    /** 是否共享给普通用户（仅管理员可写） */
    shared?: boolean
    /** 用户可见别名；空则回落到 display_name 或 id */
    shared_alias?: string | null
    /** 共享说明，如「由管理员提供」 */
    shared_note?: string | null
    /** 共享模型的每用户每日调用上限；空=不限 */
    user_daily_limit?: number | null
}

export interface ProviderConfig {
    enabled: boolean
    api_key?: string
    api_keys?: string[]
    api_base?: string
    name?: string | null
    api_type?: ProviderApiType
    models?: ProviderModelEntry[]
}

export interface ModelConfig {
    provider: string
    model: string
    api_mode: 'chat_completions'
    temperature: number
    max_tokens: number
    max_iterations: number
    thinking_enabled: boolean
    /** 是否以流式方式请求上游模型；关闭后一次性返回，前端仍按 SSE 接收 */
    stream_enabled: boolean
    /** 思考档位：设置页全局默认与会话级覆盖共用该字段 */
    reasoning_level?: string | null
    supports_image?: boolean | null
    api_key?: string
    api_base?: string
}

export interface SecurityConfig {
    dangerous_commands_blocked: boolean
    custom_deny_patterns: string[]
    command_whitelist_enabled: boolean
    custom_allow_patterns: string[]
    audit_log_enabled: boolean
    command_timeout: number
    subagent_timeout: number
    max_output_length: number
    restrict_to_workspace: boolean
}

export interface HeartbeatConfig {
    enabled: boolean
    channel: string
    account_id?: string
    chat_id: string
    schedule: string
    idle_threshold_hours: number
    quiet_start: number
    quiet_end: number
    max_greets_per_day?: number
}

export interface PersonaConfig {
    ai_name: string
    user_name: string
    user_address: string
    output_language: string
    personality: string
    custom_personality: string
    max_history_messages: number
    enable_short_context_summary: boolean
    heartbeat?: HeartbeatConfig
}

export interface InjectionConfig {
    core_rules: boolean
    external_coding_guidance: boolean
    skills_always: boolean
    skills_summary: boolean
    agent_teams: boolean
    dynamic_context: boolean
    team_reminder: boolean
    memory: boolean
    disabled_tools: string[]
    auto_memory_summary: boolean
}

export type ChatMode = 'agent' | 'chat'
export type ChatModePolicy = 'all' | ChatMode

export interface SessionModelConfig extends ModelConfig {
    api_key: string
    api_base: string
    /** 会话对话模式：agent 可调用工具；chat 只对话，不注入工具与技能 */
    chat_mode?: ChatMode
}

export interface SessionPersonaConfig extends PersonaConfig {}

export interface SessionConfigResponse {
    session_id: string
    use_custom_config: boolean
    model_config: SessionModelConfig
    persona_config: SessionPersonaConfig
    global_defaults: {
        model: SessionModelConfig
        persona: SessionPersonaConfig
    }
    workspace: {
        path: string | null
        effective_path: string
        global_path: string
    }
}

export interface SessionConfigRequest {
    model_config?: Partial<SessionModelConfig>
    persona_config?: Partial<SessionPersonaConfig>
}

export interface WorkspaceConfig {
    path: string
}

export interface ExternalCodingToolProfile {
    name: string
    aliases: string[]
    type: string
    icon_svg: string
    enabled: boolean
    description: string
    command: string
    args: string[]
    working_dir: string
    stdin_template?: string | null
    env: Record<string, string>
    inherit_env: string[]
    session_mode: 'stateless' | 'history' | 'native'
    history_message_count: number
    timeout?: number | null
    success_exit_codes: number[]
}

export interface ExternalCodingToolsConfig {
    version: number
    profiles: ExternalCodingToolProfile[]
    config_path?: string
}

export interface ExternalCodingToolCheckResponse {
    success: boolean
    message: string
    resolved_command?: string | null
    missing_env: string[]
}

export interface UpdateSettingsRequest {
    providers?: Record<string, Partial<ProviderConfig>>
    model?: Partial<ModelConfig>
    workspace?: Partial<WorkspaceConfig>
    security?: Partial<SecurityConfig>
    persona?: Partial<PersonaConfig>
    injection?: Partial<InjectionConfig>
}

export interface Settings {
    providers: Record<string, ProviderConfig>
    model: ModelConfig
    workspace: WorkspaceConfig
    security: SecurityConfig
    persona: PersonaConfig
    injection?: InjectionConfig
}

export interface TestConnectionRequest {
    provider: string
    api_key?: string
    api_base?: string
    model?: string
    api_type?: ProviderApiType
    api_mode?: 'chat_completions'
    temperature?: number
    max_tokens?: number
    thinking_enabled?: boolean
}

export interface TestConnectionResponse {
    success: boolean
    message?: string
    error?: string
}

export interface ProviderModelCatalogEntry {
    id: string
    display_name?: string | null
    owned_by?: string | null
}

export interface ProviderModelCatalogResponse {
    success: boolean
    provider: string
    models: ProviderModelCatalogEntry[]
    error?: string | null
}

export interface ProviderConnectionTestResponse {
    success: boolean
    latency_ms?: number | null
    model_count?: number | null
    error?: string | null
}

export interface AddProviderModelsRequest {
    models: Array<Partial<ProviderModelEntry> & { id: string }>
    source?: ProviderModelEntry['source']
}

export interface UpdateProviderModelRequest {
    display_name?: string | null
    enabled?: boolean
    context_window?: number | null
    supports_image?: boolean | null
    /** 输出模式：空=不修改，true=流式，false=非流式 */
    stream_enabled?: boolean | null
    /** 思考档位列表；传空数组表示改用内置建议 */
    reasoning_levels?: string[]
    /** 默认思考档位 */
    reasoning_level?: string | null
    /** 供应商原生能力开关；不传则不修改 */
    native_capabilities?: NativeCapabilities
    clear_display_name?: boolean
    clear_context_window?: boolean
    clear_supports_image?: boolean
    /** 清空模型级输出模式，回落到跟随全局 */
    clear_stream_enabled?: boolean
    /** 清空默认思考档位 */
    clear_reasoning_level?: boolean
    /** 多用户共享元数据（仅管理员可写） */
    shared?: boolean
    shared_alias?: string | null
    shared_note?: string | null
    user_daily_limit?: number | null
    clear_shared_alias?: boolean
    clear_shared_note?: boolean
    clear_user_daily_limit?: boolean
}

export interface ReasoningLevelsResponse {
    model: string
    /** 内置建议档位（从低到高）；未收录的模型返回空数组 */
    levels: string[]
    /** 常用档位全集，仅作自定义填写参考 */
    known_levels: string[]
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

export interface SelfImprovingMemoryContent {
    memory: string
    corrections: string
    index: string
    heartbeat_state: string
    projects: string[]
    domains: string[]
    archive: string[]
}

export interface UpdateMemoryRequest {
    content: string
}

export interface UpdateSelfImprovingMemoryRequest {
    memory: string
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
    hasConfig: boolean
    requirements: string[]
    source?: 'workspace' | 'builtin' | 'openclaw' | 'shared'
    /** 随应用分发的内置技能（初始化时播种进工作区，非用户自建） */
    bundled?: boolean
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

// Skills Config API Types
export interface ConfigFieldSchema {
    key: string
    type: string
    label: string
    description?: string
    required?: boolean
    sensitive?: boolean
    readonly?: boolean
    default?: any
    placeholder?: string
    validation?: string
    min?: number
    max?: number
    options?: Array<{ value: string; label: string }>
    help_url?: string
    fields?: ConfigFieldSchema[]
    collapsible?: boolean
}

export interface SkillConfigSchemaResponse {
    has_schema: boolean
    schema?: {
        skill_name: string
        version: string
        description: string
        config_file: string
        help_file?: string
        fields: ConfigFieldSchema[]
    }
}

export interface SkillConfigResponse {
    has_config: boolean
    config?: Record<string, any>
    status: string
    errors: string[]
}

export interface UpdateSkillConfigRequest {
    config: Record<string, any>
}

export interface SkillConfigStatusResponse {
    status: string
    message: string
    errors: string[]
}

export interface SkillConfigHelpResponse {
    has_help: boolean
    content?: string
}

export interface FixSkillConfigResponse {
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
    account_id?: string | null
    chat_id?: string | null
    deliver_response: boolean
    model_provider?: string | null
    model_name?: string | null
    last_run?: string | null
    last_finished_at?: string | null
    next_run?: string | null
    last_status?: string | null
    last_error?: string | null
    last_delivery_status?: string | null
    last_delivery_error?: string | null
    run_count: number
    error_count: number
    created_at: string
    max_retries?: number
    retry_delay?: number
    delete_on_success?: boolean
    link_context?: boolean
    is_running?: boolean
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
    account_id?: string | null
    chat_id?: string | null
    deliver_response?: boolean
    max_retries?: number
    retry_delay?: number
    delete_on_success?: boolean
    link_context?: boolean
    model_provider?: string | null
    model_name?: string | null
}

export interface UpdateCronJobRequest {
    name?: string
    schedule?: string
    message?: string
    enabled?: boolean
    channel?: string | null
    account_id?: string | null
    chat_id?: string | null
    deliver_response?: boolean
    max_retries?: number
    retry_delay?: number
    delete_on_success?: boolean
    link_context?: boolean
    model_provider?: string | null
    model_name?: string | null
}

export interface ExecuteCronJobResponse {
    success: boolean
    message?: string
}

// Tasks API Types

/** 子代理单次工具调用记录（后端持久化字段） */
export interface TaskToolCallRecord {
    tool_call_id: string
    name: string
    arguments: Record<string, unknown>
    result: string | null
    status: string
    duration_ms?: number
}

export interface Task {
    id: string
    label: string
    status: 'running' | 'completed' | 'failed'
    progress: number
    result?: string
    created_at: string
    completed_at?: string
}

export interface SubagentTaskDetail {
    task_id: string
    label: string
    message: string
    session_id: string | null
    status: string
    progress: number
    result: string | null
    error: string | null
    created_at: string
    started_at: string | null
    completed_at: string | null
    tool_call_records: TaskToolCallRecord[]
}

export interface CreateTaskRequest {
    task: string
    label: string
}

export interface CreateTaskResponse {
    task_id: string
}

// ── spawn 面板前端状态类型（localStorage 缓存 / spawnTaskMap 使用）──────

/** spawn 面板中单条嵌套工具调用的前端状态 */
export interface SpawnToolCall {
    id: string
    name: string
    arguments: Record<string, unknown>
    status: 'running' | 'success' | 'cancelled'
    result?: string
    error?: string
    duration?: number
    /** 内部字段：用于计算 duration，不持久化 */
    _startTs?: number
}

/** spawn 面板日志条目 */
export interface SpawnLogEntry {
    level: string
    text: string
    ts: number
}

/** spawn 工具调用在 ChatWindow 中的完整运行时状态 */
export interface SpawnTaskState {
    task_id: string
    label: string
    status: string
    progress: number
    result: string | null
    error: string | null
    logs: SpawnLogEntry[]
    toolCalls: SpawnToolCall[]
    /** 最新进度描述（折叠预览文字） */
    progressMessage?: string
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

/** Health Check API */
export const healthAPI = {
    check: (): Promise<{ status: string }> =>
        apiClient.get('/health'),
}

/** Auth API */
export const authAPI = {
    status: (): Promise<{
        is_local: boolean
        auth_enabled: boolean
        authenticated: boolean
        remote_access_enabled: boolean
        multiuser_enabled?: boolean
        registration_open?: boolean
        approval_mode?: string
        role?: string | null
    }> =>
        apiClient.get('/auth/status'),

    setup: (data: { username: string; password: string }): Promise<{ success: boolean; token: string }> =>
        apiClient.post('/auth/setup', data),

    login: (data: { username: string; password: string }): Promise<{ success: boolean; token: string }> =>
        apiClient.post('/auth/login', data),

    register: (data: { username: string; password: string; display_name?: string }): Promise<{
        success: boolean
        status?: string
        message?: string
    }> =>
        apiClient.post('/auth/register', data),

    logout: (): Promise<{ success: boolean }> =>
        apiClient.post('/auth/logout'),

    changePassword: (data: { old_password: string; new_password: string }): Promise<{ success: boolean }> =>
        apiClient.post('/auth/change-password', data),
}

/** Current user API (/api/me) */
export interface MeModelItem {
    ref: string
    source: 'shared' | 'own'
    provider: string
    model: string
    alias: string
    note?: string
    provider_name?: string
    daily_limit?: number | null
    context_window?: number | null
    supports_image?: boolean | null
    native_capabilities?: NativeCapabilities
    available: boolean
}

export interface MeModelsResponse {
    shared: MeModelItem[]
    own: MeModelItem[]
    selected: string | null
    mode: 'shared' | 'isolated'
    shared_enabled: boolean
}

export interface MeProfile {
    id: string
    username: string
    display_name: string
    role: 'admin' | 'user'
    status: string
    is_admin: boolean
    chat_mode_policy: ChatModePolicy
    allowed_chat_modes: ChatMode[]
    mode: string
    shared_providers: boolean
    shared_skills_wiki_mcp: boolean
}

export interface MeMcpServer extends Record<string, unknown> {
    id: string
    name: string
    enabled: boolean
    transport: 'stdio' | 'streamable_http' | 'sse' | null
    description: string
    include_tools: string[]
    exclude_tools: string[]
    enable_resources: boolean
    enable_prompts: boolean
    command: string
    args: string[]
    env: Record<string, string>
    url: string
    headers: Record<string, string>
    timeout: number
    connect_timeout: number
    running?: boolean
    tool_count?: number
}

export interface MeMcpState {
    enabled: boolean
    max_servers: number
    stdio_allowlist: string[]
    connected: boolean
    tool_count: number
    servers: MeMcpServer[]
}

export const meAPI = {
    profile: (): Promise<MeProfile> => apiClient.get('/me'),

    listModels: (): Promise<MeModelsResponse> => apiClient.get('/me/models'),

    getReasoningLevels: (model: string): Promise<{ model: string; levels: string[]; known_levels: string[] }> =>
        apiClient.get('/me/reasoning-levels', { params: { model } }),

    addModel: (data: {
        provider: string
        model: string
        display_name?: string
        api_key?: string
        api_base?: string
    }): Promise<MeModelsResponse> => apiClient.post('/me/models', data),

    deleteModel: (provider: string, model: string): Promise<MeModelsResponse> =>
        apiClient.delete('/me/models', { params: { provider, model } }),

    selectModel: (data: { source: string; provider: string; model: string }): Promise<MeModelsResponse> =>
        apiClient.put('/me/model-selection', data),

    testModel: (data: { source: string; provider: string; model: string }): Promise<{ success: boolean; message: string }> =>
        apiClient.post('/me/models/test', data),

    getPersona: (): Promise<Record<string, unknown>> => apiClient.get('/me/persona'),

    updatePersona: (data: Record<string, unknown>): Promise<Record<string, unknown>> =>
        apiClient.put('/me/persona', data),

    getMcp: (): Promise<MeMcpState> => apiClient.get('/me/mcp'),

    updateMcp: (servers: MeMcpServer[]): Promise<MeMcpState> =>
        apiClient.put('/me/mcp', { servers }),

    testMcpServer: (server: MeMcpServer): Promise<{ success: boolean; message: string }> =>
        apiClient.post('/me/mcp/test', { server }),
}

/** Admin API (/api/admin) */
export interface AdminUserItem {
    id: string
    username: string
    role: 'admin' | 'user'
    status: 'pending' | 'active' | 'disabled'
    display_name?: string
    chat_mode_policy: ChatModePolicy
    created_at?: string
    approved_at?: string
    last_login_at?: string
    /** 连续登录失败触发的临时锁定剩余秒数；0 表示未锁定 */
    login_locked?: number
}

export interface SharedModelItem {
    ref: string
    provider: string
    model: string
    alias: string
    note: string
    daily_limit?: number | null
    context_window?: number | null
    supports_image?: boolean | null
    provider_name: string
}

export interface SharedModelUsageItem {
    owner_id: string
    username: string
    provider: string
    model: string
    today_calls: number
    total_calls: number
    today_tokens: number
}

export interface SharedModelsResponse {
    enabled: boolean
    mode: string
    shared_providers: boolean
    items: SharedModelItem[]
    usage: SharedModelUsageItem[]
}

export const adminAPI = {
    listUsers: (params?: { q?: string; status?: string; page?: number; page_size?: number }): Promise<{
        items: AdminUserItem[]
        total: number
        page: number
        page_size: number
    }> => apiClient.get('/admin/users', { params }),

    createUser: (data: {
        username: string
        password: string
        role?: string
        status?: string
        display_name?: string
        chat_mode_policy?: ChatModePolicy
    }): Promise<AdminUserItem> => apiClient.post('/admin/users', data),

    updateUser: (id: string, data: { status?: string; role?: string; display_name?: string; chat_mode_policy?: ChatModePolicy }): Promise<AdminUserItem> =>
        apiClient.patch(`/admin/users/${id}`, data),

    resetPassword: (id: string, newPassword: string): Promise<{ success: boolean; message: string }> =>
        apiClient.put(`/admin/users/${id}/password`, { new_password: newPassword }),

    unlockUser: (id: string): Promise<{ success: boolean; message: string }> =>
        apiClient.post(`/admin/users/${id}/unlock`, {}),

    deleteUser: (id: string): Promise<{ success: boolean; message: string }> =>
        apiClient.delete(`/admin/users/${id}`),

    getMultiuserSettings: (): Promise<{
        enabled: boolean
        registration_open: boolean
        approval: string
        mode: string
        shared_providers: boolean
        shared_skills_wiki_mcp: boolean
        allow_user_mcp: boolean
        user_mcp_stdio_allowlist: string[]
        notify_shared_channels?: string[]
        allow_local_admin_bypass: boolean
        max_users: number
    }> => apiClient.get('/admin/multiuser/settings'),

    updateMultiuserSettings: (data: Record<string, unknown>): Promise<Record<string, unknown>> =>
        apiClient.put('/admin/multiuser/settings', data),

    getSharedModels: (params?: { include_usage?: boolean }): Promise<SharedModelsResponse> =>
        apiClient.get('/admin/shared-models', { params }),

    listAuditLogs: (params?: { action?: string; page?: number; page_size?: number }): Promise<{
        items: Array<Record<string, unknown>>
        total: number
        page: number
        page_size: number
    }> => apiClient.get('/admin/audit-logs', { params }),
}

/** System Info API */
export const systemAPI = {
    getInfo: (): Promise<SystemInfo> =>
        apiClient.get('/system/info'),
}

/** Chat API */
export const chatAPI = {
    sendMessage: (data: SendMessageRequest): Promise<SendMessageResponse> =>
        apiClient.post('/chat/send', data),

    uploadAttachment: (sessionId: string, file: File): Promise<AttachmentItem> =>
        apiClient.post(`/chat/sessions/${sessionId}/attachments`, file, {
            headers: {
                'Content-Type': file.type || 'application/octet-stream',
                'X-File-Name': encodeURIComponent(file.name || 'attachment'),
                'X-File-Size': String(file.size ?? 0),
            },
        }),

    getSessions: (params?: { limit?: number; offset?: number }): Promise<Session[]> =>
        apiClient.get('/chat/sessions', {
            params: withFreshParams(params),
            headers: noCacheHeaders(),
        }),

    createSession: (name: string): Promise<Session> =>
        apiClient.post('/chat/sessions', null, { params: { name } }),

    updateSession: (id: string, name: string): Promise<Session> =>
        apiClient.put(`/chat/sessions/${id}`, { name }),

    deleteSession: (id: string): Promise<{ success: boolean }> =>
        apiClient.delete(`/chat/sessions/${id}`),

    getMessages: (sessionId: string, params?: GetMessagesParams): Promise<Message[]> =>
        apiClient.get(`/chat/sessions/${sessionId}/messages`, {
            params: withFreshParams(params),
            headers: noCacheHeaders(),
        }),

    getMessageToolCalls: (
        sessionId: string,
        messageId: number,
        params?: GetMessageToolCallsParams
    ): Promise<MessageToolCallPageResponse> =>
        apiClient.get(`/chat/sessions/${sessionId}/messages/${messageId}/tool-calls`, {
            params: withFreshParams(params),
            headers: noCacheHeaders(),
        }),

    getToolCallDetail: (toolCallId: string): Promise<ToolCall> =>
        apiClient.get(`/chat/tool-calls/${toolCallId}`, {
            params: withFreshParams(),
            headers: noCacheHeaders(),
        }),

    deleteMessage: (sessionId: string, messageId: number): Promise<{ success: boolean; message: string }> =>
        apiClient.delete(`/chat/sessions/${sessionId}/messages/${messageId}`),

    clearMessages: (sessionId: string): Promise<{ success: boolean }> =>
        apiClient.delete(`/chat/sessions/${sessionId}/messages`),

    // 会话总结 API
    getSession: (sessionId: string): Promise<Session> =>
        apiClient.get(`/chat/sessions/${sessionId}`, {
            params: withFreshParams(),
            headers: noCacheHeaders(),
        }),

    searchSessions: (data: {
        query: string
        limit?: number
        per_session_snippets?: number
    }): Promise<SessionSearchResponse> =>
        apiClient.post('/session-search', data),

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

    // 手动压缩会话上下文：按 token 水位折叠过长的历史，保留头部与最近若干条原文
    compactSessionContext: (sessionId: string, focusTopic?: string): Promise<{
        success: boolean
        session_id: string
        reason: string
        before_tokens: number
        after_tokens: number
        saved_tokens: number
        savings_ratio: number
        summarized_messages: number
        pruned_tool_results: number
        summary_deterministic: boolean
        message: string
    }> =>
        apiClient.post(
            `/chat/sessions/${sessionId}/compact`,
            focusTopic ? { focus_topic: focusTopic } : {},
        ),

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
    
    // 会话配置 API
    getSessionConfig: (sessionId: string): Promise<SessionConfigResponse> =>
        apiClient.get(`/chat/sessions/${sessionId}/config`),
    
    updateSessionConfig: (sessionId: string, data: SessionConfigRequest): Promise<{
        success: boolean
        session_id: string
        message: string
    }> =>
        apiClient.put(`/chat/sessions/${sessionId}/config`, data),
    
    resetSessionConfig: (sessionId: string): Promise<{
        success: boolean
        session_id: string
        message: string
    }> =>
        apiClient.delete(`/chat/sessions/${sessionId}/config`),

    updateSessionWorkspace: (sessionId: string, path: string | null): Promise<{
        success: boolean
        session_id: string
        workspace_path: string | null
        effective_workspace_path: string
    }> =>
        apiClient.put(`/chat/sessions/${sessionId}/workspace`, { path }),
}

function normalizeOptionalText(value?: string | null): string | undefined {
    if (value === undefined || value === null) {
        return undefined
    }
    const normalized = String(value).trim()
    return normalized || undefined
}

function withFreshParams<T extends Record<string, any> | undefined>(params?: T) {
    return {
        ...(params || {}),
        _ts: Date.now(),
    }
}

function noCacheHeaders() {
    return {
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        Pragma: 'no-cache',
        Expires: '0',
    }
}

/** Settings API */
export const settingsAPI = {
    get: (): Promise<Settings> =>
        apiClient.get('/settings'),

    update: (data: UpdateSettingsRequest): Promise<Settings> =>
        apiClient.put('/settings', data),

    testConnection: (data: TestConnectionRequest): Promise<TestConnectionResponse> =>
        apiClient.post('/settings/test-connection', {
            ...data,
            api_key: String(data.api_key || '').trim(),
            api_base: normalizeOptionalText(data.api_base),
            model: normalizeOptionalText(data.model),
        }),

    getProviders: (): Promise<ProviderMetadata[]> =>
        apiClient.get('/settings/providers'),

    getProviderModelCatalog: (providerId: string): Promise<ProviderModelCatalogResponse> =>
        apiClient.get(`/settings/providers/${encodeURIComponent(providerId)}/models/catalog`),

    getReasoningLevels: (model: string): Promise<ReasoningLevelsResponse> =>
        apiClient.get('/settings/reasoning-levels', { params: { model } }),

    addProviderModels: (
        providerId: string,
        data: AddProviderModelsRequest,
    ): Promise<ProviderModelEntry[]> =>
        apiClient.post(`/settings/providers/${encodeURIComponent(providerId)}/models`, data),

    updateProviderModel: (
        providerId: string,
        modelId: string,
        data: UpdateProviderModelRequest,
    ): Promise<ProviderModelEntry[]> =>
        apiClient.put(
            `/settings/providers/${encodeURIComponent(providerId)}/models/${encodeURIComponent(modelId)}`,
            data,
        ),

    deleteProviderModel: (providerId: string, modelId: string): Promise<ProviderModelEntry[]> =>
        apiClient.delete(
            `/settings/providers/${encodeURIComponent(providerId)}/models/${encodeURIComponent(modelId)}`,
        ),

    reorderProviderModels: (providerId: string, modelIds: string[]): Promise<ProviderModelEntry[]> =>
        apiClient.put(
            `/settings/providers/${encodeURIComponent(providerId)}/models/order`,
            { model_ids: modelIds },
        ),

    testProviderConnection: (providerId: string): Promise<ProviderConnectionTestResponse> =>
        apiClient.post(`/settings/providers/${encodeURIComponent(providerId)}/test`),

    getExternalCodingTools: (): Promise<ExternalCodingToolsConfig> =>
        apiClient.get('/settings/external-coding-tools'),

    updateExternalCodingTools: (data: ExternalCodingToolsConfig): Promise<ExternalCodingToolsConfig> =>
        apiClient.put('/settings/external-coding-tools', data),

    checkExternalCodingTool: (profile: ExternalCodingToolProfile): Promise<ExternalCodingToolCheckResponse> =>
        apiClient.post('/settings/external-coding-tools/check', { profile }),
}

/**
 * 普通用户自有供应商 API：与管理员 settingsAPI 的供应商部分同形，
 * 路径前缀 /me/providers。getView 返回 providers + model 局部视图
 * （model 为全局生成参数，普通用户只读），消费方只读这两段。
 */
export const meProvidersAPI = {
    getView: (): Promise<Settings> =>
        apiClient.get('/me/providers'),

    updateProviders: (data: { providers: Record<string, ProviderConfig> }): Promise<Settings> =>
        apiClient.put('/me/providers', data),

    deleteProvider: (providerId: string): Promise<Settings> =>
        apiClient.delete(`/me/providers/${encodeURIComponent(providerId)}`),

    getProviders: (): Promise<ProviderMetadata[]> =>
        apiClient.get('/me/providers/metadata'),

    getProviderModelCatalog: (providerId: string): Promise<ProviderModelCatalogResponse> =>
        apiClient.get(`/me/providers/${encodeURIComponent(providerId)}/models/catalog`),

    getReasoningLevels: (model: string): Promise<ReasoningLevelsResponse> =>
        apiClient.get('/me/reasoning-levels', { params: { model } }),

    addProviderModels: (
        providerId: string,
        data: AddProviderModelsRequest,
    ): Promise<ProviderModelEntry[]> =>
        apiClient.post(`/me/providers/${encodeURIComponent(providerId)}/models`, data),

    updateProviderModel: (
        providerId: string,
        modelId: string,
        data: UpdateProviderModelRequest,
    ): Promise<ProviderModelEntry[]> =>
        apiClient.put(
            `/me/providers/${encodeURIComponent(providerId)}/models/${encodeURIComponent(modelId)}`,
            data,
        ),

    deleteProviderModel: (providerId: string, modelId: string): Promise<ProviderModelEntry[]> =>
        apiClient.delete(
            `/me/providers/${encodeURIComponent(providerId)}/models/${encodeURIComponent(modelId)}`,
        ),

    reorderProviderModels: (providerId: string, modelIds: string[]): Promise<ProviderModelEntry[]> =>
        apiClient.put(
            `/me/providers/${encodeURIComponent(providerId)}/models/order`,
            { model_ids: modelIds },
        ),

    testConnection: (data: TestConnectionRequest): Promise<TestConnectionResponse> =>
        apiClient.post('/me/providers/test-connection', {
            ...data,
            api_key: String(data.api_key || '').trim(),
            api_base: normalizeOptionalText(data.api_base),
            model: normalizeOptionalText(data.model),
        }),

    testProviderConnection: (providerId: string): Promise<ProviderConnectionTestResponse> =>
        apiClient.post(`/me/providers/${encodeURIComponent(providerId)}/test`),
}

/** Tools API */
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

/** Memory API（简化版）：只保留长期记忆功能 */
export const memoryAPI = {
    getLongTerm: (): Promise<MemoryContent> =>
        apiClient.get('/memory/long-term'),

    updateLongTerm: (data: UpdateMemoryRequest): Promise<UpdateMemoryResponse> =>
        apiClient.put('/memory/long-term', data),

    getSelfImproving: (): Promise<SelfImprovingMemoryContent> =>
        apiClient.get('/memory/self-improving'),

    updateSelfImproving: (data: UpdateSelfImprovingMemoryRequest): Promise<UpdateMemoryResponse> =>
        apiClient.put('/memory/self-improving', data),

    getStats: (): Promise<{ total: number; sources: Record<string, number>; date_range: string }> =>
        apiClient.get('/memory/stats'),

    getRecent: (count: number = 10): Promise<MemoryContent> =>
        apiClient.get(`/memory/recent?count=${count}`),

    search: (data: { keywords: string; max_results?: number }): Promise<{ results: string; total: number }> =>
        apiClient.post('/memory/search', data),
}

/** Skills API */
export interface SharedSkillItem {
    id: string
    name: string
    owner_id?: string | null
    scope: string
    visibility: string
    status: 'draft' | 'pending' | 'approved' | 'rejected' | 'revoked'
    description: string
    version: number
    /** null 表示全站可见 */
    audience?: string[] | null
    reject_reason?: string | null
    approved_at?: string | null
    created_at?: string | null
    is_mine: boolean
    /** 当前用户是否启用了该技能 */
    enabled: boolean
}

export const sharedSkillsAPI = {
    list: (): Promise<SharedSkillItem[]> => apiClient.get('/shared-skills'),

    publishable: (): Promise<string[]> => apiClient.get('/shared-skills/publishable'),

    publish: (data: { name: string; audience?: string[] | null }): Promise<SharedSkillItem> =>
        apiClient.post('/shared-skills/publish', data),

    review: (id: string, approved: boolean, reason = ''): Promise<SharedSkillItem> =>
        apiClient.post(`/shared-skills/${id}/review`, { approved, reason }),

    revoke: (id: string, reason = ''): Promise<SharedSkillItem> =>
        apiClient.post(`/shared-skills/${id}/revoke`, { reason }),

    setState: (id: string, enabled: boolean): Promise<SharedSkillItem> =>
        apiClient.put(`/shared-skills/${id}/state`, { enabled }),
}

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

    // 配置相关API
    getConfigSchema: (name: string): Promise<SkillConfigSchemaResponse> =>
        apiClient.get(`/skills/${name}/config/schema`),

    getConfig: (name: string): Promise<SkillConfigResponse> =>
        apiClient.get(`/skills/${name}/config`),

    updateConfig: (name: string, data: UpdateSkillConfigRequest): Promise<SkillConfigResponse> =>
        apiClient.put(`/skills/${name}/config`, data),

    getConfigStatus: (name: string): Promise<SkillConfigStatusResponse> =>
        apiClient.get(`/skills/${name}/config/status`),

    fixConfig: (name: string): Promise<FixSkillConfigResponse> =>
        apiClient.post(`/skills/${name}/config/fix`),

    getConfigHelp: (name: string): Promise<SkillConfigHelpResponse> =>
        apiClient.get(`/skills/${name}/config/help`),

    // 重载技能
    reload: (): Promise<{ success: boolean; message: string; total: number }> =>
        apiClient.post('/skills/reload'),
}

/** Cron API */
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

/** Tasks API */
export const tasksAPI = {
    list: (): Promise<{ tasks: Task[] }> =>
        apiClient.get('/tasks'),

    get: (taskId: string): Promise<SubagentTaskDetail> =>
        apiClient.get(`/tasks/${taskId}`),

    create: (data: CreateTaskRequest): Promise<CreateTaskResponse> =>
        apiClient.post('/tasks', data),

    delete: (id: string): Promise<{ success: boolean }> =>
        apiClient.delete(`/tasks/${id}`),
}

/** Queue & Task API - 队列和任务管理 */
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

/** Settings Export/Import API - 配置导出导入 */
export interface ExportConfigParams {
    include_api_keys?: boolean
    sections?: string
}

export interface ImportConfigRequest {
    version: string
    config: Record<string, any>
    merge?: boolean
    sections?: string[]
}

export interface ImportConfigResponse {
    success: boolean
    message: string
    settings: Settings
}

export const configAPI = {
        /** 导出配置 */
    export: (params: ExportConfigParams = {}): Promise<{
        version: string
        exported_at: string
        app_version: string
        config: Record<string, any>
    }> => {
        const queryParams = new URLSearchParams()
        if (params.include_api_keys !== undefined) {
            // 确保传递正确的布尔字符串值
            queryParams.append('include_api_keys', params.include_api_keys ? 'true' : 'false')
        }
        if (params.sections) {
            queryParams.append('sections', params.sections)
        }
        const query = queryParams.toString()
        return apiClient.get(`/settings/export${query ? '?' + query : ''}`)
    },

        /** 导入配置 */
    import: (data: ImportConfigRequest): Promise<ImportConfigResponse> =>
        apiClient.post('/settings/import', data),
}
