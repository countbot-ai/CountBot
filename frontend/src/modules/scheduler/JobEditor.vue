<template>
  <!-- Cron Job Editor with inline toggle switches -->
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
      <div class="form-group toggle-group">
        <div class="toggle-wrapper">
          <div class="toggle-content">
            <div class="toggle-label-text">
              <span class="toggle-title">{{ $t('cron.deliverToChannel') }}</span>
              <p class="toggle-hint">{{ $t('cron.deliverToChannelHint') }}</p>
            </div>
          </div>
          <SwitchToggle
            v-model="formData.deliverResponse"
            :width="44"
            :height="24"
            :aria-label="$t('cron.deliverToChannel')"
          />
        </div>
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
          <option value="wecom">{{ $t('cron.channelNames.wecom') }}</option>
          <option value="wechat">{{ $t('cron.channelNames.wechat') }}</option>
          <option value="weibo">{{ $t('cron.channelNames.weibo') }}</option>
          <option value="qq">{{ $t('cron.channelNames.qq') }}</option>
        </select>

        <label class="form-label" style="margin-top: var(--spacing-md)">
          {{ $t('cron.accountId') }}
        </label>
        <Input
          v-model="formData.accountId"
          :placeholder="$t('cron.accountIdPlaceholder')"
        />
        <p class="form-hint">
          {{ $t('cron.accountIdHint') }}
        </p>
        
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

      <!-- Advanced Options Section -->
      <div class="form-section">
        <div class="section-header">
          <h3 class="section-title">{{ $t('cron.advancedOptions') }}</h3>
        </div>

        <!-- Retry Configuration -->
        <div class="form-group toggle-group">
          <div class="toggle-wrapper">
            <div class="toggle-content">
              <div class="toggle-label-text">
                <span class="toggle-title">{{ $t('cron.enableRetry') }}</span>
                <p class="toggle-hint">{{ $t('cron.enableRetryHint') }}</p>
              </div>
            </div>
            <SwitchToggle
              v-model="formData.enableRetry"
              :width="44"
              :height="24"
              :aria-label="$t('cron.enableRetry')"
            />
          </div>
        </div>

        <!-- Retry Settings (shown when enableRetry is true) -->
        <div v-if="formData.enableRetry" class="retry-config">
          <div class="form-row">
            <div class="form-col">
              <label class="form-label">
                {{ $t('cron.maxRetries') }}
              </label>
              <Input
                v-model.number="formData.maxRetries"
                type="number"
                min="1"
                max="5"
                :placeholder="$t('cron.maxRetriesPlaceholder')"
              />
              <p class="form-hint">
                {{ $t('cron.maxRetriesHint') }}
              </p>
            </div>
            <div class="form-col">
              <label class="form-label">
                {{ $t('cron.retryDelay') }}
              </label>
              <Input
                v-model.number="formData.retryDelay"
                type="number"
                min="10"
                max="3600"
                :placeholder="$t('cron.retryDelayPlaceholder')"
              />
              <p class="form-hint">
                {{ $t('cron.retryDelayHint') }}
              </p>
            </div>
          </div>
        </div>

        <!-- One-time Task (Delete on Success) -->
        <div class="form-group toggle-group">
          <div class="toggle-wrapper">
            <div class="toggle-content">
              <div class="toggle-label-text">
                <span class="toggle-title">{{ $t('cron.deleteOnSuccess') }}</span>
                <p class="toggle-hint">{{ $t('cron.deleteOnSuccessHint') }}</p>
              </div>
            </div>
            <SwitchToggle
              v-model="formData.deleteOnSuccess"
              :width="44"
              :height="24"
              :aria-label="$t('cron.deleteOnSuccess')"
            />
          </div>
        </div>

        <!-- Warning for one-time task -->
        <div v-if="formData.deleteOnSuccess" class="warning-box">
          <span>{{ $t('cron.deleteOnSuccessWarning') }}</span>
        </div>
      </div>

      <!-- Enabled Toggle -->
      <div class="form-group toggle-group">
        <div class="toggle-wrapper">
          <div class="toggle-content">
            <div class="toggle-label-text">
              <span class="toggle-title">{{ $t('cron.enabledOnCreation') }}</span>
              <p class="toggle-hint">{{ $t('cron.enabledHint') }}</p>
            </div>
          </div>
          <SwitchToggle
            v-model="formData.enabled"
            :width="44"
            :height="24"
            :aria-label="$t('cron.enabledOnCreation')"
          />
        </div>
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
import { reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Loader2 as LoaderIcon } from 'lucide-vue-next'
import Modal from '@/components/ui/Modal.vue'
import Input from '@/components/ui/Input.vue'
import SwitchToggle from '@/components/ui/SwitchToggle.vue'
import CronBuilder from './CronBuilder.vue'
import type { CronJob } from '@/api'

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
  accountId: props.job?.account_id || 'default',
  chatId: props.job?.chat_id || '',
  enableRetry: props.job?.max_retries !== undefined ? props.job.max_retries > 0 : true,
  maxRetries: props.job?.max_retries || 1,
  retryDelay: props.job?.retry_delay || 60,
  deleteOnSuccess: props.job?.delete_on_success ?? false
})

const errors = reactive({
  name: '',
  schedule: '',
  message: ''
})

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
      deliver_response: formData.deliverResponse,
      max_retries: formData.enableRetry ? formData.maxRetries : 0,
      retry_delay: formData.retryDelay,
      delete_on_success: formData.deleteOnSuccess
    }

    // 只在启用渠道推送时包含渠道信息
    if (formData.deliverResponse) {
      data.channel = formData.channel
      data.account_id = formData.channel === 'web' ? null : (formData.accountId.trim() || 'default')
      data.chat_id = formData.chatId.trim()
    } else {
      data.channel = null
      data.account_id = null
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
@import './styles/JobEditor.css';
</style>
