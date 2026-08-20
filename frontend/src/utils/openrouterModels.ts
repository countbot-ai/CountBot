interface OpenRouterModelRecord {
  id?: string
  canonical_slug?: string | null
  name?: string
  description?: string
  context_length?: number | null
  supported_parameters?: string[] | null
  architecture?: {
    modality?: string | null
    output_modalities?: string[] | null
  } | null
}

interface OpenRouterModelsResponse {
  data?: OpenRouterModelRecord[]
}

export interface OpenRouterFreeModelOption {
  id: string
  baseId: string
  variantId: string
  name: string
  description: string
  contextLength: number | null
  supportedParameters: string[]
  supportsReasoning: boolean
}

const OPENROUTER_MODELS_URL = 'https://openrouter.ai/api/v1/models'

function isTextOutputModel(model: OpenRouterModelRecord): boolean {
  const outputModalities = Array.isArray(model.architecture?.output_modalities)
    ? model.architecture?.output_modalities
    : []
  const modality = String(model.architecture?.modality || '')

  return outputModalities.includes('text') || modality.endsWith('->text') || modality.includes('text->text')
}

export async function fetchOpenRouterFreeModels(): Promise<OpenRouterFreeModelOption[]> {
  const response = await fetch(OPENROUTER_MODELS_URL, {
    headers: {
      Accept: 'application/json',
    },
  })

  if (!response.ok) {
    throw new Error(`OpenRouter models request failed: ${response.status}`)
  }

  const payload = await response.json() as OpenRouterModelsResponse
  const models = Array.isArray(payload.data) ? payload.data : []

  return models
    .filter(model => typeof model.id === 'string' && model.id.endsWith(':free'))
    .filter(isTextOutputModel)
    .map(model => ({
      id: String(model.id || '').trim(),
      baseId: String(model.canonical_slug || model.id || '').replace(/:free$/, '').trim(),
      variantId: String(model.id || '').trim(),
      name: String(model.name || model.canonical_slug || model.id || '').trim(),
      description: String(model.description || '').trim(),
      contextLength: typeof model.context_length === 'number' ? model.context_length : null,
      supportedParameters: Array.isArray(model.supported_parameters)
        ? model.supported_parameters.filter(parameter => typeof parameter === 'string')
        : [],
      supportsReasoning: Array.isArray(model.supported_parameters)
        ? model.supported_parameters.includes('reasoning') || model.supported_parameters.includes('include_reasoning')
        : false,
    }))
    .sort((left, right) => right.contextLength === left.contextLength
      ? left.name.localeCompare(right.name)
      : (right.contextLength || 0) - (left.contextLength || 0))
}
