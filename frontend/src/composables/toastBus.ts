export type ToastType = 'success' | 'error' | 'warning' | 'info'

export interface ToastOptions {
  id?: string
  type?: ToastType
  title?: string
  message: string
  duration?: number
  closable?: boolean
}

export type ToastExtra = string | Omit<Partial<ToastOptions>, 'message' | 'type'>

export const TOAST_EVENT = 'countbot:toast'

export function normalizeToastExtra(extra?: ToastExtra): Omit<Partial<ToastOptions>, 'message' | 'type'> {
  if (!extra) {
    return {}
  }

  if (typeof extra === 'string') {
    return { title: extra }
  }

  return extra
}

export function emitToast(options: ToastOptions) {
  if (typeof window === 'undefined') {
    return
  }

  window.dispatchEvent(new CustomEvent<ToastOptions>(TOAST_EVENT, { detail: options }))
}
