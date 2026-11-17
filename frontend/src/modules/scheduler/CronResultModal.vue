<template>
  <Modal
    :model-value="modelValue"
    :title="$t('cron.result.title')"
    size="large"
    :show-footer="true"
    @update:model-value="handleVisibilityChange"
  >
    <div class="cron-result">
      <div class="result-hero" :class="statusClass">
        <div class="result-hero-icon">
          <component :is="status === 'ok' ? CheckCircleIcon : AlertCircleIcon" :size="26" />
        </div>
        <div class="result-hero-copy">
          <p class="result-eyebrow">{{ payload?.jobName || jobName || $t('cron.title') }}</p>
          <h3 class="result-heading">
            {{ status === 'ok' ? $t('cron.result.statusOk') : $t('cron.result.statusError') }}
          </h3>
          <p class="result-subheading">
            {{ status === 'ok' ? $t('cron.result.statusOkHint') : $t('cron.result.statusErrorHint') }}
          </p>
        </div>
      </div>

      <div class="result-meta">
        <div class="meta-item">
          <span class="meta-label">{{ $t('cron.result.schedule') }}</span>
          <span class="meta-value">{{ displaySchedule || '—' }}</span>
        </div>
        <div class="meta-item">
          <span class="meta-label">{{ $t('cron.result.finishedAt') }}</span>
          <span class="meta-value">{{ displayFinishedAt || '—' }}</span>
        </div>
        <div class="meta-item">
          <span class="meta-label">{{ $t('cron.result.delivery') }}</span>
          <span class="meta-value" :class="deliveryStatus === 'failed' ? 'is-error' : ''">
            {{ deliveryLabel }}
          </span>
        </div>
      </div>

      <div v-if="loading" class="result-loading">
        <component :is="LoaderIcon" :size="18" class="spin" />
        <span>{{ $t('cron.result.loading') }}</span>
      </div>

      <template v-else>
        <section v-if="displayError" class="result-section result-section--error">
          <header class="result-section-head">
            <AlertCircleIcon :size="15" />
            <span>{{ $t('cron.result.error') }}</span>
          </header>
          <pre class="result-text">{{ displayError }}</pre>
        </section>

        <section v-if="displayResponse" class="result-section">
          <header class="result-section-head">
            <MessageSquareIcon :size="15" />
            <span>{{ $t('cron.result.response') }}</span>
          </header>
          <!-- eslint-disable-next-line vue/no-v-html -->
          <div class="markdown-content result-markdown" v-html="renderedResponse" />
        </section>

        <div v-if="!displayError && !displayResponse" class="result-empty">
          <InfoIcon :size="18" />
          <span>{{ $t('cron.result.empty') }}</span>
        </div>
      </template>
    </div>

    <template #footer>
      <Button variant="ghost" @click="close">
        {{ $t('cron.result.close') }}
      </Button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  AlertCircle as AlertCircleIcon,
  CheckCircle as CheckCircleIcon,
  Info as InfoIcon,
  Loader2 as LoaderIcon,
  MessageSquare as MessageSquareIcon,
} from 'lucide-vue-next'
import Button from '@/components/ui/Button.vue'
import Modal from '@/components/ui/Modal.vue'
import { cronAPI, type CronJobDetail } from '@/api'
import { useMarkdown } from '@/composables/useMarkdown'
import type { CronResultNotification } from './cronNotifications'

interface Props {
  modelValue: boolean
  jobId?: string
  payload?: CronResultNotification | null
}

const props = defineProps<Props>()
const emit = defineEmits<{ (e: 'update:modelValue', value: boolean): void }>()

const { t, locale } = useI18n()
const { renderMarkdown } = useMarkdown()

const detail = ref<CronJobDetail | null>(null)
const loading = ref(false)
const failure = ref('')

const status = computed(() => detail.value?.last_status || props.payload?.status || (failure.value ? 'error' : 'ok'))
const statusClass = computed(() => status.value === 'ok' ? 'is-success' : 'is-error')

const displaySchedule = computed(() => detail.value?.schedule || '')
const displayFinishedAt = computed(() => {
  const value = detail.value?.last_finished_at || detail.value?.last_run
  if (!value) return ''
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString(locale.value, {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      })
})
const displayResponse = computed(() => detail.value?.last_response || props.payload?.response || '')
const displayError = computed(() => {
  if (failure.value) return failure.value
  if (status.value === 'error') {
    return detail.value?.last_error || props.payload?.error || ''
  }
  return detail.value?.last_delivery_status === 'failed'
    ? detail.value?.last_delivery_error || ''
    : ''
})
const renderedResponse = computed(() => renderMarkdown(displayResponse.value))
const deliveryStatus = computed(() => detail.value?.last_delivery_status || props.payload?.deliveryStatus || '')
const deliveryLabel = computed(() => {
  switch (deliveryStatus.value) {
    case 'ok':
      return t('cron.result.deliveryOk')
    case 'failed':
      return t('cron.result.deliveryFailed')
    default:
      return t('cron.result.deliverySkipped')
  }
})
const jobName = computed(() => detail.value?.name || props.payload?.jobName || '')

async function loadDetail() {
  if (!props.modelValue || !props.jobId) {
    return
  }
  loading.value = true
  failure.value = ''
  detail.value = null
  try {
    const response = await cronAPI.getDetail(props.jobId)
    detail.value = {
      ...response.job,
      last_response: response.last_response,
      last_error: response.last_error,
    }
  } catch (error: any) {
    // 成功后自动删除的任务已经没有详情接口，此时直接使用推送携带的结果
    if (!props.payload?.response && !props.payload?.error) {
      failure.value = error?.message || t('cron.result.loadFailed')
    }
  } finally {
    loading.value = false
  }
}

function close() {
  emit('update:modelValue', false)
}

function handleVisibilityChange(value: boolean) {
  emit('update:modelValue', value)
}

watch(
  () => [props.modelValue, props.jobId],
  () => {
    if (props.modelValue) {
      void loadDetail()
    }
  },
  { immediate: true },
)
</script>

<style scoped>
@import './styles/CronResultModal.css';
</style>
