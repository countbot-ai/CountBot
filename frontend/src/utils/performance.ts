/**
 * Performance Utilities
 * Debounce, Throttle, and other performance optimization helpers
 */

/**
 * Debounce function - delays execution until after wait milliseconds have elapsed
 * since the last time it was invoked
 * 
 * @param func - Function to debounce
 * @param wait - Milliseconds to wait
 * @param immediate - Trigger on leading edge instead of trailing
 * @returns Debounced function
 */
export function debounce<T extends (...args: any[]) => any>(
    func: T,
    wait: number,
    immediate = false
): (...args: Parameters<T>) => void {
    let timeout: ReturnType<typeof setTimeout> | null = null

    return function executedFunction(...args: Parameters<T>) {
        const later = () => {
            timeout = null
            if (!immediate) func(...args)
        }

        const callNow = immediate && !timeout

        if (timeout) clearTimeout(timeout)
        timeout = setTimeout(later, wait)

        if (callNow) func(...args)
    }
}

/**
 * Throttle function - ensures function is called at most once per specified time period
 * 
 * @param func - Function to throttle
 * @param limit - Milliseconds to wait between calls
 * @param options - Throttle options
 * @returns Throttled function
 */
export function throttle<T extends (...args: any[]) => any>(
    func: T,
    limit: number,
    options: { leading?: boolean; trailing?: boolean } = {}
): (...args: Parameters<T>) => void {
    let inThrottle: boolean
    let lastFunc: ReturnType<typeof setTimeout>
    let lastRan: number
    const { leading = true, trailing = true } = options

    return function executedFunction(...args: Parameters<T>) {
        if (!inThrottle) {
            if (leading) func(...args)
            lastRan = Date.now()
            inThrottle = true
        } else {
            if (trailing) {
                clearTimeout(lastFunc)
                lastFunc = setTimeout(() => {
                    if (Date.now() - lastRan >= limit) {
                        func(...args)
                        lastRan = Date.now()
                    }
                }, Math.max(limit - (Date.now() - lastRan), 0))
            }
        }

        setTimeout(() => {
            inThrottle = false
        }, limit)
    }
}

/**
 * Request Animation Frame throttle - throttles function to animation frame rate
 * 
 * @param func - Function to throttle
 * @returns RAF throttled function
 */
export function rafThrottle<T extends (...args: any[]) => any>(
    func: T
): (...args: Parameters<T>) => void {
    let rafId: number | null = null

    return function executedFunction(...args: Parameters<T>) {
        if (rafId !== null) return

        rafId = requestAnimationFrame(() => {
            func(...args)
            rafId = null
        })
    }
}

/**
 * Memoize function - caches function results
 * 
 * @param func - Function to memoize
 * @param resolver - Custom key resolver
 * @returns Memoized function
 */
export function memoize<T extends (...args: any[]) => any>(
    func: T,
    resolver?: (...args: Parameters<T>) => string
): T & { cache: Map<string, ReturnType<T>> } {
    const cache = new Map<string, ReturnType<T>>()

    const memoized = function (...args: Parameters<T>): ReturnType<T> {
        const key = resolver ? resolver(...args) : JSON.stringify(args)

        if (cache.has(key)) {
            return cache.get(key)!
        }

        const result = func(...args)
        cache.set(key, result)
        return result
    } as T & { cache: Map<string, ReturnType<T>> }

    memoized.cache = cache
    return memoized
}

/**
 * Once function - ensures function is called only once
 * 
 * @param func - Function to call once
 * @returns Function that can only be called once
 */
export function once<T extends (...args: any[]) => any>(
    func: T
): (...args: Parameters<T>) => ReturnType<T> | undefined {
    let called = false
    let result: ReturnType<T>

    return function (...args: Parameters<T>) {
        if (!called) {
            called = true
            result = func(...args)
            return result
        }
        return result
    }
}

/**
 * Batch function calls - collects multiple calls and executes them in batches
 * 
 * @param func - Function to batch
 * @param wait - Milliseconds to wait before executing batch
 * @returns Batched function
 */
export function batch<T>(
    func: (items: T[]) => void,
    wait: number
): (item: T) => void {
    let items: T[] = []
    let timeout: ReturnType<typeof setTimeout> | null = null

    return function (item: T) {
        items.push(item)

        if (timeout) clearTimeout(timeout)

        timeout = setTimeout(() => {
            func(items)
            items = []
            timeout = null
        }, wait)
    }
}

/**
 * Idle callback - executes function when browser is idle
 * 
 * @param func - Function to execute
 * @param options - Idle callback options
 */
export function runWhenIdle(
    func: () => void,
    options?: IdleRequestOptions
): number {
    if ('requestIdleCallback' in window) {
        return window.requestIdleCallback(func, options)
    }
    // Fallback to setTimeout
    return setTimeout(func, 1) as unknown as number
}

/**
 * Cancel idle callback
 * 
 * @param id - Idle callback ID
 */
export function cancelIdle(id: number): void {
    if ('cancelIdleCallback' in window) {
        window.cancelIdleCallback(id)
    } else {
        clearTimeout(id)
    }
}
