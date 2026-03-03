<template>
  <Modal
    :model-value="true"
    :title="job ? $t('cron.editJob') : $t('cron.createJob')"
    @close="handleClose"
  >
    <div class="job-editor">
      <!-- Job Name -->
      <div class="form-group">
        <label class="form-label">
          {{ $t('cron.jobName') }}
          <span class="required">*</span>
        </label>
        <Input
          v-model="formData.name"
          :placeholder="$t('cron.jobNamePlaceholder')"
          :error="errors.name"
        />
        <p
          v-if="errors.name"
          class="error-message"
        >
          {{ errors.name }}
        </p>
      </div>

      <!-- Cron Schedule -->
      <div class="form-group">
        <label class="form-label">
          {{ $t('cron.schedule') }}
          <span class="required">*</span>
        </label>
        <CronBuilder v-model="formData.schedule" />
        <p
          v-if="errors.schedule"
          class="error-message"
        >
          {{ errors.schedule }}
        </p>
      </div>

      <!-- Message -->
      <div class="form-group">
        <label class="form-label">
          {{ $t('cron.message') }}
          <span class="required">*</span>
        </label>
        <textarea
          v-model="formData.message"
          class="form-textarea"
          :placeholder="$t('cron.messagePlaceholder')"
          rows="4"
        />
        <p class="form-hint">
          {{ $t('cron.messageHint') }}
        </p>
        <p
          v-if="errors.message"
          class="error-message"
        >
          {{ errors.message }}
        </p>
      </div>

      <!-- Channel Delivery -->
      <div class="form-group">
        <label class="form-label checkbox-label">
          <input
            v-model="formData.deliverResponse"
            type="checkbox"
            class="form-checkbox"
          >
          <span>{{ $t('cron.deliverToChannel') }}</span>
        </label>
        <p class="form-hint">
          {{ $t('cron.deliverToChannelHint') }}
        </p>
      </div>

      <!-- Channel Selection (shown when deliverResponse is true) -->
      <div v-if="formData.deliverResponse" class="form-group channel-config">
        <label class="form-label">
          {{ $t('cron.channel') }}
        </label>
        <select v-model="formData.channel" class="form-select">
          <option value="web">{{ $t('cron.channelNames.web') }}</option>
          <option value="feishu">{{ $t('cron.channelNames.feishu') }}</option>
          <option value="telegram">{{ $t('cron.channelNames.telegram') }}</option>
          <option value="dingtalk">{{ $t('cron.channelNames.dingtalk') }}</option>
          <option value="wechat">{{ $t('cron.channelNames.wechat') }}</option>
          <option value="qq">{{ $t('cron.channelNames.qq') }}</option>
        </select>
        
        <label class="form-label" style="margin-top: var(--spacing-md)">
          {{ $t('cron.chatId') }}
        </label>
        <Input
          v-model="formData.chatId"
          :placeholder="$t('cron.chatIdPlaceholder')"
        />
        <p class="form-hint">
          {{ $t('cron.chatIdHint') }}
        </p>
      </div>

      <!-- Enabled Toggle -->
      <div class="form-group">
        <label class="form-label checkbox-label">
          <input
            v-model="formData.enabled"
            type="checkbox"
            class="form-checkbox"
          >
          <span>{{ $t('cron.enabledOnCreation') }}</span>
        </label>
        <p class="form-hint">
          {{ $t('cron.enabledHint') }}
        </p>
      </div>

      <!-- Actions -->
      <div class="form-actions">
        <button
          class="action-btn secondary"
          @click="handleClose"
        >
          {{ $t('common.cancel') }}
        </button>
        <button
          class="action-btn primary"
          :disabled="saving"
          @click="handleSave"
        >
          <component
            :is="LoaderIcon"
            v-if="saving"
            :size="16"
            class="spin"
          />
          {{ saving ? $t('common.saving') : $t('common.save') }}
        </button>
      </div>
    </div>
  </Modal>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useI18n } from 'vue-i18n'
import { Loader2 as LoaderIcon } from 'lucide-vue-next'
import Modal from '@/components/ui/Modal.vue'
import Input from '@/components/ui/Input.vue'
import CronBuilder from './CronBuilder.vue'
import type { CronJob } from '@/store/cron'

interface Props {
  job?: CronJob | null
}

interface Emits {
  (e: 'close'): void
  (e: 'save', data: any): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()
const { t } = useI18n()

// State
const saving = ref(false)
const formData = reactive({
  name: props.job?.name || '',
  schedule: props.job?.schedule || '',
  message: props.job?.message || '',
  enabled: props.job?.enabled ?? true,
  deliverResponse: props.job?.deliver_response ?? false,
  channel: props.job?.channel || 'web',
  chatId: props.job?.chat_id || ''
})

const errors = reactive({
  name: '',
  schedule: '',
  message: ''
})

// Methods
const validateForm = (): boolean => {
  let isValid = true

  // Reset errors
  errors.name = ''
  errors.schedule = ''
  errors.message = ''

  // Validate name
  if (!formData.name.trim()) {
    errors.name = t('cron.errors.nameRequired')
    isValid = false
  }

  // Validate schedule
  if (!formData.schedule.trim()) {
    errors.schedule = t('cron.errors.scheduleRequired')
    isValid = false
  } else {
    // Basic cron expression validation (5 parts)
    const parts = formData.schedule.trim().split(/\s+/)
    if (parts.length !== 5) {
      errors.schedule = t('cron.errors.scheduleInvalid')
      isValid = false
    }
  }

  // Validate message
  if (!formData.message.trim()) {
    errors.message = t('cron.errors.messageRequired')
    isValid = false
  }

  return isValid
}

const handleSave = async () => {
  if (!validateForm()) {
    return
  }

  saving.value = true
  try {
    const data: any = {
      name: formData.name.trim(),
      schedule: formData.schedule.trim(),
      message: formData.message.trim(),
      enabled: formData.enabled,
      deliver_response: formData.deliverResponse
    }

    // 只在启用渠道推送时包含渠道信息
    if (formData.deliverResponse) {
      data.channel = formData.channel
      data.chat_id = formData.chatId.trim()
    } else {
      data.channel = null
      data.chat_id = null
    }

    emit('save', data)
  } finally {
    saving.value = false
  }
}

const handleClose = () => {
  emit('close')
}
</script>

<style scoped>
.job-editor {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
  padding: var(--spacing-md) 0;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.form-label {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--text-primary);
}

.required {
  color: var(--color-error);
  margin-left: 2px;
}

.form-hint {
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
  margin: 0;
}

.error-message {
  font-size: var(--font-size-xs);
  color: var(--color-error);
  margin: 0;
}

.form-textarea {
  width: 100%;
  padding: var(--spacing-sm);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: var(--font-size-sm);
  font-family: inherit;
  resize: vertical;
  transition: all var(--transition-base);
}

.form-textarea:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px var(--color-primary-alpha);
}

.form-textarea::placeholder {
  color: var(--text-tertiary);
}

.form-select {
  width: 100%;
  padding: var(--spacing-sm);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: var(--font-size-sm);
  cursor: pointer;
  transition: all var(--transition-base);
}

.form-select:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px var(--color-primary-alpha);
}

/* Channel Config */
.channel-config {
  padding: var(--spacing-md);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-secondary);
}

/* Checkbox */
.checkbox-label {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  cursor: pointer;
}

.form-checkbox {
  width: 16px;
  height: 16px;
  cursor: pointer;
}

/* Actions */
.form-actions {
  display: flex;
  gap: var(--spacing-sm);
  justify-content: flex-end;
  padding-top: var(--spacing-md);
  border-top: 1px solid var(--border-color);
}

.action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: all var(--transition-base);
}

.action-btn:hover:not(:disabled) {
  background: var(--hover-bg);
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.action-btn.primary {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: white;
}

.action-btn.primary:hover:not(:disabled) {
  background: var(--color-primary-dark);
}

/* Animations */
.spin {
  animation: spin 1s linear infinite;
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
