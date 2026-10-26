/**
 * 模型供应商设置的常量与纯函数。
 * 只保留无状态逻辑，方便被三个 composable 与子组件共用。
 */

import type { ProviderApiType } from '@/api'

/** 本地推理服务：不要求 API Key。 */
export const LOCAL_PROVIDERS = ['ollama', 'vllm', 'lm_studio']

/** 自定义接口：不要求 API Key。 */
export const NO_API_KEY_PROVIDERS = ['custom_openai', 'custom_anthropic']

/** 需要用户手填 Base URL 的供应商。 */
export const CUSTOM_PROVIDERS = ['custom_openai', 'custom_anthropic']

export const DEFAULT_API_TYPE: ProviderApiType = 'openai-chat-completions'
export const ANTHROPIC_API_TYPE: ProviderApiType = 'anthropic-messages'

/** Anthropic 系走 messages 协议，其余默认 chat.completions。 */
export function resolveDefaultApiType(providerId: string | undefined): ProviderApiType {
  return providerId === 'anthropic' || providerId === 'custom_anthropic'
    ? ANTHROPIC_API_TYPE
    : DEFAULT_API_TYPE
}

/** 去重 + 去空的密钥清理，供草稿与持久化共用。 */
export function normalizeApiKeys(values: string[] | undefined, fallbackApiKey = ''): string[] {
  const normalized: string[] = []
  const seen = new Set<string>()

  const push = (value: string | undefined) => {
    const trimmed = String(value || '').trim()
    if (!trimmed || seen.has(trimmed)) {
      return
    }
    seen.add(trimmed)
    normalized.push(trimmed)
  }

  for (const value of values || []) {
    push(value)
  }
  push(fallbackApiKey)

  return normalized
}

/** 输入框至少要有一行，即使密钥为空。 */
export function buildEditableApiKeys(
  values: string[] | undefined,
  fallbackApiKey = '',
): string[] {
  const normalized = normalizeApiKeys(values, fallbackApiKey)
  return normalized.length ? normalized : ['']
}
