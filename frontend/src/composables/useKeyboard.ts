import { onMounted, onBeforeUnmount } from 'vue'

export interface KeyboardShortcut {
    key: string
    ctrl?: boolean
    shift?: boolean
    alt?: boolean
    meta?: boolean
    handler: (event: KeyboardEvent) => void
    description?: string
}

export function useKeyboard(shortcuts: KeyboardShortcut[]) {
    const handleKeyDown = (event: KeyboardEvent) => {
        // 防御性检查：确保 event.key 存在
        if (!event || !event.key) {
            return
        }
        
        for (const shortcut of shortcuts) {
            const keyMatch = event.key.toLowerCase() === shortcut.key.toLowerCase()
            const ctrlMatch = shortcut.ctrl ? event.ctrlKey || event.metaKey : !event.ctrlKey && !event.metaKey
            const shiftMatch = shortcut.shift ? event.shiftKey : !event.shiftKey
            const altMatch = shortcut.alt ? event.altKey : !event.altKey
            const metaMatch = shortcut.meta ? event.metaKey : !event.metaKey

            if (keyMatch && ctrlMatch && shiftMatch && altMatch && metaMatch) {
                event.preventDefault()
                shortcut.handler(event)
                break
            }
        }
    }

    // 必须在组件的 setup 函数中调用
    onMounted(() => {
        window.addEventListener('keydown', handleKeyDown)
    })

    onBeforeUnmount(() => {
        window.removeEventListener('keydown', handleKeyDown)
    })

    return {
        shortcuts
    }
}

// 用于在组件外部使用的版本（不使用生命周期钩子）
export function createKeyboardListener(shortcuts: KeyboardShortcut[]) {
    const handleKeyDown = (event: KeyboardEvent) => {
        // 防御性检查：确保 event.key 存在
        if (!event || !event.key) {
            return
        }
        
        for (const shortcut of shortcuts) {
            const keyMatch = event.key.toLowerCase() === shortcut.key.toLowerCase()
            const ctrlMatch = shortcut.ctrl ? event.ctrlKey || event.metaKey : !event.ctrlKey && !event.metaKey
            const shiftMatch = shortcut.shift ? event.shiftKey : !event.shiftKey
            const altMatch = shortcut.alt ? event.altKey : !event.altKey
            const metaMatch = shortcut.meta ? event.metaKey : !event.metaKey

            if (keyMatch && ctrlMatch && shiftMatch && altMatch && metaMatch) {
                event.preventDefault()
                shortcut.handler(event)
                break
            }
        }
    }

    // 立即添加监听器
    window.addEventListener('keydown', handleKeyDown)

    return {
        shortcuts,
        cleanup: () => {
            window.removeEventListener('keydown', handleKeyDown)
        }
    }
}

// 常用快捷键组合
export const commonShortcuts = {
    // Ctrl/Cmd + Enter: 发送消息
    send: (handler: () => void): KeyboardShortcut => ({
        key: 'Enter',
        ctrl: true,
        handler,
        description: 'Send message'
    }),

    // Escape: 取消/关闭
    escape: (handler: () => void): KeyboardShortcut => ({
        key: 'Escape',
        handler,
        description: 'Cancel/Close'
    }),

    // Ctrl/Cmd + K: 快速搜索
    search: (handler: () => void): KeyboardShortcut => ({
        key: 'k',
        ctrl: true,
        handler,
        description: 'Quick search'
    }),

    // Ctrl/Cmd + N: 新建
    new: (handler: () => void): KeyboardShortcut => ({
        key: 'n',
        ctrl: true,
        handler,
        description: 'New item'
    }),

    // Ctrl/Cmd + S: 保存
    save: (handler: () => void): KeyboardShortcut => ({
        key: 's',
        ctrl: true,
        handler,
        description: 'Save'
    }),

    // Ctrl/Cmd + /: 切换侧边栏
    toggleSidebar: (handler: () => void): KeyboardShortcut => ({
        key: '/',
        ctrl: true,
        handler,
        description: 'Toggle sidebar'
    }),

    // Ctrl/Cmd + ,: 打开设置
    settings: (handler: () => void): KeyboardShortcut => ({
        key: ',',
        ctrl: true,
        handler,
        description: 'Open settings'
    }),

    // Ctrl/Cmd + Shift + D: 切换深色模式
    toggleTheme: (handler: () => void): KeyboardShortcut => ({
        key: 'd',
        ctrl: true,
        shift: true,
        handler,
        description: 'Toggle theme'
    })
}
