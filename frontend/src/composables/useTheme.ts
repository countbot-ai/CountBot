/**
 * 主题管理 Composable
 * 
 * 提供主题切换、持久化和系统主题检测功能
 */

import { ref, computed } from 'vue'
import {
    type Theme,
    type ThemePalette,
    type ThemePreset,
    detectSystemTheme,
    watchSystemTheme,
    getStoredTheme,
    setStoredTheme,
    getStoredThemePalette,
    setStoredThemePalette
} from '@/i18n/utils/detector'

const currentTheme = ref<'light' | 'dark'>('light')
const themeMode = ref<Theme>('auto')
const themePalette = ref<ThemePalette>('warm')

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
     * 当前设置页应高亮的主题预设。
     * auto 优先；暖色回落为 light/dark，非暖色色调直接作为预设值。
     */
    const themePreset = computed<ThemePreset>(() => {
        if (themeMode.value === 'auto') return 'auto'
        if (themePalette.value === 'warm') {
            return themeMode.value === 'dark' ? 'dark' : 'light'
        }
        return themePalette.value
    })

    /**
     * 应用色调
     */
    function applyPalette(palette: ThemePalette) {
        themePalette.value = palette
        setStoredThemePalette(palette)
        document.documentElement.setAttribute('data-palette', palette)

        // 触发自定义事件
        window.dispatchEvent(
            new CustomEvent('theme-change', {
                detail: { theme: currentTheme.value, palette }
            })
        )
    }

    /**
     * 设置主题
     */
    function setTheme(theme: 'light' | 'dark') {
        currentTheme.value = theme
        document.documentElement.setAttribute('data-theme', theme)
        document.documentElement.setAttribute('data-palette', themePalette.value)

        // 同时更新 body class（兼容某些组件库）
        document.body.classList.remove('light', 'dark')
        document.body.classList.add(theme)

        // 触发自定义事件
        window.dispatchEvent(
            new CustomEvent('theme-change', {
                detail: { theme, palette: themePalette.value }
            })
        )
    }

    /**
     * 设置完整主题预设（设置页 6 个选项）。
     * 「跟随系统」保留当前色调，只把明暗交给系统。
     */
    function setThemePreset(preset: ThemePreset) {
        if (preset === 'auto') {
            setThemeMode('auto')
            return
        }

        if (preset === 'light' || preset === 'dark') {
            applyPalette('warm')
            setThemeMode(preset)
            return
        }

        // 冷色 / 森绿 / 樱花：固定浅色外观，同时写入色调
        applyPalette(preset)
        setThemeMode('light')
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
        const storedPalette = getStoredThemePalette()
        if (storedPalette) {
            themePalette.value = storedPalette
        }
        document.documentElement.setAttribute('data-palette', themePalette.value)

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
        themePalette,
        themePreset,
        isDark,
        isLight,
        isAuto,

        // 方法
        setTheme,
        setThemeMode,
        setThemePreset,
        applyPalette,
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
