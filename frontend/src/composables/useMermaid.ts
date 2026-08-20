import { nextTick, onBeforeUnmount, onMounted, watch, type Ref, type WatchOptions, type WatchSource } from 'vue'
import { renderMermaidBlocks } from '@/utils/mermaid'

export function useMermaid(
  rootRef: Ref<HTMLElement | null | undefined>,
  watchSources: WatchSource<unknown>[] = [],
  watchOptions?: WatchOptions<boolean>
) {
  let frameId: number | null = null

  const runRender = async () => {
    await nextTick()
    await renderMermaidBlocks(rootRef.value)
  }

  const scheduleMermaidRender = () => {
    if (typeof window === 'undefined') {
      return
    }

    if (frameId !== null && typeof window.cancelAnimationFrame === 'function') {
      window.cancelAnimationFrame(frameId)
      frameId = null
    }

    if (typeof window.requestAnimationFrame === 'function') {
      frameId = window.requestAnimationFrame(() => {
        frameId = null
        void runRender()
      })
      return
    }

    void runRender()
  }

  const handleThemeChange = () => {
    scheduleMermaidRender()
  }

  onMounted(() => {
    scheduleMermaidRender()
    window.addEventListener('theme-change', handleThemeChange)
  })

  onBeforeUnmount(() => {
    if (frameId !== null && typeof window.cancelAnimationFrame === 'function') {
      window.cancelAnimationFrame(frameId)
    }
    window.removeEventListener('theme-change', handleThemeChange)
  })

  if (watchSources.length > 0) {
    watch(watchSources, scheduleMermaidRender, {
      flush: 'post',
      ...watchOptions
    })
  }

  return {
    scheduleMermaidRender
  }
}