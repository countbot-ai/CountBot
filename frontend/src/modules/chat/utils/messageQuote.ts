import type { MessageQuote } from '@/types/chat'

/**
 * 引用在消息正文里的存储格式（同时也是发给模型的内容）：
 *
 * > 引用 · 我
 * > 被引用的原文
 *
 * 用户本次输入
 *
 * 用固定文本而不是结构化字段，是为了不改动后端存储与历史加载逻辑：
 * 引用内容天然进入上下文，重载历史后也能被 splitQuotedContent 还原成引用卡片。
 */

/** 引用正文最多带入上下文的字符数，避免一条长回复挤占上下文 */
export const QUOTE_MAX_CHARS = 800

const QUOTE_HEADER = /^>\s*引用\s*[·・:：]\s*(我|AI)\s*$/

export interface QuotedContentParts {
  /** 被引用的正文，没有引用时为 null */
  quote: string | null
  quoteRole: 'user' | 'assistant' | null
  /** 用户本次真正输入的内容 */
  body: string
}

export function buildQuotedContent(
  quote: MessageQuote,
  body: string,
  maxChars: number = QUOTE_MAX_CHARS,
): string {
  const raw = (quote.content || '').trim()
  if (!raw) return body
  const text = raw.length > maxChars ? `${raw.slice(0, maxChars)}…` : raw
  const header = `> 引用 · ${quote.role === 'user' ? '我' : 'AI'}`
  const quoted = text
    .split('\n')
    .map((line) => `> ${line}`.trimEnd())
    .join('\n')
  return body ? `${header}\n${quoted}\n\n${body}` : `${header}\n${quoted}`
}

export function splitQuotedContent(content: string): QuotedContentParts {
  const body = content || ''
  const empty: QuotedContentParts = { quote: null, quoteRole: null, body }
  if (!body) return empty

  const lines = body.split('\n')
  const header = QUOTE_HEADER.exec(lines[0])
  if (!header) return empty

  const quoteLines: string[] = []
  let index = 1
  while (index < lines.length && lines[index].startsWith('>')) {
    quoteLines.push(lines[index].replace(/^>\s?/, ''))
    index += 1
  }
  if (lines[index] === '') index += 1

  return {
    quote: quoteLines.join('\n'),
    quoteRole: header[1] === 'AI' ? 'assistant' : 'user',
    body: lines.slice(index).join('\n'),
  }
}
