<template>
  <div v-if="show" class="modal-overlay" @click="handleClose">
    <div class="modal-content" @click.stop>
      <div class="modal-header">
        <h3>{{ $t('settings.presets.savePreset') }}</h3>
        <button class="modal-close" @click="handleClose">
          <XIcon :size="20" />
        </button>
      </div>
      
      <div class="modal-body">
        <div class="form-group">
          <label class="label">{{ $t('settings.presets.presetName') }} *</label>
          <input
            v-model="presetName"
            type="text"
            class="input"
            :placeholder="$t('settings.presets.presetNamePlaceholder')"
            @keyup.enter="handleSave"
          />
          <p v-if="nameError" class="error-text">{{ nameError }}</p>
        </div>
        
        <div class="form-group">
          <label class="label">{{ $t('settings.presets.presetDescription') }}</label>
          <textarea
            v-model="presetDescription"
            class="textarea"
            :placeholder="$t('settings.presets.presetDescriptionPlaceholder')"
            rows="3"
          ></textarea>
        </div>
        
        <div class="preview-section">
          <h4 class="preview-title">{{ $t('settings.presets.configPreview') }}</h4>
          <div class="config-preview">
            <div class="config-grid">
              <div class="config-item">
                <span class="config-label">{{ $t('settings.providers.selectProvider') }}</span>
                <span class="config-value provider-tag">{{ config.provider || '-' }}</span>
              </div>
              <div class="config-item">
                <span class="config-label">{{ $t('settings.providers.model') }}</span>
                <span class="config-value model-tag">{{ config.model || '-' }}</span>
              </div>
              <div class="config-item">
                <span class="config-label">{{ $t('settings.providers.baseUrl') }}</span>
                <span class="config-value">{{ config.baseUrl || $t('common.default') }}</span>
              </div>
              <div class="config-item">
                <span class="config-label">{{ $t('settings.providers.apiKey') }}</span>
                <span class="config-value api-key">{{ config.apiKey ? '••••••••' : '-' }}</span>
              </div>
              <div v-if="config.temperature !== undefined" class="config-item">
                <span class="config-label">Temperature</span>
                <span class="config-value">{{ config.temperature }}</span>
              </div>
              <div v-if="config.maxTokens" class="config-item">
                <span class="config-label">Max Tokens</span>
                <span class="config-value">{{ config.maxTokens }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
      
      <div class="modal-footer">
        <button class="btn btn-secondary" @click="handleClose">
          {{ $t('common.cancel') }}
        </button>
        <button 
          class="btn btn-primary" 
          @click="handleSave"
          :disabled="!presetName.trim() || saving"
        >
          {{ saving ? $t('common.saving') : $t('common.save') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { XIcon } from 'lucide-vue-next'
import { usePresets } from '@/composables/usePresets'

interface Props {
  show: boolean
  config: {
    provider: string
    model: string
    apiKey: string
    baseUrl?: string
    temperature?: number
    maxTokens?: number
    maxIterations?: number
  }
}

interface Emits {
  (e: 'update:show', value: boolean): void
  (e: 'saved', presetId: string): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const { createPreset, presets } = usePresets()

// 本地状态
const presetName = ref('')
const presetDescription = ref('')
const saving = ref(false)
const nameError = ref('')

// 计算属性
const existingNames = computed(() => presets.value.map(p => p.name.toLowerCase()))

// 监听器
watch(() => props.show, (show) => {
  if (show) {
    // 重置表单
    presetName.value = ''
    presetDescription.value = ''
    nameError.value = ''
    saving.value = false
    
    // 生成默认名称
    generateDefaultName()
  }
})

watch(presetName, () => {
  nameError.value = ''
})

// 方法
function generateDefaultName() {
  const { provider, model } = props.config
  if (provider && model) {
    let baseName = `${provider} - ${model}`
    let counter = 1
    let finalName = baseName
    
    while (existingNames.value.includes(finalName.toLowerCase())) {
      finalName = `${baseName} (${counter})`
      counter++
    }
    
    presetName.value = finalName
  }
}

function validateName(): boolean {
  const name = presetName.value.trim()
  
  if (!name) {
    nameError.value = '预设名称不能为空'
    return false
  }
  
  if (existingNames.value.includes(name.toLowerCase())) {
    nameError.value = '预设名称已存在'
    return false
  }
  
  return true
}

async function handleSave() {
  if (!validateName()) {
    return
  }
  
  saving.value = true
  
  try {
    const presetId = createPreset({
      name: presetName.value.trim(),
      description: presetDescription.value.trim() || undefined,
      provider: props.config.provider,
      model: props.config.model,
      apiKey: props.config.apiKey,
      baseUrl: props.config.baseUrl,
      temperature: props.config.temperature,
      maxTokens: props.config.maxTokens,
      maxIterations: props.config.maxIterations
    })
    
    emit('saved', presetId)
    handleClose()
    
    // 显示成功提示
    alert('预设保存成功！')
    
  } catch (error) {
    console.error('Failed to save preset:', error)
    alert('保存预设失败：' + (error as Error).message)
  } finally {
    saving.value = false
  }
}

function handleClose() {
  emit('update:show', false)
}
</script>
<style scoped>
@import './styles/SavePresetDialog.css';
</style>
