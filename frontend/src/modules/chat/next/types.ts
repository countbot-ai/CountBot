import type { Component } from 'vue'

/**
 * 顶部导航分区：
 * - sessions 为聊天视图（会话列表 + 对话窗口）
 * - 其余分区为整屏页面，聊天窗口不参与渲染
 */
export type ChatSection =
  | 'sessions'
  | 'cron'
  | 'skills'
  | 'wiki'
  | 'multiagent'
  | 'channels'
  | 'persona'

export interface WelcomeQuickAction {
  id: string
  label: string
  icon: Component
  kind: 'settings' | 'panel'
  value: string
}
