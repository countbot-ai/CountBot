/**
 * 模型供应商设置的常量与纯函数。
 * 只保留无状态逻辑，方便被三个 composable 与子组件共用。
 */

import type { ProviderApiType, ProviderConfig, ProviderMetadata } from '@/api'

/** 本地推理服务：不要求 API Key。 */
export const LOCAL_PROVIDERS = ['ollama', 'vllm', 'lm_studio']

/** 自定义接口：不要求 API Key。 */
export const NO_API_KEY_PROVIDERS = ['custom_openai', 'custom_anthropic']

/** 该供应商是否必须配置 API Key。 */
export function providerRequiresApiKey(providerId: string | undefined): boolean {
  const key = providerId || ''
  return !LOCAL_PROVIDERS.includes(key) && !NO_API_KEY_PROVIDERS.includes(key)
}

/** 需要用户手填 Base URL 的供应商。 */
export const CUSTOM_PROVIDERS = ['custom_openai', 'custom_anthropic']

export const DEFAULT_API_TYPE: ProviderApiType = 'openai-chat-completions'
export const ANTHROPIC_API_TYPE: ProviderApiType = 'anthropic-messages'

/**
 * 同一供应商在不同 API 协议下的专用根地址。
 * 例：DeepSeek 的 OpenAI 兼容端点是 /v1，Anthropic 兼容端点是 /anthropic。
 */
const API_TYPE_BASE_URLS: Record<string, Partial<Record<ProviderApiType, string>>> = {
  deepseek: {
    'anthropic-messages': 'https://api.deepseek.com/anthropic',
  },
}

/** 该供应商 + 协议是否有专用的根地址，没有则返回空串。 */
export function resolveApiTypeBaseUrl(
  providerId: string | undefined,
  apiType: ProviderApiType,
): string {
  return API_TYPE_BASE_URLS[providerId || '']?.[apiType] || ''
}

/** Anthropic 系与 DeepSeek 官方默认走 messages 协议，其余默认 chat.completions。 */
export function resolveDefaultApiType(providerId: string | undefined): ProviderApiType {
  return providerId === 'anthropic' || providerId === 'custom_anthropic' || providerId === 'deepseek'
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

/**
 * 连接信息的可比较签名。
 *
 * 只比较会写回后端的字段，并在这里补上默认值——
 * 例如已保存的 `api_base` 为空时界面会展示默认地址，不能因此被判成「有未保存更改」。
 */
export function buildConnectionSignature(
  meta: ProviderMetadata,
  config?: ProviderConfig,
): string {
  const defaultBase = (meta.defaultApiBase || meta.default_api_base || '').replace(/\/+$/, '')
  return JSON.stringify({
    name: String(config?.name || '').trim(),
    api_base: String(config?.api_base || defaultBase || '').replace(/\/+$/, ''),
    api_type: config?.api_type || resolveDefaultApiType(meta.id),
    enabled: config?.enabled !== false,
    api_keys: normalizeApiKeys(config?.api_keys, config?.api_key || ''),
  })
}

/**
 * 供应商展示名：优先用 i18n 里的本地化名称，其次用后端元数据，最后回落到 ID。
 * 用户自定义的显示名不在这里处理，由调用方优先判断。
 */
export function resolveProviderLabel(
  providerId: string,
  translate: (key: string) => string,
  hasTranslation: (key: string) => boolean,
  fallback = '',
): string {
  const key = `settings.providers.${providerId}`
  if (providerId && hasTranslation(key)) {
    return translate(key)
  }
  return fallback || providerId
}
