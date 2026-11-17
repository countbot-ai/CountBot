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
        <p class="form-hint">
          {{ $t('cron.scheduleTimezoneHint') }}
        </p>
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
          maxlength="10000"
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
            :disabled="!canDeliver"
            :width="44"
            :height="24"
            :aria-label="$t('cron.deliverToChannel')"
            @change="handleDeliverToggle"
          />
        </div>
        <p v-if="!canDeliver" class="form-hint">
          {{ $t('cron.noConfiguredChannelHint') }}
        </p>
      </div>

      <!-- Channel Selection (shown when deliverResponse is true) -->
      <div v-if="formData.deliverResponse" class="form-group channel-config">
        <label class="form-label">
          {{ $t('cron.channel') }}
        </label>
        <select v-model="formData.channel" class="form-select">
          <option value="" disabled>{{ $t('cron.selectChannel') }}</option>
          <option
            v-for="option in channelOptions"
            :key="option.value"
            :value="option.value"
          >
            {{ option.label }}
          </option>
        </select>
        <p v-if="!channelOptions.length" class="form-hint">
          {{ $t('cron.noConfiguredChannelHint') }}
        </p>
        <p v-if="errors.channel" class="error-message">
          {{ errors.channel }}
        </p>

        <p v-if="formData.channel === 'web'" class="form-hint web-channel-hint">
          {{ $t('cron.webChannelHint') }}
        </p>

        <template v-if="formData.channel && formData.channel !== 'web'">
          <label class="form-label" style="margin-top: var(--spacing-md)">
            {{ $t('cron.accountId') }}
          </label>
          <select
            v-if="accountOptions.length"
            v-model="formData.accountId"
            class="form-select"
          >
            <option
              v-for="account in accountOptions"
              :key="account.account_id"
              :value="account.account_id"
            >
              {{ account.display_name }}（{{ account.account_id }}）
            </option>
          </select>
          <Input
            v-else
            v-model="formData.accountId"
            :placeholder="$t('cron.accountIdPlaceholder')"
          />
          <p class="form-hint">
            {{ $t('cron.accountIdHint') }}
          </p>

          <template v-if="channelNeedsChatId">
            <label class="form-label" style="margin-top: var(--spacing-md)">
              {{ $t('cron.chatId') }}
            </label>
            <select
              v-if="chatOptions.length"
              :value="selectedChatOption"
              class="form-select"
              @change="handleChatOptionChange"
            >
              <option
                v-for="chat in chatOptions"
                :key="chat.chat_id"
                :value="chat.chat_id"
              >
                {{ formatChatOption(chat) }}
              </option>
              <option value="__custom__">{{ $t('cron.chatIdCustom') }}</option>
            </select>
            <Input
              v-if="selectedChatOption === '__custom__' || !chatOptions.length"
              v-model="formData.chatId"
              :placeholder="$t('cron.chatIdPlaceholder')"
              style="margin-top: var(--spacing-sm)"
            />
            <p class="form-hint">
              {{ chatOptions.length ? $t('cron.chatIdPickHint') : $t('cron.chatIdHint') }}
            </p>
            <p v-if="errors.chatId" class="error-message">
              {{ errors.chatId }}
            </p>
          </template>
          <p v-else class="form-hint" style="margin-top: var(--spacing-md)">
            {{ $t('cron.chatIdNotRequiredHint') }}
          </p>
        </template>
      </div>

      <!-- Model Selection -->
      <div class="form-group">
        <label class="form-label">
          {{ $t('cron.model') }}
        </label>
        <select v-model="modelSelectionKey" class="form-select">
          <option value="">{{ followGlobalModelLabel }}</option>
          <option v-if="currentModelMissing" :value="modelSelectionKey">
            {{ formData.modelProvider }} / {{ formData.modelName }}{{ $t('cron.modelMissingSuffix') }}
          </option>
          <optgroup
            v-for="group in modelGroups"
            :key="group.providerId"
            :label="group.providerName"
          >
            <option
              v-for="model in group.models"
              :key="modelOptionKey(group, model)"
              :value="modelOptionKey(group, model)"
            >
              {{ model.display_name || model.id }}
            </option>
          </optgroup>
        </select>
        <p class="form-hint">
          {{ $t('cron.modelHint') }}
        </p>
        <p v-if="!modelGroups.length" class="form-hint">
          {{ $t('cron.modelEmptyHint') }}
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

        <!-- 关联上下文：开启后把该任务之前的执行记录一起发给模型 -->
        <div class="form-group toggle-group">
          <div class="toggle-wrapper">
            <div class="toggle-content">
              <div class="toggle-label-text">
                <span class="toggle-title">{{ $t('cron.linkContext') }}</span>
                <p class="toggle-hint">{{ $t('cron.linkContextHint') }}</p>
              </div>
            </div>
            <SwitchToggle
              v-model="formData.linkContext"
              :width="44"
              :height="24"
              :aria-label="$t('cron.linkContext')"
            />
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
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Loader2 as LoaderIcon } from 'lucide-vue-next'
import Modal from '@/components/ui/Modal.vue'
import Input from '@/components/ui/Input.vue'
import SwitchToggle from '@/components/ui/SwitchToggle.vue'
import CronBuilder from './CronBuilder.vue'
import { useChannelsStore, type DeliveryTarget } from '@/store/channels'
import { useSettingsStore } from '@/store/settings'
import { cronAPI, meAPI } from '@/api'
import type { CronJob, ProviderMetadata } from '@/api'
import { useModelCatalog } from '@/composables/useModelCatalog'
import {
  buildProviderOptions,
  buildProviderOptionsFromMeModels,
  buildSelectableModelGroups,
  type ProviderOption,
} from '@/composables/useProviderModelCatalog'

interface Props {
  job?: CronJob | null
}

interface Emits {
  (e: 'close'): void
  (e: 'save', data: any): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()
const { t, te } = useI18n()
const channelsStore = useChannelsStore()

// 推送目标：网页站内通知 + 「设置 - 渠道」里已配置好的真实渠道
const deliveryTargets = computed(() => channelsStore.deliveryTargets)
const webTarget = computed<DeliveryTarget>(() => ({
  channel: 'web',
  name: t('cron.webChannelName'),
  icon: '',
  enabled: true,
  configured: true,
  running: true,
  accounts: [],
  chats: [],
}))
const deliverableTargets = computed(() => [
  webTarget.value,
  ...deliveryTargets.value.filter((target) => target.channel !== 'web'),
])

const channelOptions = computed(() => {
  const options = deliverableTargets.value.map((target) => ({
    value: target.channel,
    label: target.running ? target.name : `${target.name}（${t('cron.channelNotRunning')}）`
  }))

  // 历史任务可能指向已下线/未配置的渠道，保留原值避免静默改写配置
  const current = props.job?.channel
  if (current && current !== 'web' && !options.some((item) => item.value === current)) {
    const fallbackKey = `cron.channelNames.${current}`
    options.push({
      value: current,
      label: te(fallbackKey) ? t(fallbackKey) : current
    })
  }

  return options
})

// 网页站内通知始终可用；历史真实渠道允许保留原值
const canDeliver = computed(() =>
  deliverableTargets.value.length > 0 ||
  Boolean(props.job?.channel)
)

const selectedTarget = computed(() =>
  deliverableTargets.value.find((target) => target.channel === formData.channel) || null
)

const accountOptions = computed(() => selectedTarget.value?.accounts || [])

const chatOptions = computed(() => {
  const target = selectedTarget.value
  if (!target) {
    return []
  }
  const accountId = formData.accountId || 'default'
  const matched = target.chats.filter((chat) => chat.account_id === accountId)
  return matched.length ? matched : target.chats
})

const selectedChatOption = computed(() =>
  chatOptions.value.some((chat) => chat.chat_id === formData.chatId)
    ? formData.chatId
    : '__custom__'
)

const formatChatOption = (chat: { chat_id: string; is_group: boolean; session_name?: string }) => {
  const scope = chat.is_group ? t('cron.chatTypeGroup') : t('cron.chatTypeUser')
  return `${chat.chat_id} · ${scope}`
}

const handleChatOptionChange = (event: Event) => {
  const value = (event.target as HTMLSelectElement).value
  if (value !== '__custom__') {
    formData.chatId = value
  }
}

// 复用渠道设置里已配置的账号，避免手填 account_id
const syncAccountWithChannel = () => {
  const target = deliverableTargets.value.find((item) => item.channel === formData.channel)
  if (!target || !target.accounts.length) {
    return
  }
  if (!target.accounts.some((account) => account.account_id === formData.accountId)) {
    formData.accountId = target.accounts[0].account_id
  }
}

// State
const saving = ref(false)
const formData = reactive({
  name: props.job?.name || '',
  schedule: props.job?.schedule || '',
  message: props.job?.message || '',
  enabled: props.job?.enabled ?? true,
  deliverResponse: props.job?.deliver_response ?? false,
  channel: props.job?.channel || '',
  accountId: props.job?.account_id || 'default',
  chatId: props.job?.chat_id || '',
  modelProvider: props.job?.model_provider || '',
  modelName: props.job?.model_name || '',
  enableRetry: props.job?.max_retries !== undefined ? props.job.max_retries > 0 : true,
  maxRetries: props.job?.max_retries || 1,
  retryDelay: props.job?.retry_delay || 60,
  linkContext: props.job?.link_context ?? false,
  deleteOnSuccess: props.job?.delete_on_success ?? false
})

const errors = reactive({
  name: '',
  schedule: '',
  message: '',
  channel: '',
  chatId: ''
})

// Server酱等只推送渠道没有会话目标，chat_id 用渠道名占位即可，无需用户填写
const PUSH_ONLY_CHANNELS = ['serverchan']
const channelNeedsChatId = computed(
  () => formData.channel !== 'web' && !PUSH_ONLY_CHANNELS.includes(formData.channel)
)

const syncChatIdWithChannel = () => {
  if (formData.channel === 'web') {
    formData.chatId = ''
    return
  }
  if (!channelNeedsChatId.value) {
    formData.chatId = formData.channel
    return
  }
  // 离开只推送渠道时清掉占位值，避免把渠道名当成真实聊天 ID 保存
  if (PUSH_ONLY_CHANNELS.includes(formData.chatId.trim())) {
    formData.chatId = ''
  }
}

const handleChannelChange = (channel: string, previous: string) => {
  syncChatIdWithChannel()
  syncAccountWithChannel()
  if (
    channel &&
    previous &&
    channel !== previous &&
    formData.chatId &&
    chatOptions.value.length &&
    !chatOptions.value.some((chat) => chat.chat_id === formData.chatId)
  ) {
    formData.chatId = ''
  }
}

watch(() => formData.channel, handleChannelChange)
syncChatIdWithChannel()

const syncDeliverySelection = () => {
  if (!formData.deliverResponse) {
    return
  }
  if (!formData.channel) {
    formData.channel = deliverableTargets.value[0]?.channel || ''
  }
  if (!formData.channel) {
    return
  }
  syncAccountWithChannel()
}

const handleDeliverToggle = (checked: boolean) => {
  if (checked) {
    syncDeliverySelection()
  }
}

onMounted(async () => {
  await channelsStore.fetchDeliveryTargets(true).catch(() => [])
  syncDeliverySelection()
})

watch(deliveryTargets, () => {
  syncDeliverySelection()
})

// 任务模型：管理员复用全局供应商清单；普通用户复用 /api/me/models 的可选模型
const settingsStore = useSettingsStore()
const modelCatalog = useModelCatalog()
const providerMetadata = ref<ProviderMetadata[]>([])
const userProviderOptions = ref<ProviderOption[]>([])

const modelGroups = computed(() =>
  buildSelectableModelGroups(
    modelCatalog.isUserScoped.value
      ? userProviderOptions.value
      : buildProviderOptions(settingsStore.settings?.providers, providerMetadata.value)
  )
)

/** 共享模型合并展示时，条目自带真实供应商 ID。 */
const modelOptionKey = (group: { providerId: string }, model: { id: string; provider_id?: string | null }) =>
  `${model.provider_id || group.providerId}:${model.id}`

const globalModelLabel = computed(() => {
  const model = settingsStore.settings?.model
  if (!model?.provider || !model?.model) {
    return ''
  }
  return `${model.provider} / ${model.model}`
})

const followGlobalModelLabel = computed(() =>
  globalModelLabel.value
    ? `${t('cron.modelFollowGlobal')}（${globalModelLabel.value}）`
    : t('cron.modelFollowGlobal')
)

/** 用 `供应商:模型` 作为下拉 key，空串表示跟随全局默认。 */
const modelSelectionKey = computed({
  get: () =>
    formData.modelProvider && formData.modelName
      ? `${formData.modelProvider}:${formData.modelName}`
      : '',
  set: (value: string) => {
    if (!value) {
      formData.modelProvider = ''
      formData.modelName = ''
      return
    }
    const separatorIndex = value.indexOf(':')
    formData.modelProvider = value.slice(0, separatorIndex)
    formData.modelName = value.slice(separatorIndex + 1)
  },
})

// 任务保存的模型可能已从清单移除，回退显示原值避免静默改写
const currentModelMissing = computed(() => {
  const key = modelSelectionKey.value
  if (!key) {
    return false
  }
  return !modelGroups.value.some(group =>
    group.models.some(model => modelOptionKey(group, model) === key)
  )
})

onMounted(async () => {
  await modelCatalog.ensureIdentity().catch(() => {})
  if (modelCatalog.isUserScoped.value) {
    const data = await meAPI.listModels().catch(() => null)
    userProviderOptions.value = data ? buildProviderOptionsFromMeModels(data) : []
    return
  }
  // 全局设置仅管理员可读
  if (!settingsStore.settings) {
    await settingsStore.loadSettings().catch(() => {})
  }
  providerMetadata.value = await modelCatalog.listProviders().catch(() => [])
})

const validateForm = async (): Promise<boolean> => {
  let isValid = true

  // Reset errors
  errors.name = ''
  errors.schedule = ''
  errors.message = ''
  errors.channel = ''
  errors.chatId = ''

  // Validate name
  if (!formData.name.trim()) {
    errors.name = t('cron.errors.nameRequired')
    isValid = false
  }

  // Validate schedule
  const schedule = formData.schedule.trim()
  if (!schedule) {
    errors.schedule = t('cron.errors.scheduleRequired')
    isValid = false
  } else {
    const parts = schedule.split(/\s+/)
    if (parts.length !== 5) {
      errors.schedule = t('cron.errors.scheduleInvalid')
      isValid = false
    } else {
      try {
        const result = await cronAPI.validate(schedule)
        if (!result.valid) {
          errors.schedule = result.description || t('cron.errors.scheduleInvalid')
          isValid = false
        }
      } catch {
        errors.schedule = t('cron.errors.scheduleInvalid')
        isValid = false
      }
    }
  }

  // Validate message
  if (!formData.message.trim()) {
    errors.message = t('cron.errors.messageRequired')
    isValid = false
  }

  if (formData.deliverResponse) {
    if (!formData.channel) {
      errors.channel = t('cron.errors.channelRequired')
      isValid = false
    }
    if (channelNeedsChatId.value && !formData.chatId.trim()) {
      errors.chatId = t('cron.errors.chatRequired')
      isValid = false
    }
  }

  return isValid
}

const handleSave = async () => {
  if (saving.value) {
    return
  }

  saving.value = true
  try {
    if (!(await validateForm())) {
      return
    }

    const data: any = {
      name: formData.name.trim(),
      schedule: formData.schedule.trim(),
      message: formData.message.trim(),
      enabled: formData.enabled,
      deliver_response: formData.deliverResponse,
      max_retries: formData.enableRetry ? formData.maxRetries : 0,
      retry_delay: formData.retryDelay,
      delete_on_success: formData.deleteOnSuccess,
      link_context: formData.linkContext,
      // 空字符串表示改回跟随全局默认模型
      model_provider: formData.modelProvider.trim(),
      model_name: formData.modelName.trim(),
    }

    // 关闭推送时显式清空目标，避免后端保留旧渠道
    if (formData.deliverResponse && formData.channel === 'web') {
      data.channel = 'web'
      data.account_id = null
      data.chat_id = null
    } else if (formData.deliverResponse) {
      data.channel = formData.channel
      data.account_id = formData.accountId.trim() || 'default'
      data.chat_id = channelNeedsChatId.value
        ? formData.chatId.trim()
        : formData.channel
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
