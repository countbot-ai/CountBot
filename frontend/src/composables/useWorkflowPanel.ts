import { ref } from 'vue'

export function useWorkflowPanel() {
  // 存储每个 workflow_run toolCall 的面板展开状态
  const wfPanelExpanded = ref<Record<string, boolean>>({})
  // 存储每个 agent 的工具调用展开状态
  const wfAgentExpanded = ref<Record<string, boolean>>({})
  // 存储每个 workflow_run 面板的并排对比模式状态
  const wfCompareMode = ref<Record<string, boolean>>({})
  
  /**
   * 判断 workflow 面板是否展开
   * - 用户手动切换过：使用手动状态
   * - 否则：运行中自动展开，完成后折叠
   */
  const isWfPanelOpen = (tcId: string, status?: string): boolean => {
    if (wfPanelExpanded.value[tcId] !== undefined) return wfPanelExpanded.value[tcId]
    return status === 'running'
  }
  
  const toggleWorkflowPanel = (tcId: string, status?: string) => {
    const cur = isWfPanelOpen(tcId, status)
    wfPanelExpanded.value = { ...wfPanelExpanded.value, [tcId]: !cur }
  }
  
  /** 判断某个 agent 是否展开 */
  const isAgentOpen = (tcId: string, agentId: string, status?: string): boolean => {
    const key = `${tcId}:${agentId}`
    if (wfAgentExpanded.value[key] !== undefined) return wfAgentExpanded.value[key]
    return status === 'running'
  }
  
  const toggleAgentPanel = (tcId: string, agentId: string, status?: string) => {
    const key = `${tcId}:${agentId}`
    const cur = isAgentOpen(tcId, agentId, status)
    wfAgentExpanded.value = { ...wfAgentExpanded.value, [key]: !cur }
  }
  
  return {
    // 状态
    wfPanelExpanded,
    wfAgentExpanded,
    wfCompareMode,
    
    // 方法
    isWfPanelOpen,
    toggleWorkflowPanel,
    isAgentOpen,
    toggleAgentPanel
  }
}
