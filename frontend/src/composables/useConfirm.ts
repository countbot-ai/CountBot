import { ref } from 'vue'

export interface ConfirmOptions {
    title?: string
    message?: string
    icon?: string
    type?: 'danger' | 'warning' | 'info' | 'success'
    confirmText?: string
    cancelText?: string
    confirmVariant?: 'primary' | 'danger' | 'warning'
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
        if (state.value.resolve) {
            state.value.loading = true
            state.value.resolve(true)
            // 延迟关闭，让调用者有机会处理
            setTimeout(() => {
                state.value.show = false
                state.value.loading = false
            }, 100)
        }
    }

    const handleCancel = () => {
        if (state.value.resolve) {
            state.value.resolve(false)
        }
        state.value.show = false
        state.value.loading = false
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
