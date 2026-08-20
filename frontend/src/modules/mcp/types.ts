export interface McpServerConfig {
    id: string
    name: string
    enabled: boolean
    transport: 'stdio' | 'streamable_http' | 'sse'
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
}

export interface McpRegistryData {
    version: number
    servers: McpServerConfig[]
}

export interface McpServerTestResult {
    success: boolean
    message: string
    resolved_command?: string | null
    normalized_url?: string | null
}

export interface McpOverviewData {
    success: boolean
    enabled: boolean
    summary: {
        total_servers: number
        enabled_servers: number
        connected_servers: number
        mcp_tool_count: number
    }
    servers: McpServerStatus[]
}

export interface McpServerStatus {
    id: string
    name: string
    description: string
    enabled: boolean
    running: boolean
    transport: string
    tool_count: number | null
    tools: string[]
    last_error: string | null
}

export function createEmptyServer(): McpServerConfig {
    return {
        id: '',
        name: '',
        enabled: true,
        transport: 'stdio',
        description: '',
        include_tools: ['*'],
        exclude_tools: [],
        enable_resources: false,
        enable_prompts: false,
        command: '',
        args: [],
        env: {},
        url: '',
        headers: {},
        timeout: 30,
        connect_timeout: 10,
    }
}

export function cloneServer(src: McpServerConfig): McpServerConfig {
    return {
        ...src,
        include_tools: [...src.include_tools],
        exclude_tools: [...src.exclude_tools],
        args: [...src.args],
        env: { ...src.env },
        headers: { ...src.headers },
    }
}

export function inferTransport(s: McpServerConfig): string {
    if (s.transport) return s.transport
    if (s.command) return 'stdio'
    if (s.url) {
        return s.url.endsWith('/sse') ? 'sse' : 'streamable_http'
    }
    return ''
}

export const TRANSPORT_LABELS: Record<string, string> = {
    stdio: 'stdio',
    sse: 'SSE',
    streamable_http: 'HTTP',
}
