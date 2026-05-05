/**
 * 国际化 Composable
 * 
 * 提供语言切换和格式化功能
 */

import { computed } from 'vue'
import { useI18n as useVueI18n } from 'vue-i18n'
import {
    type SupportedLocale,
    detectSystemLanguage,
    getStoredLocale,
    setStoredLocale,
    normalizeLocale
} from '@/i18n/utils/detector'
import { useFormatter } from '@/i18n/utils/formatter'

export function useI18n() {
    const i18n = useVueI18n()
    const formatter = useFormatter()

    /**
     * 当前语言
     */
    const locale = computed({
        get: () => i18n.locale.value as SupportedLocale,
        set: (value: SupportedLocale) => {
            i18n.locale.value = value
            setStoredLocale(value)
            document.documentElement.setAttribute('lang', value)
        }
    })

    /**
     * 可用语言列表
     */
    const availableLocales = computed(() => i18n.availableLocales as SupportedLocale[])

    /**
     * 是否为中文
     */
    const isZhCN = computed(() => locale.value === 'zh-CN')

    /**
     * 是否为英文
     */
    const isEnUS = computed(() => locale.value === 'en-US')

    /**
     * 切换语言
     */
    function setLocale(newLocale: SupportedLocale) {
        locale.value = newLocale
    }

    /**
     * 切换到下一个语言
     */
    function toggleLocale() {
        const locales = availableLocales.value
        const currentIndex = locales.indexOf(locale.value)
        const nextIndex = (currentIndex + 1) % locales.length
        setLocale(locales[nextIndex])
    }

    /**
     * 获取语言显示名称
     */
    function getLocaleName(loc: SupportedLocale): string {
        const names: Record<SupportedLocale, string> = {
            'zh-CN': '简体中文',
            'en-US': 'English'
        }
        return names[loc] || loc
    }

    /**
     * 初始化语言设置
     */
    function initLocale() {
        const stored = getStoredLocale()
        if (stored) {
            setLocale(stored)
        } else {
            const detected = detectSystemLanguage()
            setLocale(detected)
        }
    }

    /**
     * 翻译函数（简写）
     */
    const t = i18n.t

    /**
     * 翻译函数（带复数）
     */
    const tc = i18n.tc || i18n.t

    /**
     * 翻译函数（带默认值）
     */
    function td(key: string, defaultValue: string, ...args: any[]): string {
        const value = i18n.te(key) ? i18n.t(key, ...args) : defaultValue
        return value as string
    }

    return {
        // 状态
        locale,
        availableLocales,
        isZhCN,
        isEnUS,

        // 方法
        t,
        tc,
        td,
        setLocale,
        toggleLocale,
        getLocaleName,
        initLocale,

        // 格式化工具
        ...formatter
    }
}
