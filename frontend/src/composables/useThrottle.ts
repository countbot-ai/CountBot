/**
 * Throttle Composables
 */

import { ref, watch, Ref, UnwrapRef } from 'vue'
import { throttle, rafThrottle } from '@/utils/performance'

/**
 * Throttle a ref value
 * 
 * @param value - Ref to throttle
 * @param limit - Time limit in milliseconds
 * @param options - Throttle options
 * @returns Throttled ref
 */
export function useThrottle<T>(
    value: Ref<T>,
    limit: number,
    options?: { leading?: boolean; trailing?: boolean }
): Ref<UnwrapRef<T>> {
    const throttledValue = ref(value.value) as Ref<UnwrapRef<T>>

    const updateValue = throttle((newValue: T) => {
        throttledValue.value = newValue as UnwrapRef<T>
    }, limit, options)

    watch(value, (newValue) => {
        updateValue(newValue)
    })

    return throttledValue
}

/**
 * Create a throttled function
 * 
 * @param func - Function to throttle
 * @param limit - Time limit in milliseconds
 * @param options - Throttle options
 * @returns Throttled function
 */
export function useThrottleFn<T extends (...args: any[]) => any>(
    func: T,
    limit: number,
    options?: { leading?: boolean; trailing?: boolean }
): (...args: Parameters<T>) => void {
    return throttle(func, limit, options)
}

/**
 * Create a RAF throttled function
 * 
 * @param func - Function to throttle
 * @returns RAF throttled function
 */
export function useRafFn<T extends (...args: any[]) => any>(
    func: T
): (...args: Parameters<T>) => void {
    return rafThrottle(func)
}
