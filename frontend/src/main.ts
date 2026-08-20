/**
 * Vue3 应用入口
 */

import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import { pinia } from './store'
import i18n from './i18n'
import './assets/styles/main.css'

const VITE_PRELOAD_RELOAD_KEY = '__countbot_vite_preload_reload_at__'
const VITE_PRELOAD_RELOAD_COOLDOWN_MS = 10_000

const installViteChunkRecovery = () => {
    if (typeof window === 'undefined') {
        return
    }

    window.addEventListener('vite:preloadError', event => {
        const now = Date.now()
        const lastReloadAt = Number.parseInt(sessionStorage.getItem(VITE_PRELOAD_RELOAD_KEY) || '0', 10)

        if (now - lastReloadAt < VITE_PRELOAD_RELOAD_COOLDOWN_MS) {
            sessionStorage.removeItem(VITE_PRELOAD_RELOAD_KEY)
            return
        }

        event.preventDefault()
        sessionStorage.setItem(VITE_PRELOAD_RELOAD_KEY, String(now))
        window.location.reload()
    })
}

installViteChunkRecovery()

const app = createApp(App)

app.use(router)
app.use(pinia)
app.use(i18n)

router.isReady().then(() => {
    app.mount('#app')
})
