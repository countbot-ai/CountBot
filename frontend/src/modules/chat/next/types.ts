import type { Component } from 'vue'

export interface WelcomeQuickAction {
  id: string
  label: string
  icon: Component
  kind: 'settings' | 'panel'
  value: string
}
