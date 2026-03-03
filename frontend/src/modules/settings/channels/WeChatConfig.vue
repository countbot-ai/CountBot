<template>
  <div class="wechat-config">
    <div class="config-section">
      <label class="config-label">
        <span>{{ t('settings.channels.wechat.enabled') }}</span>
        <input type="checkbox" v-model="localConfig.enabled" @change="handleChange" class="config-checkbox" />
      </label>
    </div>

    <div class="config-section">
      <label class="config-label">
        {{ t('settings.channels.wechat.appId') }}
        <span class="required">*</span>
      </label>
      <input type="text" v-model="localConfig.app_id" @input="handleChange" 
        :placeholder="t('settings.channels.wechat.appIdPlaceholder')" class="config-input" />
      <p class="config-hint">{{ t('settings.channels.wechat.appIdHint') }}</p>
    </div>

    <div class="config-section">
      <label class="config-label">
        {{ t('settings.channels.wechat.appSecret') }}
        <span class="required">*</span>
      </label>
      <input type="password" v-model="localConfig.app_secret" @input="handleChange" 
        :placeholder="t('settings.channels.wechat.appSecretPlaceholder')" class="config-input" />
      <p class="config-hint">{{ t('settings.channels.wechat.appSecretHint') }}</p>
    </div>

    <div class="config-section">
      <label class="config-label">{{ t('settings.channels.wechat.allowFrom') }}</label>
      <div class="allow-list">
        <div v-for="(user, index) in localConfig.allow_from" :key="index" class="allow-item">
          <input type="text" v-model="localConfig.allow_from[index]" @input="handleChange" 
            :placeholder="t('settings.channels.wechat.userIdPlaceholder')" class="config-input" />
          <button @click="removeAllowUser(index)" class="remove-button" type="button">×</button>
        </div>
        <button @click="addAllowUser" class="add-button" type="button">
          + {{ t('settings.channels.wechat.addUser') }}
        </button>
      </div>
      <p class="config-hint">{{ t('settings.channels.wechat.allowFromHint') }}</p>
    </div>

    <div class="config-actions">
      <button @click="handleTest" :disabled="!localConfig.app_id || !localConfig.app_secret || testing" class="test-button">
        {{ testing ? t('common.testing') : t('common.test') }}
      </button>
      <button @click="handleSave" :disabled="!hasChanges || saving" class="save-button">
        {{ saving ? t('common.saving') : t('common.save') }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

interface Props {
  channelId: string
  config: Record<string, any>
}

const props = defineProps<Props>()
const emit = defineEmits<{
  update: [channelId: string, config: Record<string, any>]
  test: [channelId: string]
}>()

const localConfig = ref({
  enabled: props.config.enabled !== undefined ? props.config.enabled : true,
  app_id: props.config.app_id || '',
  app_secret: props.config.app_secret || '',
  allow_from: props.config.allow_from || []
})

const originalConfig = ref(JSON.stringify(localConfig.value))
const testing = ref(false)
const saving = ref(false)

const hasChanges = computed(() => JSON.stringify(localConfig.value) !== originalConfig.value)

const handleChange = () => {}

const addAllowUser = () => {
  localConfig.value.allow_from.push('')
}

const removeAllowUser = (index: number) => {
  localConfig.value.allow_from.splice(index, 1)
  handleChange()
}

const handleTest = async () => {
  testing.value = true
  try {
    emit('test', props.channelId)
  } finally {
    setTimeout(() => { testing.value = false }, 1000)
  }
}

const handleSave = async () => {
  saving.value = true
  try {
    const config = {
      ...localConfig.value,
      allow_from: localConfig.value.allow_from.filter(u => u.trim())
    }
    emit('update', props.channelId, config)
    originalConfig.value = JSON.stringify(localConfig.value)
  } finally {
    setTimeout(() => { saving.value = false }, 500)
  }
}

watch(() => props.config, (newConfig) => {
  localConfig.value = {
    enabled: newConfig.enabled !== undefined ? newConfig.enabled : true,
    app_id: newConfig.app_id || '',
    app_secret: newConfig.app_secret || '',
    allow_from: newConfig.allow_from || []
  }
  originalConfig.value = JSON.stringify(localConfig.value)
}, { deep: true })
</script>

<style scoped>
.wechat-config {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.config-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.config-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 8px;
}

.required {
  color: var(--error-color);
}

.config-checkbox {
  margin-left: auto;
  width: 20px;
  height: 20px;
  cursor: pointer;
}

.config-input {
  padding: 10px 12px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  font-size: 14px;
  background: var(--bg-primary);
  color: var(--text-primary);
  transition: all 0.2s;
}

.config-input:focus {
  outline: none;
  border-color: var(--primary-color);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.config-hint {
  font-size: 12px;
  color: var(--text-secondary);
  margin: 0;
}

.allow-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.allow-item {
  display: flex;
  gap: 8px;
}

.allow-item .config-input {
  flex: 1;
}

.remove-button {
  width: 36px;
  height: 36px;
  background: var(--error-color);
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.remove-button:hover {
  background: #dc2626;
}

.add-button {
  padding: 8px 16px;
  background: var(--bg-tertiary);
  border: 1px dashed var(--border-color);
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  color: var(--text-secondary);
  transition: all 0.2s;
}

.add-button:hover {
  background: var(--bg-hover);
  border-color: var(--primary-color);
  color: var(--primary-color);
}

.config-actions {
  display: flex;
  gap: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border-color);
}

.test-button,
.save-button {
  padding: 10px 20px;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.test-button {
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
}

.test-button:hover:not(:disabled) {
  background: var(--bg-hover);
}

.save-button {
  background: var(--primary-color);
  color: white;
}

.save-button:hover:not(:disabled) {
  background: #2563eb;
}

.test-button:disabled,
.save-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
