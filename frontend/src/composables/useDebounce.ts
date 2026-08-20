/**
 * Debounce Composables
 */

import { ref, watch, Ref, UnwrapRef } from 'vue'
import { debounce } from '@/utils/performance'

/**
 * Debounce a ref value
 * 
 * @param value - Ref to debounce
 * @param delay - Delay in milliseconds
 * @returns Debounced ref
 */
export function useDebounce<T>(value: Ref<T>, delay: number): Ref<UnwrapRef<T>> {
    const debouncedValue = ref(value.value) as Ref<UnwrapRef<T>>

    const updateValue = debounce((newValue: T) => {
        debouncedValue.value = newValue as UnwrapRef<T>
    }, delay)

    watch(value, (newValue) => {
        updateValue(newValue)
    })

    return debouncedValue
}

/**
 * Create a debounced function
 * 
 * @param func - Function to debounce
 * @param delay - Delay in milliseconds
 * @param immediate - Execute on leading edge
 * @returns Debounced function
 */
export function useDebounceFn<T extends (...args: any[]) => any>(
    func: T,
    delay: number,
    immediate = false
): (...args: Parameters<T>) => void {
    return debounce(func, delay, immediate)
}
