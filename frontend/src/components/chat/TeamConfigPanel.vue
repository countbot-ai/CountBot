<template>
  <!-- 全屏遮罩 -->
  <div class="config-modal-overlay" @click="$emit('close')">
    <div class="config-modal" @click.stop>
      <div class="modal-container">
        <!-- Header -->
        <div class="modal-header">
          <div class="header-content">
            <div class="header-icon">
              <Settings :size="24" />
            </div>
            <div class="header-text">
              <h3>{{ $t('chat.sessionConfig.modelSettings') }}</h3>
              <p class="header-subtitle">{{ teamName }}</p>
            </div>
          </div>
          <button class="close-btn" @click="$emit('close')" :title="$t('common.close')">
            <X :size="20" />
          </button>
        </div>

        <!-- Scrollable Content -->
        <div class="modal-body">
          <!-- 使用自定义配置开关 -->
          <div class="config-toggle" :class="{ active: useCustomModel }">
            <div class="toggle-header">
              <label class="toggle-label">
                <SwitchToggle
                  v-model="useCustomModel"
                  :width="48"
                  :height="28"
                  aria-label="为此团队使用自定义模型"
                  @change="onToggleCustomModel"
                />
                <div class="toggle-content">
                  <span class="toggle-text">为此团队使用自定义模型</span>
                  <span class="toggle-hint">团队成员将使用此配置的模型和 API</span>
                </div>
              </label>
              <div v-if="useCustomModel" class="config-badge">
                <Sparkles :size="14" />
                <span>自定义</span>
              </div>
            </div>
          </div>

          <div v-if="useCustomModel" class="config-sections">
            <!-- 模型配置 -->
            <section class="config-section">
              <div class="section-header">
                <div class="section-icon">
                  <Cpu :size="20" />
                </div>
                <h4>{{ $t('chat.sessionConfig.modelSettings') }}</h4>
              </div>

              <div class="form-grid">
                <div class="form-group">
                  <label>{{ $t('settings.providers.selectProvider') }}</label>
                  <div class="select-wrapper">
                    <select v-model="modelConfig.provider" class="select-input">
                      <option v-for="p in providers" :key="p.id" :value="p.id">
                        {{ p.name }}
                      </option>
                    </select>
                    <ChevronDown :size="16" class="select-icon" />
                  </div>
                </div>

                <div class="form-group">
                  <label>{{ $t('settings.providers.model') }}</label>
                  <input v-model="modelConfig.model" type="text" class="text-input" placeholder="glm-5" />
                </div>

              </div>

              <ModelParameterFields
                :temperature="modelConfig.temperature ?? 0"
                :max-tokens="modelConfig.max_tokens ?? 0"
                :max-iterations="modelConfig.max_iterations ?? 25"
                :thinking-enabled="modelConfig.thinking_enabled ?? true"
                @update:temperature="modelConfig.temperature = $event"
                @update:maxTokens="modelConfig.max_tokens = $event"
                @update:maxIterations="modelConfig.max_iterations = $event"
                @update:thinkingEnabled="modelConfig.thinking_enabled = $event"
              />

              <!-- 高级 API 设置 -->
              <details class="advanced-config">
                <summary>
                  <Lock :size="16" />
                  <span>{{ $t('chat.sessionConfig.advancedApiSettings') }}</span>
                  <ChevronDown :size="16" class="chevron" />
                </summary>

                <div class="advanced-content">
                  <div class="form-group">
                    <label>{{ $t('settings.providers.apiKey') }}</label>
                    <input
                      v-model="modelConfig.api_key"
                      type="password"
                      :placeholder="$t('chat.sessionConfig.leaveEmptyForGlobal')"
                      class="text-input"
                    />
                    <p class="hint">
                      {{ globalDefaults?.api_key ? '✓ 全局已配置 API 密钥' : '⚠️ 全局未配置 API 密钥' }}
                    </p>
                  </div>

                  <div class="form-group">
                    <label>{{ $t('settings.providers.baseUrl') }}</label>
                    <input
                      v-model="modelConfig.api_base"
                      type="text"
                      :placeholder="globalDefaults?.api_base || $t('chat.sessionConfig.leaveEmptyForGlobal')"
                      class="text-input"
                    />
                    <p class="hint">
                      {{ globalDefaults?.api_base ? `✓ 全局配置: ${globalDefaults.api_base}` : '⚠️ 全局未配置 Base URL' }}
                    </p>
                  </div>

                  <!-- 测试连接按钮 -->
                  <div class="form-group">
                    <button
                      @click="handleTestConnection"
                      class="btn-secondary"
                      :disabled="testing"
                    >
                      <Loader2 v-if="testing" :size="16" class="spin" />
                      <span>{{ testing ? $t('settings.providers.testing') : $t('settings.providers.testConnection') }}</span>
                    </button>
                  </div>

                  <!-- 测试结果 -->
                  <div
                    v-if="testResult"
                    class="test-result"
                    :class="testResult.success ? 'success' : 'error'"
                  >
                    <CheckCircle v-if="testResult.success" :size="16" />
                    <XCircle v-else :size="16" />
                    <span>{{ testResult.message }}</span>
                  </div>
                </div>
              </details>
            </section>
          </div>

          <div v-else class="empty-state">
            <div class="empty-icon">
              <Globe :size="48" />
            </div>
            <h4>使用全局默认配置</h4>
            <p>启用自定义配置以为此团队设置专属的模型和 API</p>
          </div>
        </div>

        <!-- Fixed Footer -->
        <div v-if="useCustomModel" class="modal-footer">
          <button @click="saveConfig" class="btn-primary" :disabled="saving">
            <Save :size="16" v-if="!saving" />
            <Loader2 :size="16" class="spin" v-if="saving" />
            <span>{{ saving ? '保存中...' : '保存' }}</span>
          </button>
          <button @click="resetToDefaults" class="btn-secondary">
            <RotateCcw :size="16" />
            <span>重置为默认</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { 
  X, Settings, Sparkles, Cpu, ChevronDown, Lock, 
  Save, RotateCcw, Loader2, Globe, CheckCircle, XCircle
} from 'lucide-vue-next'
import { settingsAPI, type ProviderMetadata } from '@/api'
import { agentTeamsApi, type TeamModelConfig } from '@/api/agentTeams'
import { useToast } from '@/composables/useToast'
import SwitchToggle from '@/components/ui/SwitchToggle.vue'
import ModelParameterFields from '@/components/ui/ModelParameterFields.vue'
import {
  findFirstSelectableProvider,
  findProviderById,
  getSelectableProviders,
  resolveProviderDefaultApiBase,
  resolveProviderDefaultModel,
} from '@/utils/providerRuntime'
import {
  buildCustomModelEditorConfig,
  buildEffectiveModelConfig,
  buildModelConfigOverrides,
  MODEL_CONFIG_FALLBACK,
  buildSendableModelConfig,
} from '@/utils/modelConfig'

const { t } = useI18n()
const toast = useToast()

type ProviderOption = Pick<ProviderMetadata, 'id' | 'name'> & {
  defaultApiBase?: string
  defaultModel?: string
}

const createDefaultModelConfig = (): TeamModelConfig =>
  buildCustomModelEditorConfig<TeamModelConfig>()

const props = defineProps<{
  teamId: string
  teamName?: string
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'updated'): void
}>()

const useCustomModel = ref(false)
const saving = ref(false)
const testing = ref(false)
const testResult = ref<{ success: boolean; message: string } | null>(null)
const providers = ref<ProviderOption[]>([])
const isHydratingConfig = ref(false)

const modelConfig = ref<TeamModelConfig>(createDefaultModelConfig())

async function loadProviders() {
  try {
    const providersData = await settingsAPI.getProviders()
    providers.value = getSelectableProviders(providersData).map(p => ({
      id: p.id,
      name: p.name,
      defaultApiBase: resolveProviderDefaultApiBase(p),
      defaultModel: resolveProviderDefaultModel(p)
    }))
    ensureValidProviderSelection()
  } catch (error) {
    console.error('Failed to load providers:', error)
    toast.error('加载服务商列表失败')
  }
}

function applyConfig(config: TeamModelConfig, enabled: boolean) {
  isHydratingConfig.value = true
  try {
    useCustomModel.value = enabled
    modelConfig.value = buildCustomModelEditorConfig<TeamModelConfig>(
      globalDefaults.value,
      enabled ? config : undefined,
    )
    testResult.value = null
    ensureValidProviderSelection()
  } finally {
    isHydratingConfig.value = false
  }
}

function ensureValidProviderSelection() {
  if (providers.value.length === 0) {
    return
  }

  const currentProvider = findProviderById(providers.value, modelConfig.value.provider)
  if (currentProvider) {
    return
  }

  const fallbackProvider = findFirstSelectableProvider(providers.value)
  if (!fallbackProvider) {
    return
  }

  modelConfig.value.provider = fallbackProvider.id
  if (!modelConfig.value.api_base) {
    modelConfig.value.api_base = fallbackProvider.defaultApiBase || ''
  }
  if (
    !modelConfig.value.model
    || modelConfig.value.model === MODEL_CONFIG_FALLBACK.model
  ) {
    modelConfig.value.model = fallbackProvider.defaultModel || modelConfig.value.model
  }
}

onMounted(async () => {
  await loadProviders()
  await loadConfig()
})

watch(() => props.teamId, async (newTeamId, oldTeamId) => {
  if (newTeamId && newTeamId !== oldTeamId) {
    await loadConfig()
  }
})

watch(() => modelConfig.value.provider, (newProvider, oldProvider) => {
  if (!newProvider || providers.value.length === 0 || isHydratingConfig.value) {
    return
  }

  const nextProvider = providers.value.find(p => p.id === newProvider)
  const previousProvider = oldProvider ? providers.value.find(p => p.id === oldProvider) : null

  if (!nextProvider) {
    return
  }

  const shouldUpdateApiBase = !modelConfig.value.api_base || (
    !!previousProvider?.defaultApiBase && modelConfig.value.api_base === previousProvider.defaultApiBase
  )
  if (shouldUpdateApiBase) {
    modelConfig.value.api_base = nextProvider.defaultApiBase || ''
  }

  const shouldUpdateModel = !modelConfig.value.model || (
    !!previousProvider?.defaultModel && modelConfig.value.model === previousProvider.defaultModel
  )
  if (shouldUpdateModel && nextProvider.defaultModel) {
    modelConfig.value.model = nextProvider.defaultModel
  }
})

// 保存全局默认配置的引用
const globalDefaults = ref<TeamModelConfig>(createDefaultModelConfig())

async function loadConfig() {
  if (!props.teamId) {
    globalDefaults.value = createDefaultModelConfig()
    applyConfig(globalDefaults.value, false)
    return
  }

  try {
    const config = await agentTeamsApi.getConfig(props.teamId)
    
    // 保存全局默认配置
    globalDefaults.value = buildEffectiveModelConfig<TeamModelConfig>(
      undefined,
      config.global_defaults,
    )
    
    // 如果启用了自定义模型，使用团队配置；否则使用全局默认
    if (config.use_custom_model) {
      applyConfig(config.model_settings, true)
    } else {
      // 启用时默认填充全局配置
      applyConfig(config.global_defaults, false)
    }
  } catch (error) {
    console.error('Failed to load team config:', error)
    toast.error('加载团队配置失败')
  }
}

async function saveConfig() {
  if (!useCustomModel.value) {
    useCustomModel.value = true
  }
  
  saving.value = true
  try {
    // 准备要保存的配置
    const configToSave = buildModelConfigOverrides<TeamModelConfig>(
      modelConfig.value,
      globalDefaults.value,
    )

    await agentTeamsApi.updateConfig(props.teamId, configToSave)
    toast.success('团队配置已保存')
    emit('updated')
  } catch (error) {
    console.error('Failed to save config:', error)
    toast.error('保存配置失败')
  } finally {
    saving.value = false
  }
}

async function resetToDefaults() {
  if (!confirm('确定要重置为全局默认配置吗？')) {
    return false
  }

  try {
    await agentTeamsApi.resetConfig(props.teamId)
    await loadConfig()
    toast.success('已重置为默认配置')
    emit('updated')
    return true
  } catch (error) {
    console.error('Failed to reset config:', error)
    toast.error('重置配置失败')
    return false
  }
}

async function onToggleCustomModel() {
  if (!useCustomModel.value) {
    // 关闭自定义模型 - 重置为默认
    const reset = await resetToDefaults()
    if (!reset) {
      useCustomModel.value = true
    }
    return
  }

  modelConfig.value = buildCustomModelEditorConfig<TeamModelConfig>(
    globalDefaults.value,
    modelConfig.value,
  )
  testResult.value = null
}

async function handleTestConnection() {
  testing.value = true
  testResult.value = null

  try {
    const response = await settingsAPI.testConnection({
      provider: modelConfig.value.provider || 'zhipu',
      api_key: modelConfig.value.api_key || undefined,
      api_base: modelConfig.value.api_base || undefined,
      model: modelConfig.value.model || 'glm-5',
      ...buildSendableModelConfig(modelConfig.value),
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
</script>
<style scoped>
@import './styles/TeamConfigPanel.css';
</style>
