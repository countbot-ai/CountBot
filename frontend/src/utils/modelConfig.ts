export interface ModelConfigLike {
  provider?: string
  model?: string
  api_mode?: 'chat_completions'
  temperature?: number
  max_tokens?: number
  max_iterations?: number
  thinking_enabled?: boolean
  api_key?: string
  api_base?: string
}

export const MODEL_CONFIG_FALLBACK: Required<ModelConfigLike> = {
  provider: 'zhipu',
  model: 'glm-5',
  api_mode: 'chat_completions',
  temperature: 0,
  max_tokens: 0,
  max_iterations: 25,
  thinking_enabled: true,
  api_key: '',
  api_base: '',
}

export const MAX_TOKENS_INPUT_STEP = 1000
export const MAX_TOKENS_INPUT_MAX = 2_000_000
export const MAX_TOKENS_PRESET_VALUES = [
  0,
  4_000,
  8_000,
  16_000,
  32_000,
  64_000,
  128_000,
  256_000,
  512_000,
  1_050_000,
] as const
export const MAX_TOKENS_SLIDER_STEP = 1
export const MAX_TOKENS_SLIDER_MAX = MAX_TOKENS_PRESET_VALUES.length - 1

const STRING_KEYS = new Set<keyof ModelConfigLike>([
  'provider',
  'model',
  'api_mode',
  'api_key',
  'api_base',
])

const DIFF_KEYS: Array<keyof ModelConfigLike> = [
  'provider',
  'model',
  'api_mode',
  'temperature',
  'max_tokens',
  'max_iterations',
  'thinking_enabled',
  'api_key',
  'api_base',
]

function assignDefined(target: ModelConfigLike, source?: Partial<ModelConfigLike> | null) {
  if (!source) {
    return
  }

  for (const key of DIFF_KEYS) {
    if (source[key] !== undefined) {
      ;(target as Record<string, unknown>)[key] = source[key]
    }
  }
}

export function buildEffectiveModelConfig<T extends ModelConfigLike>(
  base?: Partial<T> | null,
  override?: Partial<T> | null,
): T {
  const merged: ModelConfigLike = { ...MODEL_CONFIG_FALLBACK }
  assignDefined(merged, base)
  assignDefined(merged, override)
  merged.api_mode = 'chat_completions'
  merged.api_key = typeof merged.api_key === 'string' ? merged.api_key : ''
  merged.api_base = typeof merged.api_base === 'string' ? merged.api_base : ''
  return merged as T
}

export function buildCustomModelEditorConfig<T extends ModelConfigLike>(
  base?: Partial<T> | null,
  override?: Partial<T> | null,
): T {
  const provider =
    typeof override?.provider === 'string' && override.provider !== ''
      ? override.provider
      : typeof base?.provider === 'string' && base.provider !== ''
        ? base.provider
        : MODEL_CONFIG_FALLBACK.provider

  const model =
    typeof override?.model === 'string' && override.model !== ''
      ? override.model
      : typeof base?.model === 'string' && base.model !== ''
        ? base.model
        : MODEL_CONFIG_FALLBACK.model

  return {
    ...MODEL_CONFIG_FALLBACK,
    provider,
    model,
    api_mode: 'chat_completions',
    temperature: override?.temperature ?? MODEL_CONFIG_FALLBACK.temperature,
    max_tokens: override?.max_tokens ?? MODEL_CONFIG_FALLBACK.max_tokens,
    max_iterations: override?.max_iterations ?? MODEL_CONFIG_FALLBACK.max_iterations,
    thinking_enabled: override?.thinking_enabled ?? MODEL_CONFIG_FALLBACK.thinking_enabled,
    api_key: typeof override?.api_key === 'string' ? override.api_key : '',
    api_base: typeof override?.api_base === 'string' ? override.api_base : '',
  } as T
}

export function buildModelConfigOverrides<T extends ModelConfigLike>(
  current?: Partial<T> | null,
  base?: Partial<T> | null,
): Partial<T> {
  const effectiveCurrent = buildEffectiveModelConfig<T>(base, current)
  const effectiveBase = buildEffectiveModelConfig<T>(base)
  const overrides: Partial<T> = {}

  for (const key of DIFF_KEYS) {
    const currentValue = effectiveCurrent[key]
    const baseValue = effectiveBase[key]
    if (currentValue === baseValue) {
      continue
    }

    if (STRING_KEYS.has(key)) {
      if (typeof currentValue === 'string' && currentValue !== '') {
        overrides[key as keyof T] = currentValue as T[keyof T]
      }
      continue
    }

    overrides[key as keyof T] = currentValue as T[keyof T]
  }

  return overrides
}

export function buildSendableModelConfig(
  config?: Pick<ModelConfigLike, 'temperature' | 'max_tokens' | 'thinking_enabled'> | null,
): Partial<Pick<ModelConfigLike, 'temperature' | 'max_tokens' | 'thinking_enabled'>> {
  const payload: Partial<
    Pick<ModelConfigLike, 'temperature' | 'max_tokens' | 'thinking_enabled'>
  > = {}

  if (config?.temperature != null && config.temperature > 0) {
    payload.temperature = config.temperature
  }

  if (config?.max_tokens != null && config.max_tokens > 0) {
    payload.max_tokens = config.max_tokens
  }

  if (config?.thinking_enabled != null) {
    payload.thinking_enabled = config.thinking_enabled
  }

  return payload
}

function stripTrailingZeros(value: string): string {
  return value.replace(/\.0+$|(\.\d*[1-9])0+$/, '$1')
}

function findClosestMaxTokensPresetIndex(value: number): number {
  let closestIndex = 0
  let closestDistance = Math.abs(MAX_TOKENS_PRESET_VALUES[0] - value)

  for (let index = 1; index < MAX_TOKENS_PRESET_VALUES.length; index += 1) {
    const nextDistance = Math.abs(MAX_TOKENS_PRESET_VALUES[index] - value)
    if (nextDistance < closestDistance) {
      closestIndex = index
      closestDistance = nextDistance
    }
  }

  return closestIndex
}

export function normalizeMaxTokensValue(value?: number | null): number {
  if (!Number.isFinite(value) || value == null || value <= 0) {
    return 0
  }

  const rounded = Math.round(value / MAX_TOKENS_INPUT_STEP) * MAX_TOKENS_INPUT_STEP
  return Math.min(MAX_TOKENS_INPUT_MAX, Math.max(MAX_TOKENS_INPUT_STEP, rounded))
}

export function getMaxTokensSliderIndex(value?: number | null): number {
  return findClosestMaxTokensPresetIndex(normalizeMaxTokensValue(value))
}

export function getMaxTokensValueFromSliderIndex(index?: number | null): number {
  if (!Number.isFinite(index)) {
    return MAX_TOKENS_PRESET_VALUES[0]
  }

  const normalizedIndex = Math.min(
    MAX_TOKENS_SLIDER_MAX,
    Math.max(0, Math.round(index as number)),
  )

  return MAX_TOKENS_PRESET_VALUES[normalizedIndex] ?? MAX_TOKENS_PRESET_VALUES[0]
}

export function normalizeMaxTokensSliderValue(value?: number | null): number {
  if (value == null || value <= 0) {
    return 0
  }

  return normalizeMaxTokensValue(value)
}

export function formatMaxTokensValue(
  value?: number | null,
  labels?: {
    unlimitedLabel?: string
  },
): string {
  const unlimitedLabel = labels?.unlimitedLabel || 'Provider Default'

  if (value == null || value <= 0) {
    return unlimitedLabel
  }

  if (value >= 1_000_000) {
    const megaTokens = value / 1_000_000
    const precision = Number.isInteger(megaTokens) ? 0 : 2
    return `${stripTrailingZeros(megaTokens.toFixed(precision))}M`
  }

  if (value >= 1_000) {
    const kiloTokens = value / 1_000
    const precision = Number.isInteger(kiloTokens) ? 0 : 1
    return `${stripTrailingZeros(kiloTokens.toFixed(precision))}K`
  }

  return String(value)
}

export function formatModelConfigSummary(
  config: Pick<ModelConfigLike, 'temperature' | 'max_tokens' | 'max_iterations'>,
  labels?: {
    defaultLabel?: string
    unlimitedLabel?: string
  },
): string {
  const defaultLabel = labels?.defaultLabel || 'Default'
  const unlimitedLabel = labels?.unlimitedLabel || 'Provider Default'

  const temperatureLabel =
    config.temperature == null || config.temperature === MODEL_CONFIG_FALLBACK.temperature
      ? defaultLabel
      : String(config.temperature)
  const maxTokensLabel = formatMaxTokensValue(config.max_tokens, { unlimitedLabel })
  const maxIterationsLabel =
    config.max_iterations == null || config.max_iterations === MODEL_CONFIG_FALLBACK.max_iterations
      ? defaultLabel
      : String(config.max_iterations)

  return `Temp ${temperatureLabel} · Tokens ${maxTokensLabel} · Iterations ${maxIterationsLabel}`
}
