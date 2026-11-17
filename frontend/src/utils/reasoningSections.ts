export interface ReasoningSections {
  reasoning: string | null
  content: string | null
}

const HEADING_PATTERN = /^##\s*(思考过程|回复|Reasoning|Response)\s*$/gm
const LEADING_SEPARATOR_PATTERN = /^(?:---\s*\n+)*/
const TRAILING_SEPARATOR_PATTERN = /(?:\n+\s*---\s*)+$/

function normalizeSectionText(text: string): string {
  return text
    .replace(/\r\n/g, '\n')
    .replace(LEADING_SEPARATOR_PATTERN, '')
    .replace(TRAILING_SEPARATOR_PATTERN, '')
    .trim()
}

export function splitReasoningSections(raw: string | null | undefined): ReasoningSections {
  const normalized = String(raw || '').replace(/\r\n/g, '\n').trim()
  if (!normalized) {
    return { reasoning: null, content: null }
  }

  const matches = Array.from(normalized.matchAll(HEADING_PATTERN))
  if (matches.length === 0) {
    return { reasoning: null, content: normalized }
  }

  const reasoningParts: string[] = []
  const contentParts: string[] = []

  const prefix = normalizeSectionText(normalized.slice(0, matches[0].index ?? 0))
  if (prefix) {
    contentParts.push(prefix)
  }

  for (let index = 0; index < matches.length; index += 1) {
    const match = matches[index]
    const label = match[1]
    const sectionStart = (match.index ?? 0) + match[0].length
    const sectionEnd =
      index + 1 < matches.length ? (matches[index + 1].index ?? normalized.length) : normalized.length
    const sectionText = normalizeSectionText(normalized.slice(sectionStart, sectionEnd))
    if (!sectionText) {
      continue
    }

    if (label === '思考过程' || label === 'Reasoning') {
      reasoningParts.push(sectionText)
    } else {
      contentParts.push(sectionText)
    }
  }

  return {
    reasoning: reasoningParts.length > 0 ? reasoningParts.join('\n\n---\n\n') : null,
    content: contentParts.length > 0 ? contentParts.join('\n\n') : null,
  }
}
