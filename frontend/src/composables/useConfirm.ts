import { ref } from 'vue'

export interface ConfirmOptions {
    title?: string
    message?: string
    icon?: string
    type?: 'danger' | 'warning' | 'info' | 'success'
    confirmText?: string
    cancelText?: string
    confirmVariant?: 'primary' | 'danger' | 'warning'
    /**
     * 确认后要执行的动作。提供后弹窗保持 loading 直到动作完成，
     * 期间取消 / 关闭 / Esc 全部锁死，避免重复触发。
     */
    onConfirm?: () => void | Promise<void>
}

interface ConfirmState extends ConfirmOptions {
    show: boolean
    loading: boolean
    resolve?: (value: boolean) => void
}

const state = ref<ConfirmState>({
    show: false,
    loading: false
})

export function useConfirm() {
    const confirm = (options: ConfirmOptions): Promise<boolean> => new Promise((resolve) => {
            state.value = {
                ...options,
                show: true,
                loading: false,
                resolve
            }
        })

    const handleConfirm = async () => {
        if (!state.value.show || state.value.loading) return
        const current = state.value

        // 未提供动作：立即返回结果并关闭，绝不留出可重复点击的窗口
        if (!current.onConfirm) {
            current.resolve?.(true)
            state.value.show = false
            return
        }

        // 提供动作：先进入 loading 锁死交互，动作完成后才关窗
        state.value.loading = true
        try {
            await current.onConfirm()
            current.resolve?.(true)
            state.value.show = false
        } catch {
            // 动作失败不自动关窗，解除 loading 让用户自行重试或取消
            state.value.loading = false
            current.resolve?.(false)
        }
    }

    const handleCancel = () => {
        if (state.value.loading) return
        state.value.resolve?.(false)
        state.value.show = false
    }

    // 便捷方法
    const confirmDelete = (itemName?: string): Promise<boolean> => confirm({
            title: '确认删除',
            message: itemName ? `确定要删除 "${itemName}" 吗？此操作无法撤销。` : '确定要删除吗？此操作无法撤销。',
            type: 'danger',
            confirmText: '删除',
            confirmVariant: 'danger'
        })

    const confirmClear = (): Promise<boolean> => confirm({
            title: '确认清空',
            message: '确定要清空所有内容吗？此操作无法撤销。',
            type: 'warning',
            confirmText: '清空',
            confirmVariant: 'warning'
        })

    return {
        state,
        confirm,
        confirmDelete,
        confirmClear,
        handleConfirm,
        handleCancel
    }
}
