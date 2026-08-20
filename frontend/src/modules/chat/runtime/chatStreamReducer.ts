import type { ChatMessage, ChatToolCall, WorkflowAgentState } from '@/types/chat'

interface SpawnTaskLink {
  messageId: string
  toolCallId: string
}

export interface ChatStreamRuntimeState {
  messages: ChatMessage[]
  isStreaming: boolean
  currentStreamingMessageId: string | null
  currentWorkflowToolCallId: string | null
  spawnTaskMap: Record<string, SpawnTaskLink>
  pendingSpawnLink: SpawnTaskLink | null
  isStopping: boolean
}

export type StreamRealtimeMessage = Record<string, any> & {
  type: string
}

export type ChatStreamAction =
  | { type: 'replace_messages'; messages: ChatMessage[] }
  | {
      type: 'hydrate_runtime'
      messages: ChatMessage[]
      isStreaming: boolean
      currentStreamingMessageId: string | null
      currentWorkflowToolCallId: string | null
    }
  | { type: 'reasoning_chunk'; payload: StreamRealtimeMessage; now: number }
  | { type: 'message_chunk'; payload: StreamRealtimeMessage; now: number }
  | { type: 'tool_call'; payload: StreamRealtimeMessage; now: number }
  | { type: 'tool_progress'; payload: StreamRealtimeMessage }
  | { type: 'tool_result'; payload: StreamRealtimeMessage }
  | { type: 'workflow_event'; payload: StreamRealtimeMessage; now: number }
  | { type: 'spawn_event'; payload: StreamRealtimeMessage }
  | { type: 'message_complete' }
  | { type: 'stop_streaming' }
  | { type: 'clear_messages' }
  | { type: 'add_thinking_message'; now: number }

const workflowEventTypes = new Set([
  'workflow_agent_start',
  'workflow_agent_chunk',
  'workflow_agent_tool_call',
  'workflow_agent_tool_result',
  'workflow_agent_complete',
])

const spawnEventTypes = new Set([
  'task_created',
  'task_status',
  'task_progress',
  'task_log',
  'task_tool_call',
  'task_tool_result',
  'task_complete',
  'task_failed',
])

export function createInitialChatStreamState(): ChatStreamRuntimeState {
  return {
    messages: [],
    isStreaming: false,
    currentStreamingMessageId: null,
    currentWorkflowToolCallId: null,
    spawnTaskMap: {},
    pendingSpawnLink: null,
    isStopping: false,
  }
}

export function mapRealtimeMessageToAction(
  message: StreamRealtimeMessage,
  now: number = Date.now()
): ChatStreamAction | null {
  switch (message.type) {
    case 'reasoning_chunk':
      return { type: 'reasoning_chunk', payload: message, now }
    case 'message_chunk':
      return { type: 'message_chunk', payload: message, now }
    case 'tool_call':
      return { type: 'tool_call', payload: message, now }
    case 'tool_progress':
      return { type: 'tool_progress', payload: message }
    case 'tool_result':
      return { type: 'tool_result', payload: message }
    case 'message_complete':
      return { type: 'message_complete' }
    default:
      if (workflowEventTypes.has(message.type)) {
        return { type: 'workflow_event', payload: message, now }
      }
      if (spawnEventTypes.has(message.type)) {
        return { type: 'spawn_event', payload: message }
      }
      return null
  }
}

export function chatStreamReducer(
  state: ChatStreamRuntimeState,
  action: ChatStreamAction
): ChatStreamRuntimeState {
  switch (action.type) {
    case 'replace_messages':
      return {
        ...createInitialChatStreamState(),
        messages: action.messages,
      }
    case 'hydrate_runtime':
      return {
        ...createInitialChatStreamState(),
        messages: action.messages,
        isStreaming: action.isStreaming,
        currentStreamingMessageId: action.currentStreamingMessageId,
        currentWorkflowToolCallId: action.currentWorkflowToolCallId,
      }
    case 'reasoning_chunk':
      return reduceReasoningChunk(state, action.payload, action.now)
    case 'message_chunk':
      return reduceMessageChunk(state, action.payload, action.now)
    case 'tool_call':
      return reduceToolCall(state, action.payload, action.now)
    case 'tool_progress':
      return reduceToolProgress(state, action.payload)
    case 'tool_result':
      return reduceToolResult(state, action.payload)
    case 'workflow_event':
      return reduceWorkflowEvent(state, action.payload, action.now)
    case 'spawn_event':
      return reduceSpawnEvent(state, action.payload)
    case 'message_complete':
      return reduceMessageComplete(state)
    case 'stop_streaming':
      return reduceStopStreaming(state)
    case 'clear_messages':
      return createInitialChatStreamState()
    case 'add_thinking_message':
      return reduceAddThinkingMessage(state, action.now)
    default:
      return state
  }
}

function reduceMessageChunk(
  state: ChatStreamRuntimeState,
  message: StreamRealtimeMessage,
  now: number
): ChatStreamRuntimeState {
  if (state.isStopping) {
    return state
  }

  const content = message.content || ''
  const currentIndex = findMessageIndex(state.messages, state.currentStreamingMessageId)

  if (currentIndex === -1) {
    const newMessage: ChatMessage = {
      id: `temp-${now}`,
      role: 'assistant',
      content,
      timestamp: new Date(),
      toolCalls: [],
    }

    return {
      ...state,
      messages: [...state.messages, newMessage],
      isStreaming: true,
      currentStreamingMessageId: newMessage.id,
    }
  }

  const currentMessage = state.messages[currentIndex]
  const updatedMessage: ChatMessage = currentMessage.isThinking
    ? { ...currentMessage, isThinking: false, content }
    : { ...currentMessage, content: `${currentMessage.content || ''}${content}` }

  return {
    ...state,
    messages: replaceMessage(state.messages, currentIndex, updatedMessage),
    isStreaming: true,
    currentStreamingMessageId: updatedMessage.id,
  }
}

function reduceReasoningChunk(
  state: ChatStreamRuntimeState,
  message: StreamRealtimeMessage,
  now: number
): ChatStreamRuntimeState {
  if (state.isStopping) {
    return state
  }

  const content = message.content || ''
  const currentIndex = findMessageIndex(state.messages, state.currentStreamingMessageId)

  if (currentIndex === -1) {
    const newMessage: ChatMessage = {
      id: `temp-${now}`,
      role: 'assistant',
      content: '',
      reasoningContent: content,
      timestamp: new Date(),
      toolCalls: [],
      isThinking: true,
    }

    return {
      ...state,
      messages: [...state.messages, newMessage],
      isStreaming: true,
      currentStreamingMessageId: newMessage.id,
    }
  }

  const currentMessage = state.messages[currentIndex]
  const updatedMessage: ChatMessage = {
    ...currentMessage,
    reasoningContent: `${currentMessage.reasoningContent || ''}${content}`,
    isThinking: !Boolean(currentMessage.content),
  }

  return {
    ...state,
    messages: replaceMessage(state.messages, currentIndex, updatedMessage),
    isStreaming: true,
    currentStreamingMessageId: updatedMessage.id,
  }
}

function reduceToolCall(
  state: ChatStreamRuntimeState,
  message: StreamRealtimeMessage,
  now: number
): ChatStreamRuntimeState {
  const toolName = message.tool || message.tool_name
  if (!toolName) {
    return state
  }
  const toolCallId = `${now}-${toolName}`
  const initialToolCall: ChatToolCall = {
    id: toolCallId,
    name: toolName,
    arguments: message.arguments,
    status: 'running',
    progress: 0,
    progressMessage: null,
    progressDetails: null,
    messageId: message.messageId || null,
  }

  if (toolName === 'workflow_run') {
    initialToolCall.workflowAgents = {}
  }

  if (toolName === 'spawn') {
    const initLabel = message.arguments?.label || (message.arguments?.task || '').slice(0, 30)
    initialToolCall.spawn_task = {
      task_id: '',
      label: initLabel,
      status: 'pending',
      progress: 0,
      logs: [],
      tool_call_records: [],
    } as any
  }

  const currentIndex = findMessageIndex(state.messages, state.currentStreamingMessageId)
  const targetIndex = currentIndex === -1 ? state.messages.length : currentIndex
  const targetMessage =
    currentIndex === -1
      ? {
          id: `tool-${now}`,
          role: 'assistant' as const,
          content: '',
          timestamp: new Date(),
          toolCalls: [],
        }
      : state.messages[currentIndex]

  const toolCalls = [...(targetMessage.toolCalls || [])]
  const exists = toolCalls.some((toolCall) => toolCall.name === toolName && toolCall.status === 'running')
  if (exists) {
    return {
      ...state,
      isStreaming: true,
    }
  }

  const nextMessage: ChatMessage = {
    ...targetMessage,
    isThinking: false,
    toolCalls: [...toolCalls, initialToolCall],
  }

  const nextMessages =
    currentIndex === -1
      ? [...state.messages, nextMessage]
      : replaceMessage(state.messages, targetIndex, nextMessage)

  return {
    ...state,
    messages: nextMessages,
    isStreaming: true,
    currentStreamingMessageId: nextMessage.id,
    currentWorkflowToolCallId:
      toolName === 'workflow_run' ? toolCallId : state.currentWorkflowToolCallId,
    pendingSpawnLink:
      toolName === 'spawn'
        ? { messageId: nextMessage.id, toolCallId }
        : state.pendingSpawnLink,
  }
}

function reduceToolProgress(
  state: ChatStreamRuntimeState,
  message: StreamRealtimeMessage
): ChatStreamRuntimeState {
  const toolName = message.tool || message.tool_name
  if (!toolName) {
    return state
  }

  const match = findLatestRunningToolCall(state.messages, toolName, state.currentStreamingMessageId)
  if (!match) {
    return state
  }

  const targetMessage = state.messages[match.messageIndex]
  const toolCalls = [...(targetMessage.toolCalls || [])]
  const toolCall = toolCalls[match.toolCallIndex]

  toolCalls[match.toolCallIndex] = {
    ...toolCall,
    progress:
      message.progress === undefined || message.progress === null
        ? toolCall.progress ?? null
        : Number(message.progress),
    progressMessage:
      message.message === undefined ? toolCall.progressMessage ?? null : message.message,
    progressDetails: message.details ?? toolCall.progressDetails ?? null,
  }

  return {
    ...state,
    messages: replaceMessage(state.messages, match.messageIndex, {
      ...targetMessage,
      toolCalls,
    }),
  }
}

function reduceToolResult(
  state: ChatStreamRuntimeState,
  message: StreamRealtimeMessage
): ChatStreamRuntimeState {
  const toolName = message.tool || message.tool_name
  if (!toolName) {
    return state
  }

  const match = findLatestRunningToolCall(state.messages, toolName, state.currentStreamingMessageId)
  if (!match) {
    return state
  }

  const targetMessage = state.messages[match.messageIndex]
  const toolCalls = [...(targetMessage.toolCalls || [])]
  const toolCall = toolCalls[match.toolCallIndex]

  toolCalls[match.toolCallIndex] = {
    ...toolCall,
    status: 'success',
    result: message.result,
    duration: message.duration,
    progress: 100,
    progressMessage: null,
  }

  return {
    ...state,
    messages: replaceMessage(state.messages, match.messageIndex, {
      ...targetMessage,
      toolCalls,
    }),
  }
}

function reduceWorkflowEvent(
  state: ChatStreamRuntimeState,
  message: StreamRealtimeMessage,
  now: number
): ChatStreamRuntimeState {
  const messageIndex = findMessageIndex(state.messages, state.currentStreamingMessageId)
  if (messageIndex === -1 || !state.currentWorkflowToolCallId) {
    return state
  }

  const targetMessage = state.messages[messageIndex]
  const toolCalls = [...(targetMessage.toolCalls || [])]
  const workflowIndex = toolCalls.findIndex((toolCall) => toolCall.id === state.currentWorkflowToolCallId)
  if (workflowIndex === -1) {
    return state
  }

  const workflowToolCall = toolCalls[workflowIndex]
  const workflowAgents = { ...(workflowToolCall.workflowAgents || {}) }
  const agentId = message.agent_id

  if (message.type === 'workflow_agent_start') {
    workflowAgents[agentId] = {
      id: agentId,
      label: message.agent_label || agentId,
      status: 'running',
      toolCalls: [],
    }
  } else if (message.type === 'workflow_agent_chunk') {
    const agent = ensureWorkflowAgent(workflowAgents, agentId)
    workflowAgents[agentId] = {
      ...agent,
      streamingText: `${agent.streamingText || ''}${message.chunk || ''}`,
    }
  } else if (message.type === 'workflow_agent_tool_call') {
    const agent = ensureWorkflowAgent(workflowAgents, agentId)
    workflowAgents[agentId] = {
      ...agent,
      toolCalls: [
        ...(agent.toolCalls || []),
        {
          id: `${agentId}-${now}`,
          tool: message.tool,
          arguments: message.arguments || {},
          status: 'running',
        },
      ],
    }
  } else if (message.type === 'workflow_agent_tool_result') {
    const agent = ensureWorkflowAgent(workflowAgents, agentId)
    const toolCallRecords = [...(agent.toolCalls || [])]
    for (let index = toolCallRecords.length - 1; index >= 0; index -= 1) {
      if (toolCallRecords[index].tool === message.tool && toolCallRecords[index].status === 'running') {
        toolCallRecords[index] = {
          ...toolCallRecords[index],
          status: 'success',
          result: message.result,
        }
        break
      }
    }
    workflowAgents[agentId] = {
      ...agent,
      toolCalls: toolCallRecords,
    }
  } else if (message.type === 'workflow_agent_complete') {
    const agent = ensureWorkflowAgent(workflowAgents, agentId)
    workflowAgents[agentId] = {
      ...agent,
      status: 'complete',
      result: message.result,
      agentResult: message.result || '',
    }
  }

  toolCalls[workflowIndex] = {
    ...workflowToolCall,
    workflowAgents,
  }

  return {
    ...state,
    messages: replaceMessage(state.messages, messageIndex, {
      ...targetMessage,
      toolCalls,
    }),
  }
}

function reduceSpawnEvent(
  state: ChatStreamRuntimeState,
  message: StreamRealtimeMessage
): ChatStreamRuntimeState {
  if (message.type === 'task_created') {
    if (!state.pendingSpawnLink) {
      return state
    }

    const { messageId, toolCallId } = state.pendingSpawnLink
    const messageIndex = findMessageIndex(state.messages, messageId)
    if (messageIndex === -1) {
      return {
        ...state,
        pendingSpawnLink: null,
      }
    }

    const targetMessage = state.messages[messageIndex]
    const toolCalls = [...(targetMessage.toolCalls || [])]
    const toolCallIndex = toolCalls.findIndex((toolCall) => toolCall.id === toolCallId)
    if (toolCallIndex === -1 || !toolCalls[toolCallIndex].spawn_task) {
      return {
        ...state,
        pendingSpawnLink: null,
      }
    }

    toolCalls[toolCallIndex] = {
      ...toolCalls[toolCallIndex],
      spawn_task: {
        ...toolCalls[toolCallIndex].spawn_task!,
        task_id: message.task_id,
        label: message.label || toolCalls[toolCallIndex].spawn_task!.label,
        status: 'running',
      },
    }

    return {
      ...state,
      messages: replaceMessage(state.messages, messageIndex, {
        ...targetMessage,
        toolCalls,
      }),
      spawnTaskMap: {
        ...state.spawnTaskMap,
        [message.task_id]: state.pendingSpawnLink,
      },
      pendingSpawnLink: null,
    }
  }

  const spawnLink = state.spawnTaskMap[message.task_id]
  if (!spawnLink) {
    return state
  }

  const messageIndex = findMessageIndex(state.messages, spawnLink.messageId)
  if (messageIndex === -1) {
    return state
  }

  const targetMessage = state.messages[messageIndex]
  const toolCalls = [...(targetMessage.toolCalls || [])]
  const toolCallIndex = toolCalls.findIndex((toolCall) => toolCall.id === spawnLink.toolCallId)
  if (toolCallIndex === -1 || !toolCalls[toolCallIndex].spawn_task) {
    return state
  }

  const spawnTask: any = { ...(toolCalls[toolCallIndex].spawn_task as any) }

  if (message.type === 'task_status') {
    spawnTask.status = message.status
    if (message.progress !== undefined) spawnTask.progress = message.progress
  } else if (message.type === 'task_progress') {
    spawnTask.progress = message.progress
    if (message.message) spawnTask.progressMessage = message.message
  } else if (message.type === 'task_log') {
    spawnTask.logs = [
      ...(spawnTask.logs || []),
      { level: message.level, text: message.message, ts: message.timestamp },
    ]
  } else if (message.type === 'task_tool_call') {
    const newRecord = {
      tool_call_id:
        message.tool_call_id || `stc-${message.task_id}-${message.tool_name}-${message.timestamp}`,
      name: message.tool_name,
      arguments: message.arguments,
      status: 'running',
      result: undefined,
      duration_ms: undefined,
      _startTs: message.timestamp,
    }
    spawnTask.tool_call_records = [...(spawnTask.tool_call_records || []), newRecord]
  } else if (message.type === 'task_tool_result') {
    const toolCallRecords: any[] = [...(spawnTask.tool_call_records || [])]
    for (let index = toolCallRecords.length - 1; index >= 0; index -= 1) {
      const isMatch = message.tool_call_id
        ? toolCallRecords[index].tool_call_id === message.tool_call_id
        : toolCallRecords[index].name === message.tool_name && toolCallRecords[index].status === 'running'
      if (isMatch) {
        const durationMs = toolCallRecords[index]._startTs
          ? Math.round((message.timestamp - toolCallRecords[index]._startTs) * 1000)
          : undefined
        toolCallRecords[index] = {
          ...toolCallRecords[index],
          status: 'success',
          result: message.result,
          duration_ms: durationMs,
        }
        break
      }
    }
    spawnTask.tool_call_records = toolCallRecords
    spawnTask.progress = message.progress
  } else if (message.type === 'task_complete') {
    spawnTask.status = 'completed'
    spawnTask.progress = 100
    spawnTask.result = message.result || ''
  } else if (message.type === 'task_failed') {
    spawnTask.status = 'failed'
    spawnTask.error = message.error || ''
  }

  toolCalls[toolCallIndex] = {
    ...toolCalls[toolCallIndex],
    spawn_task: spawnTask,
  }

  const nextSpawnTaskMap = { ...state.spawnTaskMap }
  if (message.type === 'task_complete' || message.type === 'task_failed') {
    delete nextSpawnTaskMap[message.task_id]
  }

  return {
    ...state,
    messages: replaceMessage(state.messages, messageIndex, {
      ...targetMessage,
      toolCalls,
    }),
    spawnTaskMap: nextSpawnTaskMap,
  }
}

function reduceMessageComplete(state: ChatStreamRuntimeState): ChatStreamRuntimeState {
  const messageIndex = findMessageIndex(state.messages, state.currentStreamingMessageId)
  let nextMessages = state.messages

  if (messageIndex !== -1 && state.messages[messageIndex].isThinking) {
    nextMessages = replaceMessage(state.messages, messageIndex, {
      ...state.messages[messageIndex],
      isThinking: false,
      content: state.messages[messageIndex].content || '',
    })
  }

  return {
    ...state,
    messages: nextMessages,
    currentStreamingMessageId: null,
    currentWorkflowToolCallId: null,
    isStreaming: false,
    isStopping: false,
    pendingSpawnLink: null,
  }
}

function reduceStopStreaming(state: ChatStreamRuntimeState): ChatStreamRuntimeState {
  const messageIndex = findMessageIndex(state.messages, state.currentStreamingMessageId)
  let nextMessages = state.messages

  if (messageIndex !== -1) {
    const currentMessage = state.messages[messageIndex]
    const toolCalls = (currentMessage.toolCalls || []).map((toolCall) =>
      toolCall.status === 'running' ? { ...toolCall, status: 'cancelled' as const } : toolCall
    )
    nextMessages = replaceMessage(state.messages, messageIndex, {
      ...currentMessage,
      toolCalls,
    })
  }

  return {
    ...state,
    messages: nextMessages,
    currentStreamingMessageId: null,
    currentWorkflowToolCallId: null,
    isStreaming: false,
    isStopping: false,
  }
}

function reduceAddThinkingMessage(
  state: ChatStreamRuntimeState,
  now: number
): ChatStreamRuntimeState {
  const thinkingMessage: ChatMessage = {
    id: `assistant-${now}`,
    role: 'assistant',
    content: '',
    timestamp: new Date(),
    isThinking: true,
  }

  return {
    ...state,
    messages: [...state.messages, thinkingMessage],
    currentStreamingMessageId: thinkingMessage.id,
    currentWorkflowToolCallId: null,
    isStreaming: true,
  }
}

function ensureWorkflowAgent(
  workflowAgents: Record<string, WorkflowAgentState>,
  agentId: string
): WorkflowAgentState {
  return (
    workflowAgents[agentId] || {
      id: agentId,
      label: agentId,
      status: 'running',
      toolCalls: [],
    }
  )
}

function findLatestRunningToolCall(
  messages: ChatMessage[],
  toolName: string,
  preferredMessageId: string | null
): { messageIndex: number; toolCallIndex: number } | null {
  const preferredMessageIndex = findMessageIndex(messages, preferredMessageId)

  if (preferredMessageIndex !== -1) {
    const toolCallIndex = findRunningToolCallIndex(messages[preferredMessageIndex], toolName)
    if (toolCallIndex !== -1) {
      return { messageIndex: preferredMessageIndex, toolCallIndex }
    }
  }

  for (let messageIndex = messages.length - 1; messageIndex >= 0; messageIndex -= 1) {
    if (messageIndex === preferredMessageIndex) {
      continue
    }

    const toolCallIndex = findRunningToolCallIndex(messages[messageIndex], toolName)
    if (toolCallIndex !== -1) {
      return { messageIndex, toolCallIndex }
    }
  }

  return null
}

function findRunningToolCallIndex(message: ChatMessage, toolName: string): number {
  const toolCalls = message.toolCalls || []
  for (let index = toolCalls.length - 1; index >= 0; index -= 1) {
    if (toolCalls[index].name === toolName && toolCalls[index].status === 'running') {
      return index
    }
  }
  return -1
}

function findMessageIndex(messages: ChatMessage[], messageId: string | null): number {
  if (!messageId) {
    return -1
  }
  return messages.findIndex((message) => message.id === messageId)
}

function replaceMessage(
  messages: ChatMessage[],
  index: number,
  nextMessage: ChatMessage
): ChatMessage[] {
  const nextMessages = [...messages]
  nextMessages[index] = nextMessage
  return nextMessages
}
