/**
 * CJK 输入法确认键守卫。
 *
 * 输入法按 Enter 确认选词时，浏览器先派发 isComposing=true 的 keydown，
 * 随后在 compositionend 之后补一个 isComposing=false 的「伴生」Enter。
 * 伴生 Enter 与真实 Enter 事件对象一致，只能靠 compositionend 时间戳区分。
 *
 * 挂在 document 捕获阶段截断：Vue 的 @keydown.enter 只比较 event.key，
 * 逐处补判断会随新增控件持续遗漏。
 */

const GHOST_WINDOW_MS = 500
const EDITABLE_TAGS = new Set(['INPUT', 'TEXTAREA'])

type GuardHost = HTMLElement & {
  /** 最近一次 compositionend 的时刻，用于识别伴生 Enter */
  __imeCompositionEndAt?: number
  /** 伴生 Enter 的 keydown 已拦截，用此标记回收配对的 keyup */
  __imeGhostPending?: boolean
}

let installed = false

const asEditable = (target: EventTarget | null): GuardHost | null => {
  if (!(target instanceof HTMLElement)) return null
  if (EDITABLE_TAGS.has(target.tagName) || target.isContentEditable) {
    return target as GuardHost
  }
  return null
}

const isGhostWithinWindow = (host: GuardHost) =>
  performance.now() - (host.__imeCompositionEndAt ?? 0) < GHOST_WINDOW_MS

const handleCompositionStart = (event: CompositionEvent) => {
  const host = asEditable(event.target)
  if (host) host.__imeCompositionEndAt = 0
}

const handleCompositionEnd = (event: CompositionEvent) => {
  const host = asEditable(event.target)
  if (host) host.__imeCompositionEndAt = performance.now()
}

const handleKeyDown = (event: KeyboardEvent) => {
  if (event.key !== 'Enter') return
  const host = asEditable(event.target)
  if (!host) return

  if (event.isComposing) {
    // 组字中的 Enter 只用于确认候选词。不 preventDefault 以免影响输入法收键，
    // 只截断页面侧处理器。
    event.stopImmediatePropagation()
    return
  }

  if (isGhostWithinWindow(host)) {
    // 伴生 Enter 会同时落成 keydown 与 keyup，标记交给 keyup 阶段回收；
    // 时间戳当场复位，避免吞掉紧随的正常按键。
    host.__imeGhostPending = true
    host.__imeCompositionEndAt = 0
    event.preventDefault()
    event.stopImmediatePropagation()
    window.setTimeout(() => {
      host.__imeGhostPending = false
    }, GHOST_WINDOW_MS)
  }
}

const handleKeyUp = (event: KeyboardEvent) => {
  if (event.key !== 'Enter') return
  const host = asEditable(event.target)
  if (!host) return

  const ghost = host.__imeGhostPending === true
  host.__imeGhostPending = false
  if (ghost || event.isComposing) {
    event.preventDefault()
    event.stopImmediatePropagation()
  }
}

/** 全局安装一次，重复调用无副作用。 */
export const installImeGuard = () => {
  if (installed || typeof document === 'undefined') return
  installed = true
  document.addEventListener('compositionstart', handleCompositionStart, true)
  document.addEventListener('compositionend', handleCompositionEnd, true)
  document.addEventListener('keydown', handleKeyDown, true)
  document.addEventListener('keyup', handleKeyUp, true)
}
