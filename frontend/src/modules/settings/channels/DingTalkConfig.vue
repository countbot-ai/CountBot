<template>
  <div class="dingtalk-config">
    <!-- 启用开关 - 突出显示 -->
    <div class="config-section config-section-highlight">
      <div class="enable-toggle-wrapper">
        <div class="enable-toggle-content">
          <div class="enable-toggle-label">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 2v20M2 12h20"></path>
            </svg>
            <span class="enable-toggle-title">{{ t('settings.channels.dingtalk.enabled') }}</span>
          </div>
          <p class="enable-toggle-hint">配置完成后，请确保启用此开关以激活频道</p>
        </div>
        <label class="toggle-switch">
          <input type="checkbox" v-model="localConfig.enabled" @change="handleChange" />
          <span class="toggle-slider"></span>
        </label>
      </div>
      <div v-if="!localConfig.enabled" class="enable-warning">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
          <line x1="12" y1="9" x2="12" y2="13"></line>
          <line x1="12" y1="17" x2="12.01" y2="17"></line>
        </svg>
        <span>频道未启用，配置后不会生效</span>
      </div>
    </div>

    <div class="config-section">
      <label class="config-label">
        {{ t('settings.channels.dingtalk.clientId') }}
        <span class="required">*</span>
      </label>
      <input type="text" v-model="localConfig.client_id" @input="handleChange" 
        :placeholder="t('settings.channels.dingtalk.clientIdPlaceholder')" class="config-input" 
        autocomplete="username" />
      <p class="config-hint">{{ t('settings.channels.dingtalk.clientIdHint') }}</p>
    </div>

    <div class="config-section">
      <label class="config-label">
        {{ t('settings.channels.dingtalk.clientSecret') }}
        <span class="required">*</span>
      </label>
      <div class="password-input-wrapper">
        <input :type="showPassword ? 'text' : 'password'" v-model="localConfig.client_secret" @input="handleChange" 
          :placeholder="t('settings.channels.dingtalk.clientSecretPlaceholder')" class="config-input" 
          autocomplete="current-password" />
        <button type="button" class="toggle-password" @click="showPassword = !showPassword" :title="showPassword ? t('common.hidePassword') : t('common.showPassword')">
          <svg v-if="showPassword" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path>
            <line x1="1" y1="1" x2="23" y2="23"></line>
          </svg>
          <svg v-else width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
            <circle cx="12" cy="12" r="3"></circle>
          </svg>
        </button>
      </div>
      <p class="config-hint">{{ t('settings.channels.dingtalk.clientSecretHint') }}</p>
    </div>

    <div class="config-section">
      <label class="config-label">{{ t('settings.channels.dingtalk.allowFrom') }}</label>
      <div class="allow-list">
        <div v-for="(user, index) in localConfig.allow_from" :key="index" class="allow-item">
          <input type="text" v-model="localConfig.allow_from[index]" @input="handleChange" 
            :placeholder="t('settings.channels.dingtalk.userIdPlaceholder')" class="config-input" />
          <button @click="removeAllowUser(index)" class="remove-button" type="button">×</button>
        </div>
        <button @click="addAllowUser" class="add-button" type="button">
          + {{ t('settings.channels.dingtalk.addUser') }}
        </button>
      </div>
      <p class="config-hint">{{ t('settings.channels.dingtalk.allowFromHint') }}</p>
    </div>

    <div class="config-actions">
      <button @click="handleTest" :disabled="!localConfig.client_id || !localConfig.client_secret || testing" class="test-button">
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
  client_id: props.config.client_id || '',
  client_secret: props.config.client_secret || '',
  allow_from: props.config.allow_from || []
})

const showPassword = ref(false)
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
    // 传递当前用户输入的配置进行测试
    emit('test', props.channelId, localConfig.value)
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
    client_id: newConfig.client_id || '',
    client_secret: newConfig.client_secret || '',
    allow_from: newConfig.allow_from || []
  }
  originalConfig.value = JSON.stringify(localConfig.value)
}, { deep: true, immediate: true })
</script>

<style scoped>
.dingtalk-config {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.config-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.config-section-highlight {
  background: var(--bg-tertiary);
  border: 2px solid #10b981;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 8px;
}

.enable-toggle-wrapper {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.enable-toggle-content {
  flex: 1;
}

.enable-toggle-label {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.enable-toggle-label svg {
  color: #10b981;
}

.enable-toggle-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.enable-toggle-hint {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0;
}

.toggle-switch {
  position: relative;
  display: inline-block;
  width: 52px;
  height: 28px;
  flex-shrink: 0;
}

.toggle-switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.toggle-slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: #cbd5e1;
  transition: .3s;
  border-radius: 28px;
}

.toggle-slider:before {
  position: absolute;
  content: "";
  height: 22px;
  width: 22px;
  left: 3px;
  bottom: 3px;
  background-color: white;
  transition: .3s;
  border-radius: 50%;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
}

.toggle-switch input:checked + .toggle-slider {
  background-color: #10b981;
}

.toggle-switch input:checked + .toggle-slider:before {
  transform: translateX(24px);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3);
}

.toggle-switch input:focus + .toggle-slider {
  box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.2);
}

:root[data-theme="dark"] .toggle-slider {
  background-color: #475569;
}

:root[data-theme="dark"] .toggle-switch input:checked + .toggle-slider {
  background-color: #10b981;
}

.enable-warning {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  padding: 10px 12px;
  background: #fef3c7;
  border: 1px solid #fbbf24;
  border-radius: 6px;
  font-size: 13px;
  color: #92400e;
}

.enable-warning svg {
  flex-shrink: 0;
  color: #f59e0b;
}

:root[data-theme="dark"] .enable-warning {
  background: rgba(251, 191, 36, 0.1);
  border-color: #b45309;
  color: #fde68a;
}

:root[data-theme="dark"] .enable-warning svg {
  color: #fbbf24;
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

.password-input-wrapper {
  position: relative;
  display: flex;
  align-items: center;
}

.password-input-wrapper .config-input {
  flex: 1;
  padding-right: 45px;
}

.toggle-password {
  position: absolute;
  right: 8px;
  background: transparent;
  border: none;
  padding: 6px;
  cursor: pointer;
  color: var(--text-tertiary);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
  border-radius: 6px;
  opacity: 0.7;
}

.toggle-password:hover {
  color: var(--text-primary);
  background: var(--bg-tertiary);
  opacity: 1;
}

.toggle-password:active {
  transform: scale(0.92);
}

.toggle-password svg {
  width: 18px;
  height: 18px;
  stroke-width: 2.2;
}




</style>
