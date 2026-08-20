import type { AttachmentItem, SpawnTaskState, SubagentTaskDetail } from '@/api/endpoints'

export type ToolCallStatus = 'pending' | 'running' | 'success' | 'error' | 'cancelled'

export interface WorkflowAgentToolCall {
  id: string
  tool: string
  arguments?: Record<string, any>
  result?: string | null
  error?: string | null
  status?: ToolCallStatus
  duration?: number | null
}

export interface WorkflowAgentState {
  id: string
  label: string
  status: 'running' | 'complete'
  toolCalls?: WorkflowAgentToolCall[]
  streamingText?: string
  result?: string | null
  agentResult?: string | null
}

export interface ChatToolCall {
  id: string
  name: string
  arguments?: Record<string, any>
  result?: string | null
  error?: string | null
  status?: ToolCallStatus
  duration?: number | null
  detailAvailable?: boolean
  detailLoaded?: boolean
  resultTruncated?: boolean
  errorTruncated?: boolean
  progress?: number | null
  progressMessage?: string | null
  progressDetails?: Record<string, any> | null
  messageId?: string | null
  workflowAgents?: Record<string, WorkflowAgentState>
  spawn_task?: SubagentTaskDetail | SpawnTaskState | null
}

export interface ChatMessage {
  id: string
  sessionId?: string
  role: 'user' | 'assistant'
  content: string
  attachmentItems?: AttachmentItem[]
  timestamp: Date
  toolCalls?: ChatToolCall[]
  toolCallCount?: number
  specialToolCallNames?: string[]
  reasoningContent?: string
  isThinking?: boolean
  queued?: boolean
}
