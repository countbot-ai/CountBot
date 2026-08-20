import type { SpawnTaskState } from '@/api/endpoints'
import type { Message as ChatHistoryMessage } from '@/store/chat'
import type { ChatMessage, ChatToolCall, WorkflowAgentState } from '@/types/chat'

type SpawnTaskResolver = (taskId: string) => SpawnTaskState | null

function extractExecMetadata(resultStr: string): Record<string, any> | null {
  if (!resultStr) return null
  const marker = '<!--WORKFLOW_EXEC:'
  const endMarker = ':WORKFLOW_EXEC-->'
  const start = resultStr.indexOf(marker)
  if (start === -1) return null
  const jsonStart = start + marker.length
  const end = resultStr.indexOf(endMarker, jsonStart)
  if (end === -1) return null

  try {
    return JSON.parse(resultStr.substring(jsonStart, end))
  } catch {
    return null
  }
}

export function reconstructWorkflowAgents(
  toolCall: Pick<ChatToolCall, 'name' | 'arguments' | 'result'>
): Record<string, WorkflowAgentState> | undefined {
  if (toolCall.name !== 'workflow_run') return undefined

  const execMeta = extractExecMetadata(toolCall.result || '')
  if (execMeta) {
    const result: Record<string, WorkflowAgentState> = {}
    for (const [agentId, data] of Object.entries(execMeta) as [string, any][]) {
      result[agentId] = {
        id: agentId,
        label: data.label || agentId,
        status: 'complete',
        toolCalls: (data.toolCalls || []).map((call: any) => ({
          id: call.id || `${agentId}:${call.tool || 'tool'}`,
          tool: call.tool,
          arguments: call.arguments || {},
          result: call.result || '',
          status: call.status || 'success',
        })),
        agentResult: data.result || '',
      }
    }
    return result
  }

  const args = toolCall.arguments || {}
  const mode = args.mode
  const agents: any[] = args.agents || []
  if (!agents.length) return {}

  const result: Record<string, WorkflowAgentState> = {}
  if (mode === 'council') {
    for (const member of agents) {
      const memberId = member.id
      const perspective = member.perspective || memberId
      const firstRoundId = `${memberId}:R1`
      const secondRoundId = `${memberId}:R2`
      result[firstRoundId] = {
        id: firstRoundId,
        label: `${perspective} - 第1轮`,
        status: 'complete',
        toolCalls: [],
      }
      result[secondRoundId] = {
        id: secondRoundId,
        label: `${perspective} - 交叉评审`,
        status: 'complete',
        toolCalls: [],
      }
    }
  } else {
    for (const agent of agents) {
      const agentId = agent.id || agent.role
      const label = agent.role || agentId
      result[agentId] = { id: agentId, label, status: 'complete', toolCalls: [] }
    }
  }

  return result
}

export function normalizeHistoryToolCall(
  toolCall: any,
  getCachedSpawnTask?: SpawnTaskResolver
): ChatToolCall {
  const normalizedToolCall: ChatToolCall = {
    id: toolCall.id,
    name: toolCall.name,
    arguments: toolCall.arguments,
    result: toolCall.result,
    error: toolCall.error,
    status: toolCall.status || (toolCall.error ? 'error' : 'success'),
    duration: toolCall.duration,
    detailAvailable: Boolean(toolCall.detail_available),
    detailLoaded: toolCall.detail_loaded !== false,
    resultTruncated: Boolean(toolCall.result_truncated),
    errorTruncated: Boolean(toolCall.error_truncated),
  }

  if (toolCall.name === 'workflow_run') {
    normalizedToolCall.workflowAgents = reconstructWorkflowAgents(toolCall) || {}
  }

  if (toolCall.name === 'spawn') {
    if (toolCall.spawn_task) {
      normalizedToolCall.spawn_task = toolCall.spawn_task
    } else if (toolCall.result && getCachedSpawnTask) {
      try {
        const resultObj =
          typeof toolCall.result === 'string' ? JSON.parse(toolCall.result) : toolCall.result
        if (resultObj.task_id) {
          const cached = getCachedSpawnTask(resultObj.task_id)
          if (cached) normalizedToolCall.spawn_task = cached
        }
      } catch {
        /* ignore malformed spawn result */
      }
    }
  }

  return normalizedToolCall
}

export function normalizeHistoryMessages(
  historyMessages: ChatHistoryMessage[],
  getCachedSpawnTask?: SpawnTaskResolver
): ChatMessage[] {
  const visibleHistoryMessages = historyMessages.filter(
    (message): message is ChatHistoryMessage & { role: 'user' | 'assistant' } =>
      message.role === 'user' || message.role === 'assistant'
  )

  return visibleHistoryMessages.map((message) => ({
    id: String(message.id),
    sessionId: message.sessionId,
    role: message.role,
    content: message.content,
    attachmentItems: message.attachmentItems || [],
    reasoningContent: message.reasoningContent || undefined,
    timestamp: message.createdAt.includes('+') || message.createdAt.includes('Z')
      ? new Date(message.createdAt)
      : new Date(`${message.createdAt}Z`),
    toolCallCount: message.toolCallCount || message.toolCalls?.length || 0,
    specialToolCallNames: message.specialToolCallNames || [],
    toolCalls: message.toolCalls?.map((toolCall: any) =>
      normalizeHistoryToolCall(toolCall, getCachedSpawnTask)
    ) || [],
  }))
}
