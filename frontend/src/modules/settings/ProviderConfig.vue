<template>
  <div class="provider-config">
    <div class="section-header">
      <h3 class="section-title">
        {{ $t('settings.providers.title') }}
      </h3>
      <p class="section-desc">
        {{ $t('settings.providers.description') }}
      </p>
      <div v-if="currentModelDisplay" class="current-model">
        <span class="label">{{ $t('settings.providers.currentModel') }}:</span>
        <span class="value">{{ currentModelDisplay }}</span>
      </div>
    </div>

    <!-- Provider Selection -->
    <div class="form-group">
      <label class="label">{{ $t('settings.providers.selectProvider') }}</label>
      <Select
        v-model="selectedProvider"
        :options="providerOptions"
        :placeholder="$t('settings.providers.selectProvider')"
      />
    </div>

    <!-- Provider Configuration Form -->
    <div
      v-if="selectedProvider"
      class="provider-form"
    >
      <!-- Model Selection -->
      <div class="form-group">
        <label class="label">{{ $t('settings.providers.model') }}</label>
        <Input
          v-model="modelName"
          type="text"
          :placeholder="$t('settings.providers.modelPlaceholder')"
        />
        <p class="hint">{{ $t('settings.providers.modelHint') }}</p>
      </div>

      <!-- API Key (not required for local providers like Ollama/vLLM) -->
      <div class="form-group">
        <label class="label">
          {{ $t('settings.providers.apiKey') }}
          <span v-if="isLocalProvider" class="label-hint">({{ $t('common.optional') }})</span>
        </label>
        <Input
          v-model="providerConfig.apiKey"
          type="password"
          :placeholder="isLocalProvider ? $t('settings.providers.apiKeyOptionalPlaceholder') : $t('settings.providers.apiKeyPlaceholder')"
        />
      </div>

      <!-- Base URL -->
      <div class="form-group">
        <label class="label">
          {{ $t('settings.providers.baseUrl') }}
          <span v-if="currentDefaultBaseUrl" class="label-hint">({{ $t('common.optional') }})</span>
          <span v-else-if="isCustomProvider" class="label-hint required-hint">*</span>
        </label>
        <Input
          v-model="providerConfig.baseUrl"
          type="text"
          :placeholder="isCustomProvider ? $t('settings.providers.baseUrlRequiredPlaceholder') : (currentDefaultBaseUrl || $t('settings.providers.baseUrlPlaceholder'))"
        />
        <p class="hint">
          {{ $t('settings.providers.baseUrlHint') }}
          <template v-if="currentDefaultBaseUrl">
            {{ $t('settings.providers.defaultBaseUrl') }}: {{ currentDefaultBaseUrl }}
          </template>
        </p>
      </div>

      <!-- Enabled Toggle -->
      <div class="form-group">
        <label class="checkbox-label">
          <input
            v-model="providerConfig.enabled"
            type="checkbox"
            class="checkbox"
          >
          <span>{{ $t('settings.providers.enabled') }}</span>
        </label>
      </div>

      <!-- Test Connection Button -->
      <div class="form-group">
        <Button
          variant="secondary"
          :loading="testing"
          :disabled="!isLocalProvider && !providerConfig.apiKey"
          @click="handleTestConnection"
        >
          {{ testing ? $t('settings.providers.testing') : $t('settings.providers.testConnection') }}
        </Button>
      </div>

      <!-- Test Result -->
      <div
        v-if="testResult"
        class="test-result"
        :class="testResult.success ? 'success' : 'error'"
      >
        <component
          :is="testResult.success ? CheckCircleIcon : XCircleIcon"
          :size="16"
        />
        <span>{{ testResult.message }}</span>
      </div>
    </div>

    <!-- No Provider Selected -->
    <div
      v-else
      class="empty-state"
    >
      <p>{{ $t('settings.providers.noProviderSelected') }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { CheckCircle as CheckCircleIcon, XCircle as XCircleIcon } from 'lucide-vue-next'
import Input from '@/components/ui/Input.vue'
import Select from '@/components/ui/Select.vue'
import Button from '@/components/ui/Button.vue'
import { useSettingsStore } from '@/store/settings'
import { settingsAPI } from '@/api'
import type { ProviderConfig as ProviderConfigType, ProviderMetadata } from '@/types/settings'

const { t } = useI18n()
const settingsStore = useSettingsStore()

const selectedProvider = ref<string>('')
const modelName = ref<string>('')
const providerConfig = ref<ProviderConfigType>({
  apiKey: '',
  baseUrl: '',
  enabled: true
})
const testing = ref(false)
const testResult = ref<{ success: boolean; message: string } | null>(null)
const availableProviders = ref<ProviderMetadata[]>([])

// 动态加载 provider 列表
const providerOptions = computed(() => 
  availableProviders.value.map(p => ({
    value: p.id,
    label: t(`settings.providers.${p.id}`, p.name)
  }))
)

// 当前使用的模型显示
const currentModelDisplay = computed(() => {
  if (!settingsStore.settings?.model) return ''
  const { provider, model } = settingsStore.settings.model
  const providerLabel = t(`settings.providers.${provider}`, provider)
  return `${providerLabel} / ${model}`
})

// 判断是否为本地模型 provider（不需要 API Key）
const LOCAL_PROVIDERS = ['ollama', 'vllm', 'lm_studio']
const isLocalProvider = computed(() => LOCAL_PROVIDERS.includes(selectedProvider.value))

// 判断是否为自定义 API provider（需要填写 Base URL）
const CUSTOM_PROVIDERS = ['custom_openai', 'custom_gemini', 'custom_anthropic']
const isCustomProvider = computed(() => CUSTOM_PROVIDERS.includes(selectedProvider.value))

// 当前选中 provider 的默认 API base URL
const currentDefaultBaseUrl = computed(() => {
  if (!selectedProvider.value) return ''
  const providerMeta = availableProviders.value.find(p => p.id === selectedProvider.value)
  return providerMeta?.defaultApiBase || providerMeta?.default_api_base || ''
})

// 加载可用的 providers
const loadProviders = async () => {
  try {
    availableProviders.value = await settingsAPI.getProviders()
  } catch (error) {
    console.error('Failed to load providers:', error)
    // 如果加载失败，使用默认列表
    availableProviders.value = [
      { id: 'openrouter', name: 'OpenRouter' },
      { id: 'anthropic', name: 'Anthropic' },
      { id: 'openai', name: 'OpenAI' },
      { id: 'deepseek', name: 'DeepSeek' },
      { id: 'gemini', name: 'Google Gemini' },
      { id: 'moonshot', name: 'Moonshot AI / Kimi' },
      { id: 'zhipu', name: 'Zhipu AI (GLM)' },
      { id: 'groq', name: 'Groq' },
      { id: 'mistral', name: 'Mistral AI' },
      { id: 'cohere', name: 'Cohere' },
      { id: 'together_ai', name: 'Together AI' },
      { id: 'qwen', name: 'Alibaba Cloud Bailian (阿里云百炼)' },
      { id: 'hunyuan', name: 'Tencent Cloud (腾讯云)' },
      { id: 'ernie', name: 'Baidu Qianfan (百度智能云千帆)' },
      { id: 'doubao', name: 'Volcengine (字节火山引擎)' },
      { id: 'yi', name: '01.AI (Yi)' },
      { id: 'baichuan', name: 'Baichuan AI' },
      { id: 'minimax', name: 'MiniMax' },
      { id: 'vllm', name: 'vLLM' },
      { id: 'ollama', name: 'Ollama' },
      { id: 'lm_studio', name: 'LM Studio' },
      { id: 'custom_openai', name: 'Custom API (OpenAI)' },
      { id: 'custom_gemini', name: 'Custom API (Gemini)' },
      { id: 'custom_anthropic', name: 'Custom API (Anthropic)' }
    ]
  }
}

// Watch for provider selection changes - 自动填充配置
watch(selectedProvider, (newProvider) => {
  if (newProvider && settingsStore.settings?.providers) {
    // Load existing config or use defaults
    const existing = settingsStore.settings.providers[newProvider]
    
    // 获取该 provider 的默认配置（自动填充）
    const providerMeta = availableProviders.value.find(p => p.id === newProvider)
    const defaultBaseUrl = providerMeta?.defaultApiBase || providerMeta?.default_api_base || ''
    const defaultModel = providerMeta?.defaultModel || providerMeta?.default_model || ''
    
    if (existing) {
      providerConfig.value = {
        apiKey: existing.api_key || '',  // 后端字段是 api_key
        baseUrl: existing.api_base || defaultBaseUrl,  // 后端字段是 api_base
        enabled: existing.enabled
      }
      
      // 如果当前选中的 provider 与配置中的 provider 匹配，加载模型名称
      if (settingsStore.settings.model.provider === newProvider) {
        modelName.value = settingsStore.settings.model.model || defaultModel
      } else {
        // 否则使用默认模型
        modelName.value = defaultModel
      }
    } else {
      // 新 provider，自动填充默认配置
      providerConfig.value = {
        apiKey: '',
        baseUrl: defaultBaseUrl,  // 自动填充默认 API base
        enabled: true
      }
      modelName.value = defaultModel  // 自动填充默认模型
    }
    testResult.value = null
  }
}, { immediate: true })

// Watch for settings changes to update model name
watch(() => settingsStore.settings?.model, (newModel) => {
  if (newModel && newModel.provider === selectedProvider.value) {
    modelName.value = newModel.model || ''
  }
}, { deep: true })

// Watch for config changes and update store (save happens via SettingsPanel)
watch(providerConfig, (newConfig) => {
  if (selectedProvider.value && settingsStore.settings?.providers) {
    settingsStore.settings.providers[selectedProvider.value] = {
      enabled: newConfig.enabled,
      api_key: newConfig.apiKey,
      api_base: newConfig.baseUrl || undefined
    }
  }
}, { deep: true })

// Watch for model name changes and update store (save happens via SettingsPanel)
watch(modelName, (newModel) => {
  if (settingsStore.settings?.model && selectedProvider.value) {
    settingsStore.settings.model.model = newModel
    settingsStore.settings.model.provider = selectedProvider.value
  }
})

const handleTestConnection = async () => {
  if (!selectedProvider.value) return
  if (!isLocalProvider.value && !providerConfig.value.apiKey) return

  testing.value = true
  testResult.value = null

  try {
    const response = await settingsAPI.testConnection({
      provider: selectedProvider.value,
      api_key: providerConfig.value.apiKey,
      api_base: providerConfig.value.baseUrl,
      model: modelName.value
    })
    
    testResult.value = {
      success: response.success,
      message: response.success 
        ? (response.message || t('settings.providers.testSuccess'))
        : (response.error || response.message || t('settings.providers.testFailed'))
    }
  } catch (error: any) {
    testResult.value = {
      success: false,
      message: error.response?.data?.error || error.message || t('settings.providers.testFailed')
    }
  } finally {
    testing.value = false
  }
}

// Initialize with first provider if available
const initializeProvider = () => {
  if (!settingsStore.settings || !settingsStore.settings.model) {
    return
  }
  // 优先使用当前配置的 provider
  const currentProvider = settingsStore.settings.model.provider
  if (currentProvider) {
    selectedProvider.value = currentProvider
  } else if (settingsStore.settings.providers) {
    // 否则使用第一个可用的 provider
    const providers = Object.keys(settingsStore.settings.providers)
    if (providers.length > 0) {
      selectedProvider.value = providers[0]
    }
  }
}

// 组件挂载时加载 providers
onMounted(async () => {
  await loadProviders()
})

// 等待 settings 加载后再初始化
watch(() => settingsStore.settings, (newSettings) => {
  if (newSettings) {
    initializeProvider()
  }
}, { immediate: true })
</script>

<style scoped>
.provider-config {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xl);
}

.section-header {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.section-title {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  margin: 0;
}

.section-desc {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  margin: 0;
}

.current-model {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin-top: var(--spacing-md);
  padding: var(--spacing-md);
  background: var(--bg-tertiary);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-color);
}

.current-model .label {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--text-secondary);
}

.current-model .value {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-primary);
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.label {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
}

.label-hint {
  font-weight: var(--font-weight-normal);
  color: var(--text-tertiary);
  font-size: var(--font-size-xs);
}

.label-hint.required-hint {
  color: var(--color-error);
  font-size: var(--font-size-sm);
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--font-size-sm);
  color: var(--text-primary);
  cursor: pointer;
}

.checkbox {
  width: 18px;
  height: 18px;
  border: 2px solid var(--border-color);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition-base);
}

.checkbox:checked {
  background-color: var(--color-primary);
  border-color: var(--color-primary);
}

.provider-form {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
  padding: var(--spacing-lg);
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-color);
}

.test-result {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-sm);
  padding: var(--spacing-md);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  line-height: 1.5;
}

.test-result.success {
  background: rgba(16, 185, 129, 0.1);
  color: var(--color-success);
  border: 1px solid rgba(16, 185, 129, 0.3);
}

.test-result.error {
  background: rgba(239, 68, 68, 0.1);
  color: var(--color-error);
  border: 1px solid rgba(239, 68, 68, 0.3);
}

.test-result span {
  flex: 1;
  word-break: break-word;
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-3xl);
  color: var(--text-tertiary);
  font-size: var(--font-size-sm);
}

.hint {
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
  margin: 0;
  margin-top: calc(var(--spacing-xs) * -1);
}


</style>
