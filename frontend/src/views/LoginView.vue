<template>
  <div class="login-page">
    <div class="login-card">
      <!-- Logo area -->
      <div class="login-brand">
        <div class="brand-icon">
          <img src="@/assets/countbot-logo.svg" alt="CountBot Logo" />
        </div>
        <h1 class="brand-name">
          <span class="brand-count">Count</span><span class="brand-bot">Bot</span>
        </h1>
      </div>

      <!-- Mode hint -->
      <p class="login-hint">
        {{ hintText }}
      </p>

      <!-- Form -->
      <form @submit.prevent="handleSubmit" class="login-form" autocomplete="on">
        <div class="field">
          <label for="username">{{ $t('login.page.username') }}</label>
          <input
            id="username"
            v-model="username"
            type="text"
            :placeholder="isSetup ? $t('login.page.usernameSetupPlaceholder') : $t('login.page.usernamePlaceholder')"
            autocomplete="username"
            required
          />
        </div>

        <div class="field">
          <label for="password">{{ $t('login.page.password') }}</label>
          <input
            id="password"
            v-model="password"
            type="password"
            :placeholder="isSetup ? $t('login.page.passwordSetupPlaceholder') : $t('login.page.passwordPlaceholder')"
            :autocomplete="isSetup ? 'new-password' : 'current-password'"
            required
          />
        </div>

        <!-- 设置管理员与注册均需确认密码，两处提交都会校验 confirmPassword -->
        <div v-if="isSetup || isRegister" class="field">
          <label for="confirmPassword">{{ $t('login.page.confirmPassword') }}</label>
          <input
            id="confirmPassword"
            v-model="confirmPassword"
            type="password"
            :placeholder="$t('login.page.confirmPasswordPlaceholder')"
            autocomplete="new-password"
            required
          />
        </div>

        <!-- Registration mode: display name is optional -->
        <div v-if="isRegister" class="field">
          <label for="displayName">{{ $t('login.page.displayName') }}</label>
          <input
            id="displayName"
            v-model="displayName"
            type="text"
            :placeholder="$t('login.page.displayNamePlaceholder')"
            autocomplete="nickname"
          />
        </div>

        <!-- Password requirements (always visible in setup/register mode) -->
        <div v-if="isSetup || isRegister" class="password-rules">
          {{ $t('login.page.passwordRequirement') }}
        </div>

        <div v-if="isRegister && approvalManual" class="password-rules">
          {{ $t('login.page.pendingApprovalNotice') }}
        </div>

        <div v-if="infoMsg" class="password-rules">{{ infoMsg }}</div>

        <div v-if="needsLocalSetup" class="error-box" role="alert">
          {{ $t('login.page.localSetupNotice') }}
        </div>

        <!-- Error message -->
        <div v-if="errorMsg" class="error-box" role="alert">{{ errorMsg }}</div>

        <button type="submit" class="submit-btn" :disabled="loading || needsLocalSetup">
          <span v-if="loading" class="spinner"></span>
          {{ loading ? $t('login.page.loading') : (isSetup ? $t('login.page.setupAndLogin') : (isRegister ? $t('login.page.register') : $t('login.page.login'))) }}
        </button>
      </form>

      <!-- 注册 / 登录切换 -->
      <div v-if="canRegister && !isSetup" class="login-footer">
        <a v-if="!isRegister" href="#" @click.prevent="switchMode('register')">{{ $t('login.page.noAccount') }}</a>
        <a v-else href="#" @click.prevent="switchMode('login')">{{ $t('login.page.hasAccount') }}</a>
      </div>

      <!-- Footer -->
      <div class="login-footer">
        <span v-if="!isSetup">{{ $t('login.page.passwordRequirementShort') }}</span>
        <span v-else>{{ $t('login.page.autoLogin') }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import axios from 'axios'
import { authAPI } from '@/api/endpoints'
import { useUserStore } from '@/store/user'

const router = useRouter()
const userStore = useUserStore()
const { t } = useI18n()
const route = useRoute()

const isSetup = ref(false)
const isRegister = ref(false)
const canRegister = ref(false)
const approvalManual = ref(true)
const displayName = ref('')
const infoMsg = ref('')
const username = ref('')
const password = ref('')
const confirmPassword = ref('')
const errorMsg = ref('')
const loading = ref(false)
const needsLocalSetup = ref(false)
const setupSecret = computed(() => {
  const value = route.params.setupSecret
  return typeof value === 'string' ? value : ''
})

const setupBlockedText = computed(() => {
  return setupSecret.value
    ? t('login.page.setupInvalid')
    : t('login.page.setupRemote')
})

const hintText = computed(() => {
  if (needsLocalSetup.value) {
    return setupSecret.value ? t('login.page.setupUnavailable') : t('login.page.remoteSetupOnly')
  }
  if (isSetup.value) return t('login.page.firstSetupHint')
  if (isRegister.value) return t('login.page.registerHint')
  return t('login.page.loginHint')
})

function switchMode(mode: 'login' | 'register') {
  isRegister.value = mode === 'register'
  errorMsg.value = ''
  infoMsg.value = ''
}

function getSetupHeaders() {
  return setupSecret.value ? { 'X-Setup-Secret': setupSecret.value } : undefined
}

onMounted(async () => {
  try {
    const { data } = await axios.get('/api/auth/status', {
      headers: getSetupHeaders(),
    })
    if (data.authenticated) {
      router.replace('/')
      return
    }
    isSetup.value = Boolean(data.setup_allowed)
    needsLocalSetup.value = !data.auth_enabled && !data.setup_allowed
    canRegister.value = Boolean(data.registration_open)
    approvalManual.value = String(data.approval_mode || 'manual') !== 'auto'
    if (canRegister.value) {
      // 仅作为入口提示，是否真的能注册由服务端判定
      isRegister.value = false
    }
  } catch {
    // 默认显示登录模式
  }
})

async function handleSubmit() {
  errorMsg.value = ''
  infoMsg.value = ''
  if (needsLocalSetup.value) {
    errorMsg.value = setupBlockedText.value
    return
  }
  loading.value = true

  try {
    if (isSetup.value) {
      if (password.value !== confirmPassword.value) {
        errorMsg.value = t('login.page.passwordMismatch')
        return
      }
      const { data } = await axios.post(
        '/api/auth/setup',
        {
          username: username.value,
          password: password.value,
        },
        {
          headers: getSetupHeaders(),
        }
      )
      if (data.token) {
        localStorage.setItem('CountBot_token', data.token)
      }
      await userStore.refresh().catch(() => undefined)
      router.replace('/')
    } else if (isRegister.value) {
      if (password.value !== confirmPassword.value) {
        errorMsg.value = t('login.page.passwordMismatch')
        return
      }
      const data = await authAPI.register({
        username: username.value,
        password: password.value,
        display_name: displayName.value || undefined,
      })
      if (data?.status === 'pending') {
        infoMsg.value = t('login.page.registerSuccess')
        isRegister.value = false
        return
      }
      await userStore.refresh().catch(() => undefined)
      router.replace('/')
    } else {
      const { data } = await axios.post('/api/auth/login', {
        username: username.value,
        password: password.value,
      })
      if (data.token) {
        localStorage.setItem('CountBot_token', data.token)
      }
      await userStore.refresh().catch(() => undefined)
      router.replace('/')
    }
  } catch (err: any) {
    // 错误信息已由 transformError 转成统一结构，同时兼容 axios 形态
    const payload = err?.response?.data ?? err
    const detail = payload?.detail
    const code = payload?.code
    if (code === 'ACCOUNT_PENDING') {
      infoMsg.value = t('login.page.accountPending')
    } else {
      const text =
        (typeof detail === 'string' ? detail : detail?.detail) ||
        payload?.message ||
        t('login.page.operationFailed')
      errorMsg.value = text
    }
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
/* ===== Page layout ===== */
.login-page {
  /* 固定铺满视口：父级 overflow:hidden，自身需成为独立滚动容器 */
  position: fixed;
  inset: 0;
  display: flex;
  justify-content: center;
  padding: 24px;
  background: var(--bg-secondary);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif;
  overflow-y: auto;
  box-sizing: border-box;
}

/* ===== Card ===== */
.login-card {
  width: 100%;
  max-width: 380px;
  padding: 40px 36px 32px;
  background: var(--bg-primary);
  border: 1px solid var(--border-color, var(--color-border-primary));
  border-radius: 12px;
  box-shadow: var(--shadow-sm);
  /* 内容可放下时垂直居中，放不下时保留完整高度 */
  margin: auto;
}

/* ===== Brand ===== */
.login-brand {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.brand-icon {
  width: 64px;
  height: 64px;
  border-radius: 12px;
  overflow: hidden;
}

.brand-icon img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.brand-name {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.02em;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  display: flex;
  align-items: center;
  gap: 0;
}

.brand-count {
  color: var(--text-primary);
}

.brand-bot {
  background: linear-gradient(135deg, var(--color-primary) 0%, var(--color-secondary) 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  font-weight: var(--font-weight-bold);
}

/* ===== Hint ===== */
.login-hint {
  text-align: center;
  margin: 12px 0 28px;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-secondary);
}

/* ===== Form ===== */
.login-form {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}

.field input {
  padding: 10px 14px;
  font-size: 14px;
  line-height: 1.5;
  color: var(--text-primary);
  background: var(--bg-primary);
  border: 1px solid var(--border-color, var(--color-border-primary));
  border-radius: 8px;
  outline: none;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.field input::placeholder {
  color: var(--text-tertiary);
}

.field input:focus {
  border-color: var(--color-border-strong);
  box-shadow: var(--shadow-sm);
}

/* ===== Password rules ===== */
.password-rules {
  padding: 10px 12px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-secondary);
  background: var(--bg-tertiary);
  border-radius: 6px;
}

/* ===== Error ===== */
.error-box {
  padding: 10px 12px;
  font-size: 13px;
  line-height: 1.5;
  color: var(--color-error);
  background: var(--color-error-bg);
  border: 1px solid var(--color-border-primary);
  border-radius: 6px;
}

/* ===== Submit button ===== */
.submit-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  padding: 11px 0;
  margin-top: 4px;
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text-inverse);
  background: var(--color-primary);
  border: 1px solid var(--color-primary, var(--color-border-strong));
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s, box-shadow 0.15s, transform 0.1s;
  box-shadow: var(--shadow-sm);
}

.submit-btn:hover:not(:disabled) {
  background: var(--color-primary-hover);
  box-shadow: var(--shadow-sm);
  transform: translateY(-1px);
}

.submit-btn:active:not(:disabled) {
  transform: translateY(0);
}

.submit-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

/* ===== Spinner ===== */
.spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid var(--color-border-primary);
  border-top-color: var(--color-border-primary);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ===== Footer ===== */
.login-footer {
  margin-top: 24px;
  text-align: center;
  font-size: 12px;
  color: var(--text-tertiary);
}

/* ===== Dark theme ===== */



























</style>
