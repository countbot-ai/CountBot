import { ref, nextTick } from 'vue'
import type { AgentTeam } from '@/store/agentTeams'

export function useChatInput() {
  const inputMessage = ref('')
  const textareaRef = ref<HTMLTextAreaElement>()
  const isInputFocused = ref(false)
  
  // @ 团队选择器状态
  const showTeamPicker = ref(false)
  const teamPickerQuery = ref('')
  const teamPickerIndex = ref(0)
  const atStartPos = ref(-1)
  
  // 调整输入框高度
  const adjustHeight = () => {
    nextTick(() => {
      if (textareaRef.value) {
        textareaRef.value.style.height = 'auto'
        textareaRef.value.style.height = `${Math.min(textareaRef.value.scrollHeight, 160)}px`
      }
    })
  }
  
  // 处理输入
  const handleInput = () => {
    adjustHeight()
    const ta = textareaRef.value
    if (!ta) return
    const cursor = ta.selectionStart ?? ta.value.length
    const text = ta.value
    
    // 从光标向前找最近的 @ 符号（遇到换行停止）
    let i = cursor - 1
    while (i >= 0 && text[i] !== '@' && text[i] !== '\n') i--
    
    if (i >= 0 && text[i] === '@') {
      const query = text.slice(i + 1, cursor)
      if (!query.includes(' ')) {
        atStartPos.value = i
        teamPickerQuery.value = query
        teamPickerIndex.value = 0
        showTeamPicker.value = true
        return
      }
    }
    // 没有找到有效 @ 前缀 → 关闭选择器
    showTeamPicker.value = false
    teamPickerQuery.value = ''
    atStartPos.value = -1
  }
  
  // 选中团队
  const selectTeam = (team: AgentTeam) => {
    const ta = textareaRef.value
    if (!ta) return
    const cursorPos = ta.selectionStart ?? inputMessage.value.length
    const before = inputMessage.value.slice(0, atStartPos.value)
    const after = inputMessage.value.slice(cursorPos)
    const insertion = `@${team.name} `
    inputMessage.value = before + insertion + after
    
    showTeamPicker.value = false
    teamPickerQuery.value = ''
    atStartPos.value = -1
    
    nextTick(() => {
      if (textareaRef.value) {
        const pos = before.length + insertion.length
        textareaRef.value.setSelectionRange(pos, pos)
        textareaRef.value.focus()
        adjustHeight()
      }
    })
  }
  
  // 关闭团队选择器
  const closeTeamPicker = () => {
    showTeamPicker.value = false
    teamPickerQuery.value = ''
    atStartPos.value = -1
  }
  
  // 检测操作系统
  const isMac = () => {
    return navigator.platform.toUpperCase().indexOf('MAC') >= 0 || 
           navigator.userAgent.toUpperCase().indexOf('MAC') >= 0
  }
  
  // 处理键盘事件
  const handleKeydown = (e: KeyboardEvent, filteredTeams: AgentTeam[], onSend: () => void) => {
    // 选择器打开时的导航
    if (showTeamPicker.value) {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        teamPickerIndex.value = Math.min(teamPickerIndex.value + 1, filteredTeams.length - 1)
        return
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        teamPickerIndex.value = Math.max(teamPickerIndex.value - 1, 0)
        return
      }
      if (e.key === 'Enter' && !e.shiftKey && !e.ctrlKey && !e.metaKey) {
        e.preventDefault()
        const team = filteredTeams[teamPickerIndex.value]
        if (team) selectTeam(team)
        return
      }
      if (e.key === 'Escape') {
        e.preventDefault()
        closeTeamPicker()
        return
      }
    }
    
    // 正常输入模式 - 根据平台处理发送快捷键
    if (e.key === 'Enter') {
      const macOS = isMac()
      
      if (macOS) {
        // Mac: Cmd+Enter 发送，Enter 换行
        if (e.metaKey && !e.shiftKey) {
          e.preventDefault()
          onSend()
        }
        // Enter 或 Shift+Enter 都是换行（默认行为）
      } else {
        // Windows/Linux: Enter 发送，Shift+Enter 换行
        if (e.shiftKey) {
          // Shift+Enter 换行（默认行为）
          return
        } else {
          // Enter 发送消息
          e.preventDefault()
          onSend()
        }
      }
    }
  }
  
  // 清空输入
  const clearInput = () => {
    inputMessage.value = ''
    if (textareaRef.value) {
      textareaRef.value.style.height = 'auto'
    }
  }
  
  return {
    // 状态
    inputMessage,
    textareaRef,
    isInputFocused,
    showTeamPicker,
    teamPickerQuery,
    teamPickerIndex,
    
    // 方法
    handleInput,
    handleKeydown,
    selectTeam,
    closeTeamPicker,
    adjustHeight,
    clearInput,
    
    // 工具函数
    isMac
  }
}
