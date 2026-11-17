<template>
  <div class="channels-config">
    <div class="channels-toolbar">
      <div class="status-pill">
        <span class="status-item">
          <span class="status-dot running"></span>
          <span class="status-text">{{ channelsStore.runningChannels.length }} {{ t('settings.channels.running') }}</span>
        </span>
        <span class="status-divider"></span>
        <span class="status-item">
          <span class="status-dot enabled"></span>
          <span class="status-text">{{ channelsStore.enabledChannels.length }} {{ t('settings.channels.enabled') }}</span>
        </span>
      </div>

      <div class="header-actions">
        <a
          href="https://countbot.cn/docs/getting-started/ChannelConfig"
          target="_blank"
          rel="noopener noreferrer"
          class="co-btn co-btn--secondary"
          title="打开渠道配置教程"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M14 3h7v7"></path>
            <path d="M10 14L21 3"></path>
            <path d="M21 14v6a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h6"></path>
          </svg>
          <span>配置教程</span>
        </a>
        <button
          class="co-btn co-btn--secondary icon-action"
          :title="t('common.refresh')"
          :aria-label="t('common.refresh')"
          @click="channelsStore.fetchStatus()"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2"/>
          </svg>
        </button>
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
          'is-implemented': isImplemented(id),
          'is-planned': isPlanned(id)
        }"
      >
        <!-- 卡片头部 -->
        <div class="channel-head" @click="toggleChannelConfig(id)">
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
            <svg width="18" height="18" viewBox="0 0 20 20" fill="currentColor">
              <path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd"/>
            </svg>
          </button>
        </div>

        <!-- 配置面板 -->
        <transition name="slide-down">
          <div v-show="expandedChannel === id" class="channel-body">
            <div class="channel-body-inner">
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
                <ServerChanConfig
                  v-else-if="id === 'serverchan'"
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
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
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
import ServerChanConfig from './channels/ServerChanConfig.vue'
import { getChannelIcon } from './channelIcons'

const { t, te } = useI18n()
const channelsStore = useChannelsStore()
const toast = useToast()

const expandedChannel = ref<string | null>(null)
const testResult = ref<any>(null)
const configChanged = ref(false)
const activeTestTarget = ref<{ channelId: string; accountId: string | null } | null>(null)

// 已实现的渠道（按展示优先级排序）
const implementedChannels = ['feishu', 'wecom', 'wechat', 'xiaozhi', 'qq', 'dingtalk', 'telegram', 'weibo', 'serverchan']

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

const isRunning = (channelId: string) => {
  const status = channelsStore.status[channelId]
  return status && status.running
}

const getChannelDisplayName = (channelId: string, fallback: string) => {
  const key = `settings.channels.catalog.${channelId}.name`
  return te(key) ? t(key) : fallback
}

const getChannelDisplayDescription = (channelId: string, fallback: string) => {
  const key = `settings.channels.catalog.${channelId}.description`
  return te(key) ? t(key) : fallback
}

let statusPollTimer: number | null = null

// 展开渠道时轮询加快至 2s，平时 10s；仅页面挂载期间运行
const STATUS_POLL_INTERVAL_IDLE = 10000
const STATUS_POLL_INTERVAL_ACTIVE = 2000

const stopStatusPolling = () => {
  if (statusPollTimer !== null) {
    window.clearInterval(statusPollTimer)
    statusPollTimer = null
  }
}

const startStatusPolling = (intervalMs: number) => {
  stopStatusPolling()
  statusPollTimer = window.setInterval(() => {
    void channelsStore.fetchStatus()
  }, intervalMs)
}

const syncStatusPolling = () => {
  startStatusPolling(
    expandedChannel.value ? STATUS_POLL_INTERVAL_ACTIVE : STATUS_POLL_INTERVAL_IDLE
  )
}

onMounted(syncStatusPolling)

watch(expandedChannel, syncStatusPolling)

onBeforeUnmount(stopStatusPolling)

const toggleChannelConfig = (channelId: string) => {
  expandedChannel.value = expandedChannel.value === channelId ? null : channelId
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
