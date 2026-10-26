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

/**
 * 消息内的顺序块：记录本轮「正文 / 工具调用」的真实发生顺序。
 *
 * 后端按事件顺序分别推送正文 chunk 与工具调用，两者一旦分别累积就丢失了先后关系，
 * 因此流式过程中在这里留一份顺序记录，渲染时才能把正文和工具调用交织还原。
 * 仅实时消息会填充；历史消息没有该信息，由渲染层按「工具在前、正文在后」兜底。
 */
export type ChatMessageBlock =
  | { type: 'text'; text: string }
  | { type: 'tool'; toolCallId: string }

/** 正文块的渲染输入（html 已由 markdown 渲染器处理） */
export interface InterleavedTextBlock {
  kind: 'text'
  key: string
  html: string
}

/** 工具调用块的渲染输入，指向消息内的一次工具调用 */
export interface InterleavedToolBlock {
  kind: 'tool'
  key: string
  toolCall: ChatToolCall
  showResult: boolean
}

export type InterleavedRenderBlock = InterleavedTextBlock | InterleavedToolBlock

export interface ChatMessage {
  id: string
  sessionId?: string
  role: 'user' | 'assistant'
  content: string
  attachmentItems?: AttachmentItem[]
  timestamp: Date
  toolCalls?: ChatToolCall[]
  /** 正文与工具调用的顺序记录，见 ChatMessageBlock */
  blocks?: ChatMessageBlock[]
  toolCallCount?: number
  specialToolCallNames?: string[]
  reasoningContent?: string
  isThinking?: boolean
  queued?: boolean
}
