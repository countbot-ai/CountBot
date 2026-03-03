/**
 * 系统语言和主题检测工具
 */

export type SupportedLocale = 'zh-CN' | 'en-US'
export type Theme = 'light' | 'dark' | 'auto'

/**
 * 检测系统语言
 */
export function detectSystemLanguage(): SupportedLocale {
    const browserLang = navigator.language || (navigator as any).userLanguage

    // 检查是否为中文
    if (browserLang.startsWith('zh')) {
        // 区分简体和繁体
        if (browserLang.includes('TW') || browserLang.includes('HK')) {
            // 繁体中文，暂时使用简体
            return 'zh-CN'
        }
        return 'zh-CN'
    }

    // 默认英文
    return 'en-US'
}

/**
 * 检测系统主题
 */
export function detectSystemTheme(): 'light' | 'dark' {
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
        return 'dark'
    }
    return 'light'
}

/**
 * 监听系统主题变化
 */
export function watchSystemTheme(callback: (theme: 'light' | 'dark') => void): () => void {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')

    const handler = (e: MediaQueryListEvent) => {
        callback(e.matches ? 'dark' : 'light')
    }

    // 现代浏览器使用 addEventListener
    if (mediaQuery.addEventListener) {
        mediaQuery.addEventListener('change', handler)
        return () => mediaQuery.removeEventListener('change', handler)
    }
    // 旧浏览器使用 addListener
    else if (mediaQuery.addListener) {
        mediaQuery.addListener(handler)
        return () => mediaQuery.removeListener(handler)
    }

    return () => { }
}

/**
 * 获取浏览器支持的语言列表
 */
export function getBrowserLanguages(): string[] {
    return navigator.languages || [navigator.language]
}

/**
 * 检测是否支持某个语言
 */
export function isSupportedLocale(locale: string): locale is SupportedLocale {
    return locale === 'zh-CN' || locale === 'en-US'
}

/**
 * 标准化语言代码
 */
export function normalizeLocale(locale: string): SupportedLocale {
    const normalized = locale.toLowerCase().replace('_', '-')

    if (normalized.startsWith('zh')) {
        return 'zh-CN'
    }

    return 'en-US'
}

/**
 * 从存储中获取语言设置
 */
export function getStoredLocale(): SupportedLocale | null {
    const stored = localStorage.getItem('CountBot-language')
    if (stored && isSupportedLocale(stored)) {
        return stored
    }
    return null
}

/**
 * 保存语言设置到存储
 */
export function setStoredLocale(locale: SupportedLocale): void {
    localStorage.setItem('CountBot-language', locale)
}

/**
 * 从存储中获取主题设置
 */
export function getStoredTheme(): Theme | null {
    const stored = localStorage.getItem('CountBot-theme')
    if (stored === 'light' || stored === 'dark' || stored === 'auto') {
        return stored
    }
    return null
}

/**
 * 保存主题设置到存储
 */
export function setStoredTheme(theme: Theme): void {
    localStorage.setItem('CountBot-theme', theme)
}

/**
 * 获取最终使用的语言（优先级：存储 > 系统 > 默认）
 */
export function getEffectiveLocale(): SupportedLocale {
    return getStoredLocale() || detectSystemLanguage()
}

/**
 * 获取最终使用的主题（优先级：存储 > 系统 > 默认）
 */
export function getEffectiveTheme(): 'light' | 'dark' {
    const stored = getStoredTheme()

    if (stored === 'light' || stored === 'dark') {
        return stored
    }

    // auto 或未设置，使用系统主题
    return detectSystemTheme()
}
