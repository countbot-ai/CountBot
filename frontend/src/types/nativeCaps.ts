/** 模型原生能力与聊天事件的前端类型。 */

export type DocumentParsingMode = 'off' | 'text' | 'rich'

export interface NativeCapabilities {
  web_search: boolean
  read_url: boolean
  document_parsing: DocumentParsingMode
  safety_check: boolean
  asr: boolean
  tts: boolean
}

export const DEFAULT_NATIVE_CAPABILITIES: NativeCapabilities = {
  web_search: false,
  read_url: false,
  document_parsing: 'off',
  safety_check: false,
  asr: false,
  tts: false,
}

export interface NativeSearchResult {
  title?: string
  url?: string
  snippet?: string
  site_name?: string | null
  site_icon?: string | null
  page_age?: string | null
  image_url?: string | null
  error?: string
}

export interface NativeChatEvent {
  kind: string
  id?: string
  queries?: string[]
  results?: NativeSearchResult[]
  url?: string
  title?: string | null
  cited_text?: string | null
  ok?: boolean
  error?: string | null
  message?: string
  action?: string
  deep?: boolean
  image?: boolean
  published_at?: string | null
  protocol?: string
  blocks?: Record<string, unknown>[]
  server_tool_calls?: Record<string, unknown>[]
}

export function normalizeNativeCapabilities(
  raw?: Partial<NativeCapabilities> | null,
): NativeCapabilities {
  const mode = raw?.document_parsing
  return {
    web_search: Boolean(raw?.web_search),
    read_url: Boolean(raw?.read_url),
    document_parsing: mode === 'text' || mode === 'rich' ? mode : 'off',
    safety_check: Boolean(raw?.safety_check),
    asr: Boolean(raw?.asr),
    tts: Boolean(raw?.tts),
  }
}

export function hasAnyNativeCapability(caps?: NativeCapabilities | null): boolean {
  if (!caps) return false
  return Boolean(
    caps.web_search
      || caps.read_url
      || caps.safety_check
      || caps.asr
      || caps.tts
      || caps.document_parsing !== 'off',
  )
}
