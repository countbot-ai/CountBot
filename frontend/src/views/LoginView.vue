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
        <p class="brand-tagline">654321, AI Delivers</p>
      </div>

      <!-- Mode hint -->
      <p class="login-hint">
        {{ isSetup ? '首次远程访问，请设置管理员账号和密码' : '远程访问需要身份验证' }}
      </p>

      <!-- Form -->
      <form @submit.prevent="handleSubmit" class="login-form" autocomplete="on">
        <div class="field">
          <label for="username">账号</label>
          <input
            id="username"
            v-model="username"
            type="text"
            :placeholder="isSetup ? '设置管理员账号' : '请输入账号'"
            autocomplete="username"
            required
          />
        </div>

        <div class="field">
          <label for="password">密码</label>
          <input
            id="password"
            v-model="password"
            type="password"
            :placeholder="isSetup ? '设置密码' : '请输入密码'"
            :autocomplete="isSetup ? 'new-password' : 'current-password'"
            required
          />
        </div>

        <div v-if="isSetup" class="field">
          <label for="confirmPassword">确认密码</label>
          <input
            id="confirmPassword"
            v-model="confirmPassword"
            type="password"
            placeholder="再次输入密码"
            autocomplete="new-password"
            required
          />
        </div>

        <!-- Password requirements (always visible in setup mode) -->
        <div v-if="isSetup" class="password-rules">
          密码要求：至少 8 位，必须同时包含大写字母、小写字母和数字
        </div>

        <!-- Error message -->
        <div v-if="errorMsg" class="error-box" role="alert">{{ errorMsg }}</div>

        <button type="submit" class="submit-btn" :disabled="loading">
          <span v-if="loading" class="spinner"></span>
          {{ loading ? '请稍候...' : (isSetup ? '设置并登录' : '登录') }}
        </button>
      </form>

      <!-- Footer -->
      <div class="login-footer">
        <span v-if="!isSetup">密码要求：至少 8 位，包含大写字母、小写字母和数字</span>
        <span v-else>设置完成后将自动登录</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'

const router = useRouter()

const isSetup = ref(false)
const username = ref('')
const password = ref('')
const confirmPassword = ref('')
const errorMsg = ref('')
const loading = ref(false)

onMounted(async () => {
  try {
    const { data } = await axios.get('/api/auth/status')
    if (data.authenticated) {
      router.replace('/')
      return
    }
    isSetup.value = !data.auth_enabled
  } catch {
    // 默认显示登录模式
  }
})

async function handleSubmit() {
  errorMsg.value = ''
  loading.value = true

  try {
    if (isSetup.value) {
      if (password.value !== confirmPassword.value) {
        errorMsg.value = '两次输入的密码不一致'
        return
      }
      const { data } = await axios.post('/api/auth/setup', {
        username: username.value,
        password: password.value,
      })
      if (data.token) {
        localStorage.setItem('CountBot_token', data.token)
      }
    } else {
      const { data } = await axios.post('/api/auth/login', {
        username: username.value,
        password: password.value,
      })
      if (data.token) {
        localStorage.setItem('CountBot_token', data.token)
      }
    }
    router.replace('/')
  } catch (err: any) {
    const detail = err?.response?.data?.detail
    errorMsg.value = detail || '操作失败，请重试'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
/* ===== Page layout ===== */
.login-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  padding: 24px;
  background: var(--bg-secondary, #f8fafc);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif;
}

/* ===== Card ===== */
.login-card {
  width: 100%;
  max-width: 380px;
  padding: 40px 36px 32px;
  background: var(--bg-primary, #ffffff);
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 12px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.06);
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
  color: var(--text-primary, #0f172a);
  letter-spacing: -0.02em;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  display: flex;
  align-items: center;
  gap: 0;
}

.brand-count {
  color: var(--text-primary, #0f172a);
}

.brand-bot {
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 50%, #1d4ed8 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  font-weight: 800;
}

.brand-tagline {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--text-secondary, #64748b);
  font-weight: 500;
}

/* ===== Hint ===== */
.login-hint {
  text-align: center;
  margin: 12px 0 28px;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-secondary, #475569);
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
  color: var(--text-secondary, #475569);
}

.field input {
  padding: 10px 14px;
  font-size: 14px;
  line-height: 1.5;
  color: var(--text-primary, #0f172a);
  background: var(--bg-primary, #ffffff);
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 8px;
  outline: none;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.field input::placeholder {
  color: var(--text-tertiary, #94a3b8);
}

.field input:focus {
  border-color: var(--color-primary, #334155);
  box-shadow: 0 0 0 3px rgba(51, 65, 85, 0.08);
}

/* ===== Password rules ===== */
.password-rules {
  padding: 10px 12px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-secondary, #475569);
  background: var(--bg-tertiary, #f1f5f9);
  border-radius: 6px;
}

/* ===== Error ===== */
.error-box {
  padding: 10px 12px;
  font-size: 13px;
  line-height: 1.5;
  color: var(--color-error, #ef4444);
  background: var(--color-error-bg, #fee2e2);
  border: 1px solid rgba(239, 68, 68, 0.2);
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
  color: #ffffff;
  background: var(--color-primary, #334155);
  border: 1px solid var(--color-primary, #334155);
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s, box-shadow 0.15s, transform 0.1s;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.submit-btn:hover:not(:disabled) {
  background: var(--color-primary-hover, #1e293b);
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15);
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
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #ffffff;
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
  color: var(--text-tertiary, #94a3b8);
}

/* ===== Dark theme (cyberpunk) ===== */
[data-theme="dark"] .login-page {
  background: var(--bg-secondary, #0e1422);
}

[data-theme="dark"] .login-card {
  background: var(--bg-primary, #0a0e1a);
  border-color: var(--border-color, #152035);
  box-shadow: 0 4px 32px rgba(0, 0, 0, 0.4);
}

[data-theme="dark"] .brand-name {
  color: var(--text-primary, #d0e8f0);
}

[data-theme="dark"] .brand-count {
  color: var(--text-primary, #d0e8f0);
}

[data-theme="dark"] .brand-bot {
  background: linear-gradient(135deg, #00f0ff 0%, #00d4ff 50%, #00b8ff 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

[data-theme="dark"] .brand-tagline {
  color: var(--text-secondary, #7a9ab0);
}

[data-theme="dark"] .field input {
  background: var(--bg-secondary, #0e1422);
  border-color: var(--border-color, #152035);
  color: var(--text-primary, #d0e8f0);
}

[data-theme="dark"] .field input:focus {
  border-color: var(--color-primary, #00f0ff);
  box-shadow: 0 0 0 2px rgba(0, 240, 255, 0.1);
}

[data-theme="dark"] .field input::placeholder {
  color: var(--text-tertiary, #4a6578);
}

[data-theme="dark"] .password-rules {
  background: var(--bg-tertiary, #131b2c);
  color: var(--text-secondary, #7a9ab0);
}

[data-theme="dark"] .error-box {
  color: #ff6b8a;
  background: rgba(255, 45, 111, 0.1);
  border-color: rgba(255, 45, 111, 0.2);
}

[data-theme="dark"] .submit-btn {
  background: var(--bg-tertiary, #131b2c);
  border-color: var(--color-primary, #00f0ff);
  color: var(--color-primary, #00f0ff);
  box-shadow: 0 0 8px rgba(0, 240, 255, 0.1);
}

[data-theme="dark"] .submit-btn:hover:not(:disabled) {
  background: var(--bg-active, #152035);
  border-color: var(--color-primary-hover, #33f5ff);
  color: var(--color-primary-hover, #33f5ff);
  box-shadow: 0 0 14px rgba(0, 240, 255, 0.2);
}

[data-theme="dark"] .login-footer {
  color: var(--text-tertiary, #4a6578);
}
</style>
