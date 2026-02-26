/**
 * vue-i18n 配置
 */

import { createI18n } from 'vue-i18n'
import { getEffectiveLocale } from './utils/detector'
import zhCN from './locales/zh-CN.json'
import enUS from './locales/en-US.json'

const i18n = createI18n({
    legacy: false,
    locale: getEffectiveLocale(),
    fallbackLocale: 'en-US',
    messages: {
        'zh-CN': zhCN,
        'en-US': enUS,
    },
    // 全局注入 $t
    globalInjection: true,
    // 缺失警告
    missingWarn: import.meta.env.DEV,
    fallbackWarn: import.meta.env.DEV,
})

export default i18n

/**
 * 获取 i18n 实例的全局 t 函数
 */
export const t = i18n.global.t

/**
 * 获取 i18n 实例的全局 locale
 */
export const locale = i18n.global.locale

/**
 * 设置语言
 */
export function setLocale(newLocale: 'zh-CN' | 'en-US') {
    i18n.global.locale.value = newLocale
    localStorage.setItem('CountBot-language', newLocale)
    document.documentElement.setAttribute('lang', newLocale)
}
