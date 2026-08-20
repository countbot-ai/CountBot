<template>
  <MultiBotChannelEditor
    :channel-id="channelId"
    :config="config"
    :create-default-account="createDefaultAccount"
    :enable-title="t('settings.channels.wechat.enabled')"
    :enable-hint="t('settings.channels.wechat.enableHint')"
    :disabled-warning="t('settings.channels.wechat.disabledWarning')"
    :guide="guide"
    :can-test="canTest"
    :testing-account-id="testingAccountId"
    @update="(nextChannelId, nextConfig) => emit('update', nextChannelId, nextConfig)"
    @test="(nextChannelId, nextConfig, accountId) => emit('test', nextChannelId, nextConfig, accountId)"
  >
    <template #fields="{ model, handleChange, botKey, isPrimary }">
      <div class="config-section">
        <label class="config-label">{{ t('settings.channels.wechat.baseUrl') }}</label>
        <input
          v-model="model.base_url"
          type="text"
          :placeholder="t('settings.channels.wechat.baseUrlPlaceholder')"
          class="config-input"
          @input="handleChange"
        />
        <p class="config-hint">{{ t('settings.channels.wechat.baseUrlHint') }}</p>
      </div>

      <div class="config-section">
        <label class="config-label">{{ t('settings.channels.wechat.cdnBaseUrl') }}</label>
        <input
          v-model="model.cdn_base_url"
          type="text"
          :placeholder="t('settings.channels.wechat.cdnBaseUrlPlaceholder')"
          class="config-input"
          @input="handleChange"
        />
        <p class="config-hint">{{ t('settings.channels.wechat.cdnBaseUrlHint') }}</p>
      </div>

      <div class="config-section">
        <label class="config-label">{{ t('settings.channels.wechat.token') }}</label>
        <div class="password-input-wrapper">
          <input
            :type="showSecrets[botKey] ? 'text' : 'password'"
            v-model="model.token"
            :placeholder="t('settings.channels.wechat.tokenPlaceholder')"
            class="config-input"
            @input="handleChange"
          />
          <button
            type="button"
            class="toggle-password"
            :title="showSecrets[botKey] ? t('common.hidePassword') : t('common.showPassword')"
            @click="toggleSecret(botKey)"
          >
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
        <p class="config-hint">{{ t('settings.channels.wechat.tokenHint') }}</p>
      </div>

      <div class="config-section login-section">
        <div class="login-section-header">
          <div>
            <label class="config-label">{{ t('settings.channels.wechat.qrLogin') }}</label>
            <p class="config-hint">{{ t('settings.channels.wechat.qrLoginHint') }}</p>
          </div>
          <button
            type="button"
            class="login-button"
            :disabled="getLoginState(botKey).busy"
            @click="beginQrLogin(model, botKey, isPrimary)"
          >
            {{
              getLoginState(botKey).busy
                ? t('settings.channels.wechat.loginStarting')
                : t('settings.channels.wechat.startLogin')
            }}
          </button>
        </div>

        <div class="login-status-card" :class="`status-${getLoginState(botKey).status}`">
          <div class="status-row">
            <span class="status-label">{{ t('settings.channels.wechat.loginStatus') }}</span>
            <span class="status-value">{{ formatLoginStatus(getLoginState(botKey).status) }}</span>
          </div>
          <p class="status-message">{{ getLoginState(botKey).message || t('settings.channels.wechat.loginIdle') }}</p>

          <div
            v-if="model.login_bot_id || model.login_user_id"
            class="login-meta"
          >
            <div v-if="model.login_bot_id" class="meta-item">
              <span class="meta-label">{{ t('settings.channels.wechat.loginBotId') }}</span>
              <span class="meta-value">{{ model.login_bot_id }}</span>
            </div>
            <div v-if="model.login_user_id" class="meta-item">
              <span class="meta-label">{{ t('settings.channels.wechat.loginUserId') }}</span>
              <span class="meta-value">{{ model.login_user_id }}</span>
            </div>
          </div>

          <div v-if="getLoginState(botKey).qrcodeUrl" class="qr-card">
            <img
              :src="getLoginState(botKey).qrcodeUrl"
              :alt="t('settings.channels.wechat.qrCodeAlt')"
              class="qr-image"
              @error="handleQrImageError(botKey)"
            />
            <div class="qr-actions">
              <button
                type="button"
                class="secondary-button"
                :disabled="getLoginState(botKey).polling"
                @click="pollQrLogin(botKey)"
              >
                {{
                  getLoginState(botKey).polling
                    ? t('settings.channels.wechat.polling')
                    : t('settings.channels.wechat.checkLogin')
                }}
              </button>
              <button
                type="button"
                class="secondary-button"
                @click="clearLoginState(botKey)"
              >
                {{ t('common.close') }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <div class="config-section">
        <label class="config-label">{{ t('settings.channels.wechat.allowFrom') }}</label>
        <div class="allow-list">
          <div v-for="(_, index) in model.allow_from" :key="index" class="allow-item">
            <input
              v-model="model.allow_from[index]"
              type="text"
              :placeholder="t('settings.channels.wechat.userIdPlaceholder')"
              class="config-input"
              @input="handleChange"
            />
            <button type="button" class="remove-button" @click="model.allow_from.splice(index, 1); handleChange()">×</button>
          </div>
          <button type="button" class="add-button" @click="model.allow_from.push(''); handleChange()">
            + {{ t('settings.channels.wechat.addUser') }}
          </button>
        </div>
        <p class="config-hint">{{ t('settings.channels.wechat.allowFromHint') }}</p>
      </div>
    </template>
  </MultiBotChannelEditor>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import QRCode from 'qrcode'
import MultiBotChannelEditor from './MultiBotChannelEditor.vue'

interface Props {
  channelId: string
  config: Record<string, any>
  testingAccountId?: string | null
}

type LoginStatus = 'idle' | 'starting' | 'wait' | 'scaned' | 'confirmed' | 'expired' | 'error'

interface LoginState {
  status: LoginStatus
  message: string
  qrcodeUrl: string
  rawQrcodeValue: string
  sessionKey: string
  busy: boolean
  polling: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
  update: [channelId: string, config: Record<string, any>]
  test: [channelId: string, config?: Record<string, any>, accountId?: string]
}>()

const { t } = useI18n()
const showSecrets = ref<Record<string, boolean>>({})
const loginStates = ref<Record<string, LoginState>>({})
const pollTimers = new Map<string, number>()

const createDefaultAccount = () => ({
  enabled: true,
  display_name: '',
  account_id: 'default',
  base_url: 'https://ilinkai.weixin.qq.com',
  cdn_base_url: 'https://novac2c.cdn.weixin.qq.com/c2c',
  token: '',
  login_bot_id: '',
  login_user_id: '',
  allow_from: []
})

const guide = computed(() => ({
  title: t('settings.channels.wechat.guideTitle'),
  linkText: t('settings.channels.wechat.guideLink'),
  linkHref: 'https://ilinkai.weixin.qq.com',
  stepText: t('settings.channels.wechat.guideStep1'),
  detailText: t('settings.channels.wechat.guideStep2')
}))

const canTest = (account: Record<string, any>) => Boolean(account.token)

const toggleSecret = (botKey: string) => {
  showSecrets.value[botKey] = !showSecrets.value[botKey]
}

const getLoginState = (botKey: string): LoginState => {
  if (!loginStates.value[botKey]) {
    loginStates.value[botKey] = {
      status: 'idle',
      message: '',
      qrcodeUrl: '',
      rawQrcodeValue: '',
      sessionKey: '',
      busy: false,
      polling: false
    }
  }
  return loginStates.value[botKey]
}

const formatLoginStatus = (status: LoginStatus) => {
  const keyMap: Record<LoginStatus, string> = {
    idle: 'settings.channels.wechat.statusIdle',
    starting: 'settings.channels.wechat.statusStarting',
    wait: 'settings.channels.wechat.statusWaiting',
    scaned: 'settings.channels.wechat.statusScanned',
    confirmed: 'settings.channels.wechat.statusConfirmed',
    expired: 'settings.channels.wechat.statusExpired',
    error: 'settings.channels.wechat.statusError'
  }
  return t(keyMap[status])
}

const stopPolling = (botKey: string) => {
  const timer = pollTimers.get(botKey)
  if (timer) {
    window.clearTimeout(timer)
    pollTimers.delete(botKey)
  }
}

const clearLoginState = (botKey: string) => {
  stopPolling(botKey)
  loginStates.value[botKey] = {
    status: 'idle',
    message: '',
    qrcodeUrl: '',
    rawQrcodeValue: '',
    sessionKey: '',
    busy: false,
    polling: false
  }
}

const cloneConfig = () => JSON.parse(JSON.stringify(props.config || {}))

const buildConfigSnapshot = (model: Record<string, any>, isPrimary: boolean) => {
  const nextConfig = cloneConfig()
  nextConfig.account_id = String(nextConfig.account_id || 'default')
  nextConfig.accounts = { ...(nextConfig.accounts || {}) }
  const accountId = String(model.account_id || 'default')

  if (isPrimary || accountId === nextConfig.account_id) {
    Object.assign(nextConfig, JSON.parse(JSON.stringify(model)))
    nextConfig.accounts = { ...(nextConfig.accounts || {}) }
  } else {
    nextConfig.accounts[accountId] = JSON.parse(JSON.stringify(model))
  }

  return nextConfig
}

const normalizeQrImageSrc = (value: string) => {
  const normalized = String(value || '').trim()
  if (!normalized) {
    return ''
  }
  if (normalized.startsWith('//')) {
    return `https:${normalized}`
  }
  return normalized
}

const toQrImageSrc = async (value: string) => {
  const normalized = String(value || '').trim()
  if (!normalized) {
    return ''
  }
  try {
    return await QRCode.toDataURL(normalized, {
      width: 240,
      margin: 1
    })
  } catch {
    return normalized
  }
}

const applyConfigFromServer = (config: Record<string, any>) => {
  emit('update', props.channelId, config)
}

const handleQrImageError = async (botKey: string) => {
  const state = getLoginState(botKey)
  const rawValue = String(state.rawQrcodeValue || '').trim()
  if (!rawValue || state.qrcodeUrl.startsWith('data:image/')) {
    return
  }

  state.qrcodeUrl = await toQrImageSrc(rawValue)
}

const schedulePoll = (botKey: string) => {
  stopPolling(botKey)
  const timer = window.setTimeout(() => {
    void pollQrLogin(botKey)
  }, 2000)
  pollTimers.set(botKey, timer)
}

const beginQrLogin = async (model: Record<string, any>, botKey: string, isPrimary: boolean) => {
  const state = getLoginState(botKey)
  state.busy = true
  state.status = 'starting'
  state.message = t('settings.channels.wechat.loginStarting')
  state.qrcodeUrl = ''
  state.rawQrcodeValue = ''
  state.sessionKey = ''
  stopPolling(botKey)

  try {
    const response = await fetch('/api/channels/wechat/login/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        account_id: String(model.account_id || 'default'),
        config: buildConfigSnapshot(model, isPrimary)
      })
    })
    const data = await response.json()
    if (!data.success) {
      throw new Error(data.message || t('settings.channels.wechat.startLoginFailed'))
    }

    state.status = 'wait'
    state.message = t('settings.channels.wechat.qrReady')
    state.rawQrcodeValue = String(data.qrcode_url || '')
    state.qrcodeUrl = normalizeQrImageSrc(state.rawQrcodeValue)
    state.sessionKey = String(data.session_key || '')
    schedulePoll(botKey)
  } catch (error: any) {
    state.status = 'error'
    state.message = error.message || t('settings.channels.wechat.startLoginFailed')
  } finally {
    state.busy = false
  }
}

const pollQrLogin = async (botKey: string) => {
  const state = getLoginState(botKey)
  if (!state.sessionKey) {
    return
  }

  state.polling = true
  try {
    const response = await fetch('/api/channels/wechat/login/poll', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_key: state.sessionKey })
    })
    const data = await response.json()

    if (!data.success && data.status !== 'expired') {
      throw new Error(data.message || t('settings.channels.wechat.pollLoginFailed'))
    }

    state.status = (data.status || 'wait') as LoginStatus
    state.message = String(data.message || '')

    if (state.status === 'confirmed') {
      if (data.config) {
        applyConfigFromServer(data.config)
      }
      state.qrcodeUrl = ''
      state.rawQrcodeValue = ''
      state.sessionKey = ''
      stopPolling(botKey)
      return
    }

    if (state.status === 'expired') {
      state.qrcodeUrl = ''
      state.rawQrcodeValue = ''
      state.sessionKey = ''
      stopPolling(botKey)
      return
    }

    schedulePoll(botKey)
  } catch (error: any) {
    state.status = 'error'
    state.message = error.message || t('settings.channels.wechat.pollLoginFailed')
    stopPolling(botKey)
  } finally {
    state.polling = false
  }
}

onBeforeUnmount(() => {
  Array.from(pollTimers.values()).forEach((timer) => window.clearTimeout(timer))
  pollTimers.clear()
})
</script>
<style scoped>
@import './styles/WeChatConfig.css';
</style>
