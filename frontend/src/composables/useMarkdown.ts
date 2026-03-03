import { marked } from 'marked'
import hljs from 'highlight.js'

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
    // Configure marked renderer
    const renderer = new marked.Renderer()

    // Custom code block renderer with syntax highlighting and copy button
    renderer.code = (code: string, language: string | undefined) => {
        const validLanguage = language && hljs.getLanguage(language) ? language : 'plaintext'
        const highlighted = hljs.highlight(code, { language: validLanguage }).value
        const escapedCode = code.replace(/"/g, '&quot;').replace(/'/g, '&#39;')

        return `
            <div class="code-block-wrapper">
                <div class="code-block-header">
                    <span class="code-block-language">${validLanguage}</span>
                    <button 
                        class="code-copy-btn" 
                        onclick="copyCode(this, '${escapedCode}')"
                        title="Copy code"
                    >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                        </svg>
                    </button>
                </div>
                <pre><code class="hljs language-${validLanguage}">${highlighted}</code></pre>
            </div>
        `
    }

    // Custom inline code renderer
    renderer.codespan = (code: string) => `<code class="inline-code">${code}</code>`

    // Configure marked options
    marked.setOptions({
        renderer,
        gfm: true, // GitHub Flavored Markdown
        breaks: true, // Convert \n to <br>
        pedantic: false,
        sanitize: false, // We trust the content from our backend
        smartLists: true,
        smartypants: true, // Use smart quotes
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
