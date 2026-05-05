/**
 * Toast 通知 Composable
 */

import { emitToast, normalizeToastExtra, type ToastExtra, type ToastOptions } from './toastBus'

export type { ToastExtra, ToastOptions } from './toastBus'

export function useToast() {
  const show = (options: ToastOptions) => {
    emitToast({
      duration: 3000,
      closable: true,
      ...options
    })
  }

  return {
    success: (message: string, extra?: ToastExtra) => show({ ...normalizeToastExtra(extra), type: 'success', message }),
    error: (message: string, extra?: ToastExtra) => show({ ...normalizeToastExtra(extra), type: 'error', message }),
    warning: (message: string, extra?: ToastExtra) => show({ ...normalizeToastExtra(extra), type: 'warning', message }),
    info: (message: string, extra?: ToastExtra) => show({ ...normalizeToastExtra(extra), type: 'info', message })
  }
}
