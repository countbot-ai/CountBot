/**
 * Axios API 客户端
 * 
 * 功能:
 * - 自动重试失败的请求
 * - 请求/响应拦截器
 * - 错误处理和转换
 * - 请求超时控制
 * - 请求取消支持
 */

import axios, { AxiosError, AxiosInstance, AxiosResponse, InternalAxiosRequestConfig } from 'axios'

// ============================================================================
// 类型定义
// ============================================================================

export interface ApiError {
    message: string
    status?: number
    code?: string
    details?: any
}

export interface RetryConfig {
    retries: number
    retryDelay: number
    retryCondition?: (error: AxiosError) => boolean
}

// ============================================================================
// 配置
// ============================================================================

const DEFAULT_TIMEOUT = 30000 // 30 秒
const DEFAULT_RETRY_COUNT = 3
const DEFAULT_RETRY_DELAY = 1000 // 1 秒

// 可重试的 HTTP 状态码
const RETRYABLE_STATUS_CODES = [408, 429, 500, 502, 503, 504]

// 可重试的错误代码
const RETRYABLE_ERROR_CODES = ['ECONNABORTED', 'ETIMEDOUT', 'ENOTFOUND', 'ENETUNREACH']

// ============================================================================
// API 客户端实例
// ============================================================================

const apiClient: AxiosInstance = axios.create({
    baseURL: '/api',
    timeout: DEFAULT_TIMEOUT,
    headers: {
        'Content-Type': 'application/json',
    },
})

// ============================================================================
// 请求拦截器
// ============================================================================

apiClient.interceptors.request.use(
    (config: InternalAxiosRequestConfig) => {
        // 添加请求时间戳（用于性能监控）
        config.metadata = { startTime: Date.now() }

        // 添加请求 ID（用于追踪）
        config.headers['X-Request-ID'] = generateRequestId()

        // 添加认证 token（远程访问时需要）
        const token = localStorage.getItem('CountBot_token')
        if (token) {
            config.headers['Authorization'] = `Bearer ${token}`
        }

        return config
    },
    (error: AxiosError) => {
        console.error('[API Request Error]', error)
        return Promise.reject(error)
    }
)

// ============================================================================
// 响应拦截器
// ============================================================================

apiClient.interceptors.response.use(
    (response: AxiosResponse) => {
        // 计算请求耗时
        const duration = Date.now() - (response.config.metadata?.startTime || 0)

        // 性能警告（超过 3 秒）
        if (duration > 3000) {
            console.warn(`[API Performance] Slow request: ${response.config.url} (${duration}ms)`)
        }

        // 返回响应数据
        return response.data
    },
    async (error: AxiosError) =>
        // 错误处理和重试逻辑
        handleApiError(error)


)

// ============================================================================
// 错误处理
// ============================================================================

async function handleApiError(error: AxiosError): Promise<never> {
    const config = error.config as InternalAxiosRequestConfig & { _retry?: number }

    // 401 未认证 → 跳转登录页（远程访问场景）
    if (error.response?.status === 401) {
        const data = error.response.data as any
        if (data?.code === 'AUTH_REQUIRED' || data?.code === 'AUTH_SETUP_REQUIRED') {
            // 避免在登录页循环跳转
            if (window.location.pathname !== '/login') {
                window.location.href = '/login'
            }
            return Promise.reject(transformError(error))
        }
    }

    // 检查是否应该重试
    if (shouldRetry(error, config)) {
        const retryCount = config._retry || 0
        const retryDelay = calculateRetryDelay(retryCount)

        config._retry = retryCount + 1

        // 等待后重试
        await sleep(retryDelay)
        return apiClient.request(config)
    }

    // 转换错误格式
    const apiError = transformError(error)

    // 日志记录
    console.error('[API Error]', {
        url: config?.url,
        method: config?.method,
        status: error.response?.status,
        message: apiError.message,
    })

    // 抛出转换后的错误
    return Promise.reject(apiError)
}

function shouldRetry(error: AxiosError, config?: InternalAxiosRequestConfig & { _retry?: number }): boolean {
    // 没有配置或已达到最大重试次数
    if (!config || (config._retry || 0) >= DEFAULT_RETRY_COUNT) {
        return false
    }

    // 检查是否是可重试的状态码
    if (error.response && RETRYABLE_STATUS_CODES.includes(error.response.status)) {
        return true
    }

    // 检查是否是可重试的错误代码
    if (error.code && RETRYABLE_ERROR_CODES.includes(error.code)) {
        return true
    }

    // 网络错误（没有响应）
    if (!error.response && error.request) {
        return true
    }

    return false
}

function calculateRetryDelay(retryCount: number): number {
    // 指数退避策略: 1s, 2s, 4s
    return DEFAULT_RETRY_DELAY * Math.pow(2, retryCount)
}

function transformError(error: AxiosError): ApiError {
    if (error.response) {
        // 服务器返回错误响应
        const data = error.response.data as any

        return {
            message: data?.message || data?.detail || `Request failed with status ${error.response.status}`,
            status: error.response.status,
            code: data?.code || error.code,
            details: data?.details || data,
        }
    } else if (error.request) {
        // 请求已发送但没有收到响应
        return {
            message: 'Network error: No response received from server',
            code: error.code || 'NETWORK_ERROR',
            details: error.message,
        }
    } else {
        // 请求配置错误
        return {
            message: error.message || 'Request configuration error',
            code: error.code || 'REQUEST_ERROR',
        }
    }
}

// ============================================================================
// 工具函数
// ============================================================================

function generateRequestId(): string {
    return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
}

function sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms))
}

// ============================================================================
// 扩展 Axios 类型
// ============================================================================

declare module 'axios' {
    export interface InternalAxiosRequestConfig {
        metadata?: {
            startTime: number
        }
        _retry?: number
    }
}

// ============================================================================
// 导出
// ============================================================================

export default apiClient
