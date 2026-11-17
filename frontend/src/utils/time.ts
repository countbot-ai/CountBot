/**
 * 时间格式化工具
 */

export function parseTimestamp(timestamp: string | Date | number): Date {
  if (timestamp instanceof Date) {
    return timestamp
  }

  if (typeof timestamp === 'number') {
    return new Date(timestamp)
  }

  if (!timestamp) {
    return new Date('')
  }

  const trimmed = timestamp.trim()
  if (!trimmed) {
    return new Date('')
  }

  return trimmed.includes('+') || trimmed.includes('Z')
    ? new Date(trimmed)
    : new Date(`${trimmed}Z`)
}

/**
 * 格式化时间为相对时间或绝对时间
 * @param timestamp ISO 8601 时间字符串或 Date 对象
 * @returns 格式化后的时间字符串
 */
export function formatTime(timestamp: string | Date): string {
  const date = parseTimestamp(timestamp)
  
  // 检查是否是有效日期
  if (isNaN(date.getTime())) {
    return '无效时间'
  }
  
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  const seconds = Math.floor(diff / 1000)
  const minutes = Math.floor(seconds / 60)
  const hours = Math.floor(minutes / 60)
  const days = Math.floor(hours / 24)
  
  // 相对时间
  if (seconds < 10) return '刚刚'
  if (seconds < 60) return `${seconds}秒前`
  if (minutes < 60) return `${minutes}分钟前`
  if (hours < 24) return `${hours}小时前`
  if (days < 7) return `${days}天前`
  
  // 超过7天显示具体日期
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

/**
 * 格式化为完整日期时间
 * @param timestamp ISO 8601 时间字符串或 Date 对象
 * @returns 格式化后的日期时间字符串
 */
export function formatDateTime(timestamp: string | Date): string {
  const date = parseTimestamp(timestamp)
  
  if (isNaN(date.getTime())) {
    return '无效时间'
  }
  
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

/**
 * 格式化为日期
 * @param timestamp ISO 8601 时间字符串或 Date 对象
 * @returns 格式化后的日期字符串
 */
export function formatDate(timestamp: string | Date): string {
  const date = parseTimestamp(timestamp)
  
  if (isNaN(date.getTime())) {
    return '无效日期'
  }
  
  return date.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  })
}
