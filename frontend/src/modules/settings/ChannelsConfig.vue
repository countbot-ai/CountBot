<template>
  <div class="channels-config">
    <div class="section-header">
      <div class="header-top">
        <h3 class="section-title">
          {{ t('settings.channels.title') }}
        </h3>
        <div class="header-actions">
          <a
            href="https://654321.ai/docs/getting-started/ChannelConfig"
            target="_blank"
            rel="noopener noreferrer"
            class="action-btn btn-secondary"
            title="打开渠道配置教程"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M14 3h7v7"></path>
              <path d="M10 14L21 3"></path>
              <path d="M21 14v6a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h6"></path>
            </svg>
            <span>配置教程</span>
          </a>
          <button @click="channelsStore.fetchStatus()" class="action-btn btn-secondary" :title="t('common.refresh')">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2"/>
            </svg>
          </button>
        </div>
      </div>
      <p class="section-desc">
        {{ t('settings.channels.description') }}
      </p>
      <div class="status-summary">
        <div class="status-item">
          <span class="status-dot running"></span>
          <span class="status-text">{{ channelsStore.runningChannels.length }} {{ t('settings.channels.running') }}</span>
        </div>
        <div class="status-divider"></div>
        <div class="status-item">
          <span class="status-dot enabled"></span>
          <span class="status-text">{{ channelsStore.enabledChannels.length }} {{ t('settings.channels.enabled') }}</span>
        </div>
      </div>
    </div>

    <!-- 重启提示 -->
    <div v-if="configChanged" class="restart-notice">
      <div class="notice-icon">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
          <line x1="12" y1="9" x2="12" y2="13"></line>
          <line x1="12" y1="17" x2="12.01" y2="17"></line>
        </svg>
      </div>
      <div class="notice-content">
        <strong>{{ t('settings.channels.configUpdated') }}</strong>
        <p>{{ t('settings.channels.restartNotice') }}</p>
      </div>
      <button @click="configChanged = false" class="notice-close">
        <svg width="16" height="16" viewBox="0 0 20 20" fill="currentColor">
          <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"/>
        </svg>
      </button>
    </div>

    <div v-if="channelsStore.loading" class="loading-state">
      <div class="spinner"></div>
      <p>{{ t('common.loading') }}</p>
    </div>

    <div v-else-if="channelsStore.error" class="error-state">
      <div class="error-icon">⚠️</div>
      <p>{{ channelsStore.error }}</p>
      <button @click="channelsStore.fetchChannels()" class="retry-button">
        {{ t('common.retry') }}
      </button>
    </div>

    <div v-else class="channels-grid">
      <div
        v-for="(channel, id) in sortedChannels"
        :key="id"
        class="channel-card"
        :class="{ 
          'is-enabled': channel.enabled, 
          'is-running': isRunning(id),
          'is-expanded': expandedChannel === id,
          'is-recommended': isRecommended(id),
          'is-implemented': isImplemented(id),
          'is-planned': isPlanned(id)
        }"
      >
        <!-- 卡片头部 -->
        <div class="card-header" @click="toggleChannelConfig(id)">
          <div class="channel-icon-box" :class="`icon-${id}`">
            <div class="icon-inner" v-html="getChannelIcon(id)"></div>
          </div>
          
          <div class="channel-meta">
            <div class="channel-name">
              <h4>{{ getChannelDisplayName(id, channel.name) }}</h4>
              <span v-if="isRunning(id)" class="badge badge-success">
                <span class="pulse-dot"></span>
                {{ t('settings.channels.running') }}
              </span>
              <span v-else-if="channel.enabled" class="badge badge-primary">
                {{ t('settings.channels.enabled') }}
              </span>
              <span v-else class="badge badge-secondary">
                {{ t('settings.channels.disabled') }}
              </span>
            </div>
            <p class="channel-desc">{{ getChannelDisplayDescription(id, channel.description) }}</p>
          </div>

          <button class="expand-btn" :class="{ 'is-expanded': expandedChannel === id }">
            <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor">
              <path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd"/>
            </svg>
          </button>
        </div>

        <!-- 配置面板 -->
        <transition name="slide-down">
          <div v-show="expandedChannel === id" class="card-body">
            <div class="card-body-inner">
              <div v-if="getChannelInstances(id).length" class="instance-status-panel">
                <div class="instance-status-header">
                  <h5>{{ translateOr('settings.channels.multiBot.instanceStatusTitle', '账号运行状态') }}</h5>
                  <span class="instance-status-summary">
                    {{ getChannelInstances(id).length }} {{ translateOr('settings.channels.multiBot.instanceCount', '个账号') }}
                  </span>
                </div>
                <div class="instance-status-list">
                  <div
                    v-for="instance in getChannelInstances(id)"
                    :key="instance.instance_key"
                    class="instance-status-item"
                    :class="{ 'is-running': instance.running }"
                  >
                    <div class="instance-status-avatar" aria-hidden="true">
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                        <rect x="5" y="7" width="14" height="10" rx="4" fill="currentColor" opacity="0.16"></rect>
                        <rect x="7" y="9" width="10" height="8" rx="3" stroke="currentColor" stroke-width="1.8"></rect>
                        <path d="M10 6L8.5 4.5M14 6l1.5-1.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"></path>
                        <circle cx="10" cy="13" r="1" fill="currentColor"></circle>
                        <circle cx="14" cy="13" r="1" fill="currentColor"></circle>
                        <path d="M10 15.5h4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"></path>
                      </svg>
                    </div>
                    <div class="instance-status-main">
                      <span class="instance-display-name">{{ getInstanceDisplayName(instance) }}</span>
                      <span class="instance-account-id">{{ getInstanceMeta(instance) }}</span>
                    </div>
                    <span
                      class="instance-status-badge"
                      :class="instance.running ? 'running' : (instance.enabled ? 'enabled' : 'stopped')"
                    >
                      {{
                        instance.running
                          ? t('settings.channels.running')
                          : (instance.enabled
                              ? t('settings.channels.enabled')
                              : translateOr('settings.channels.multiBot.instanceStopped', '未运行'))
                      }}
                    </span>
                  </div>
                </div>
              </div>

              <!-- 已实现渠道 -->
              <template v-if="isImplemented(id)">
                <TelegramConfig
                  v-if="id === 'telegram'"
                  :channel-id="id"
                  :config="channel.config"
                  :testing-account-id="activeTestTarget?.channelId === id ? activeTestTarget.accountId : null"
                  @update="handleConfigUpdate"
                  @test="handleTest"
                />
                <QQConfig
                  v-else-if="id === 'qq'"
                  :channel-id="id"
                  :config="channel.config"
                  :testing-account-id="activeTestTarget?.channelId === id ? activeTestTarget.accountId : null"
                  @update="handleConfigUpdate"
                  @test="handleTest"
                />
                <WeChatConfig
                  v-else-if="id === 'wechat'"
                  :channel-id="id"
                  :config="channel.config"
                  :testing-account-id="activeTestTarget?.channelId === id ? activeTestTarget.accountId : null"
                  @update="handleConfigUpdate"
                  @test="handleTest"
                />
                <DingTalkConfig
                  v-else-if="id === 'dingtalk'"
                  :channel-id="id"
                  :config="channel.config"
                  :testing-account-id="activeTestTarget?.channelId === id ? activeTestTarget.accountId : null"
                  @update="handleConfigUpdate"
                  @test="handleTest"
                />
                <FeishuConfig
                  v-else-if="id === 'feishu'"
                  :channel-id="id"
                  :config="channel.config"
                  :testing-account-id="activeTestTarget?.channelId === id ? activeTestTarget.accountId : null"
                  @update="handleConfigUpdate"
                  @test="handleTest"
                />
                <WeComConfig
                  v-else-if="id === 'wecom'"
                  :channel-id="id"
                  :config="channel.config"
                  :testing-account-id="activeTestTarget?.channelId === id ? activeTestTarget.accountId : null"
                  @update="handleConfigUpdate"
                  @test="handleTest"
                />
                <XiaozhiConfig
                  v-else-if="id === 'xiaozhi'"
                  :channel-id="id"
                  :config="channel.config"
                  :testing-account-id="activeTestTarget?.channelId === id ? activeTestTarget.accountId : null"
                  @update="handleConfigUpdate"
                  @test="handleTest"
                />
                <WeiboConfig
                  v-else-if="id === 'weibo'"
                  :channel-id="id"
                  :config="channel.config"
                  :testing-account-id="activeTestTarget?.channelId === id ? activeTestTarget.accountId : null"
                  @update="handleConfigUpdate"
                  @test="handleTest"
                />
                <DiscordConfig
                  v-else-if="id === 'discord'"
                  :channel-id="id"
                  :config="channel.config"
                  @update="handleConfigUpdate"
                  @test="handleTest"
                />
              </template>
              <!-- 计划中渠道 -->
              <div v-else class="planned-notice">
                <div class="planned-icon">
                  <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="10"></circle>
                    <line x1="12" y1="8" x2="12" y2="12"></line>
                    <line x1="12" y1="16" x2="12.01" y2="16"></line>
                  </svg>
                </div>
                <h4>{{ t('settings.channels.comingSoon') }}</h4>
                <p>{{ t('settings.channels.comingSoonDesc', { channel: getChannelDisplayName(id, channel.name) }) }}</p>
              </div>
            </div>
          </div>
        </transition>
      </div>
    </div>

    <!-- 测试结果对话框 -->
    <transition name="modal">
      <div v-if="testResult" class="test-result-modal" @click="testResult = null">
        <div class="test-result-content" @click.stop>
          <div class="test-result-header">
            <div class="header-icon-wrapper" :class="testResult.success ? 'success' : 'error'">
              <svg v-if="testResult.success" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
                <polyline points="22 4 12 14.01 9 11.01"></polyline>
              </svg>
              <svg v-else width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"></circle>
                <line x1="15" y1="9" x2="9" y2="15"></line>
                <line x1="9" y1="9" x2="15" y2="15"></line>
              </svg>
            </div>
            <div class="header-text">
              <h4>
                {{ testResult.success ? t('settings.channels.testSuccess') : t('settings.channels.testFailed') }}
              </h4>
              <p class="test-message">{{ testResult.message }}</p>
            </div>
            <button @click="testResult = null" class="close-button">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"/>
              </svg>
            </button>
          </div>
          <div v-if="testResult.data" class="test-result-body">
            <div class="result-info">
              <div v-if="testResult.data.app_id || testResult.data.client_id || testResult.data.username" class="info-item">
                <span class="info-label">ID:</span>
                <span class="info-value">{{ testResult.data.username ? `@${testResult.data.username}` : (testResult.data.app_id || testResult.data.client_id) }}</span>
              </div>
              <div v-if="testResult.data.status" class="info-item">
                <span class="info-label">{{ t('app.status') }}:</span>
                <span class="info-value status-badge" :class="testResult.data.status">
                  {{ testResult.data.status === 'connected' ? t('settings.channels.credentialsVerified') : 
                     testResult.data.status === 'configured' ? t('settings.channels.configValidated') : 
                     testResult.data.status }}
                </span>
              </div>
              <div v-if="testResult.data.note" class="info-note">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <circle cx="12" cy="12" r="10"></circle>
                  <line x1="12" y1="16" x2="12" y2="12"></line>
                  <line x1="12" y1="8" x2="12.01" y2="8"></line>
                </svg>
                <span>{{ testResult.data.note }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useChannelsStore } from '@/store/channels'
import { useToast } from '@/composables/useToast'
import TelegramConfig from './channels/TelegramConfig.vue'
import DiscordConfig from './channels/DiscordConfig.vue'
import QQConfig from './channels/QQConfig.vue'
import WeChatConfig from './channels/WeChatConfig.vue'
import DingTalkConfig from './channels/DingTalkConfig.vue'
import FeishuConfig from './channels/FeishuConfig.vue'
import WeComConfig from './channels/WeComConfig.vue'
import XiaozhiConfig from './channels/XiaozhiConfig.vue'
import WeiboConfig from './channels/WeiboConfig.vue'
import type { ChannelInstanceStatus } from '@/store/channels'

const { t, te } = useI18n()
const channelsStore = useChannelsStore()
const toast = useToast()

const expandedChannel = ref<string | null>(null)
const testResult = ref<any>(null)
const configChanged = ref(false)
const activeTestTarget = ref<{ channelId: string; accountId: string | null } | null>(null)

// 推荐的渠道（优先显示）
const recommendedChannels = ['feishu', 'wecom', 'wechat', 'xiaozhi', 'qq', 'dingtalk']

// 已实现的渠道
const implementedChannels = ['feishu', 'wecom', 'wechat', 'xiaozhi', 'qq', 'dingtalk', 'telegram', 'weibo']

// 计划中的渠道
const plannedChannels = ['discord']

// 排序渠道：已实现的在前，计划中的在后
const sortedChannels = computed(() => {
  const channels = channelsStore.channels
  const sorted: Record<string, any> = {}
  
  // 先添加已实现的渠道（按推荐顺序）
  implementedChannels.forEach(id => {
    if (channels[id]) {
      sorted[id] = channels[id]
    }
  })
  
  // 再添加计划中的渠道
  plannedChannels.forEach(id => {
    if (channels[id]) {
      sorted[id] = channels[id]
    }
  })
  
  return sorted
})

const isImplemented = (channelId: string) => {
  return implementedChannels.includes(channelId)
}

const isPlanned = (channelId: string) => {
  return plannedChannels.includes(channelId)
}

const isRecommended = (channelId: string) => {
  return recommendedChannels.includes(channelId)
}

const isRunning = (channelId: string) => {
  const status = channelsStore.status[channelId]
  return status && status.running
}

const getChannelInstances = (channelId: string): Array<ChannelInstanceStatus & { account_id: string; channel_id: string }> => {
  const statusInstances = channelsStore.status[channelId]?.instances || {}
  const config = channelsStore.channels[channelId]?.config || {}
  const merged = new Map<string, ChannelInstanceStatus & { account_id: string; channel_id: string }>()

  const hasConfiguredFields = (account: Record<string, any>) =>
    Object.entries(account || {}).some(([key, value]) => {
      if (['enabled', 'allow_from', 'account_id', 'draft_account_id', 'accounts'].includes(key)) {
        return false
      }
      if (Array.isArray(value)) {
        return value.length > 0
      }
      return Boolean(value)
    })

  const upsertInstance = (accountId: string, account: Record<string, any>, fromStatus = false) => {
    const existing = merged.get(accountId)
    const configured = hasConfiguredFields(account)
    if (!configured && !account.enabled && !fromStatus) {
      return
    }

    merged.set(accountId, {
      channel_id: channelId,
      account_id: accountId,
      enabled: account.enabled ?? existing?.enabled ?? false,
      running: account.running ?? existing?.running ?? false,
      display_name:
        account.display_name ||
        existing?.display_name ||
        '',
      instance_key: account.instance_key || existing?.instance_key || `${channelId}:${accountId}`
    })
  }

  const primaryAccountId = String(config.account_id || 'default')
  upsertInstance(primaryAccountId, config)

  Object.entries(config.accounts || {}).forEach(([accountId, account]) => {
    upsertInstance(accountId, account as Record<string, any>)
  })

  Object.entries(statusInstances).forEach(([accountId, instance]) => {
    upsertInstance(accountId, instance as Record<string, any>, true)
  })

  return Array.from(merged.values()).sort((left, right) => {
    if (left.account_id === 'default') return -1
    if (right.account_id === 'default') return 1
    return left.account_id.localeCompare(right.account_id)
  })
}

const getChannelDisplayName = (channelId: string, fallback: string) => {
  const key = `settings.channels.catalog.${channelId}.name`
  return te(key) ? t(key) : fallback
}

const getChannelDisplayDescription = (channelId: string, fallback: string) => {
  const key = `settings.channels.catalog.${channelId}.description`
  return te(key) ? t(key) : fallback
}

const translateOr = (key: string, fallback: string) => (te(key) ? t(key) : fallback)

const formatInternalAccountId = (accountId: string) =>
  te('settings.channels.multiBot.internalAccountIdBadge')
    ? t('settings.channels.multiBot.internalAccountIdBadge', { id: accountId })
    : `内部ID：${accountId}`

const getInstanceDisplayName = (instance: ChannelInstanceStatus & { account_id: string; channel_id: string }) => {
  const explicitName = String(instance.display_name || '').trim()
  const channelName = String(getChannelDisplayName(instance.channel_id, instance.channel_id)).trim().toLowerCase()
  // 渠道名不适合当机器人名展示，空名时走统一兜底。
  if (explicitName && explicitName.trim().toLowerCase() !== channelName) {
    return explicitName
  }

  if (instance.account_id === 'default') {
    return translateOr('settings.channels.multiBot.primaryTitle', '主机器人')
  }

  return te('settings.channels.multiBot.botLabelWithId')
    ? t('settings.channels.multiBot.botLabelWithId', { id: instance.account_id })
    : `机器人 ${instance.account_id}`
}

const getInstanceMeta = (instance: ChannelInstanceStatus & { account_id: string; channel_id: string }) => {
  // 默认账号显示更友好的说明，其他账号保留内部 ID。
  if (instance.account_id === 'default') {
    return translateOr('settings.channels.multiBot.defaultAccount', '默认账号')
  }
  return formatInternalAccountId(instance.account_id)
}

const toggleChannelConfig = (channelId: string) => {
  expandedChannel.value = expandedChannel.value === channelId ? null : channelId
}

const getChannelIcon = (channelId: string) => {
  const icons: Record<string, string> = {
    telegram: `<svg t="1770777159632" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="10792" width="200" height="200"><path d="M679.424 746.862l84.005-395.996c7.424-34.852-12.581-48.567-35.438-40.009L234.277 501.138c-33.72 13.13-33.134 32-5.706 40.558l126.282 39.424 293.156-184.576c13.714-9.143 26.295-3.986 16.018 5.157L426.898 615.973l-9.143 130.304c13.13 0 18.871-5.706 25.71-12.581l61.696-59.429 128 94.282c23.442 13.129 40.01 6.29 46.3-21.724zM1024 512c0 282.843-229.157 512-512 512S0 794.843 0 512 229.157 0 512 0s512 229.157 512 512z" fill="#1296DB" p-id="10793"></path></svg>`,
    discord: `<svg t="1770777174043" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="11772" width="200" height="200"><path d="M0 512a512 512 0 1 0 1024 0A512 512 0 1 0 0 512z" fill="#738BD8" p-id="11773"></path><path d="M190.915 234.305h642.169v477.288H190.915z" fill="#FFFFFF" p-id="11774"></path><path d="M698.157 932.274L157.288 862.85c-58.43-7.5-55.4-191.167-50.26-249.853l26.034-297.22c5.14-58.686 74.356-120.22 132.7-128.362l466.441-65.085c58.346-8.14 177.24 212.65 176.09 271.548l-8.677 445.108M512 300.373c-114.347 0-194.56 49.067-194.56 49.067 43.947-39.253 120.747-61.867 120.747-61.867l-7.254-7.253c-72.106 1.28-137.386 51.2-137.386 51.2-73.387 153.173-68.694 285.44-68.694 285.44 59.734 77.227 148.48 71.68 148.48 71.68l30.294-38.4c-53.334-11.52-87.04-58.88-87.04-58.88S396.8 645.973 512 645.973c115.2 0 195.413-54.613 195.413-54.613s-33.706 47.36-87.04 58.88l30.294 38.4s88.746 5.547 148.48-71.68c0 0 4.693-132.267-68.694-285.44 0 0-65.28-49.92-137.386-51.2l-7.254 7.253s76.8 22.614 120.747 61.867c0 0-80.213-49.067-194.56-49.067M423.68 462.08c27.733 0 50.347 24.32 49.92 54.187 0 29.44-22.187 54.186-49.92 54.186-27.307 0-49.493-24.746-49.493-54.186 0-29.867 21.76-54.187 49.493-54.187m177.92 0c27.733 0 49.92 24.32 49.92 54.187 0 29.44-22.187 54.186-49.92 54.186-27.307 0-49.493-24.746-49.493-54.186 0-29.867 21.76-54.187 49.493-54.187z" fill="#738BD8" p-id="11775"></path></svg>`,
    qq: `<svg t="1770777134598" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="9780" width="200" height="200"><path d="M511.09761 957.257c-80.159 0-153.737-25.019-201.11-62.386-24.057 6.702-54.831 17.489-74.252 30.864-16.617 11.439-14.546 23.106-11.55 27.816 13.15 20.689 225.583 13.211 286.912 6.767v-3.061z" fill="#FAAD08" p-id="9781"></path><path d="M496.65061 957.257c80.157 0 153.737-25.019 201.11-62.386 24.057 6.702 54.83 17.489 74.253 30.864 16.616 11.439 14.543 23.106 11.55 27.816-13.15 20.689-225.584 13.211-286.914 6.767v-3.061z" fill="#FAAD08" p-id="9782"></path><path d="M497.12861 474.524c131.934-0.876 237.669-25.783 273.497-35.34 8.541-2.28 13.11-6.364 13.11-6.364 0.03-1.172 0.542-20.952 0.542-31.155C784.27761 229.833 701.12561 57.173 496.64061 57.162 292.15661 57.173 209.00061 229.832 209.00061 401.665c0 10.203 0.516 29.983 0.547 31.155 0 0 3.717 3.821 10.529 5.67 33.078 8.98 140.803 35.139 276.08 36.034h0.972z" fill="#000000" p-id="9783"></path><path d="M860.28261 619.782c-8.12-26.086-19.204-56.506-30.427-85.72 0 0-6.456-0.795-9.718 0.148-100.71 29.205-222.773 47.818-315.792 46.695h-0.962C410.88561 582.017 289.65061 563.617 189.27961 534.698 185.44461 533.595 177.87261 534.063 177.87261 534.063 166.64961 563.276 155.56661 593.696 147.44761 619.782 108.72961 744.168 121.27261 795.644 130.82461 796.798c20.496 2.474 79.78-93.637 79.78-93.637 0 97.66 88.324 247.617 290.576 248.996a718.01 718.01 0 0 1 5.367 0C708.80161 950.778 797.12261 800.822 797.12261 703.162c0 0 59.284 96.111 79.783 93.637 9.55-1.154 22.093-52.63-16.623-177.017" fill="#000000" p-id="9784"></path><path d="M434.38261 316.917c-27.9 1.24-51.745-30.106-53.24-69.956-1.518-39.877 19.858-73.207 47.764-74.454 27.875-1.224 51.703 30.109 53.218 69.974 1.527 39.877-19.853 73.2-47.742 74.436m206.67-69.956c-1.494 39.85-25.34 71.194-53.24 69.956-27.888-1.238-49.269-34.559-47.742-74.435 1.513-39.868 25.341-71.201 53.216-69.974 27.909 1.247 49.285 34.576 47.767 74.453" fill="#FFFFFF" p-id="9785"></path><path d="M683.94261 368.627c-7.323-17.609-81.062-37.227-172.353-37.227h-0.98c-91.29 0-165.031 19.618-172.352 37.227a6.244 6.244 0 0 0-0.535 2.505c0 1.269 0.393 2.414 1.006 3.386 6.168 9.765 88.054 58.018 171.882 58.018h0.98c83.827 0 165.71-48.25 171.881-58.016a6.352 6.352 0 0 0 1.002-3.395c0-0.897-0.2-1.736-0.531-2.498" fill="#FAAD08" p-id="9786"></path><path d="M467.63161 256.377c1.26 15.886-7.377 30-19.266 31.542-11.907 1.544-22.569-10.083-23.836-25.978-1.243-15.895 7.381-30.008 19.25-31.538 11.927-1.549 22.607 10.088 23.852 25.974m73.097 7.935c2.533-4.118 19.827-25.77 55.62-17.886 9.401 2.07 13.75 5.116 14.668 6.316 1.355 1.77 1.726 4.29 0.352 7.684-2.722 6.725-8.338 6.542-11.454 5.226-2.01-0.85-26.94-15.889-49.905 6.553-1.579 1.545-4.405 2.074-7.085 0.242-2.678-1.834-3.786-5.553-2.196-8.135" fill="#000000" p-id="9787"></path><path d="M504.33261 584.495h-0.967c-63.568 0.752-140.646-7.504-215.286-21.92-6.391 36.262-10.25 81.838-6.936 136.196 8.37 137.384 91.62 223.736 220.118 224.996H506.48461c128.498-1.26 211.748-87.612 220.12-224.996 3.314-54.362-0.547-99.938-6.94-136.203-74.654 14.423-151.745 22.684-215.332 21.927" fill="#FFFFFF" p-id="9788"></path><path d="M323.27461 577.016v137.468s64.957 12.705 130.031 3.91V591.59c-41.225-2.262-85.688-7.304-130.031-14.574" fill="#EB1C26" p-id="9789"></path><path d="M788.09761 432.536s-121.98 40.387-283.743 41.539h-0.962c-161.497-1.147-283.328-41.401-283.744-41.539l-40.854 106.952c102.186 32.31 228.837 53.135 324.598 51.926l0.96-0.002c95.768 1.216 222.4-19.61 324.6-51.924l-40.855-106.952z" fill="#EB1C26" p-id="9790"></path></svg>`,
    xiaozhi: `<svg t="1773731826147" class="icon" viewBox="0 0 1095 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="7944" width="200" height="200"><path d="M606.082246 72.596211l-216.459228-32.336843 89.824561-40.259368 216.477193 32.336842-89.824561 40.259369z" fill="#CECEF9" p-id="7945"></path><path d="M389.640982 40.259368v98.088421l89.824562-40.277333v-98.088421l-89.824562 40.277333z" fill="#CECEF9" p-id="7946"></path><path d="M389.640982 138.329825l64.925193 9.701052 89.824562-40.241403-64.925193-9.719018-89.824562 40.259369z" fill="#CECEF9" p-id="7947"></path><path d="M454.566175 148.030877v49.044211l89.824562-40.259369v-49.04421l-89.824562 40.259368z" fill="#CECEF9" p-id="7948"></path><path d="M454.566175 197.075088L129.886316 148.569825l89.824561-40.277334 324.697825 48.505263-89.824562 40.277334z" fill="#CECEF9" p-id="7949"></path><path d="M129.886316 148.569825v760.095438l89.824561-40.241403V108.274526l-89.824561 40.277334z" fill="#CECEF9" p-id="7950"></path><path d="M129.886316 908.665263l735.950596 109.981193 89.824562-40.259368-735.950597-109.981193-89.824561 40.277333z" fill="#CECEF9" p-id="7951"></path><path d="M865.836912 1018.646456v-760.095438l89.824562-40.277334v760.095439l-89.824562 40.277333zM865.836912 258.533053l-324.679859-48.505264 89.824561-40.277333 324.67986 48.505263-89.824562 40.277334z" fill="#CECEF9" p-id="7952"></path><path d="M541.157053 210.009825V160.965614l89.824561-40.241403v49.026245l-89.824561 40.259369z" fill="#CECEF9" p-id="7953"></path><path d="M541.157053 160.965614l64.925193 9.701053 89.824561-40.241404-64.925193-9.701052-89.824561 40.241403z" fill="#CECEF9" p-id="7954"></path><path d="M606.082246 170.684632v-98.088421l89.824561-40.259369v98.088421l-89.824561 40.259369zM606.082246 72.596211l89.824561-40.259369-89.824561 40.259369zM216.459228 823.529544V259.592982l89.824561-40.259368V783.270175l-89.824561 40.259369z" fill="#CECEF9" p-id="7955"></path><path d="M216.459228 259.592982l562.786807 84.07579 89.824561-40.259368-562.786807-84.093755-89.824561 40.259369zM779.264 343.668772v563.972491l89.824561-40.277333V303.427368l-89.824561 40.277334z" fill="#CECEF9" p-id="7956"></path><path d="M779.246035 907.641263L216.477193 823.511579l89.824561-40.259368 562.786807 84.093754-89.824561 40.277333zM216.459228 823.529544l89.824561-40.259369-89.824561 40.259369zM0 374.352842v269.725193l89.824561-40.277333V334.093474l-89.824561 40.259368z" fill="#CECEF9" p-id="7957"></path><path d="M0 644.078035l86.590877 12.934737 89.824562-40.277333L89.824561 603.800702l-89.824561 40.277333z" fill="#CECEF9" p-id="7958"></path><path d="M86.590877 657.012772V387.287579l89.824562-40.259368V616.735439l-89.824562 40.241403z" fill="#CECEF9" p-id="7959"></path><path d="M86.590877 387.287579L0 374.352842l89.824561-40.259368 86.590878 12.934737-89.824562 40.259368zM0 374.352842l89.824561-40.259368-89.824561 40.259368zM909.132351 510.203509v269.725193l89.824561-40.277334V469.962105l-89.824561 40.259369z" fill="#CECEF9" p-id="7960"></path><path d="M909.132351 779.928702l86.590877 12.934737 89.824561-40.277334-86.590877-12.934737-89.824561 40.277334z" fill="#CECEF9" p-id="7961"></path><path d="M995.723228 792.863439V523.138246l89.824561-40.259369v269.707228l-89.824561 40.277334z" fill="#CECEF9" p-id="7962"></path><path d="M995.723228 523.138246l-86.590877-12.934737 89.824561-40.259369 86.590877 12.934737-89.824561 40.259369zM909.132351 510.203509l89.824561-40.259369-89.824561 40.259369zM432.918456 512.610807l-108.220631-16.168421 89.824561-40.277333 108.220632 16.168421-89.824562 40.259368z" fill="#CECEF9" p-id="7963"></path><path d="M324.697825 496.424421v122.610526l89.824561-40.277333v-122.592561l-89.824561 40.259368z" fill="#CECEF9" p-id="7964"></path><path d="M324.697825 619.034947l108.220631 16.168421 89.824562-40.259368-108.220632-16.168421-89.824561 40.241403z" fill="#CECEF9" p-id="7965"></path><path d="M432.918456 635.203368v-122.592561l89.824562-40.277333v122.610526l-89.824562 40.259368zM432.918456 512.610807l89.824562-40.277333-89.824562 40.277333zM671.025404 548.181333l-108.220632-16.168421 89.824561-40.259368 108.220632 16.168421-89.824561 40.259368z" fill="#CECEF9" p-id="7966"></path><path d="M562.804772 532.012912v122.592562l89.824561-40.259369v-122.592561l-89.824561 40.259368z" fill="#CECEF9" p-id="7967"></path><path d="M562.804772 654.605474l108.220632 16.168421 89.824561-40.259369-108.220632-16.168421-89.824561 40.259369z" fill="#CECEF9" p-id="7968"></path><path d="M671.025404 670.79186v-122.610527l89.824561-40.259368v122.592561l-89.824561 40.277334zM671.025404 548.181333l89.824561-40.259368-89.824561 40.259368z" fill="#CECEF9" p-id="7969"></path><path d="M606.082246 72.596211l-216.459228-32.336843v98.088421l64.943157 9.701053v49.044211L129.868351 148.569825v760.095438l735.968561 109.981193v-760.095438L541.157053 210.009825V160.965614l64.925193 9.701053V72.578246z m-389.623018 750.933333V259.592982l562.804772 84.11172v563.954526L216.459228 823.511579zM0 374.352842v269.725193l86.590877 12.934737V387.287579L0 374.352842zM909.132351 510.203509v269.725193l86.590877 12.934737V523.138246l-86.590877-12.934737z m-476.213895 2.407298l-108.220631-16.168421v122.592561l108.220631 16.168421v-122.592561z m238.106948 35.570526l-108.220632-16.168421v122.592562l108.220632 16.168421v-122.592562z" fill="#4E5969" p-id="7970"></path></svg>`,
    wechat: `<svg t="1770777063094" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="6815" width="200" height="200"><path d="M337.387283 341.82659c-17.757225 0-35.514451 11.83815-35.514451 29.595375s17.757225 29.595376 35.514451 29.595376 29.595376-11.83815 29.595376-29.595376c0-18.49711-11.83815-29.595376-29.595376-29.595375zM577.849711 513.479769c-11.83815 0-22.936416 12.578035-22.936416 23.6763 0 12.578035 11.83815 23.676301 22.936416 23.676301 17.757225 0 29.595376-11.83815 29.595376-23.676301s-11.83815-23.676301-29.595376-23.6763zM501.641618 401.017341c17.757225 0 29.595376-12.578035 29.595376-29.595376 0-17.757225-11.83815-29.595376-29.595376-29.595375s-35.514451 11.83815-35.51445 29.595375 17.757225 29.595376 35.51445 29.595376zM706.589595 513.479769c-11.83815 0-22.936416 12.578035-22.936416 23.6763 0 12.578035 11.83815 23.676301 22.936416 23.676301 17.757225 0 29.595376-11.83815 29.595376-23.676301s-11.83815-23.676301-29.595376-23.6763z" fill="#28C445" p-id="6816"></path><path d="M510.520231 2.959538C228.624277 2.959538 0 231.583815 0 513.479769s228.624277 510.520231 510.520231 510.520231 510.520231-228.624277 510.520231-510.520231-228.624277-510.520231-510.520231-510.520231zM413.595376 644.439306c-29.595376 0-53.271676-5.919075-81.387284-12.578034l-81.387283 41.433526 22.936416-71.768786c-58.450867-41.433526-93.965318-95.445087-93.965317-159.815029 0-113.202312 105.803468-201.988439 233.803468-201.98844 114.682081 0 216.046243 71.028902 236.023121 166.473989-7.398844-0.739884-14.797688-1.479769-22.196532-1.479769-110.982659 1.479769-198.289017 85.086705-198.289017 188.67052 0 17.017341 2.959538 33.294798 7.398844 49.572255-7.398844 0.739884-15.537572 1.479769-22.936416 1.479768z m346.265896 82.867052l17.757225 59.190752-63.630058-35.514451c-22.936416 5.919075-46.612717 11.83815-70.289017 11.83815-111.722543 0-199.768786-76.947977-199.768786-172.393063-0.739884-94.705202 87.306358-171.653179 198.289017-171.65318 105.803468 0 199.028902 77.687861 199.028902 172.393064 0 53.271676-34.774566 100.624277-81.387283 136.138728z" fill="#28C445" p-id="6817"></path></svg>`,
    dingtalk: `<svg t="1770777036743" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="5808" width="200" height="200"><path d="M512.003 79C272.855 79 79 272.855 79 512.003 79 751.145 272.855 945 512.003 945 751.145 945 945 751.145 945 512.003 945 272.855 751.145 79 512.003 79z m200.075 375.014c-0.867 3.764-3.117 9.347-6.234 16.012h0.087l-0.347 0.648c-18.183 38.86-65.631 115.108-65.631 115.108l-0.215-0.52-13.856 24.147h66.8L565.063 779l29.002-115.368h-52.598l18.27-76.29c-14.76 3.55-32.253 8.436-52.945 15.1 0 0-27.967 16.36-80.607-31.5 0 0-35.501-31.29-14.891-39.078 8.744-3.33 42.466-7.573 69.004-11.122 35.93-4.845 57.965-7.441 57.965-7.441s-110.607 1.643-136.841-2.468c-26.237-4.11-59.525-47.905-66.626-86.377 0 0-10.953-21.117 23.595-11.122 34.547 10 177.535 38.95 177.535 38.95s-185.933-56.992-198.36-70.929c-12.381-13.846-36.406-75.902-33.289-113.981 0 0 1.343-9.521 11.127-6.926 0 0 137.49 62.75 231.475 97.152 94.028 34.403 175.76 51.885 165.2 96.414z" fill="#3AA2EB" p-id="5809"></path></svg>`,
    feishu: `<svg t="1770776989358" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="4830" width="200" height="200"><path d="M512 0c282.76736 0 512 229.23264 512 512s-229.23264 512-512 512S0 794.76736 0 512 229.23264 0 512 0zM224.03072 421.59104l-0.03072 7.08096 0.4096 186.0096-0.23552 37.09952 0.26624 15.8976 0.29184 5.43232 0.41984 3.74272 0.08192 0.4608c0.0512 0.29184 0.11264 0.54784 0.17408 0.77824 1.1776 4.42368 3.72224 8.2432 7.64416 11.79136 3.47648 3.14368 7.74144 5.91872 14.21824 9.48736 31.46752 17.26976 61.6448 29.952 92.3904 38.62016 31.83616 8.97536 64.68608 13.77792 100.12672 14.54592 36.62336 0.7936 70.79936-3.02592 104.2176-11.50464 32-8.12032 63.69792-20.61312 97.18272-38.02624 24.92928-12.96896 52.0704-33.23392 76.96896-57.216l8.82688-8.76032 8.48896-8.94464 3.44576-3.88096-1.95584 1.1264-7.22432 3.67616-2.62656 1.24416c-28.04736 12.99456-57.18528 16.68096-89.65632 12.78464l-9.90208-1.37216-9.82528-1.7408-2.4832-0.512-2.5088-0.53248-10.3936-2.4576-2.71872-0.70144-2.77504-0.73728-11.80672-3.35872-2.09408-0.62464c-1.408-0.41984-2.8416-0.85504-4.31104-1.3056l-21.78048-6.95296-10.61888-3.5328-31.03744-11.21792-15.2576-5.7344-13.03552-5.07904-6.9632-2.85696-7.40864-3.34336-0.70144-0.35328a22.59968 22.59968 0 0 1-2.09408-1.19296l-10.0352-5.01248-26.25536-12.30336-16.32768-8.07424-5.85728-3.05152c-29.27616-15.44192-58.2144-33.7152-86.9888-54.71744-27.76576-20.26496-55.21408-42.94656-82.79552-68.16256l-13.80864-12.82048-3.64032-3.69664z m553.72288-7.5008l-10.3936 0.21504-3.97824 0.2048a230.64576 230.64576 0 0 0-46.27456 7.36768 215.62368 215.62368 0 0 0-40.13568 15.24736 229.7856 229.7856 0 0 0-37.248 23.31136l-6.50752 5.11488-1.5872 1.28-1.57696 1.3056-6.36928 5.43232-6.72768 6.0416-7.45472 6.96832-34.86208 33.85344-2.32448 2.21184c-16.8704 15.9744-29.45536 26.55232-43.93472 36.51584l-5.71904 3.84-15.09376 9.76896-2.17088 1.36704c-2.85184 1.792-5.5552 3.45088-8.11008 4.98176l-7.53152 4.34176 11.02336 4.3776 32.4352 12.1088 20.10112 7.1424 22.68672 7.38816 12.85632 3.95264 11.45856 3.26656 2.688 0.7168c2.65728 0.70656 5.2224 1.35168 7.72608 1.9456l9.72288 2.12992 2.36544 0.4608 2.34496 0.4352 9.35424 1.4848 2.3552 0.3072 2.37056 0.30208c30.6432 3.68128 57.8304 0.02048 83.98336-12.66176 33.47968-16.24064 49.3056-32.82944 71.41376-73.24672l7.2192-13.58336 11.38176-22.23104 4.99712-9.61536 1.536-2.93376c15.29344-28.96896 26.82368-46.68416 42.68032-63.05792l1.54624-1.5872-3.71712-1.42848-4.5568-1.63328-9.50784-3.1488-8.13056-2.42176-3.66592-0.96256a229.76512 229.76512 0 0 0-46.30016-6.656l-10.368-0.22016zM332.4672 272.64l9.1136 6.56384 12.90752 9.48224 5.1712 3.88096a809.55392 809.55392 0 0 1 42.68544 34.47808 730.65984 730.65984 0 0 1 55.808 53.9648c16.384 17.55136 30.5664 33.78176 43.63776 50.0224 10.24 12.71808 19.968 25.64096 29.50656 39.22432l11.19232 16.44032 18.08384 28.75904 11.2896-10.47552 17.11616-16.39424 9.8304-9.22112 12.94336-11.84256 3.00032-2.6624a403.51744 403.51744 0 0 1 25.61536-20.9408c7.12704-5.33504 15.616-10.56768 25.02656-15.50848a268.47744 268.47744 0 0 1 20.0192-9.4208l11.42272-4.51584 6.1952-2.05312-0.1536-0.91136-0.33792-1.37728c-1.42336-5.63712-3.82464-12.7744-7.00416-20.92032l-4.55168-11.1104-1.05472-2.4576c-7.1168-16.3584-15.64672-33.2544-22.03648-43.776l-12.83584-19.85536-7.08096-10.35264-1.2032-1.6896c-9.5488-13.27104-17.11616-21.36064-23.57248-24.32-4.35712-2.00192-8.14592-2.7648-14.73024-2.93888h-7.64416l-5.51936 0.08192-260.74624-0.03584-2.09408-0.11776z" fill="#3370FF" p-id="4831"></path></svg>`,
    wecom: `<svg t="1773729080381" class="icon" viewBox="0 0 1229 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="1694" width="200" height="200"><path d="M690.8 828.8c-72 28.8-148.8 33.6-225.6 28.8-33.6-4.8-67.2-9.6-100.8-19.2-4.8 0-9.6 0-14.4 4.8-43.2 19.2-86.4 43.2-124.8 62.4-14.4 9.6-28.8 9.6-43.2 0s-14.4-24-14.4-43.2c9.6-33.6 9.6-67.2 14.4-100.8 0-4.8-4.8-9.6-4.8-14.4-48-48-86.4-96-115.2-158.4-48-115.2-38.4-230.4 28.8-336C158 137.6 263.6 75.2 388.4 46.4S633.2 32 748.4 89.6c105.6 52.8 182.4 134.4 216 249.6 14.4 43.2 19.2 86.4 14.4 129.6-24-24-52.8-28.8-81.6-14.4 0-28.8 0-57.6-9.6-86.4-19.2-67.2-57.6-120-105.6-163.2-81.6-67.2-182.4-96-288-96-110.4 9.6-206.4 48-283.2 124.8-62.4 62.4-96 139.2-91.2 230.4 4.8 76.8 38.4 139.2 86.4 192l38.4 38.4c19.2 14.4 24 28.8 14.4 48-4.8 19.2-9.6 43.2-14.4 62.4 0 4.8-4.8 9.6 0 9.6 4.8 4.8 9.6 0 9.6 0 24-14.4 52.8-28.8 76.8-48 14.4-9.6 28.8-9.6 48-4.8 81.6 24 168 24 249.6 0 4.8 0 9.6-4.8 9.6 4.8 9.6 28.8 24 48 52.8 62.4z" fill="#0082EF" p-id="1695"></path><path d="M1170.8 732.8c0 33.6-24 57.6-52.8 62.4-48 9.6-86.4 28.8-120 62.4-9.6 9.6-14.4 9.6-24 4.8-4.8-4.8-4.8-14.4 0-24 33.6-33.6 52.8-76.8 62.4-120 4.8-33.6 38.4-52.8 72-52.8 38.4 4.8 62.4 33.6 62.4 67.2z" fill="#0081EE" p-id="1696"></path><path d="M926 992c-33.6 0-62.4-24-67.2-52.8-4.8-48-28.8-86.4-62.4-115.2-4.8-4.8-9.6-9.6-4.8-19.2 4.8-14.4 14.4-14.4 24-9.6 9.6 4.8 14.4 14.4 19.2 19.2 28.8 24 62.4 38.4 96 43.2 33.6 4.8 57.6 38.4 52.8 72 4.8 33.6-24 62.4-57.6 62.4z" fill="#FA6202" p-id="1697"></path><path d="M671.6 742.4c0-33.6 19.2-57.6 52.8-67.2 48-9.6 86.4-28.8 120-62.4 9.6-9.6 19.2-9.6 24 0 4.8 4.8 4.8 14.4-4.8 24-28.8 28.8-48 62.4-57.6 105.6 0 4.8 0 14.4-4.8 19.2-9.6 33.6-38.4 52.8-72 48-33.6-4.8-57.6-33.6-57.6-67.2z" fill="#FECD00" p-id="1698"></path><path d="M1002.8 574.4c14.4 28.8 28.8 52.8 48 72 9.6 9.6 9.6 19.2 4.8 24-4.8 9.6-14.4 9.6-24 0-24-28.8-57.6-48-91.2-57.6-9.6-4.8-19.2-4.8-28.8-4.8-19.2-4.8-38.4-14.4-43.2-38.4-9.6-24-9.6-48 9.6-67.2 19.2-24 43.2-28.8 67.2-24 24 9.6 43.2 24 48 52.8 0 14.4 4.8 28.8 9.6 43.2z" fill="#2CBD00" p-id="1699"></path></svg>`,
    weibo: `<svg t="1773731362244" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="4035" width="200" height="200"><path d="M851.4 590.193c-22.196-66.233-90.385-90.422-105.912-91.863-15.523-1.442-29.593-9.94-19.295-27.505 10.302-17.566 29.304-68.684-7.248-104.681-36.564-36.14-116.512-22.462-173.094 0.866-56.434 23.327-53.39 7.055-51.65-8.925 1.89-16.848 32.355-111.02-60.791-122.395C311.395 220.86 154.85 370.754 99.572 457.15 16 587.607 29.208 675.873 29.208 675.873h0.58c10.009 121.819 190.787 218.869 412.328 218.869 190.5 0 350.961-71.853 398.402-169.478 0 0 0.143-0.433 0.575-1.156 4.938-10.506 8.71-21.168 11.035-32.254 6.668-26.205 11.755-64.215-0.728-101.66z m-436.7 251.27c-157.71 0-285.674-84.095-285.674-187.768 0-103.671 127.82-187.76 285.674-187.76 157.705 0 285.673 84.089 285.673 187.76 0 103.815-127.968 187.768-285.673 187.768z" fill="#E71F19" p-id="4036"></path><path d="M803.096 425.327c2.896 1.298 5.945 1.869 8.994 1.869 8.993 0 17.7-5.328 21.323-14.112 5.95-13.964 8.993-28.793 8.993-44.205 0-62.488-51.208-113.321-114.181-113.321-15.379 0-30.32 3.022-44.396 8.926-11.755 4.896-17.263 18.432-12.335 30.24 4.933 11.662 18.572 17.134 30.465 12.238 8.419-3.46 17.268-5.33 26.41-5.33 37.431 0 67.752 30.241 67.752 67.247 0 9.068-1.735 17.857-5.369 26.202a22.832 22.832 0 0 0 12.335 30.236l0.01 0.01z" fill="#F5AA15" p-id="4037"></path><path d="M726.922 114.157c-25.969 0-51.65 3.744-76.315 10.942-18.423 5.472-28.868 24.622-23.5 42.91 5.509 18.29 24.804 28.657 43.237 23.329a201.888 201.888 0 0 1 56.578-8.064c109.253 0 198.189 88.271 198.189 196.696 0 19.436-2.905 38.729-8.419 57.16-5.508 18.289 4.79 37.588 23.212 43.053 3.342 1.014 6.817 1.442 10.159 1.442 14.943 0 28.725-9.648 33.37-24.48 7.547-24.906 11.462-50.826 11.462-77.175-0.143-146.588-120.278-265.813-267.973-265.813z" fill="#F5AA15" p-id="4038"></path><path d="M388.294 534.47c-84.151 0-152.34 59.178-152.34 132.334 0 73.141 68.189 132.328 152.34 132.328 84.148 0 152.337-59.182 152.337-132.328 0-73.15-68.19-132.334-152.337-132.334zM338.53 752.763c-29.454 0-53.39-23.755-53.39-52.987 0-29.228 23.941-52.989 53.39-52.989 29.453 0 53.39 23.76 53.39 52.989 0 29.227-23.937 52.987-53.39 52.987z m99.82-95.465c-6.382 11.086-19.296 15.696-28.726 10.219-9.43-5.323-11.75-18.717-5.37-29.803 6.386-11.09 19.297-15.7 28.725-10.224 9.43 5.472 11.755 18.864 5.37 29.808z" fill="#040000" p-id="4039"></path></svg>`,
  }
  return icons[channelId] || icons.telegram
}

const handleConfigUpdate = (channelId: string, config: Record<string, any>) => {
  channelsStore.updateLocalChannelConfig(channelId, config)
  configChanged.value = true

  const hasEnabledAccount = config.enabled ||
    (config.accounts && Object.values(config.accounts).some((acc: any) => acc.enabled))

  if (!hasEnabledAccount) {
    toast.warning(t('settings.channels.enableChannel.message'))
  }
}

const handleTest = async (channelId: string, config?: Record<string, any>, accountId?: string) => {
  activeTestTarget.value = { channelId, accountId: accountId || null }
  try {
    testResult.value = await channelsStore.testChannel(channelId, config, accountId)
  } finally {
    activeTestTarget.value = null
  }
}

channelsStore.init()
</script>
<style scoped>
@import './styles/ChannelsConfig.css';
</style>
