import { ref, onMounted, onBeforeUnmount } from 'vue'

/**
 * Composable for lazy loading elements using Intersection Observer
 * 
 * @param options - IntersectionObserver options
 * @returns Object with element ref and isVisible state
 */
export function useLazyLoad(options: IntersectionObserverInit = {}) {
    const elementRef = ref<HTMLElement>()
    const isVisible = ref(false)
    let observer: IntersectionObserver | null = null

    const defaultOptions: IntersectionObserverInit = {
        root: null,
        rootMargin: '50px',
        threshold: 0.01,
        ...options
    }

    onMounted(() => {
        if (!elementRef.value) return

        observer = new IntersectionObserver((entries) => {
            entries.forEach((entry) => {
                if (entry.isIntersecting && !isVisible.value) {
                    isVisible.value = true
                    // Once visible, stop observing
                    if (observer && elementRef.value) {
                        observer.unobserve(elementRef.value)
                    }
                }
            })
        }, defaultOptions)

        observer.observe(elementRef.value)
    })

    onBeforeUnmount(() => {
        if (observer && elementRef.value) {
            observer.unobserve(elementRef.value)
            observer.disconnect()
        }
    })

    return {
        elementRef,
        isVisible
    }
}

/**
 * Composable for lazy loading images
 * 
 * @param src - Image source URL
 * @param options - IntersectionObserver options
 * @returns Object with image ref, loading state, and error state
 */
export function useLazyImage(src: string, options: IntersectionObserverInit = {}) {
    const { elementRef, isVisible } = useLazyLoad(options)
    const isLoaded = ref(false)
    const hasError = ref(false)
    const currentSrc = ref<string>()

    // Watch for visibility and load image
    const loadImage = () => {
        if (!isVisible.value || !src) return

        const img = new Image()

        img.onload = () => {
            currentSrc.value = src
            isLoaded.value = true
            hasError.value = false
        }

        img.onerror = () => {
            hasError.value = true
            isLoaded.value = false
        }

        img.src = src
    }

    // Load image when visible
    onMounted(() => {
        const unwatch = () => {
            if (isVisible.value) {
                loadImage()
            }
        }

        // Watch for visibility changes
        const interval = setInterval(() => {
            if (isVisible.value) {
                loadImage()
                clearInterval(interval)
            }
        }, 100)

        // Cleanup
        onBeforeUnmount(() => {
            clearInterval(interval)
        })
    })

    return {
        elementRef,
        isVisible,
        isLoaded,
        hasError,
        currentSrc
    }
}
