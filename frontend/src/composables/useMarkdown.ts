import { marked } from 'marked'
import hljs from 'highlight.js'
import { copyTextToClipboard } from '@/utils/clipboard'
import { t } from '@/i18n'

const COPY_BUTTON_SELECTOR = '.code-copy-btn'
const COPY_ICON = `
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
    </svg>
`
const COPIED_ICON = `
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <polyline points="20 6 9 17 4 12"></polyline>
    </svg>
`
const MERMAID_ZOOM_OUT_ICON = `
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="11" cy="11" r="7"></circle>
        <path d="M8 11h6"></path>
        <path d="m20 20-3.5-3.5"></path>
    </svg>
`
const MERMAID_ZOOM_IN_ICON = `
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="11" cy="11" r="7"></circle>
        <path d="M11 8v6"></path>
        <path d="M8 11h6"></path>
        <path d="m20 20-3.5-3.5"></path>
    </svg>
`
const MERMAID_RESET_ICON = `
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M3 12a9 9 0 1 0 3-6.7"></path>
        <path d="M3 4v4h4"></path>
    </svg>
`
const MERMAID_FIT_ICON = `
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M9 9H5V5"></path>
        <path d="M15 9h4V5"></path>
        <path d="M9 15H5v4"></path>
        <path d="M15 15h4v4"></path>
    </svg>
`
const MERMAID_FULLSCREEN_ICON = `
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M8 3H5a2 2 0 0 0-2 2v3"></path>
        <path d="M16 3h3a2 2 0 0 1 2 2v3"></path>
        <path d="M8 21H5a2 2 0 0 1-2-2v-3"></path>
        <path d="M16 21h3a2 2 0 0 0 2-2v-3"></path>
    </svg>
`

const getMermaidActionMarkup = (action: string, title: string, icon: string) => {
    const escapedTitle = escapeHtml(title)

    return `
        <div
            class="mermaid-block__action"
            role="button"
            tabindex="0"
            data-mermaid-action="${action}"
            title="${escapedTitle}"
            aria-label="${escapedTitle}"
        >
            ${icon}
        </div>
    `
}

let hasInstalledCodeCopyHandler = false

const escapeHtml = (value: string): string => {
    return value
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;')
}

const normalizeLanguage = (language?: string): string => {
    return language?.trim().toLowerCase() || ''
}

const getCodeBlockLanguage = (language?: string): string => {
    const normalized = normalizeLanguage(language)
    return normalized && hljs.getLanguage(normalized) ? normalized : 'plaintext'
}

const getCodeBlockLabel = (language: string): string => {
    if (language === 'plaintext') {
        return 'Plain text'
    }

    return language.replace(/[-_]/g, ' ')
}

const getHighlightedCode = (code: string, language: string): string => {
    if (language === 'plaintext') {
        return escapeHtml(code)
    }

    try {
        return hljs.highlight(code, { language }).value
    } catch {
        return escapeHtml(code)
    }
}

const showCopySuccess = (button: HTMLButtonElement) => {
    button.innerHTML = COPIED_ICON
    button.classList.add('copied')
    button.setAttribute('title', 'Copied')
    button.setAttribute('aria-label', 'Copied')

    window.setTimeout(() => {
        button.innerHTML = COPY_ICON
        button.classList.remove('copied')
        button.setAttribute('title', 'Copy code')
        button.setAttribute('aria-label', 'Copy code')
    }, 2000)
}

const installCodeCopyHandler = () => {
    if (hasInstalledCodeCopyHandler || typeof document === 'undefined') {
        return
    }

    document.addEventListener('click', async event => {
        const target = event.target as Element | null
        const button = target?.closest<HTMLButtonElement>(COPY_BUTTON_SELECTOR)

        if (!button) {
            return
        }

        const encodedCode = button.dataset.code
        if (!encodedCode) {
            return
        }

        try {
            await copyTextToClipboard(decodeURIComponent(encodedCode))
            showCopySuccess(button)
        } catch (error) {
            console.error('Failed to copy code:', error)
        }
    })

    hasInstalledCodeCopyHandler = true
}

/**
 * Markdown rendering composable with syntax highlighting
 * 
 * Features:
 * - Markdown to HTML conversion using marked
 * - Syntax highlighting for code blocks using highlight.js
 * - Safe HTML rendering with sanitization
 * - Support for inline code and code blocks
 */
export function useMarkdown() {
    installCodeCopyHandler()

    // Configure marked renderer
    const renderer = new marked.Renderer()

    // Custom code block renderer with syntax highlighting and copy button
    renderer.code = (code: string, language: string | undefined) => {
        const normalizedLanguage = normalizeLanguage(language)

        if (normalizedLanguage === 'mermaid') {
            const encodedSource = escapeHtml(encodeURIComponent(code.trim()))
            const mermaidTitle = escapeHtml(t('chat.mermaid.title'))
            const mermaidHint = escapeHtml(t('chat.mermaid.hint'))
            const mermaidLoading = escapeHtml(t('chat.mermaid.loading'))
            const mermaidToolbar = escapeHtml(t('chat.mermaid.toolbar'))
            const mermaidScale = escapeHtml(t('chat.mermaid.scale'))
            const mermaidScaleValue = escapeHtml(t('chat.mermaid.scaleValue', { value: 100 }))

            return `
                <div class="mermaid-block" data-mermaid-source="${encodedSource}">
                    <div class="mermaid-block__header">
                        <div class="mermaid-block__meta">
                            <span class="mermaid-block__badge">Mermaid</span>
                            <div class="mermaid-block__copy">
                                <span class="mermaid-block__title">${mermaidTitle}</span>
                                <span class="mermaid-block__hint">${mermaidHint}</span>
                            </div>
                        </div>

                        <div class="mermaid-block__actions" role="toolbar" aria-label="${mermaidToolbar}">
                            ${getMermaidActionMarkup('zoom-out', t('chat.mermaid.zoomOut'), MERMAID_ZOOM_OUT_ICON)}
                            <div class="mermaid-block__scale" data-mermaid-scale-label aria-label="${mermaidScale}">${mermaidScaleValue}</div>
                            ${getMermaidActionMarkup('zoom-in', t('chat.mermaid.zoomIn'), MERMAID_ZOOM_IN_ICON)}
                            ${getMermaidActionMarkup('fit', t('chat.mermaid.fit'), MERMAID_FIT_ICON)}
                            ${getMermaidActionMarkup('reset', t('chat.mermaid.reset'), MERMAID_RESET_ICON)}
                            ${getMermaidActionMarkup('fullscreen', t('chat.mermaid.fullscreen'), MERMAID_FULLSCREEN_ICON)}
                        </div>
                    </div>

                    <div class="mermaid-block__viewport" data-mermaid-viewport>
                        <div class="mermaid-block__canvas" data-mermaid-canvas>
                            <div class="mermaid-block__render" data-mermaid-render-target>
                                <div class="mermaid-block__loading">${mermaidLoading}</div>
                            </div>
                        </div>
                    </div>

                    <div class="mermaid-block__footer">
                        <span class="mermaid-block__footer-label">${mermaidHint}</span>
                    </div>
                </div>
            `
        }

        const validLanguage = getCodeBlockLanguage(language)
        const highlighted = getHighlightedCode(code, validLanguage)
        const displayLanguage = getCodeBlockLabel(validLanguage)
        const encodedCode = escapeHtml(encodeURIComponent(code))

        return `
            <div class="code-block-wrapper">
                <div class="code-block-header">
                    <span class="code-block-language">${displayLanguage}</span>
                    <button 
                        class="code-copy-btn"
                        type="button"
                        data-code="${encodedCode}"
                        title="Copy code"
                        aria-label="Copy code"
                    >
                        ${COPY_ICON}
                    </button>
                </div>
                <pre><code class="hljs language-${validLanguage}">${highlighted}</code></pre>
            </div>
        `
    }

    // Custom inline code renderer
    renderer.codespan = (code: string) => `<code class="inline-code">${escapeHtml(code)}</code>`

    // Configure marked options
    marked.setOptions({
        renderer,
        gfm: true, // GitHub Flavored Markdown
        breaks: true, // Convert \n to <br>
        pedantic: false
    })

    /**
     * Render markdown to HTML
     * @param markdown - Raw markdown string
     * @returns HTML string
     */
    const renderMarkdown = (markdown: string): string => {
        if (!markdown) return ''

        try {
            return marked.parse(markdown) as string
        } catch (error) {
            console.error('Markdown rendering error:', error)
            return markdown // Fallback to plain text
        }
    }

    /**
     * Extract code blocks from markdown
     * @param markdown - Raw markdown string
     * @returns Array of code blocks with language and content
     */
    const extractCodeBlocks = (markdown: string): Array<{ language: string; code: string }> => {
        const codeBlockRegex = /```(\w+)?\n([\s\S]*?)```/g
        const blocks: Array<{ language: string; code: string }> = []
        let match

        while ((match = codeBlockRegex.exec(markdown)) !== null) {
            blocks.push({
                language: match[1] || 'plaintext',
                code: match[2].trim()
            })
        }

        return blocks
    }

    /**
     * Check if text contains markdown syntax
     * @param text - Text to check
     * @returns True if text contains markdown
     */
    const hasMarkdown = (text: string): boolean => {
        const markdownPatterns = [
            /^#{1,6}\s/, // Headers
            /\*\*.*\*\*/, // Bold
            /\*.*\*/, // Italic
            /\[.*\]\(.*\)/, // Links
            /```[\s\S]*```/, // Code blocks
            /`.*`/, // Inline code
            /^[-*+]\s/, // Lists
            /^\d+\.\s/, // Numbered lists
            /^>\s/, // Blockquotes
        ]

        return markdownPatterns.some(pattern => pattern.test(text))
    }

    return {
        renderMarkdown,
        extractCodeBlocks,
        hasMarkdown
    }
}
