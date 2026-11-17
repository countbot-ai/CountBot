import Panzoom, { type PanzoomObject } from '@panzoom/panzoom'
import { t } from '@/i18n'
import { getEffectiveTheme } from '@/i18n/utils/detector'

type MermaidApi = typeof import('mermaid')['default']

const MERMAID_BLOCK_SELECTOR = '.mermaid-block[data-mermaid-source]'
const MIN_SCALE = 0.15
const MAX_SCALE = 5
const SCALE_STEP = 1.2

interface MermaidViewerState {
  svg: SVGSVGElement
  panzoom: PanzoomObject
  renderTarget: HTMLElement
  scaleLabel: HTMLElement | null
  viewport: HTMLElement
  wheelHandler: (event: WheelEvent) => void
  changeHandler: EventListener
}

let mermaidPromise: Promise<MermaidApi> | null = null
let mermaidRenderId = 0
let hasInstalledMermaidInteractionHandlers = false

const viewerStates = new WeakMap<HTMLElement, MermaidViewerState>()

const escapeHtml = (value: string): string => {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

const getTheme = (): 'light' | 'dark' => {
  if (typeof document === 'undefined') {
    return 'light'
  }

  const activeTheme = document.documentElement.getAttribute('data-theme')
  if (activeTheme === 'light' || activeTheme === 'dark') {
    return activeTheme
  }

  return getEffectiveTheme()
}

const getCssVariable = (name: string, fallback: string): string => {
  if (typeof document === 'undefined') {
    return fallback
  }

  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback
}

const getMermaidConfig = (theme: 'light' | 'dark') => {
  const isDark = theme === 'dark'

  return {
    startOnLoad: false,
    securityLevel: 'strict' as const,
    theme: isDark ? 'dark' as const : 'neutral' as const,
    fontFamily: 'Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    themeVariables: {
      background: 'transparent',
      primaryColor: getCssVariable('--card-bg', isDark ? '#171f2b' : '#ffffff'),
      primaryTextColor: getCssVariable('--text-primary', isDark ? '#e5ecf6' : '#0f172a'),
      primaryBorderColor: getCssVariable('--card-border', isDark ? '#243040' : '#e2e8f0'),
      lineColor: getCssVariable('--text-secondary', isDark ? '#a3b0c2' : '#475569'),
      textColor: getCssVariable('--text-primary', isDark ? '#e5ecf6' : '#0f172a'),
      mainBkg: getCssVariable('--bg-primary', isDark ? '#0d1118' : '#ffffff'),
      secondaryColor: getCssVariable('--bg-secondary', isDark ? '#121821' : '#f8fafc'),
      tertiaryColor: getCssVariable('--bg-tertiary', isDark ? '#18202b' : '#f1f5f9'),
      tertiaryTextColor: getCssVariable('--text-primary', isDark ? '#e5ecf6' : '#0f172a'),
      clusterBkg: getCssVariable('--bg-secondary', isDark ? '#121821' : '#f8fafc'),
      clusterBorder: getCssVariable('--border-color', isDark ? '#223247' : '#e2e8f0'),
      edgeLabelBackground: getCssVariable('--bg-primary', isDark ? '#0d1118' : '#ffffff'),
      noteBkgColor: getCssVariable('--bg-secondary', isDark ? '#121821' : '#f8fafc'),
      noteBorderColor: getCssVariable('--border-color', isDark ? '#223247' : '#e2e8f0'),
      activationBorderColor: getCssVariable('--color-primary', isDark ? '#8ea4d6' : '#334155'),
      activationBkgColor: getCssVariable('--color-primary-light', isDark ? '#151d2a' : '#f1f5f9'),
      sequenceNumberColor: getCssVariable('--color-primary', isDark ? '#8ea4d6' : '#334155')
    }
  }
}

const getMermaid = async (): Promise<MermaidApi> => {
  if (!mermaidPromise) {
    mermaidPromise = import('mermaid').then(module => module.default)
  }

  return mermaidPromise
}

const decodeMermaidSource = (encodedSource: string): string => {
  try {
    return decodeURIComponent(encodedSource)
  } catch {
    return encodedSource
  }
}

const clamp = (value: number, min: number, max: number): number => {
  return Math.min(max, Math.max(min, value))
}

const getViewerState = (block: HTMLElement): MermaidViewerState | undefined => {
  return viewerStates.get(block)
}

const getScaleText = (scale: number): string => {
  return t('chat.mermaid.scaleValue', { value: Math.round(scale * 100) })
}

const updateScaleLabel = (block: HTMLElement, scaleOverride?: number) => {
  const state = getViewerState(block)
  const scaleLabel = state?.scaleLabel ?? block.querySelector<HTMLElement>('[data-mermaid-scale-label]')
  if (!scaleLabel) {
    return
  }

  const scale = scaleOverride ?? state?.panzoom.getScale() ?? 1
  scaleLabel.textContent = getScaleText(scale)
}

const updateFullscreenActionTitle = (block: HTMLElement) => {
  const action = block.querySelector<HTMLElement>('[data-mermaid-action="fullscreen"]')
  if (!action) {
    return
  }

  const isFullscreen = block.dataset.mermaidFullscreen === 'true'
  const label = isFullscreen ? t('chat.mermaid.exitFullscreen') : t('chat.mermaid.fullscreen')

  action.setAttribute('title', label)
  action.setAttribute('aria-label', label)
  action.setAttribute('aria-pressed', isFullscreen ? 'true' : 'false')
}

const destroyMermaidViewer = (block: HTMLElement) => {
  const state = getViewerState(block)
  if (!state) {
    return
  }

  state.viewport.removeEventListener('wheel', state.wheelHandler)
  state.svg.removeEventListener('panzoomchange', state.changeHandler)
  state.panzoom.destroy()
  viewerStates.delete(block)
}

const getDiagramElement = (renderTarget: HTMLElement): SVGSVGElement | null => {
  return renderTarget.querySelector<SVGSVGElement>('svg')
}

const getDiagramDimensions = (renderTarget: HTMLElement): { height: number; width: number } | null => {
  const svg = getDiagramElement(renderTarget)
  if (!svg) {
    return null
  }

  const viewBox = svg.viewBox?.baseVal
  if (viewBox && viewBox.width > 0 && viewBox.height > 0) {
    return { width: viewBox.width, height: viewBox.height }
  }

  const widthAttr = Number.parseFloat(svg.getAttribute('width') || '')
  const heightAttr = Number.parseFloat(svg.getAttribute('height') || '')
  if (Number.isFinite(widthAttr) && widthAttr > 0 && Number.isFinite(heightAttr) && heightAttr > 0) {
    return { width: widthAttr, height: heightAttr }
  }

  if (typeof svg.getBBox === 'function') {
    try {
      const box = svg.getBBox()
      if (box.width > 0 && box.height > 0) {
        return { width: box.width, height: box.height }
      }
    } catch {
      // Ignore and fallback to layout metrics.
    }
  }

  const rect = renderTarget.getBoundingClientRect()
  if (rect.width > 0 && rect.height > 0) {
    return { width: rect.width, height: rect.height }
  }

  return null
}

const syncDiagramSizing = (renderTarget: HTMLElement): { height: number; width: number } | null => {
  const svg = getDiagramElement(renderTarget)
  if (!svg) {
    return null
  }

  const dimensions = getDiagramDimensions(renderTarget)
  if (!dimensions) {
    return null
  }

  svg.style.width = `${dimensions.width}px`
  svg.style.height = `${dimensions.height}px`
  svg.style.maxWidth = 'none'
  svg.style.maxHeight = 'none'

  return dimensions
}

const centerMermaidBlock = (block: HTMLElement, scale: number) => {
  const state = getViewerState(block)
  if (!state) {
    return
  }

  const dimensions = syncDiagramSizing(state.renderTarget)
  if (!dimensions) {
    updateScaleLabel(block, scale)
    return
  }

  const nextScale = clamp(scale, MIN_SCALE, MAX_SCALE)
  state.panzoom.reset({ animate: false, force: true })
  state.panzoom.zoom(nextScale, { animate: false, force: true })

  const x = (state.viewport.clientWidth - dimensions.width * nextScale) / 2
  const y = (state.viewport.clientHeight - dimensions.height * nextScale) / 2
  state.panzoom.pan(x, y, { animate: false, force: true })
  updateScaleLabel(block, nextScale)
}

const resetMermaidBlock = (block: HTMLElement) => {
  centerMermaidBlock(block, 1)
}

const fitMermaidBlock = (block: HTMLElement) => {
  const state = getViewerState(block)
  if (!state) {
    return
  }

  const dimensions = syncDiagramSizing(state.renderTarget)
  if (!dimensions) {
    updateScaleLabel(block, 1)
    return
  }

  const horizontalPadding = Math.max(20, Math.min(48, state.viewport.clientWidth * 0.05))
  const verticalPadding = Math.max(20, Math.min(48, state.viewport.clientHeight * 0.08))
  const availableWidth = Math.max(80, state.viewport.clientWidth - horizontalPadding * 2)
  const availableHeight = Math.max(80, state.viewport.clientHeight - verticalPadding * 2)
  const fitScale = clamp(
    Math.min(availableWidth / dimensions.width, availableHeight / dimensions.height, 1),
    MIN_SCALE,
    MAX_SCALE
  )

  centerMermaidBlock(block, fitScale)
}

const zoomMermaidBlock = (block: HTMLElement, direction: 'in' | 'out') => {
  const state = getViewerState(block)
  if (!state) {
    return
  }

  const currentScale = state.panzoom.getScale()
  const nextScale = clamp(
    direction === 'in' ? currentScale * SCALE_STEP : currentScale / SCALE_STEP,
    MIN_SCALE,
    MAX_SCALE
  )
  const rect = state.viewport.getBoundingClientRect()

  state.panzoom.zoomToPoint(
    nextScale,
    {
      clientX: rect.left + rect.width / 2,
      clientY: rect.top + rect.height / 2
    },
    { animate: false, force: true }
  )

  updateScaleLabel(block, nextScale)
}

const toggleMermaidFullscreen = async (block: HTMLElement) => {
  if (typeof document === 'undefined') {
    return
  }

  try {
    if (document.fullscreenElement === block) {
      await document.exitFullscreen()
      return
    }

    await block.requestFullscreen()
  } catch (error) {
    console.error('Failed to toggle Mermaid fullscreen:', error)
  }
}

const setupMermaidViewer = (block: HTMLElement) => {
  const viewport = block.querySelector<HTMLElement>('[data-mermaid-viewport]')
  const renderTarget = block.querySelector<HTMLElement>('[data-mermaid-render-target]')
  const scaleLabel = block.querySelector<HTMLElement>('[data-mermaid-scale-label]')
  const svg = renderTarget ? getDiagramElement(renderTarget) : null

  updateFullscreenActionTitle(block)

  if (!viewport || !renderTarget || !svg) {
    destroyMermaidViewer(block)
    updateScaleLabel(block, 1)
    return
  }

  destroyMermaidViewer(block)
  syncDiagramSizing(renderTarget)

  const panzoom = Panzoom(svg, {
    animate: false,
    cursor: 'grab',
    maxScale: MAX_SCALE,
    minScale: MIN_SCALE,
    step: SCALE_STEP - 1
  })

  const wheelHandler = (event: WheelEvent) => {
    if (!event.ctrlKey && !event.metaKey) {
      return
    }

    event.preventDefault()
    panzoom.zoomWithWheel(event, { animate: false, force: true })
    updateScaleLabel(block)
  }

  const changeHandler: EventListener = () => {
    updateScaleLabel(block)
  }

  viewport.addEventListener('wheel', wheelHandler, { passive: false })
  svg.addEventListener('panzoomchange', changeHandler)

  viewerStates.set(block, {
    svg,
    panzoom,
    renderTarget,
    scaleLabel,
    viewport,
    wheelHandler,
    changeHandler
  })

  updateScaleLabel(block)
  window.requestAnimationFrame(() => {
    window.requestAnimationFrame(() => {
      fitMermaidBlock(block)
    })
  })
}

const renderErrorState = (block: HTMLElement, source: string, message: string) => {
  const renderTarget = block.querySelector<HTMLElement>('[data-mermaid-render-target]')
  if (!renderTarget) {
    return
  }

  destroyMermaidViewer(block)
  renderTarget.innerHTML = `
    <div class="mermaid-block__error">${escapeHtml(message)}</div>
    <pre class="mermaid-block__source"><code>${escapeHtml(source)}</code></pre>
  `
  delete block.dataset.mermaidRendered
  updateScaleLabel(block, 1)
}

const renderMermaidBlock = async (block: HTMLElement, mermaid: MermaidApi, theme: 'light' | 'dark') => {
  const renderTarget = block.querySelector<HTMLElement>('[data-mermaid-render-target]')
  const encodedSource = block.dataset.mermaidSource

  if (!renderTarget || !encodedSource) {
    return
  }

  const source = decodeMermaidSource(encodedSource).trim()
  if (!source) {
    return
  }

  const renderKey = `${theme}::${source}`
  if (block.dataset.mermaidRendered === renderKey && renderTarget.querySelector('svg')) {
    setupMermaidViewer(block)
    return
  }

  try {
    const renderResult = await mermaid.render(`countbot-mermaid-${++mermaidRenderId}`, source)
    renderTarget.innerHTML = renderResult.svg
    renderResult.bindFunctions?.(renderTarget)
    block.dataset.mermaidRendered = renderKey
    setupMermaidViewer(block)
  } catch (error) {
    console.error('Mermaid rendering failed:', error)
    renderErrorState(block, source, t('chat.mermaid.renderFailed'))
  }
}

const syncMermaidFullscreenState = () => {
  if (typeof document === 'undefined') {
    return
  }

  const fullscreenBlock = document.fullscreenElement instanceof HTMLElement &&
    document.fullscreenElement.matches(MERMAID_BLOCK_SELECTOR)
      ? document.fullscreenElement
      : null
  const activeBlocks = Array.from(
    document.querySelectorAll<HTMLElement>(`${MERMAID_BLOCK_SELECTOR}[data-mermaid-fullscreen="true"]`)
  )

  activeBlocks.forEach(block => {
    delete block.dataset.mermaidFullscreen
    updateFullscreenActionTitle(block)
    window.requestAnimationFrame(() => {
      fitMermaidBlock(block)
    })
  })

  if (fullscreenBlock) {
    fullscreenBlock.dataset.mermaidFullscreen = 'true'
    updateFullscreenActionTitle(fullscreenBlock)
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        fitMermaidBlock(fullscreenBlock)
      })
    })
  }
}

const handleMermaidAction = (block: HTMLElement, action: string) => {
  switch (action) {
    case 'zoom-in':
      zoomMermaidBlock(block, 'in')
      break
    case 'zoom-out':
      zoomMermaidBlock(block, 'out')
      break
    case 'fit':
      fitMermaidBlock(block)
      break
    case 'reset':
      resetMermaidBlock(block)
      break
    case 'fullscreen':
      void toggleMermaidFullscreen(block)
      break
    default:
      break
  }
}

const installMermaidInteractionHandlers = () => {
  if (hasInstalledMermaidInteractionHandlers || typeof document === 'undefined') {
    return
  }

  document.addEventListener('click', event => {
    const target = event.target as Element | null
    const actionElement = target?.closest<HTMLElement>('[data-mermaid-action]')
    if (!actionElement) {
      return
    }

    const block = actionElement.closest<HTMLElement>(MERMAID_BLOCK_SELECTOR)
    const action = actionElement.dataset.mermaidAction
    if (!block || !action) {
      return
    }

    handleMermaidAction(block, action)
  })

  document.addEventListener('keydown', event => {
    const target = event.target as HTMLElement | null
    if (!target?.matches('[data-mermaid-action]')) {
      return
    }

    if (event.key !== 'Enter' && event.key !== ' ') {
      return
    }

    const block = target.closest<HTMLElement>(MERMAID_BLOCK_SELECTOR)
    const action = target.dataset.mermaidAction
    if (!block || !action) {
      return
    }

    event.preventDefault()
    handleMermaidAction(block, action)
  })

  document.addEventListener('fullscreenchange', syncMermaidFullscreenState)
  hasInstalledMermaidInteractionHandlers = true
}

export async function renderMermaidBlocks(root: ParentNode | null | undefined): Promise<void> {
  if (!root || typeof window === 'undefined') {
    return
  }

  installMermaidInteractionHandlers()

  const blocks = Array.from(root.querySelectorAll<HTMLElement>(MERMAID_BLOCK_SELECTOR))
  if (!blocks.length) {
    return
  }

  const theme = getTheme()
  const mermaid = await getMermaid()
  mermaid.initialize(getMermaidConfig(theme))

  await Promise.all(blocks.map(block => renderMermaidBlock(block, mermaid, theme)))
}
