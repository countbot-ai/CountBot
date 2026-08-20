/**
 * 全局类型定义
 */

// ScrollBehavior 类型
type ScrollBehavior = 'auto' | 'smooth' | 'instant'

// 通用处理函数类型
type HandlerFn = (...args: unknown[]) => void
type AsyncHandlerFn = (...args: unknown[]) => Promise<void>

// 事件处理函数类型
type EventHandler<T = Event> = (event: T) => void
type AsyncEventHandler<T = Event> = (event: T) => Promise<void>

// 通用回调类型
type Callback<T = void> = () => T
type AsyncCallback<T = void> = () => Promise<T>

// 参数化回调类型
type CallbackWithArg<TArg, TReturn = void> = (arg: TArg) => TReturn
type AsyncCallbackWithArg<TArg, TReturn = void> = (arg: TArg) => Promise<TReturn>

// 导出类型
export {
    ScrollBehavior,
    HandlerFn,
    AsyncHandlerFn,
    EventHandler,
    AsyncEventHandler,
    Callback,
    AsyncCallback,
    CallbackWithArg,
    AsyncCallbackWithArg
}
