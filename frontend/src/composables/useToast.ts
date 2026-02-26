/**
 * Toast 通知 Composable
 */

export interface ToastOptions {
    message: string
    type?: 'success' | 'error' | 'warning' | 'info'
    duration?: number
}

export function useToast() {
    const show = (options: ToastOptions) => {
        const { message, type = 'info', duration = 3000 } = options

        // 创建 toast 元素
        const toast = document.createElement('div')
        toast.className = `toast toast-${type}`
        toast.textContent = message

        // 添加样式
        Object.assign(toast.style, {
            position: 'fixed',
            top: '20px',
            right: '20px',
            padding: '12px 20px',
            borderRadius: '8px',
            color: 'white',
            fontSize: '14px',
            fontWeight: '500',
            zIndex: '10000',
            animation: 'slideIn 0.3s ease',
            boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)',
        })

        // 根据类型设置背景色
        const colors = {
            success: '#10b981',
            error: '#ef4444',
            warning: '#f59e0b',
            info: '#3b82f6',
        }
        toast.style.background = colors[type]

        // 添加到页面
        document.body.appendChild(toast)

        // 自动移除
        setTimeout(() => {
            toast.style.animation = 'slideOut 0.3s ease'
            setTimeout(() => {
                document.body.removeChild(toast)
            }, 300)
        }, duration)
    }

    return {
        success: (message: string) => show({ message, type: 'success' }),
        error: (message: string) => show({ message, type: 'error' }),
        warning: (message: string) => show({ message, type: 'warning' }),
        info: (message: string) => show({ message, type: 'info' }),
    }
}

// 添加动画样式
if (typeof document !== 'undefined') {
    const style = document.createElement('style')
    style.textContent = `
    @keyframes slideIn {
      from {
        transform: translateX(100%);
        opacity: 0;
      }
      to {
        transform: translateX(0);
        opacity: 1;
      }
    }
    
    @keyframes slideOut {
      from {
        transform: translateX(0);
        opacity: 1;
      }
      to {
        transform: translateX(100%);
        opacity: 0;
      }
    }
  `
    document.head.appendChild(style)
}
