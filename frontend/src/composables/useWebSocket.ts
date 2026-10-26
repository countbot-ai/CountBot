import { ref } from 'vue'
import { useToast } from '@/composables/useToast'
import { t } from '@/i18n'

export interface WebSocketMessage {
  type: string
  [key: string]: any
}

export interface UseWebSocketOptions {
  onMessage?: (message: WebSocketMessage) => void
  /**
   * isReconnect 为 true 表示这是断线恢复后建立的连接，
   * 调用方可据此补齐断线期间错过的数据。
   */
  onOpen?: (isReconnect: boolean) => void
  onClose?: (event: CloseEvent) => void
  onError?: (error: Event) => void
  /**
   * 返回 true 表示当前有请求正在处理。服务端事件循环在跑对话时读不到 ping，
   * 此时不能用 pong 超时判定连接已失活，否则会误杀正常的长时间输出。
   */
  isBusy?: () => boolean
}

// 快速重连最多 10 次，耗尽后转为后台慢速轮询，网络恢复后仍能自愈
const MAX_RECONNECT_ATTEMPTS = 10
const BASE_RECONNECT_DELAY = 1000
const MAX_RECONNECT_DELAY = 30000
const SLOW_RETRY_DELAY = 60000

const HEARTBEAT_INTERVAL = 25000
const PONG_TIMEOUT = 65000

// 连续握手失败达到该次数后给出排查提示（握手被拒通常只能拿到 1006）
const HANDSHAKE_HINT_THRESHOLD = 3

/**
 * 服务端明确告知、重试没有意义的关闭。
 * 1011 带原因时才认定是模型服务不可用；不带原因的 1011 仍按普通故障重试。
 */
function isFatalClose(event: CloseEvent): boolean {
  if (event.code === 4001 || event.code === 4003) return true
  return event.code === 1011 && Boolean(event.reason)
}

export function useWebSocket() {
  const toast = useToast()

  const isConnected = ref(true)
  const isConnecting = ref(false)
  const reconnectAttempts = ref(0)
  const reconnectingVisible = ref(false)
  const reconnectAttemptsDisplay = ref(0)
  const connectionError = ref('')

  let ws: WebSocket | null = null
  let wsSessionId: string | null = null
  let desiredSessionId: string | null = null

  let heartbeatInterval: number | null = null
  let lastPongAt = 0
  let reconnectTimer: number | null = null
  let reconnectInFlight = false
  let handshakeFailures = 0
  let exhaustedNotified = false
  let fatal = false
  let disposed = false
  let listenersAttached = false

  let messageHandler: ((message: WebSocketMessage) => void) | null = null
  let openHandler: ((isReconnect: boolean) => void) | null = null
  let closeHandler: ((event: CloseEvent) => void) | null = null
  let errorHandler: ((error: Event) => void) | null = null
  let busyProbe: (() => boolean) | null = null

  // ------------------------------------------------------------------
  // 心跳
  // ------------------------------------------------------------------
  function stopHeartbeat() {
    if (heartbeatInterval !== null) {
      window.clearInterval(heartbeatInterval)
      heartbeatInterval = null
    }
  }

  function startHeartbeat(socket: WebSocket) {
    stopHeartbeat()
    lastPongAt = Date.now()

    heartbeatInterval = window.setInterval(() => {
      if (socket !== ws || socket.readyState !== WebSocket.OPEN) {
        return
      }

      // 有请求在跑时服务端无法及时回 pong，视为存活；
      // 仅在空闲状态下用 pong 超时判定连接是否已经失活。
      if (busyProbe?.() === true) {
        lastPongAt = Date.now()
      } else if (Date.now() - lastPongAt > PONG_TIMEOUT) {
        console.warn('[useWebSocket] 心跳超时，主动断开以触发重连')
        socket.close(4000, 'heartbeat timeout')
        return
      }

      try {
        socket.send(JSON.stringify({ type: 'ping' }))
      } catch (error) {
        console.error('[useWebSocket] 心跳发送失败:', error)
        socket.close()
      }
    }, HEARTBEAT_INTERVAL)
  }

  // ------------------------------------------------------------------
  // 重连调度
  // ------------------------------------------------------------------
  function getReconnectDelay(attempt: number): number {
    const base = Math.min(
      BASE_RECONNECT_DELAY * Math.pow(2, Math.max(attempt - 1, 0)),
      MAX_RECONNECT_DELAY
    )
    return Math.round(base + base * 0.2 * Math.random())
  }

  function clearReconnectTimer() {
    if (reconnectTimer !== null) {
      window.clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
  }

  function scheduleReconnect() {
    if (disposed || fatal || !desiredSessionId) return
    // 同一时刻只允许一个待执行的重连任务
    if (reconnectTimer !== null) return

    if (reconnectAttempts.value >= MAX_RECONNECT_ATTEMPTS) {
      reconnectingVisible.value = false
      if (!exhaustedNotified) {
        exhaustedNotified = true
        toast.error(t('chat.connectionStatus.retryExhausted'))
      }
      // 后台慢速轮询，网络或服务恢复后自动重连
      reconnectTimer = window.setTimeout(() => {
        reconnectTimer = null
        void attemptReconnect()
      }, SLOW_RETRY_DELAY)
      return
    }

    reconnectAttempts.value += 1
    reconnectAttemptsDisplay.value = reconnectAttempts.value
    reconnectingVisible.value = true

    const delay = getReconnectDelay(reconnectAttempts.value)
    console.log(
      `[useWebSocket] ${delay}ms 后进行第 ${reconnectAttempts.value}/${MAX_RECONNECT_ATTEMPTS} 次重连`
    )

    reconnectTimer = window.setTimeout(() => {
      reconnectTimer = null
      void attemptReconnect()
    }, delay)
  }

  async function attemptReconnect() {
    const sessionId = desiredSessionId
    if (disposed || fatal || !sessionId || reconnectInFlight) return
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return

    reconnectInFlight = true
    try {
      const ready = await isServerReady()
      if (disposed || fatal) return
      if (!ready) {
        scheduleReconnect()
        return
      }
      openSocket(sessionId, true)
    } finally {
      reconnectInFlight = false
    }
  }

  // ------------------------------------------------------------------
  // 连接生命周期
  // ------------------------------------------------------------------
  function isServerReady(): Promise<boolean> {
    return fetch('/api/health', {
      method: 'GET',
      signal: AbortSignal.timeout(2000),
    })
      .then((response) => response.ok)
      .catch(() => false)
  }

  function closeSocket() {
    const socket = ws
    // 先摘掉引用，旧 socket 的回调会被代际检查拦掉，不会污染新连接的状态
    ws = null
    wsSessionId = null
    stopHeartbeat()

    if (!socket) return
    try {
      socket.close(1000, 'client closing')
    } catch {
      // 已经关闭时忽略
    }
  }

  function describeFatalClose(event: CloseEvent): string {
    if (event.code === 4001) {
      return t('chat.connectionStatus.authRequired')
    }
    if (event.code === 4003) {
      return t('chat.connectionStatus.setupRequired')
    }
    if (event.code === 1011) {
      return t('chat.connectionStatus.providerUnavailable', {
        reason: event.reason || t('chat.connectionStatus.serverRejected'),
      })
    }
    return event.reason || t('chat.connectionStatus.disconnected')
  }

  function handleFatalClose(event: CloseEvent) {
    fatal = true
    clearReconnectTimer()
    reconnectingVisible.value = false
    reconnectAttempts.value = 0
    reconnectAttemptsDisplay.value = 0
    connectionError.value = describeFatalClose(event)
    toast.error(connectionError.value)
  }

  function openSocket(sessionId: string, isReconnect: boolean) {
    closeSocket()

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const socket = new WebSocket(`${protocol}//${window.location.host}/ws/chat`)
    let opened = false

    ws = socket
    wsSessionId = sessionId
    isConnecting.value = true

    socket.onopen = () => {
      // 旧连接迟到的回调直接忽略
      if (socket !== ws) return
      opened = true

      isConnected.value = true
      isConnecting.value = false
      reconnectingVisible.value = false
      connectionError.value = ''
      reconnectAttempts.value = 0
      reconnectAttemptsDisplay.value = 0
      handshakeFailures = 0
      exhaustedNotified = false
      clearReconnectTimer()

      startHeartbeat(socket)

      try {
        socket.send(JSON.stringify({ type: 'subscribe', sessionId }))
      } catch (error) {
        console.error('[useWebSocket] 订阅会话失败:', error)
      }

      openHandler?.(isReconnect)
    }

    socket.onmessage = (event) => {
      if (socket !== ws) return

      try {
        const message = JSON.parse(event.data)

        if (message.type === 'pong') {
          lastPongAt = Date.now()
          return
        }

        messageHandler?.(message)
      } catch (error) {
        console.error('[useWebSocket] 解析消息失败:', error)
      }
    }

    socket.onerror = (error) => {
      if (socket !== ws) return
      console.error('[useWebSocket] WebSocket error:', error)
      isConnected.value = false
      isConnecting.value = false
      // 不在这里排重连：error 之后必然会触发 close，统一在 onclose 里处理，避免重复计数
      errorHandler?.(error)
    }

    socket.onclose = (event) => {
      if (socket !== ws) return

      ws = null
      wsSessionId = null
      isConnected.value = false
      isConnecting.value = false
      stopHeartbeat()
      closeHandler?.(event)

      if (isFatalClose(event)) {
        handleFatalClose(event)
        return
      }

      // 握手都没完成通常是服务端拒绝（未认证 / 未初始化 / 模型不可用），
      // 浏览器只会给出 1006，这里累计次数后给出排查提示。
      if (opened) {
        handshakeFailures = 0
      } else {
        handshakeFailures += 1
        if (handshakeFailures >= HANDSHAKE_HINT_THRESHOLD) {
          connectionError.value = t('chat.connectionStatus.handshakeRejected')
        }
      }

      if (!desiredSessionId) return
      scheduleReconnect()
    }
  }

  function connectWebSocket(sessionId: string) {
    if (!sessionId) return

    disposed = false
    fatal = false
    desiredSessionId = sessionId
    attachNetworkListeners()

    const active = ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)
    if (active && wsSessionId === sessionId) {
      return
    }

    clearReconnectTimer()
    reconnectAttempts.value = 0
    reconnectAttemptsDisplay.value = 0
    reconnectingVisible.value = false
    connectionError.value = ''
    exhaustedNotified = false

    openSocket(sessionId, false)
  }

  function manualReconnect(sessionId?: string) {
    const target = sessionId || desiredSessionId
    if (!target) return

    console.log('[useWebSocket] 手动重连')
    disposed = false
    fatal = false
    exhaustedNotified = false
    desiredSessionId = target
    reconnectAttempts.value = 0
    reconnectAttemptsDisplay.value = 0
    reconnectingVisible.value = true
    connectionError.value = ''
    handshakeFailures = 0

    clearReconnectTimer()
    attachNetworkListeners()
    closeSocket()
    void attemptReconnect()
  }

  function closeConnection() {
    disposed = true
    desiredSessionId = null
    clearReconnectTimer()
    closeSocket()
    detachNetworkListeners()

    isConnecting.value = false
    reconnectingVisible.value = false
    connectionError.value = ''
    reconnectAttempts.value = 0
    reconnectAttemptsDisplay.value = 0
    handshakeFailures = 0
  }

  // ------------------------------------------------------------------
  // 网络/页面可见性变化时立即重试，不必等退避计时器
  // ------------------------------------------------------------------
  function tryRecoverImmediately() {
    if (disposed || fatal || !desiredSessionId) return
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return

    clearReconnectTimer()
    if (!reconnectingVisible.value && reconnectAttempts.value < MAX_RECONNECT_ATTEMPTS) {
      reconnectingVisible.value = true
      if (reconnectAttemptsDisplay.value === 0) {
        reconnectAttemptsDisplay.value = reconnectAttempts.value
      }
    }
    void attemptReconnect()
  }

  function handleOnline() {
    tryRecoverImmediately()
  }

  function handleVisibilityChange() {
    if (document.visibilityState !== 'visible') return
    tryRecoverImmediately()
  }

  function attachNetworkListeners() {
    if (listenersAttached) return
    window.addEventListener('online', handleOnline)
    document.addEventListener('visibilitychange', handleVisibilityChange)
    listenersAttached = true
  }

  function detachNetworkListeners() {
    if (!listenersAttached) return
    window.removeEventListener('online', handleOnline)
    document.removeEventListener('visibilitychange', handleVisibilityChange)
    listenersAttached = false
  }

  // ------------------------------------------------------------------
  // 对外方法
  // ------------------------------------------------------------------
  function sendMessage(message: any) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(message))
      return true
    }
    return false
  }

  function setHandlers(options: UseWebSocketOptions) {
    messageHandler = options.onMessage || null
    openHandler = options.onOpen || null
    closeHandler = options.onClose || null
    errorHandler = options.onError || null
    busyProbe = options.isBusy || null
  }

  return {
    // 状态
    isConnected,
    isConnecting,
    reconnectAttempts,
    reconnectingVisible,
    reconnectAttemptsDisplay,
    connectionError,
    maxReconnectAttempts: MAX_RECONNECT_ATTEMPTS,

    // 方法
    connectWebSocket,
    sendMessage,
    closeConnection,
    manualReconnect,
    setHandlers,

    // 获取 WebSocket 实例
    getWebSocket: () => ws,
  }
}
