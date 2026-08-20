/**
 * 主题管理 Composable
 * 
 * 提供主题切换、持久化和系统主题检测功能
 */

import { ref, computed, watch } from 'vue'
import {
    type Theme,
    detectSystemTheme,
    watchSystemTheme,
    getStoredTheme,
    setStoredTheme,
    getEffectiveTheme
} from '@/i18n/utils/detector'

const THEME_KEY = 'CountBot-theme'
const currentTheme = ref<'light' | 'dark'>('light')
const themeMode = ref<Theme>('auto')

let unwatchSystemTheme: (() => void) | null = null

export function useTheme() {
    /**
     * 是否为深色主题
     */
    const isDark = computed(() => currentTheme.value === 'dark')

    /**
     * 是否为浅色主题
     */
    const isLight = computed(() => currentTheme.value === 'light')

    /**
     * 是否为自动模式
     */
    const isAuto = computed(() => themeMode.value === 'auto')

    /**
     * 设置主题
     */
    function setTheme(theme: 'light' | 'dark') {
        currentTheme.value = theme
        document.documentElement.setAttribute('data-theme', theme)

        // 同时更新 body class（兼容某些组件库）
        document.body.classList.remove('light', 'dark')
        document.body.classList.add(theme)

        // 触发自定义事件
        window.dispatchEvent(new CustomEvent('theme-change', { detail: { theme } }))
    }

    /**
     * 设置主题模式（light/dark/auto）
     */
    function setThemeMode(mode: Theme) {
        themeMode.value = mode
        setStoredTheme(mode)

        if (mode === 'auto') {
            // 自动模式：使用系统主题
            const systemTheme = detectSystemTheme()
            setTheme(systemTheme)

            // 监听系统主题变化
            if (!unwatchSystemTheme) {
                unwatchSystemTheme = watchSystemTheme((theme) => {
                    if (themeMode.value === 'auto') {
                        setTheme(theme)
                    }
                })
            }
        } else {
            // 手动模式：使用指定主题
            setTheme(mode)

            // 停止监听系统主题
            if (unwatchSystemTheme) {
                unwatchSystemTheme()
                unwatchSystemTheme = null
            }
        }
    }

    /**
     * 切换主题（在 light 和 dark 之间切换）
     */
    function toggleTheme() {
        const newTheme = currentTheme.value === 'light' ? 'dark' : 'light'
        setThemeMode(newTheme)
    }

    /**
     * 初始化主题
     */
    function initTheme() {
        const stored = getStoredTheme()

        if (stored) {
            setThemeMode(stored)
        } else {
            // 默认使用浅色主题
            setThemeMode('light')
        }
    }

    /**
     * 获取系统主题
     */
    function getSystemTheme(): 'light' | 'dark' {
        return detectSystemTheme()
    }

    /**
     * 应用主题到元素
     */
    function applyThemeToElement(element: HTMLElement, theme?: 'light' | 'dark') {
        const targetTheme = theme || currentTheme.value
        element.setAttribute('data-theme', targetTheme)
    }

    /**
     * 移除元素的主题
     */
    function removeThemeFromElement(element: HTMLElement) {
        element.removeAttribute('data-theme')
    }

    return {
        // 状态
        theme: currentTheme,
        themeMode,
        isDark,
        isLight,
        isAuto,

        // 方法
        setTheme,
        setThemeMode,
        toggleTheme,
        initTheme,
        getSystemTheme,
        applyThemeToElement,
        removeThemeFromElement
    }
}

/**
 * 主题颜色工具
 */
export function useThemeColors() {
    const { theme } = useTheme()

    /**
     * 获取 CSS 变量值
     */
    function getCSSVariable(name: string): string {
        return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
    }

    /**
     * 设置 CSS 变量值
     */
    function setCSSVariable(name: string, value: string) {
        document.documentElement.style.setProperty(name, value)
    }

    /**
     * 获取主题颜色
     */
    const colors = computed(() => ({
        primary: getCSSVariable('--color-primary'),
        success: getCSSVariable('--color-success'),
        warning: getCSSVariable('--color-warning'),
        error: getCSSVariable('--color-error'),
        info: getCSSVariable('--color-info'),
        textPrimary: getCSSVariable('--color-text-primary'),
        textSecondary: getCSSVariable('--color-text-secondary'),
        bgPrimary: getCSSVariable('--color-bg-primary'),
        bgSecondary: getCSSVariable('--color-bg-secondary'),
        borderPrimary: getCSSVariable('--color-border-primary')
    }))

    return {
        theme,
        colors,
        getCSSVariable,
        setCSSVariable
    }
}
