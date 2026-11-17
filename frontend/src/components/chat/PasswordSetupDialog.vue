<template>
  <div v-if="show" class="password-dialog-overlay" @click.self="$emit('update:show', false)">
    <div class="password-dialog">
      <div class="password-dialog-header">
        <h3>{{ $t('security.setupPasswordTitle') }}</h3>
        <button class="icon-btn" @click="$emit('update:show', false)">
          <component :is="XIcon" :size="18" />
        </button>
      </div>
      <div class="password-dialog-body">
        <p class="password-dialog-desc">{{ $t('security.setupPasswordDesc') }}</p>
        <div class="password-field">
          <label>{{ $t('security.username') }}</label>
          <input
            v-model="localUsername"
            type="text"
            :placeholder="$t('security.usernamePlaceholder')"
            autocomplete="username"
          />
        </div>
        <div class="password-field">
          <label>{{ $t('security.password') }}</label>
          <input
            v-model="localPassword"
            type="password"
            :placeholder="$t('security.passwordPlaceholder')"
            autocomplete="new-password"
          />
        </div>
        <div class="password-field">
          <label>{{ $t('security.confirmPassword') }}</label>
          <input
            v-model="localPasswordConfirm"
            type="password"
            :placeholder="$t('security.confirmPasswordPlaceholder')"
            autocomplete="new-password"
            @keydown.enter="handleSubmit"
          />
        </div>
        <p v-if="error" class="password-error">{{ error }}</p>
      </div>
      <div class="password-dialog-footer">
        <button class="btn-cancel" @click="$emit('update:show', false)">
          {{ $t('common.cancel') }}
        </button>
        <button class="btn-confirm" :disabled="loading" @click="handleSubmit">
          <span v-if="loading" class="spin-small" />
          {{ $t('security.confirm') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { X as XIcon } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { authAPI } from '@/api/endpoints'
import { useToast } from '@/composables/useToast'

interface Props {
  show: boolean
}

interface Emits {
  (e: 'update:show', value: boolean): void
  (e: 'success'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const { t } = useI18n()
const toast = useToast()

const localUsername = ref('admin')
const localPassword = ref('')
const localPasswordConfirm = ref('')
const error = ref('')
const loading = ref(false)

// 重置表单
watch(() => props.show, (newShow) => {
  if (newShow) {
    localUsername.value = 'admin'
    localPassword.value = ''
    localPasswordConfirm.value = ''
    error.value = ''
    loading.value = false
  }
})

const handleSubmit = async () => {
  error.value = ''
  
  if (!localUsername.value.trim()) {
    error.value = t('security.errorUsernameRequired')
    return
  }
  
  if (localPassword.value !== localPasswordConfirm.value) {
    error.value = t('security.errorPasswordMismatch')
    return
  }
  
  if (
    localPassword.value.length < 8 ||
    !/[A-Z]/.test(localPassword.value) ||
    !/[a-z]/.test(localPassword.value) ||
    !/\d/.test(localPassword.value)
  ) {
    error.value = t('security.errorPasswordWeak')
    return
  }
  
  loading.value = true
  try {
    const result = await authAPI.setup({
      username: localUsername.value.trim(),
      password: localPassword.value
    })
    
    if (result.success && result.token) {
      localStorage.setItem('CountBot_token', result.token)
    }
    
    emit('update:show', false)
    emit('success')
    toast.success(t('security.setupSuccess'))
  } catch (err: any) {
    error.value = err?.message || err?.details?.detail || t('common.error')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.password-dialog-overlay {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-bg-overlay);
  backdrop-filter: blur(4px);
  z-index: 200;
}

.password-dialog {
  width: 420px;
  max-width: 90vw;
  background: var(--bg-primary);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}

.password-dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px 0;
}

.password-dialog-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
}

.icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s ease;
}

.icon-btn:hover {
  background: var(--hover-bg);
}

.password-dialog-body {
  padding: 16px 24px 8px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.password-dialog-desc {
  margin: 0;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.password-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.password-field label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
}

.password-field input {
  padding: 10px 12px;
  border: 1.5px solid var(--border-color, var(--color-border-secondary));
  border-radius: var(--radius-md);
  font-size: 14px;
  color: var(--text-primary);
  background: var(--bg-primary);
  outline: none;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.password-field input:focus {
  border-color: var(--color-border-strong);
  box-shadow: none;
}

.password-error {
  margin: 0;
  padding: 8px 12px;
  background: var(--color-error-light);
  border: 1px solid color-mix(in srgb, var(--color-error) 20%, transparent);
  border-radius: var(--radius-md);
  color: var(--color-error);
  font-size: 13px;
}



.password-dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 16px 24px 20px;
}

.btn-cancel {
  padding: 8px 18px;
  border: 1.5px solid var(--border-color, var(--color-border-secondary));
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--text-secondary);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-cancel:hover {
  background: var(--hover-bg);
}

.btn-confirm {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 20px;
  border: none;
  border-radius: var(--radius-md);
  background: var(--text-primary);
  color: var(--color-text-inverse);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-confirm:hover {
  background: var(--text-primary);
}

.btn-confirm:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}





.spin-small {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid var(--color-border-primary);
  border-top-color: var(--color-border-primary);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>
