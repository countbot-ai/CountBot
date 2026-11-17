/**
 * vue-i18n 配置
 */

import { createI18n } from 'vue-i18n'
import { getEffectiveLocale } from './utils/detector'
import zhCN from './locales/zh-CN.json'
import enUS from './locales/en-US.json'

// 历史版本迁移：GeneralConfig 曾把语言存进错误的键 'locale'（bootstrap 只认
// 'CountBot-language'），导致「设置中文保存后刷新变回英文」。首次启动时把旧键
// 迁移过来，已经用正确键保存过的用户不受影响。
try {
    const legacyLocale = localStorage.getItem('locale')
    if (legacyLocale && !localStorage.getItem('CountBot-language')) {
        localStorage.setItem('CountBot-language', legacyLocale.startsWith('zh') ? 'zh-CN' : 'en-US')
    }
    localStorage.removeItem('locale')
} catch {
    // localStorage 不可用（隐私模式等）时跳过迁移，走默认语言
}

// index.html 里写死 lang="zh-CN"，启动时按实际生效语言纠正，
// 否则英文用户拿到的是中文 lang，影响读屏与字体回退。
document.documentElement.setAttribute('lang', getEffectiveLocale())

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
