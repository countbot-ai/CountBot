import { ref, computed, nextTick, onBeforeUnmount, type Ref } from 'vue'
import { useMarkdown } from '@/composables/useMarkdown'
import type { Message } from './useMessageStreaming'

export function useMessageReplay(message: Ref<Message>) {
  const { renderMarkdown } = useMarkdown()
  
  const isReplaying = ref(false)
  const replayContent = ref<string | null>(null)
  const replayToolIndex = ref(0)
  const replayWorkflowVisibleCounts = ref<Record<string, number>>({})
  const replaySpawnVisibleCounts = ref<Record<string, number>>({})
  const replayToolResultVisible = ref<Record<string, boolean>>({})
  const replayInterleavedSegments = ref(0)
  
  let replayTimer: number | null = null
  const rootEl = ref<HTMLElement>()
  
  // 判断是否使用交织模式
  const useInterleavedMode = computed(() => {
    if (!message.value.content || !message.value.toolCalls || message.value.toolCalls.length === 0) {
      return false
    }
    
    const hasSpecialTools = message.value.toolCalls.some(
      tc => tc.name === 'workflow_run' || tc.name === 'spawn'
    )
    
    return !hasSpecialTools
  })
  
  // 可见的工具调用
  const visibleToolCalls = computed(() => {
    const all = message.value.toolCalls || []
    if (!isReplaying.value) return all
    return all.slice(0, replayToolIndex.value)
  })
  
  // 查找最近的可滚动祖先元素
  const findScrollContainer = (): HTMLElement | null => {
    let el: HTMLElement | null = rootEl.value ?? null
    while (el) {
      if (el.classList.contains('message-list-container')) return el
      el = el.parentElement
    }
    return null
  }
  
  // 将目标元素滚动到可滚动容器的视口内
  const scrollElementIntoContainer = (target: HTMLElement) => {
    const container = findScrollContainer()
    if (!container) {
      target.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
      return
    }
    const containerRect = container.getBoundingClientRect()
    const targetRect = target.getBoundingClientRect()
    const targetBottom = targetRect.bottom - containerRect.top + container.scrollTop
    const targetTop = targetRect.top - containerRect.top + container.scrollTop
    const visibleBottom = container.scrollTop + container.clientHeight
    
    if (targetBottom > visibleBottom) {
      container.scrollTo({ top: targetBottom - container.clientHeight + 16, behavior: 'smooth' })
    } else if (targetTop < container.scrollTop) {
      container.scrollTo({ top: targetTop - 16, behavior: 'smooth' })
    }
  }
  
  // 逐个展示 workflow_run 面板中的子 Agent
  const animateWorkflowAgents = (tc: any, onComplete: () => void) => {
    if (!isReplaying.value) return
    const agents = Object.values(tc.workflowAgents || {})
    const current = replayWorkflowVisibleCounts.value[tc.id] ?? 0
    if (current < agents.length) {
      replayWorkflowVisibleCounts.value[tc.id] = current + 1
      nextTick(() => {
        const panel = rootEl.value?.querySelector<HTMLElement>(`.wf-run-panel[data-tc-id="${tc.id}"]`)
        const items = panel?.querySelectorAll<HTMLElement>('.wf-agent-item')
        if (items && items.length > 0) {
          scrollElementIntoContainer(items[items.length - 1])
        }
      })
      replayTimer = window.setTimeout(() => animateWorkflowAgents(tc, onComplete), 500)
    } else {
      onComplete()
    }
  }
  
  // 逐个展示 spawn 面板中的子代理工具调用
  const animateSpawnToolCalls = (tc: any, onComplete: () => void) => {
    if (!isReplaying.value) return
    const toolCalls = tc.spawn_task?.tool_call_records || []
    const current = replaySpawnVisibleCounts.value[tc.id] ?? 0
    
    if (current < toolCalls.length) {
      replaySpawnVisibleCounts.value[tc.id] = current + 1
      nextTick(() => {
        const panel = rootEl.value?.querySelector<HTMLElement>(`.spawn-card[data-tool-call-id="${tc.id}"]`)
        if (panel) {
          scrollElementIntoContainer(panel)
        }
      })
      replayTimer = window.setTimeout(() => animateSpawnToolCalls(tc, onComplete), 400)
    } else {
      onComplete()
    }
  }
  
  // 逐个显示工具调用
  const showToolCallsSequentially = () => {
    if (!isReplaying.value) return
    
    const toolCalls = message.value.toolCalls || []
    if (replayToolIndex.value < toolCalls.length) {
      replayToolIndex.value++
      const justRevealed = toolCalls[replayToolIndex.value - 1]
      
      if (justRevealed?.name === 'workflow_run') {
        replayWorkflowVisibleCounts.value[justRevealed.id] = 0
        replayTimer = window.setTimeout(() => {
          animateWorkflowAgents(justRevealed, () => {
            replayTimer = window.setTimeout(showToolCallsSequentially, 400)
          })
        }, 300)
      } else if (justRevealed?.name === 'spawn' && justRevealed.spawn_task) {
        replaySpawnVisibleCounts.value[justRevealed.id] = 0
        replayTimer = window.setTimeout(() => {
          animateSpawnToolCalls(justRevealed, () => {
            replayTimer = window.setTimeout(showToolCallsSequentially, 400)
          })
        }, 300)
      } else {
        replayToolResultVisible.value[justRevealed.id] = false
        replayTimer = window.setTimeout(() => {
          if (isReplaying.value && justRevealed.result) {
            replayToolResultVisible.value[justRevealed.id] = true
          }
          replayTimer = window.setTimeout(showToolCallsSequentially, 300)
        }, 500)
      }
    } else {
      if (message.value.content) {
        replayTimer = window.setTimeout(startTextReplay, 300)
      } else {
        stopReplay()
      }
    }
  }
  
  // 开始文字重放
  const startTextReplay = () => {
    if (!isReplaying.value || !message.value.content) return
    
    replayContent.value = ''
    const rawText = message.value.content
    let charIndex = 0
    const speed = 15
    
    const tick = () => {
      if (!isReplaying.value) return
      
      const step = Math.min(3, rawText.length - charIndex)
      charIndex += step
      
      const partial = rawText.slice(0, charIndex)
      replayContent.value = renderMarkdown(partial)
      
      if (charIndex >= rawText.length) {
        stopReplay()
        return
      }
      
      replayTimer = window.setTimeout(tick, speed)
    }
    
    replayTimer = window.setTimeout(tick, speed)
  }
  
  // 交织模式重放
  const startInterleavedReplay = () => {
    if (!isReplaying.value) return
    
    const toolCalls = message.value.toolCalls || []
    
    if (toolCalls.length > 0) {
      showInterleavedTools()
    } else {
      startTextReplay()
    }
  }
  
  // 交织模式：逐个显示工具调用
  const showInterleavedTools = () => {
    if (!isReplaying.value) return
    
    const toolCalls = message.value.toolCalls || []
    if (replayInterleavedSegments.value < toolCalls.length) {
      replayInterleavedSegments.value++
      replayTimer = window.setTimeout(showInterleavedTools, 500)
    } else {
      if (message.value.content) {
        replayTimer = window.setTimeout(startTextReplay, 500)
      } else {
        stopReplay()
      }
    }
  }
  
  // 开始重放
  const handleReplay = (onReplayStart?: (messageId: string) => void) => {
    if (isReplaying.value) {
      stopReplay()
      return
    }
    
    const hasContent = message.value.content
    const hasToolCalls = message.value.toolCalls && message.value.toolCalls.length > 0
    if (!hasContent && !hasToolCalls) return
    
    // 先清空所有内容
    isReplaying.value = true
    replayContent.value = null
    replayToolIndex.value = 0
    replayInterleavedSegments.value = 0
    
    // 通知父组件滚动到此消息
    if (onReplayStart) {
      onReplayStart(message.value.id)
    }
    
    // 延迟后开始重放
    replayTimer = window.setTimeout(() => {
      if (useInterleavedMode.value) {
        startInterleavedReplay()
      } else if (hasToolCalls) {
        showToolCallsSequentially()
      } else {
        startTextReplay()
      }
    }, 300)
  }
  
  // 停止重放
  const stopReplay = () => {
    isReplaying.value = false
    replayContent.value = null
    replayToolIndex.value = 0
    replayWorkflowVisibleCounts.value = {}
    replaySpawnVisibleCounts.value = {}
    replayToolResultVisible.value = {}
    replayInterleavedSegments.value = 0
    if (replayTimer) {
      clearTimeout(replayTimer)
      replayTimer = null
    }
  }
  
  // 获取普通工具调用是否显示结果
  const shouldShowToolResult = (toolCallId: string): boolean => {
    if (!isReplaying.value) return true
    return replayToolResultVisible.value[toolCallId] ?? false
  }
  
  // 获取 spawn 面板中可见的工具调用数量
  const getSpawnVisibleCount = (toolCallId: string): number | undefined => {
    if (!isReplaying.value) return undefined
    return replaySpawnVisibleCounts.value[toolCallId]
  }
  
  // 获取 workflow 面板中可见的 agent 数量
  const visibleAgents = (toolCall: any): any[] => {
    const all = Object.values(toolCall.workflowAgents || {})
    if (!isReplaying.value) return all
    const count = replayWorkflowVisibleCounts.value[toolCall.id]
    if (count === undefined) return []
    return all.slice(0, count)
  }
  
  // 清理
  onBeforeUnmount(() => {
    stopReplay()
  })
  
  return {
    // 状态
    isReplaying,
    replayContent,
    replayInterleavedSegments,
    rootEl,
    useInterleavedMode,
    visibleToolCalls,
    
    // 方法
    handleReplay,
    stopReplay,
    shouldShowToolResult,
    getSpawnVisibleCount,
    visibleAgents
  }
}
