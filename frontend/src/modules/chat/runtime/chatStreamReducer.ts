import type { ChatMessage, ChatMessageBlock, ChatToolCall, WorkflowAgentState } from '@/types/chat'

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
  | { type: 'tool_error'; payload: StreamRealtimeMessage }
  | { type: 'stream_error'; payload: StreamRealtimeMessage }
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
    case 'tool_error':
      return { type: 'tool_error', payload: message }
    case 'stream_error':
      return { type: 'stream_error', payload: message }
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
    case 'tool_error':
      return reduceToolError(state, action.payload)
    case 'stream_error':
      return reduceStreamError(state, action.payload)
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
      blocks: [{ type: 'text', text: content }],
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
    ? {
        ...currentMessage,
        isThinking: false,
        content,
        blocks: appendTextBlock(currentMessage.blocks, content),
      }
    : {
        ...currentMessage,
        content: `${currentMessage.content || ''}${content}`,
        blocks: appendTextBlock(currentMessage.blocks, content),
      }

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
    // 工具调用同步落进顺序块，后续正文会另起一个文本块，从而实现「正文 → 工具 → 正文」的交织
    blocks: [...(targetMessage.blocks || []), { type: 'tool', toolCallId }],
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

function reduceToolError(
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
    status: 'error',
    error: message.error ?? message.message ?? null,
    duration: message.duration_ms ?? message.duration ?? toolCall.duration ?? null,
    progress: null,
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

function reduceStreamError(
  state: ChatStreamRuntimeState,
  message: StreamRealtimeMessage
): ChatStreamRuntimeState {
  const errorText = message.message ?? message.error ?? null
  const messages = settleRunningToolCalls(state.messages, 'error', errorText)
  const messageIndex = findMessageIndex(messages, state.currentStreamingMessageId)
  let nextMessages = messages

  if (messageIndex !== -1 && messages[messageIndex].isThinking) {
    nextMessages = replaceMessage(messages, messageIndex, {
      ...messages[messageIndex],
      isThinking: false,
      content: messages[messageIndex].content || '',
    })
  }

  // 通用 error 表示本轮对话终止，继续等待只会让界面停在流式状态。
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
  // 本轮已经结束，任何仍在 running 的卡片都不会再收到终态事件（拦截、
  // 异常、事件丢失），必须在这里收敛，否则会一直转圈。
  let nextMessages = settleRunningToolCalls(state.messages, 'error', null)

  if (messageIndex !== -1 && nextMessages[messageIndex].isThinking) {
    nextMessages = replaceMessage(nextMessages, messageIndex, {
      ...nextMessages[messageIndex],
      isThinking: false,
      content: nextMessages[messageIndex].content || '',
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

/**
 * 正文 chunk 落到顺序块上：紧挨着的 chunk 合并进尾部文本块，
 * 一旦中间插入过工具调用，就另起一个文本块，保住「正文 → 工具 → 正文」的先后关系。
 */
function appendTextBlock(
  blocks: ChatMessageBlock[] | undefined,
  text: string
): ChatMessageBlock[] {
  const next = blocks ? [...blocks] : []
  const last = next[next.length - 1]

  if (last && last.type === 'text') {
    next[next.length - 1] = { type: 'text', text: last.text + text }
  } else {
    next.push({ type: 'text', text })
  }

  return next
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

function settleRunningToolCalls(
  messages: ChatMessage[],
  status: 'error' | 'cancelled',
  errorText: string | null
): ChatMessage[] {
  let changed = false
  const nextMessages = messages.map((message) => {
    const toolCalls = message.toolCalls
    if (!toolCalls || toolCalls.length === 0) {
      return message
    }

    let messageChanged = false
    const nextToolCalls: ChatToolCall[] = toolCalls.map((toolCall) => {
      // 子代理任务有独立的 spawn 事件流，主对话结束不代表后台任务结束。
      if (toolCall.status !== 'running' || toolCall.spawn_task) {
        return toolCall
      }
      messageChanged = true
      return {
        ...toolCall,
        status,
        error: toolCall.error ?? errorText,
        progress: null,
        progressMessage: null,
      }
    })

    if (!messageChanged) {
      return message
    }
    changed = true
    return { ...message, toolCalls: nextToolCalls }
  })

  return changed ? nextMessages : messages
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
