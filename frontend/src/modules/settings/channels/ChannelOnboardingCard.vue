<template>
  <div ref="rootRef" class="onboarding-section">
    <div class="onboarding-header">
      <div class="onboarding-heading">
        <label class="config-label">{{ t(`settings.channels.${channelId}.onboardingTitle`) }}</label>
        <p class="config-hint">{{ t(`settings.channels.${channelId}.onboardingHint`) }}</p>
      </div>
      <button
        type="button"
        class="onboarding-button"
        :disabled="state.busy"
        @click="startOnboarding"
      >
        {{ buttonLabel }}
      </button>
    </div>

    <div class="onboarding-status-card" :class="`status-${state.status}`">
      <div class="status-row">
        <span class="status-label">{{ t('settings.channels.onboarding.statusLabel') }}</span>
        <span class="status-value">{{ statusLabel }}</span>
      </div>
      <p class="status-message">{{ state.message || t('settings.channels.onboarding.idle') }}</p>
      <p v-if="state.detail" class="status-detail">{{ state.detail }}</p>
      <p v-if="state.boundAccount" class="status-meta">
        {{ t('settings.channels.onboarding.boundAccount', { id: state.boundAccount }) }}
      </p>

      <div v-if="state.qrCodeUrl || state.rawQrUrl" class="onboarding-qr">
        <img
          v-if="state.qrCodeUrl"
          :src="state.qrCodeUrl"
          :alt="t('settings.channels.onboarding.qrAlt')"
          class="onboarding-qr-image"
          @error="handleQrImageError"
        />
        <a
          v-if="state.rawQrUrl"
          :href="state.rawQrUrl"
          target="_blank"
          rel="noopener noreferrer"
          class="onboarding-link"
        >
          {{ t('settings.channels.onboarding.openAuthPage') }}
        </a>
        <p v-if="state.userCode" class="onboarding-user-code">
          {{ t('settings.channels.onboarding.userCode', { code: state.userCode }) }}
        </p>
        <div class="onboarding-qr-actions">
          <button type="button" class="secondary-button" :disabled="state.polling" @click="pollNow">
            {{
              state.polling
                ? t('settings.channels.onboarding.polling')
                : t('settings.channels.onboarding.check')
            }}
          </button>
          <button type="button" class="secondary-button" @click="closeOnboarding">
            {{ t('common.close') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import QRCode from 'qrcode'

interface Props {
  channelId: string
  model: Record<string, any>
  paused?: boolean
}

type OnboardingStatus =
  | 'idle'
  | 'starting'
  | 'wait'
  | 'confirmed'
  | 'expired'
  | 'error'

interface OnboardingState {
  status: OnboardingStatus
  message: string
  qrCodeUrl: string
  rawQrUrl: string
  userCode: string
  sessionKey: string
  intervalSeconds: number
  expiresAt: number
  busy: boolean
  polling: boolean
  boundAccount: string
  detail: string
}

const props = defineProps<Props>()
const emit = defineEmits<{
  update: [channelId: string, config: Record<string, any>]
}>()

const { t } = useI18n()

const state = reactive<OnboardingState>(createInitialState())
const pollTimer = ref<number | null>(null)
const rootRef = ref<HTMLElement | null>(null)

function createInitialState(): OnboardingState {
  return {
    status: 'idle',
    message: '',
    qrCodeUrl: '',
    rawQrUrl: '',
    userCode: '',
    sessionKey: '',
    intervalSeconds: 3,
    expiresAt: 0,
    busy: false,
    polling: false,
    boundAccount: '',
    detail: ''
  }
}

const statusLabel = computed(() => {
  const keyMap: Record<OnboardingStatus, string> = {
    idle: 'settings.channels.onboarding.statusIdle',
    starting: 'settings.channels.onboarding.statusStarting',
    wait: 'settings.channels.onboarding.statusWaiting',
    confirmed: 'settings.channels.onboarding.statusConfirmed',
    expired: 'settings.channels.onboarding.statusExpired',
    error: 'settings.channels.onboarding.statusError'
  }
  return t(keyMap[state.status])
})

const buttonLabel = computed(() => {
  if (state.busy || state.status === 'starting') {
    return t('settings.channels.onboarding.startingButton')
  }
  if (state.status === 'confirmed' || state.status === 'expired' || state.status === 'error') {
    return t('settings.channels.onboarding.restart')
  }
  if (state.status === 'wait') {
    return t('settings.channels.onboarding.restart')
  }
  return t('settings.channels.onboarding.start')
})

const toQrImageSrc = async (value: string) => {
  try {
    return await QRCode.toDataURL(value, { width: 240, margin: 1 })
  } catch {
    return ''
  }
}

const stopPolling = () => {
  if (pollTimer.value !== null) {
    window.clearTimeout(pollTimer.value)
    pollTimer.value = null
  }
}

const hasExpired = () => state.expiresAt > 0 && Date.now() >= state.expiresAt

const markExpired = () => {
  state.status = 'expired'
  state.message = t('settings.channels.onboarding.expiredMessage')
  state.detail = ''
  resetQr()
  stopPolling()
}

const schedulePoll = () => {
  stopPolling()
  const delay = Math.max(2, Number(state.intervalSeconds) || 3) * 1000
  pollTimer.value = window.setTimeout(() => {
    if (hasExpired()) {
      markExpired()
      return
    }
    // 卡片折叠或页面切到后台时只保留本地定时器，不继续请求后端。
    if (document.hidden || !rootRef.value || rootRef.value.offsetParent === null) {
      schedulePoll()
      return
    }
    void pollOnboarding()
  }, delay)
}

const resetQr = () => {
  state.qrCodeUrl = ''
  state.rawQrUrl = ''
  state.userCode = ''
  state.sessionKey = ''
}

const requestJson = async (url: string, body: Record<string, any>) => {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  })
  return response.json()
}

const startOnboarding = async () => {
  stopPolling()
  state.busy = true
  state.polling = false
  state.boundAccount = ''
  state.detail = ''
  state.status = 'starting'
  state.message = t('settings.channels.onboarding.startingMessage')
  resetQr()

  try {
    const data = await requestJson(`/api/channels/${props.channelId}/onboard/start`, {
      account_id: String(props.model.account_id || 'default'),
      display_name: String(props.model.display_name || '')
    })
    if (!data.success) {
      throw new Error(data.message || t('settings.channels.onboarding.startFailed'))
    }

    state.status = 'wait'
    state.message = t('settings.channels.onboarding.waitingMessage')
    state.rawQrUrl = String(data.qr_url || '')
    state.userCode = String(data.user_code || '')
    state.sessionKey = String(data.session_key || '')
    state.intervalSeconds = Math.max(2, Number(data.interval) || 3)
    state.expiresAt = Date.now() + Math.max(60, Number(data.expires_in) || 600) * 1000
    state.qrCodeUrl = await toQrImageSrc(state.rawQrUrl)
    schedulePoll()
  } catch (error: any) {
    state.status = 'error'
    state.message = t('settings.channels.onboarding.startFailed')
    state.detail = String(error?.message || '')
  } finally {
    state.busy = false
  }
}

const pollOnboarding = async () => {
  if (!state.sessionKey) {
    return
  }
  if (hasExpired()) {
    markExpired()
    return
  }

  state.polling = true
  try {
    const data = await requestJson(`/api/channels/${props.channelId}/onboard/poll`, {
      session_key: state.sessionKey
    })
    const status = String(data.status || 'pending')
    state.intervalSeconds = Math.max(2, Number(data.interval) || state.intervalSeconds)

    if (status === 'success') {
      state.status = 'confirmed'
      state.message = t('settings.channels.onboarding.confirmedMessage')
      state.detail = ''
      state.boundAccount = String(data.account_id || '')
      resetQr()
      stopPolling()
      if (data.config) {
        emit('update', props.channelId, data.config)
      }
      return
    }

    if (status === 'expired') {
      markExpired()
      return
    }

    if (status === 'error' || status === 'access_denied') {
      state.status = 'error'
      state.message = t('settings.channels.onboarding.errorMessage')
      state.detail = String(data.message || '')
      resetQr()
      stopPolling()
      return
    }

    state.status = 'wait'
    state.message = t('settings.channels.onboarding.waitingMessage')
    state.detail = ''
    schedulePoll()
  } catch (error: any) {
    state.status = 'error'
    state.message = t('settings.channels.onboarding.pollFailed')
    state.detail = String(error?.message || '')
    stopPolling()
  } finally {
    state.polling = false
  }
}

const pollNow = async () => {
  if (state.polling) {
    return
  }
  await pollOnboarding()
}

const closeOnboarding = async () => {
  const sessionKey = state.sessionKey
  stopPolling()
  resetQr()
  Object.assign(state, createInitialState())
  if (!sessionKey) {
    return
  }
  try {
    await requestJson(`/api/channels/${props.channelId}/onboard/cancel`, {
      session_key: sessionKey
    })
  } catch {
    // 关闭二维码只是尽力清理会话，失败不影响主流程。
  }
}

const handleQrImageError = () => {
  state.qrCodeUrl = ''
}

const handleVisibilityChange = () => {
  if (!document.hidden && state.status === 'wait' && state.sessionKey) {
    void pollOnboarding()
  }
}

// 卡片折叠时立刻停止轮询；展开后如果仍在等待扫码则继续。
watch(
  () => props.paused,
  (paused) => {
    if (paused) {
      stopPolling()
      return
    }
    if (state.status === 'wait' && state.sessionKey && !hasExpired()) {
      schedulePoll()
    }
  }
)

onMounted(() => {
  document.addEventListener('visibilitychange', handleVisibilityChange)
})

onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', handleVisibilityChange)
  stopPolling()
})
</script>

<style scoped>
@import './styles/ChannelOnboardingCard.css';
</style>
