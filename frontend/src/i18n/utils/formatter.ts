/**
 * 国际化格式化工具
 * 
 * 提供日期、数字、货币等格式化功能
 */

import { useI18n } from 'vue-i18n'

/**
 * 日期格式化选项
 */
export interface DateFormatOptions {
    year?: 'numeric' | '2-digit'
    month?: 'numeric' | '2-digit' | 'long' | 'short' | 'narrow'
    day?: 'numeric' | '2-digit'
    hour?: 'numeric' | '2-digit'
    minute?: 'numeric' | '2-digit'
    second?: 'numeric' | '2-digit'
    weekday?: 'long' | 'short' | 'narrow'
    hour12?: boolean
}

/**
 * 数字格式化选项
 */
export interface NumberFormatOptions {
    style?: 'decimal' | 'currency' | 'percent'
    currency?: string
    minimumFractionDigits?: number
    maximumFractionDigits?: number
    useGrouping?: boolean
}

/**
 * 格式化日期
 */
export function formatDate(
    date: Date | string | number,
    locale: string,
    options?: DateFormatOptions
): string {
    const dateObj = typeof date === 'string' || typeof date === 'number' ? new Date(date) : date

    if (isNaN(dateObj.getTime())) {
        return 'Invalid Date'
    }

    const defaultOptions: DateFormatOptions = {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        ...options
    }

    return new Intl.DateTimeFormat(locale, defaultOptions).format(dateObj)
}

/**
 * 格式化日期时间
 */
export function formatDateTime(
    date: Date | string | number,
    locale: string,
    options?: DateFormatOptions
): string {
    const defaultOptions: DateFormatOptions = {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        ...options
    }

    return formatDate(date, locale, defaultOptions)
}

/**
 * 格式化时间
 */
export function formatTime(
    date: Date | string | number,
    locale: string,
    options?: DateFormatOptions
): string {
    const defaultOptions: DateFormatOptions = {
        hour: '2-digit',
        minute: '2-digit',
        ...options
    }

    return formatDate(date, locale, defaultOptions)
}

/**
 * 格式化相对时间（例如：2小时前）
 */
export function formatRelativeTime(
    date: Date | string | number,
    locale: string
): string {
    const dateObj = typeof date === 'string' || typeof date === 'number' ? new Date(date) : date
    const now = new Date()
    const diffMs = now.getTime() - dateObj.getTime()
    const diffSec = Math.floor(diffMs / 1000)
    const diffMin = Math.floor(diffSec / 60)
    const diffHour = Math.floor(diffMin / 60)
    const diffDay = Math.floor(diffHour / 24)

    const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' })

    if (diffSec < 60) {
        return rtf.format(-diffSec, 'second')
    } else if (diffMin < 60) {
        return rtf.format(-diffMin, 'minute')
    } else if (diffHour < 24) {
        return rtf.format(-diffHour, 'hour')
    } else if (diffDay < 30) {
        return rtf.format(-diffDay, 'day')
    } else if (diffDay < 365) {
        return rtf.format(-Math.floor(diffDay / 30), 'month')
    } else {
        return rtf.format(-Math.floor(diffDay / 365), 'year')
    }
}

/**
 * 格式化数字
 */
export function formatNumber(
    value: number,
    locale: string,
    options?: NumberFormatOptions
): string {
    return new Intl.NumberFormat(locale, options).format(value)
}

/**
 * 格式化货币
 */
export function formatCurrency(
    value: number,
    locale: string,
    currency: string = 'USD'
): string {
    return formatNumber(value, locale, {
        style: 'currency',
        currency
    })
}

/**
 * 格式化百分比
 */
export function formatPercent(
    value: number,
    locale: string,
    fractionDigits: number = 0
): string {
    return formatNumber(value, locale, {
        style: 'percent',
        minimumFractionDigits: fractionDigits,
        maximumFractionDigits: fractionDigits
    })
}

/**
 * 格式化文件大小
 */
export function formatFileSize(bytes: number, locale: string): string {
    const units = locale.startsWith('zh')
        ? ['字节', 'KB', 'MB', 'GB', 'TB']
        : ['Bytes', 'KB', 'MB', 'GB', 'TB']

    if (bytes === 0) return `0 ${units[0]}`

    const k = 1024
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    const value = bytes / Math.pow(k, i)

    return `${formatNumber(value, locale, { maximumFractionDigits: 2 })} ${units[i]}`
}

/**
 * 格式化持续时间（毫秒）
 */
export function formatDuration(ms: number, locale: string): string {
    const seconds = Math.floor(ms / 1000)
    const minutes = Math.floor(seconds / 60)
    const hours = Math.floor(minutes / 60)
    const days = Math.floor(hours / 24)

    if (days > 0) {
        return locale.startsWith('zh') ? `${days}天` : `${days}d`
    } else if (hours > 0) {
        return locale.startsWith('zh') ? `${hours}小时` : `${hours}h`
    } else if (minutes > 0) {
        return locale.startsWith('zh') ? `${minutes}分钟` : `${minutes}m`
    } else {
        return locale.startsWith('zh') ? `${seconds}秒` : `${seconds}s`
    }
}

/**
 * 使用 composable 的格式化工具
 */
export function useFormatter() {
    const { locale } = useI18n()

    return {
        formatDate: (date: Date | string | number, options?: DateFormatOptions) =>
            formatDate(date, locale.value, options),

        formatDateTime: (date: Date | string | number, options?: DateFormatOptions) =>
            formatDateTime(date, locale.value, options),

        formatTime: (date: Date | string | number, options?: DateFormatOptions) =>
            formatTime(date, locale.value, options),

        formatRelativeTime: (date: Date | string | number) =>
            formatRelativeTime(date, locale.value),

        formatNumber: (value: number, options?: NumberFormatOptions) =>
            formatNumber(value, locale.value, options),

        formatCurrency: (value: number, currency?: string) =>
            formatCurrency(value, locale.value, currency),

        formatPercent: (value: number, fractionDigits?: number) =>
            formatPercent(value, locale.value, fractionDigits),

        formatFileSize: (bytes: number) =>
            formatFileSize(bytes, locale.value),

        formatDuration: (ms: number) =>
            formatDuration(ms, locale.value)
    }
}
