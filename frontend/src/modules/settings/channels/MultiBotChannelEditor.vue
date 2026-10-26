<template>
  <div class="multi-bot-editor">
    <div class="config-section config-section-highlight">
      <div class="enable-toggle-wrapper">
        <div class="enable-toggle-content">
          <div class="enable-toggle-label">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
              <rect x="4.5" y="7" width="15" height="10.5" rx="4" fill="currentColor" opacity="0.16"></rect>
              <rect x="6.5" y="8.5" width="11" height="8" rx="3" stroke="currentColor" stroke-width="1.8"></rect>
              <path d="M10 6L8.5 4.5M14 6l1.5-1.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"></path>
              <circle cx="10" cy="12.5" r="1" fill="currentColor"></circle>
              <circle cx="14" cy="12.5" r="1" fill="currentColor"></circle>
              <path d="M10 15h4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"></path>
            </svg>
            <span class="enable-toggle-title">{{ enableTitle }}</span>
          </div>
          <p class="enable-toggle-hint">{{ enableHint }}</p>
        </div>
        <SwitchToggle
          v-model="channelEnabled"
          :width="52"
          :height="28"
          :aria-label="enableTitle"
        />
      </div>
      <div v-if="!channelEnabled" class="enable-warning">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
          <line x1="12" y1="9" x2="12" y2="13"></line>
          <line x1="12" y1="17" x2="12.01" y2="17"></line>
        </svg>
        <span>{{ disabledWarning }}</span>
      </div>
    </div>

    <div v-if="guide" class="guide-card">
      <div class="guide-header">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10"></circle>
          <line x1="12" y1="16" x2="12" y2="12"></line>
          <line x1="12" y1="8" x2="12.01" y2="8"></line>
        </svg>
        <span>{{ guide.title }}</span>
      </div>
      <div class="guide-row">
        <a
          :href="guide.linkHref"
          target="_blank"
          rel="noopener noreferrer"
          class="guide-link-button"
        >
          {{ guide.linkText }}
        </a>
        <span class="guide-inline-text">{{ guide.stepText }}</span>
      </div>
      <p class="guide-text">{{ guide.detailText }}</p>
    </div>

    <div class="bot-list">
      <div class="bot-item" :class="{ 'is-expanded': primaryExpanded }">
        <div
          class="bot-item-header"
          role="button"
          tabindex="0"
          :aria-expanded="primaryExpanded"
          @click="primaryExpanded = !primaryExpanded"
          @keydown.enter.prevent="primaryExpanded = !primaryExpanded"
          @keydown.space.prevent="primaryExpanded = !primaryExpanded"
        >
          <div class="bot-avatar" aria-hidden="true">
            <component :is="BotIcon" :size="20" />
          </div>
          <div class="bot-title">
            <div class="bot-name-row">
              <span class="bot-name">{{ getBotDisplayTitle(primaryBot, true) }}</span>
              <span class="bot-status" :class="getBotStatusClass(primaryBot)">
                {{ getBotStatusLabel(primaryBot) }}
              </span>
            </div>
            <span class="bot-meta">{{ t('settings.channels.multiBot.defaultAccount') }}</span>
          </div>
          <div class="bot-actions" @click.stop>
            <button
              type="button"
              class="bot-icon-button"
              :title="t('settings.channels.multiBot.testAccount')"
              :aria-label="t('settings.channels.multiBot.testAccount')"
              :disabled="!canTestAccount(primaryBot) || isTesting(primaryBot)"
              @click="handleTest(primaryBot)"
            >
              <component :is="PlayCircleIcon" :size="17" />
            </button>
            <SwitchToggle
              v-model="primaryBot.enabled"
              :width="40"
              :height="22"
              :aria-label="t('settings.channels.multiBot.enabled')"
              @change="handleChange"
            />
            <button
              type="button"
              class="bot-icon-button bot-chevron"
              :class="{ expanded: primaryExpanded }"
              :aria-label="primaryExpanded ? t('settings.channels.multiBot.collapseConfig') : t('settings.channels.multiBot.expandConfig')"
              @click="primaryExpanded = !primaryExpanded"
            >
              <component :is="ChevronDownIcon" :size="18" />
            </button>
          </div>
        </div>

        <div v-show="primaryExpanded" class="bot-item-body">
          <div v-if="getBotDeliveryError(primaryBot)" class="bot-delivery-error">
            <span class="bot-delivery-error-title">{{ t('settings.channels.deliveryError') }}</span>
            <span>{{ formatDeliveryError(getBotDeliveryError(primaryBot)) }}</span>
          </div>

          <div class="config-section">
            <label class="config-label">{{ t('settings.channels.multiBot.botName') }}</label>
            <input
              v-model="primaryBot.display_name"
              type="text"
              :placeholder="t('settings.channels.multiBot.primaryBotNamePlaceholder')"
              class="config-input"
              @input="handleChange"
            />
            <p class="config-hint">{{ t('settings.channels.multiBot.botNameHint') }}</p>
          </div>

          <slot
            name="fields"
            :model="primaryBot"
            :handleChange="handleChange"
            :botKey="primaryBot._draft_key"
            :isPrimary="true"
            :expanded="primaryExpanded"
          />

          <details class="advanced-group">
            <summary class="advanced-summary">
              <span class="advanced-summary-title">{{ t('settings.channels.routing.advancedTitle') }}</span>
              <span class="advanced-summary-hint">{{ t('settings.channels.routing.advancedHint') }}</span>
            </summary>

            <div class="advanced-group-body">
              <div class="config-section config-section-advanced">
                <label class="config-label">
                  {{ t('settings.channels.multiBot.internalAccountId') }}
                  <span class="advanced-badge">高级</span>
                </label>
                <input
                  type="text"
                  :value="primaryBot.draft_account_id"
                  :placeholder="t('settings.channels.multiBot.primaryAccountPlaceholder')"
                  class="config-input"
                  @input="updateDraftAccountId(primaryBot, ($event.target as HTMLInputElement).value)"
                  @blur="commitAccountId(primaryBot, 'default')"
                  @keydown.enter.prevent="commitAccountId(primaryBot, 'default')"
                />
                <p class="config-hint">{{ t('settings.channels.multiBot.internalAccountIdHint') }}</p>
              </div>

              <ChannelRouteConfig :model="primaryBot" @change="handleChange" />
            </div>
          </details>
        </div>
      </div>

      <div
        v-for="account in accounts"
        :key="account._draft_key"
        class="bot-item"
        :class="{ 'is-expanded': isAccountExpanded(account._draft_key) }"
      >
        <div
          class="bot-item-header"
          role="button"
          tabindex="0"
          :aria-expanded="isAccountExpanded(account._draft_key)"
          @click="toggleAccountExpanded(account._draft_key)"
          @keydown.enter.prevent="toggleAccountExpanded(account._draft_key)"
          @keydown.space.prevent="toggleAccountExpanded(account._draft_key)"
        >
          <div class="bot-avatar" aria-hidden="true">
            <component :is="BotIcon" :size="20" />
          </div>
          <div class="bot-title">
            <div class="bot-name-row">
              <span class="bot-name">{{ getBotDisplayTitle(account) }}</span>
              <span class="bot-status" :class="getBotStatusClass(account)">
                {{ getBotStatusLabel(account) }}
              </span>
            </div>
            <span class="bot-meta">
              {{ t('settings.channels.multiBot.internalAccountIdBadge', { id: account.account_id }) }}
            </span>
          </div>
          <div class="bot-actions" @click.stop>
            <button
              type="button"
              class="bot-icon-button"
              :title="t('settings.channels.multiBot.testAccount')"
              :aria-label="t('settings.channels.multiBot.testAccount')"
              :disabled="!canTestAccount(account) || isTesting(account)"
              @click="handleTest(account)"
            >
              <component :is="PlayCircleIcon" :size="17" />
            </button>
            <SwitchToggle
              v-model="account.enabled"
              :width="40"
              :height="22"
              :aria-label="t('settings.channels.multiBot.enabled')"
              @change="handleChange"
            />
            <button
              type="button"
              class="bot-icon-button bot-icon-button-danger"
              :title="t('common.delete')"
              :aria-label="t('common.delete')"
              @click="removeAccount(account._draft_key)"
            >
              <component :is="Trash2Icon" :size="17" />
            </button>
            <button
              type="button"
              class="bot-icon-button bot-chevron"
              :class="{ expanded: isAccountExpanded(account._draft_key) }"
              :aria-label="isAccountExpanded(account._draft_key) ? t('settings.channels.multiBot.collapseConfig') : t('settings.channels.multiBot.expandConfig')"
              @click="toggleAccountExpanded(account._draft_key)"
            >
              <component :is="ChevronDownIcon" :size="18" />
            </button>
          </div>
        </div>

        <div v-show="isAccountExpanded(account._draft_key)" class="bot-item-body">
          <div v-if="getBotDeliveryError(account)" class="bot-delivery-error">
            <span class="bot-delivery-error-title">{{ t('settings.channels.deliveryError') }}</span>
            <span>{{ formatDeliveryError(getBotDeliveryError(account)) }}</span>
          </div>

          <div class="config-section">
            <label class="config-label">{{ t('settings.channels.multiBot.botName') }}</label>
            <input
              v-model="account.display_name"
              type="text"
              :placeholder="t('settings.channels.multiBot.botNamePlaceholder')"
              class="config-input"
              @input="handleChange"
            />
          </div>

          <slot
            name="fields"
            :model="account"
            :handleChange="handleChange"
            :botKey="account._draft_key"
            :isPrimary="false"
            :expanded="isAccountExpanded(account._draft_key)"
          />

          <details class="advanced-group">
            <summary class="advanced-summary">
              <span class="advanced-summary-title">{{ t('settings.channels.routing.advancedTitle') }}</span>
              <span class="advanced-summary-hint">{{ t('settings.channels.routing.advancedHint') }}</span>
            </summary>

            <div class="advanced-group-body">
              <div class="config-section config-section-advanced">
                <label class="config-label">
                  {{ t('settings.channels.multiBot.internalAccountId') }}
                  <span class="advanced-badge">高级</span>
                </label>
                <input
                  type="text"
                  :value="account.draft_account_id"
                  :placeholder="t('settings.channels.multiBot.accountPlaceholder')"
                  class="config-input"
                  @input="updateDraftAccountId(account, ($event.target as HTMLInputElement).value)"
                  @blur="commitAccountId(account, 'bot')"
                  @keydown.enter.prevent="commitAccountId(account, 'bot')"
                />
              </div>

              <ChannelRouteConfig :model="account" @change="handleChange" />
            </div>
          </details>
        </div>
      </div>

      <button type="button" class="add-bot-row" @click="addAccount">
        <component :is="PlusIcon" :size="16" />
        <span>{{ t('settings.channels.multiBot.addAccount') }}</span>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { PropType } from 'vue'
import {
  Bot as BotIcon,
  ChevronDown as ChevronDownIcon,
  PlayCircle as PlayCircleIcon,
  Plus as PlusIcon,
  Trash2 as Trash2Icon
} from 'lucide-vue-next'
import SwitchToggle from '@/components/ui/SwitchToggle.vue'
import { useChannelsStore } from '@/store/channels'
import ChannelRouteConfig from './ChannelRouteConfig.vue'

interface GuideConfig {
  title: string
  linkText: string
  linkHref: string
  stepText: string
  detailText: string
}

interface EditorBotState extends Record<string, any> {
  _draft_key: string
  account_id: string
  draft_account_id: string
  enabled: boolean
}

const props = defineProps({
  channelId: {
    type: String,
    required: true
  },
  config: {
    type: Object as PropType<Record<string, any>>,
    required: true
  },
  createDefaultAccount: {
    type: Function as PropType<() => Record<string, any>>,
    required: true
  },
  enableTitle: {
    type: String,
    required: true
  },
  enableHint: {
    type: String,
    required: true
  },
  disabledWarning: {
    type: String,
    required: true
  },
  guide: {
    type: Object as PropType<GuideConfig | null>,
    default: null
  },
  canTest: {
    type: Function as PropType<(account: Record<string, any>) => boolean>,
    default: () => true
  },
  testingAccountId: {
    type: String as PropType<string | null>,
    default: null
  }
})

const emit = defineEmits<{
  update: [channelId: string, config: Record<string, any>]
  test: [channelId: string, config: Record<string, any>, accountId?: string]
}>()

const { t, te } = useI18n()
const channelsStore = useChannelsStore()

const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value ?? {}))

let botSeed = 0
const nextDraftKey = () => `bot-${Date.now()}-${botSeed++}`

const createBotState = (rawConfig: Record<string, any>, fallbackAccountId: string): EditorBotState => {
  const defaults = clone(props.createDefaultAccount())
  const accountId = String(rawConfig?.account_id || fallbackAccountId || 'default').trim() || fallbackAccountId
  const routingMode = String(rawConfig?.routing_mode ?? defaults.routing_mode ?? 'ai').trim().toLowerCase()

  return {
    ...defaults,
    ...clone(rawConfig || {}),
    display_name: String(rawConfig?.display_name ?? defaults.display_name ?? '').trim(),
    enabled: rawConfig?.enabled !== undefined ? Boolean(rawConfig.enabled) : Boolean(defaults.enabled),
    account_id: accountId,
    routing_mode: routingMode === 'direct' ? 'direct' : 'ai',
    external_coding_profile: String(
      rawConfig?.external_coding_profile ?? defaults.external_coding_profile ?? ''
    ).trim(),
    draft_account_id: accountId,
    _draft_key: nextDraftKey()
  }
}

const buildEditorState = (sourceConfig: Record<string, any>) => {
  const currentConfig = clone(sourceConfig || {})
  const accountsConfig = currentConfig.accounts || {}
  delete currentConfig.accounts

  const primary = createBotState(currentConfig, String(currentConfig.account_id || 'default'))
  const secondary = Object.entries(accountsConfig).map(([accountId, accountConfig]) =>
    createBotState({ ...(accountConfig as Record<string, any>), account_id: String(accountId) }, String(accountId))
  )

  return { primary, secondary }
}

const serializeComparableConfig = (sourceConfig: Record<string, any>) => {
  const normalized = clone(sourceConfig || {})
  const accounts = normalized.accounts || {}
  normalized.accounts = Object.fromEntries(
    Object.entries(accounts)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([accountId, accountConfig]) => [
        accountId,
        clone(accountConfig as Record<string, any>)
      ])
  )
  return JSON.stringify(normalized)
}

const initialState = buildEditorState(props.config)
const primaryBot = ref<EditorBotState>(initialState.primary)
const accounts = ref<EditorBotState[]>(initialState.secondary)
const primaryExpanded = ref(true)
const accountExpandedState = ref<Record<string, boolean>>({})

const syncAccountExpandedState = (items: EditorBotState[]) => {
  const next: Record<string, boolean> = {}
  for (const account of items) {
    next[account._draft_key] = accountExpandedState.value[account._draft_key] ?? false
  }
  accountExpandedState.value = next
}

syncAccountExpandedState(accounts.value)

const channelEnabled = computed({
  get: () => primaryBot.value.enabled || accounts.value.some((account) => account.enabled),
  set: (enabled: boolean) => {
    if (!enabled) {
      primaryBot.value.enabled = false
      accounts.value.forEach((account) => {
        account.enabled = false
      })
      handleChange()
      return
    }

    if (!primaryBot.value.enabled && !accounts.value.some((account) => account.enabled)) {
      primaryBot.value.enabled = true
      handleChange()
    }
  }
})

const listCommittedAccountIds = (excludeDraftKey?: string) => {
  const ids = new Set<string>()
  if (primaryBot.value._draft_key !== excludeDraftKey) {
    ids.add(primaryBot.value.account_id)
  }
  for (const account of accounts.value) {
    if (account._draft_key !== excludeDraftKey) {
      ids.add(account.account_id)
    }
  }
  return ids
}

const getUniqueAccountId = (rawValue: string, fallback: string, excludeDraftKey?: string) => {
  const baseValue = String(rawValue || '').trim() || fallback
  const occupied = listCommittedAccountIds(excludeDraftKey)
  if (!occupied.has(baseValue)) {
    return baseValue
  }

  let index = 2
  let candidate = `${baseValue}-${index}`
  while (occupied.has(candidate)) {
    index += 1
    candidate = `${baseValue}-${index}`
  }
  return candidate
}

const serializeBot = (bot: EditorBotState) => {
  const serialized = clone(bot)
  const { _draft_key, draft_account_id, ...rest } = serialized
  return rest
}

const buildConfig = () => {
  const primary = serializeBot(primaryBot.value)
  const secondary = Object.fromEntries(
    accounts.value.map((account) => [account.account_id, serializeBot(account)])
  )

  return {
    ...primary,
    accounts: secondary
  }
}

watch(
  () => props.config,
  (nextConfig) => {
    const incomingConfig = serializeComparableConfig(nextConfig || {})
    const currentConfig = serializeComparableConfig(buildConfig())
    if (incomingConfig === currentConfig) {
      return
    }

    const nextState = buildEditorState(nextConfig || {})
    primaryBot.value = nextState.primary
    accounts.value = nextState.secondary
    syncAccountExpandedState(accounts.value)
  },
  { deep: true }
)

const handleChange = () => {
  emit('update', props.channelId, buildConfig())
}

const canTestAccount = (account: EditorBotState) => props.canTest(account)

const getBotDisplayTitle = (account: EditorBotState, isPrimary = false) =>
  String(account.display_name || '').trim() || (
    isPrimary
      ? t('settings.channels.multiBot.primaryTitle')
      : account.account_id
  )

const getAccountInstance = (accountId: string) =>
  channelsStore.status[props.channelId]?.instances?.[accountId] || null

const getBotStatusLabel = (account: EditorBotState) => {
  const instance = getAccountInstance(account.account_id)
  const state = String(instance?.runtime_status?.state || '').trim()
  const stateKey = `settings.channels.runtimeState.${state}`
  if (state && te(stateKey)) {
    return t(stateKey)
  }
  if (instance?.running) {
    return t('settings.channels.running')
  }
  return account.enabled
    ? t('settings.channels.multiBot.statusEnabled')
    : t('settings.channels.multiBot.statusDisabled')
}

const getBotStatusClass = (account: EditorBotState) => {
  const instance = getAccountInstance(account.account_id)
  const state = String(instance?.runtime_status?.state || '').trim()
  if (state === 'failed') return 'failed'
  if (state === 'running' || instance?.running) return 'running'
  if (state === 'starting' || state === 'connecting' || state === 'stopping') return 'enabled'
  return account.enabled ? 'enabled' : 'stopped'
}

const getBotDeliveryError = (account: EditorBotState) =>
  getAccountInstance(account.account_id)?.runtime_status?.delivery_error || null

const formatDeliveryError = (detail: Record<string, any>) => {
  const parts = [
    detail.operation,
    detail.status ? `HTTP ${detail.status}` : '',
    detail.code !== undefined && detail.code !== null ? `code=${detail.code}` : '',
    detail.msg || detail.error || '',
    detail.log_id ? `log_id=${detail.log_id}` : ''
  ].filter(Boolean)
  return parts.join(' · ')
}

const updateDraftAccountId = (account: EditorBotState, value: string) => {
  account.draft_account_id = value
}

const commitAccountId = (account: EditorBotState, fallback: string) => {
  const nextAccountId = getUniqueAccountId(account.draft_account_id, fallback, account._draft_key)
  account.account_id = nextAccountId
  account.draft_account_id = nextAccountId
  handleChange()
}

const addAccount = () => {
  const nextAccountId = getUniqueAccountId('', 'bot')
  const nextAccount = createBotState(
    {
      ...props.createDefaultAccount(),
      enabled: true,
      account_id: nextAccountId
    },
    nextAccountId
  )
  accounts.value.push(nextAccount)
  accountExpandedState.value = {
    ...accountExpandedState.value,
    [nextAccount._draft_key]: true
  }
  handleChange()
}

const removeAccount = (draftKey: string) => {
  accounts.value = accounts.value.filter((account) => account._draft_key !== draftKey)
  syncAccountExpandedState(accounts.value)
  handleChange()
}

const isTesting = (account: EditorBotState) => props.testingAccountId === account.account_id

const handleTest = (account: EditorBotState) => {
  emit('test', props.channelId, buildConfig(), account.account_id)
}

const isAccountExpanded = (draftKey: string) => accountExpandedState.value[draftKey] ?? false

const toggleAccountExpanded = (draftKey: string) => {
  accountExpandedState.value = {
    ...accountExpandedState.value,
    [draftKey]: !isAccountExpanded(draftKey)
  }
}
</script>
<style scoped>
@import './styles/MultiBotChannelEditor.css';
</style>
