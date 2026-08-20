<template>
  <MultiBotChannelEditor
    :channel-id="channelId"
    :config="config"
    :create-default-account="createDefaultAccount"
    :enable-title="t('settings.channels.telegram.enabled')"
    :enable-hint="t('settings.channels.telegram.enableHint')"
    :disabled-warning="t('settings.channels.telegram.disabledWarning')"
    :can-test="canTest"
    :testing-account-id="testingAccountId"
    @update="(nextChannelId, nextConfig) => emit('update', nextChannelId, nextConfig)"
    @test="(nextChannelId, nextConfig, accountId) => emit('test', nextChannelId, nextConfig, accountId)"
  >
    <template #fields="{ model, handleChange, botKey }">
      <div class="config-section">
        <label class="config-label">
          {{ t('settings.channels.telegram.token') }}
          <span class="required">*</span>
        </label>
        <div class="password-input-wrapper">
          <input
            :type="showSecrets[botKey] ? 'text' : 'password'"
            v-model="model.token"
            :placeholder="t('settings.channels.telegram.tokenPlaceholder')"
            class="config-input"
            @input="handleChange"
          />
          <button type="button" class="toggle-password" @click="toggleSecret(botKey)">
            <svg v-if="showSecrets[botKey]" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path>
              <line x1="1" y1="1" x2="23" y2="23"></line>
            </svg>
            <svg v-else width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
              <circle cx="12" cy="12" r="3"></circle>
            </svg>
          </button>
        </div>
        <p class="config-hint">{{ t('settings.channels.telegram.tokenHint') }}</p>
      </div>

      <div class="config-section">
        <label class="config-label">{{ t('settings.channels.telegram.proxy') }}</label>
        <input
          v-model="model.proxy"
          type="text"
          :placeholder="t('settings.channels.telegram.proxyPlaceholder')"
          class="config-input"
          @input="handleChange"
        />
        <p class="config-hint">{{ t('settings.channels.telegram.proxyHint') }}</p>
      </div>

      <div class="config-section">
        <label class="config-label">{{ t('settings.channels.telegram.allowFrom') }}</label>
        <div class="allow-list">
          <div v-for="(_, index) in model.allow_from" :key="index" class="allow-item">
            <input
              v-model="model.allow_from[index]"
              type="text"
              :placeholder="t('settings.channels.telegram.userIdPlaceholder')"
              class="config-input"
              @input="handleChange"
            />
            <button type="button" class="remove-button" @click="model.allow_from.splice(index, 1); handleChange()">×</button>
          </div>
          <button type="button" class="add-button" @click="model.allow_from.push(''); handleChange()">
            + {{ t('settings.channels.telegram.addUser') }}
          </button>
        </div>
        <p class="config-hint">{{ t('settings.channels.telegram.allowFromHint') }}</p>
      </div>
    </template>
  </MultiBotChannelEditor>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import MultiBotChannelEditor from './MultiBotChannelEditor.vue'

interface Props {
  channelId: string
  config: Record<string, any>
  testingAccountId?: string | null
}

defineProps<Props>()
const emit = defineEmits<{
  update: [channelId: string, config: Record<string, any>]
  test: [channelId: string, config?: Record<string, any>, accountId?: string]
}>()

const { t } = useI18n()
const showSecrets = ref<Record<string, boolean>>({})

const createDefaultAccount = () => ({
  enabled: true,
  display_name: '',
  account_id: 'default',
  token: '',
  proxy: '',
  allow_from: []
})

const canTest = (account: Record<string, any>) => Boolean(account.token)

const toggleSecret = (botKey: string) => {
  showSecrets.value[botKey] = !showSecrets.value[botKey]
}
</script>
