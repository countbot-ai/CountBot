<template>
  <div class="discord-config">
    <div class="config-section">
      <div class="config-label config-label-switch">
        <span>{{ t('settings.channels.discord.enabled') }}</span>
        <SwitchToggle
          v-model="localConfig.enabled"
          :width="52"
          :height="28"
          :aria-label="t('settings.channels.discord.enabled')"
          @change="handleChange"
        />
      </div>
    </div>

    <details class="advanced-group">
      <summary class="advanced-summary">
        <span class="advanced-summary-title">{{ t('settings.channels.routing.advancedTitle') }}</span>
        <span class="advanced-summary-hint">{{ t('settings.channels.routing.advancedHint') }}</span>
      </summary>

      <div class="advanced-group-body">
        <ChannelRouteConfig :model="localConfig" @change="handleChange" />
      </div>
    </details>

    <div class="config-section">
      <label class="config-label">
        {{ t('settings.channels.discord.token') }}
        <span class="required">*</span>
      </label>
      <input
        type="password"
        v-model="localConfig.token"
        @input="handleChange"
        :placeholder="t('settings.channels.discord.tokenPlaceholder')"
        class="config-input"
      />
      <p class="config-hint">
        {{ t('settings.channels.discord.tokenHint') }}
      </p>
    </div>

    <div class="config-section">
      <label class="config-label">
        {{ t('settings.channels.discord.allowFrom') }}
      </label>
      <div class="allow-list">
        <div
          v-for="(_, index) in localConfig.allow_from"
          :key="index"
          class="allow-item"
        >
          <input
            type="text"
            v-model="localConfig.allow_from[index]"
            @input="handleChange"
            :placeholder="t('settings.channels.discord.userIdPlaceholder')"
            class="config-input"
          />
          <button
            @click="removeAllowUser(index)"
            class="remove-button"
            type="button"
          >
            ×
          </button>
        </div>
        <button
          @click="addAllowUser"
          class="add-button"
          type="button"
        >
          + {{ t('settings.channels.discord.addUser') }}
        </button>
      </div>
      <p class="config-hint">
        {{ t('settings.channels.discord.allowFromHint') }}
      </p>
    </div>

    <div class="config-actions">
      <button type="button" @click="handleTest" :disabled="!localConfig.token || testing" class="test-button">
        {{ testing ? t('common.testing') : t('common.test') }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import SwitchToggle from '@/components/ui/SwitchToggle.vue'
import ChannelRouteConfig from './ChannelRouteConfig.vue'

const { t } = useI18n()

interface Props {
  channelId: string
  config: Record<string, any>
}

const props = defineProps<Props>()
const emit = defineEmits<{
  update: [channelId: string, config: Record<string, any>]
  test: [channelId: string, config?: Record<string, any>]
}>()

const createDefaultConfig = () => {
  return {
    enabled: props.config.enabled !== undefined ? props.config.enabled : true,
    routing_mode: props.config.routing_mode || 'ai',
    external_coding_profile: props.config.external_coding_profile || '',
    token: props.config.token || '',
    allow_from: props.config.allow_from || []
  }
}

const localConfig = ref(createDefaultConfig())

const testing = ref(false)

const handleChange = () => {
  emit('update', props.channelId, localConfig.value)
}

const addAllowUser = () => {
  localConfig.value.allow_from.push('')
  handleChange()
}

const removeAllowUser = (index: number) => {
  localConfig.value.allow_from.splice(index, 1)
  handleChange()
}

const handleTest = async () => {
  testing.value = true
  try {
    emit('test', props.channelId, localConfig.value)
  } finally {
    setTimeout(() => {
      testing.value = false
    }, 1000)
  }
}

// 移除 watch - 避免父组件重新渲染时清空用户输入
// localConfig 在组件创建时初始化，之后完全由用户控制
</script>

<style scoped>
.discord-config {
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

.config-label-switch {
  justify-content: space-between;
}

.required {
  color: var(--error-color);
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

.advanced-group {
  border: 1px dashed var(--border-color);
  border-radius: 12px;
  background: var(--bg-secondary);
  overflow: hidden;
}

.advanced-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  cursor: pointer;
  list-style: none;
}

.advanced-summary::-webkit-details-marker {
  display: none;
}

.advanced-summary-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
}

.advanced-summary-hint {
  font-size: 12px;
  color: var(--text-secondary);
}

.advanced-group-body {
  padding: 0 14px 14px;
  border-top: 1px dashed var(--border-color);
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

.test-button {
  padding: 10px 20px;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
}

.test-button:hover:not(:disabled) {
  background: var(--bg-hover);
}

.test-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
