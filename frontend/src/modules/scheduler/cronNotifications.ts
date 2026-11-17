/**
 * 定时任务网页通知事件总线。
 *
 * 后端通过 WebSocket 下发 `cron_job_result`，聊天实时层转换为该事件；
 * 通知中心与详情弹窗只依赖事件，不直接耦合 WebSocket 生命周期。
 */

export interface CronResultNotification {
  jobId: string
  jobName: string
  status: 'ok' | 'error' | string
  channel?: string | null
  response?: string | null
  error?: string | null
  deliveryStatus?: string | null
  isManual?: boolean
}

export const CRON_RESULT_EVENT = 'countbot:cron-result'

export function emitCronResultNotification(payload: CronResultNotification): void {
  if (typeof window === 'undefined') {
    return
  }
  window.dispatchEvent(new CustomEvent<CronResultNotification>(CRON_RESULT_EVENT, { detail: payload }))
}

export function onCronResultNotification(
  handler: (payload: CronResultNotification) => void,
): () => void {
  if (typeof window === 'undefined') {
    return () => {}
  }
  const listener = (event: Event) => {
    const detail = (event as CustomEvent<CronResultNotification>).detail
    if (detail?.jobId) {
      handler(detail)
    }
  }
  window.addEventListener(CRON_RESULT_EVENT, listener as EventListener)
  return () => window.removeEventListener(CRON_RESULT_EVENT, listener as EventListener)
}
