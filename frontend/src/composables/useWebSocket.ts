import { ref } from 'vue'
import { useToast } from '@/composables/useToast'

export interface WebSocketMessage {
  type: string
  [key: string]: any
}

export interface UseWebSocketOptions {
  onMessage?: (message: WebSocketMessage) => void
  onOpen?: () => void
  onClose?: (event: CloseEvent) => void
  onError?: (error: Event) => void
}

export function useWebSocket() {
  const toast = useToast()
  
  const isConnected = ref(true)
  const isConnecting = ref(false)
  const reconnectAttempts = ref(0)
  const reconnectingVisible = ref(false)
  const reconnectAttemptsDisplay = ref(0)
  
  let ws: WebSocket | null = null
  let heartbeatInterval: number | null = null
  let currentConnectedSessionId: string | null = null
  let heartbeatFailures = 0
  
  const maxReconnectAttempts = 10
  const baseReconnectDelay = 1000
  const maxHeartbeatFailures = 3
  
  let messageHandler: ((message: WebSocketMessage) => void) | null = null
  let openHandler: (() => void) | null = null
  let closeHandler: ((event: CloseEvent) => void) | null = null
  let errorHandler: ((error: Event) => void) | null = null
  
  // 心跳机制
  function startHeartbeat() {
    if (heartbeatInterval) {
      clearInterval(heartbeatInterval)
    }
    
    heartbeatFailures = 0
    
    heartbeatInterval = window.setInterval(() => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        try {
          ws.send(JSON.stringify({ type: 'ping' }))
        } catch (error) {
          console.error('[useWebSocket] 心跳发送失败:', error)
          heartbeatFailures++
          
          if (heartbeatFailures >= maxHeartbeatFailures) {
            console.log('[useWebSocket] 心跳失败次数过多，关闭连接')
            stopHeartbeat()
            if (ws) {
              ws.close()
            }
          }
        }
      } else if (ws && ws.readyState === WebSocket.CLOSED) {
        // 连接已关闭，停止心跳
        stopHeartbeat()
      }
    }, 30000)
  }
  
  function stopHeartbeat() {
    if (heartbeatInterval) {
      clearInterval(heartbeatInterval)
      heartbeatInterval = null
    }
  }
  
  // 计算重连延迟（指数退避）
  function getReconnectDelay(): number {
    const delay = Math.min(
      baseReconnectDelay * Math.pow(2, reconnectAttempts.value),
      30000
    )
    return delay
  }
  
  // 检查服务器是否就绪
  async function isServerReady(): Promise<boolean> {
    try {
      const response = await fetch('/api/health', {
        method: 'GET',
        signal: AbortSignal.timeout(2000)
      })
      return response.ok
    } catch {
      return false
    }
  }
  
  // 带健康检查的重连
  async function reconnectWithHealthCheck(sessionId: string) {
    console.log(`[useWebSocket] 开始重连检查 (第 ${reconnectAttemptsDisplay.value}/${maxReconnectAttempts} 次)`)
    
    const ready = await isServerReady()
    
    if (ready) {
      console.log('[useWebSocket] 服务器就绪，开始重连')
      connectWebSocket(sessionId)
    } else {
      console.log('[useWebSocket] 服务器未就绪')
      if (reconnectAttempts.value < maxReconnectAttempts) {
        const delay = getReconnectDelay()
        console.log(`[useWebSocket] ${delay}ms 后重试`)
        
        setTimeout(() => {
          if (!ws || ws.readyState === WebSocket.CLOSED) {
            reconnectAttempts.value++
            reconnectAttemptsDisplay.value = reconnectAttempts.value
            reconnectWithHealthCheck(sessionId)
          }
        }, delay)
      } else {
        console.log('[useWebSocket] 达到最大重连次数，停止重连')
        reconnectingVisible.value = false
        toast.error('连接失败，请点击状态条重试或刷新页面')
      }
    }
  }
  
  // 手动重连
  function manualReconnect(sessionId: string) {
    if (sessionId) {
      console.log('[useWebSocket] 手动重连')
      reconnectAttempts.value = 0
      reconnectAttemptsDisplay.value = 0
      reconnectingVisible.value = true
      
      // 先关闭现有连接
      if (ws) {
        ws.close()
        ws = null
      }
      
      reconnectWithHealthCheck(sessionId)
    }
  }
  
  // WebSocket 连接
  function connectWebSocket(sessionId: string) {
    // 防止重复连接同一个session
    if (currentConnectedSessionId === sessionId && ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
      return
    }
    
    // 先关闭现有连接
    if (ws) {
      stopHeartbeat()
      ws.close()
      ws = null
      currentConnectedSessionId = null
    }
    
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const wsUrl = `${protocol}//${host}/ws/chat`
    
    isConnecting.value = true
    
    ws = new WebSocket(wsUrl)
    
    ws.onopen = () => {
      console.log('[useWebSocket] WebSocket 连接成功')
      isConnected.value = true
      isConnecting.value = false
      reconnectingVisible.value = false
      currentConnectedSessionId = sessionId
      reconnectAttempts.value = 0  // 重置重连计数
      reconnectAttemptsDisplay.value = 0
      
      // 启动心跳
      startHeartbeat()
      
      // 立即订阅会话
      ws!.send(JSON.stringify({
        type: 'subscribe',
        sessionId: sessionId
      }))
      
      if (openHandler) {
        openHandler()
      }
    }
    
    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data)
        
        // 处理pong响应
        if (message.type === 'pong') {
          heartbeatFailures = 0
          return
        }
        
        if (messageHandler) {
          messageHandler(message)
        }
      } catch (error) {
        console.error('[useWebSocket] 解析消息失败:', error)
      }
    }
    
    ws.onerror = (error) => {
      console.error('[useWebSocket] WebSocket error:', error)
      isConnected.value = false
      isConnecting.value = false
      stopHeartbeat()
      
      // 网络错误也应该触发重连
      const sessionToReconnect = currentConnectedSessionId
      if (sessionToReconnect && reconnectAttempts.value < maxReconnectAttempts) {
        reconnectAttempts.value++
        reconnectingVisible.value = true
        reconnectAttemptsDisplay.value = reconnectAttempts.value
        
        const delay = getReconnectDelay()
        console.log(`[useWebSocket] 网络错误，${delay}ms 后进行第 ${reconnectAttempts.value}/${maxReconnectAttempts} 次重连`)
        
        setTimeout(() => {
          if (!ws || ws.readyState === WebSocket.CLOSED) {
            reconnectWithHealthCheck(sessionToReconnect)
          }
        }, delay)
      }
      
      if (errorHandler) {
        errorHandler(error)
      }
    }
    
    ws.onclose = (event) => {
      isConnected.value = false
      isConnecting.value = false
      
      const sessionToReconnect = currentConnectedSessionId
      currentConnectedSessionId = null
      stopHeartbeat()
      
      if (closeHandler) {
        closeHandler(event)
      }
      
      // 正常关闭，不重连
      if (event.code === 1000 || event.code === 1001) {
        reconnectAttempts.value = 0
        reconnectingVisible.value = false
        return
      }
      
      // 需要重连的情况
      if (sessionToReconnect && reconnectAttempts.value < maxReconnectAttempts) {
        reconnectAttempts.value++
        reconnectingVisible.value = true
        reconnectAttemptsDisplay.value = reconnectAttempts.value
        
        const delay = getReconnectDelay()
        console.log(`[useWebSocket] 连接断开，${delay}ms 后进行第 ${reconnectAttempts.value}/${maxReconnectAttempts} 次重连`)
        
        setTimeout(() => {
          if (!ws || ws.readyState === WebSocket.CLOSED) {
            reconnectWithHealthCheck(sessionToReconnect)
          }
        }, delay)
      } else if (reconnectAttempts.value >= maxReconnectAttempts) {
        reconnectingVisible.value = false
        toast.error('连接失败，请点击状态条重试或刷新页面')
      }
    }
  }
  
  // 发送消息
  function sendMessage(message: any) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(message))
      return true
    }
    return false
  }
  
  // 关闭连接
  function closeConnection() {
    stopHeartbeat()
    
    if (ws) {
      ws.close()
      ws = null
    }
    
    currentConnectedSessionId = null
  }
  
  // 设置事件处理器
  function setHandlers(options: UseWebSocketOptions) {
    messageHandler = options.onMessage || null
    openHandler = options.onOpen || null
    closeHandler = options.onClose || null
    errorHandler = options.onError || null
  }
  
  return {
    // 状态
    isConnected,
    isConnecting,
    reconnectAttempts,
    reconnectingVisible,
    reconnectAttemptsDisplay,
    
    // 方法
    connectWebSocket,
    sendMessage,
    closeConnection,
    manualReconnect,
    setHandlers,
    
    // 获取 WebSocket 实例
    getWebSocket: () => ws
  }
}
