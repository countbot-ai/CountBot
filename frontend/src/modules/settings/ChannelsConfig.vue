<template>
  <div class="channels-config">
    <div class="channels-header">
      <div class="header-top">
        <div class="header-left">
          <div class="header-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
            </svg>
          </div>
          <div class="header-text">
            <h3>{{ t('settings.channels.title') }}</h3>
            <p class="channels-description">{{ t('settings.channels.description') }}</p>
          </div>
        </div>
        <div class="header-right">
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
          <button @click="channelsStore.fetchStatus()" class="refresh-button" :title="t('common.refresh')">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2"/>
            </svg>
          </button>
        </div>
      </div>
      
      <div class="implementation-status">
        <span class="status-badge implemented">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <polyline points="20 6 9 17 4 12"></polyline>
          </svg>
          {{ t('settings.channels.implemented') }}: {{ t('settings.channels.implementedList') }}
        </span>
        <span class="status-badge planned">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="12" y1="8" x2="12" y2="12"></line>
            <line x1="12" y1="16" x2="12.01" y2="16"></line>
          </svg>
          {{ t('settings.channels.planned') }}: {{ t('settings.channels.plannedList') }}
        </span>
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
              <h4>{{ channel.name }}</h4>
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
            <p class="channel-desc">{{ channel.description }}</p>
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
              <!-- 已实现渠道 -->
              <template v-if="isImplemented(id)">
                <TelegramConfig
                  v-if="id === 'telegram'"
                  :channel-id="id"
                  :config="channel.config"
                  @update="handleConfigUpdate"
                  @test="handleTest"
                />
                <QQConfig
                  v-else-if="id === 'qq'"
                  :channel-id="id"
                  :config="channel.config"
                  @update="handleConfigUpdate"
                  @test="handleTest"
                />
                <DingTalkConfig
                  v-else-if="id === 'dingtalk'"
                  :channel-id="id"
                  :config="channel.config"
                  @update="handleConfigUpdate"
                  @test="handleTest"
                />
                <FeishuConfig
                  v-else-if="id === 'feishu'"
                  :channel-id="id"
                  :config="channel.config"
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
                <WeChatConfig
                  v-else-if="id === 'wechat'"
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
                <p>{{ t('settings.channels.comingSoonDesc', { channel: channel.name }) }}</p>
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
import TelegramConfig from './channels/TelegramConfig.vue'
import DiscordConfig from './channels/DiscordConfig.vue'
import QQConfig from './channels/QQConfig.vue'
import WeChatConfig from './channels/WeChatConfig.vue'
import DingTalkConfig from './channels/DingTalkConfig.vue'
import FeishuConfig from './channels/FeishuConfig.vue'

const { t } = useI18n()
const channelsStore = useChannelsStore()

const expandedChannel = ref<string | null>(null)
const testResult = ref<any>(null)
const configChanged = ref(false)

// 推荐的渠道（优先显示）
const recommendedChannels = ['feishu', 'qq', 'dingtalk']

// 已实现的渠道
const implementedChannels = ['feishu', 'qq', 'dingtalk', 'telegram']

// 计划中的渠道
const plannedChannels = ['discord', 'wechat']

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

const toggleChannelConfig = (channelId: string) => {
  console.log('[ChannelsConfig] Toggling channel:', channelId, 'Current expanded:', expandedChannel.value)
  expandedChannel.value = expandedChannel.value === channelId ? null : channelId
  console.log('[ChannelsConfig] New expanded:', expandedChannel.value)
}

const getChannelIcon = (channelId: string) => {
  const icons: Record<string, string> = {
    telegram: `<svg t="1770777159632" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="10792" width="200" height="200"><path d="M679.424 746.862l84.005-395.996c7.424-34.852-12.581-48.567-35.438-40.009L234.277 501.138c-33.72 13.13-33.134 32-5.706 40.558l126.282 39.424 293.156-184.576c13.714-9.143 26.295-3.986 16.018 5.157L426.898 615.973l-9.143 130.304c13.13 0 18.871-5.706 25.71-12.581l61.696-59.429 128 94.282c23.442 13.129 40.01 6.29 46.3-21.724zM1024 512c0 282.843-229.157 512-512 512S0 794.843 0 512 229.157 0 512 0s512 229.157 512 512z" fill="#1296DB" p-id="10793"></path></svg>`,
    discord: `<svg t="1770777174043" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="11772" width="200" height="200"><path d="M0 512a512 512 0 1 0 1024 0A512 512 0 1 0 0 512z" fill="#738BD8" p-id="11773"></path><path d="M190.915 234.305h642.169v477.288H190.915z" fill="#FFFFFF" p-id="11774"></path><path d="M698.157 932.274L157.288 862.85c-58.43-7.5-55.4-191.167-50.26-249.853l26.034-297.22c5.14-58.686 74.356-120.22 132.7-128.362l466.441-65.085c58.346-8.14 177.24 212.65 176.09 271.548l-8.677 445.108M512 300.373c-114.347 0-194.56 49.067-194.56 49.067 43.947-39.253 120.747-61.867 120.747-61.867l-7.254-7.253c-72.106 1.28-137.386 51.2-137.386 51.2-73.387 153.173-68.694 285.44-68.694 285.44 59.734 77.227 148.48 71.68 148.48 71.68l30.294-38.4c-53.334-11.52-87.04-58.88-87.04-58.88S396.8 645.973 512 645.973c115.2 0 195.413-54.613 195.413-54.613s-33.706 47.36-87.04 58.88l30.294 38.4s88.746 5.547 148.48-71.68c0 0 4.693-132.267-68.694-285.44 0 0-65.28-49.92-137.386-51.2l-7.254 7.253s76.8 22.614 120.747 61.867c0 0-80.213-49.067-194.56-49.067M423.68 462.08c27.733 0 50.347 24.32 49.92 54.187 0 29.44-22.187 54.186-49.92 54.186-27.307 0-49.493-24.746-49.493-54.186 0-29.867 21.76-54.187 49.493-54.187m177.92 0c27.733 0 49.92 24.32 49.92 54.187 0 29.44-22.187 54.186-49.92 54.186-27.307 0-49.493-24.746-49.493-54.186 0-29.867 21.76-54.187 49.493-54.187z" fill="#738BD8" p-id="11775"></path></svg>`,
    qq: `<svg t="1770777134598" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="9780" width="200" height="200"><path d="M511.09761 957.257c-80.159 0-153.737-25.019-201.11-62.386-24.057 6.702-54.831 17.489-74.252 30.864-16.617 11.439-14.546 23.106-11.55 27.816 13.15 20.689 225.583 13.211 286.912 6.767v-3.061z" fill="#FAAD08" p-id="9781"></path><path d="M496.65061 957.257c80.157 0 153.737-25.019 201.11-62.386 24.057 6.702 54.83 17.489 74.253 30.864 16.616 11.439 14.543 23.106 11.55 27.816-13.15 20.689-225.584 13.211-286.914 6.767v-3.061z" fill="#FAAD08" p-id="9782"></path><path d="M497.12861 474.524c131.934-0.876 237.669-25.783 273.497-35.34 8.541-2.28 13.11-6.364 13.11-6.364 0.03-1.172 0.542-20.952 0.542-31.155C784.27761 229.833 701.12561 57.173 496.64061 57.162 292.15661 57.173 209.00061 229.832 209.00061 401.665c0 10.203 0.516 29.983 0.547 31.155 0 0 3.717 3.821 10.529 5.67 33.078 8.98 140.803 35.139 276.08 36.034h0.972z" fill="#000000" p-id="9783"></path><path d="M860.28261 619.782c-8.12-26.086-19.204-56.506-30.427-85.72 0 0-6.456-0.795-9.718 0.148-100.71 29.205-222.773 47.818-315.792 46.695h-0.962C410.88561 582.017 289.65061 563.617 189.27961 534.698 185.44461 533.595 177.87261 534.063 177.87261 534.063 166.64961 563.276 155.56661 593.696 147.44761 619.782 108.72961 744.168 121.27261 795.644 130.82461 796.798c20.496 2.474 79.78-93.637 79.78-93.637 0 97.66 88.324 247.617 290.576 248.996a718.01 718.01 0 0 1 5.367 0C708.80161 950.778 797.12261 800.822 797.12261 703.162c0 0 59.284 96.111 79.783 93.637 9.55-1.154 22.093-52.63-16.623-177.017" fill="#000000" p-id="9784"></path><path d="M434.38261 316.917c-27.9 1.24-51.745-30.106-53.24-69.956-1.518-39.877 19.858-73.207 47.764-74.454 27.875-1.224 51.703 30.109 53.218 69.974 1.527 39.877-19.853 73.2-47.742 74.436m206.67-69.956c-1.494 39.85-25.34 71.194-53.24 69.956-27.888-1.238-49.269-34.559-47.742-74.435 1.513-39.868 25.341-71.201 53.216-69.974 27.909 1.247 49.285 34.576 47.767 74.453" fill="#FFFFFF" p-id="9785"></path><path d="M683.94261 368.627c-7.323-17.609-81.062-37.227-172.353-37.227h-0.98c-91.29 0-165.031 19.618-172.352 37.227a6.244 6.244 0 0 0-0.535 2.505c0 1.269 0.393 2.414 1.006 3.386 6.168 9.765 88.054 58.018 171.882 58.018h0.98c83.827 0 165.71-48.25 171.881-58.016a6.352 6.352 0 0 0 1.002-3.395c0-0.897-0.2-1.736-0.531-2.498" fill="#FAAD08" p-id="9786"></path><path d="M467.63161 256.377c1.26 15.886-7.377 30-19.266 31.542-11.907 1.544-22.569-10.083-23.836-25.978-1.243-15.895 7.381-30.008 19.25-31.538 11.927-1.549 22.607 10.088 23.852 25.974m73.097 7.935c2.533-4.118 19.827-25.77 55.62-17.886 9.401 2.07 13.75 5.116 14.668 6.316 1.355 1.77 1.726 4.29 0.352 7.684-2.722 6.725-8.338 6.542-11.454 5.226-2.01-0.85-26.94-15.889-49.905 6.553-1.579 1.545-4.405 2.074-7.085 0.242-2.678-1.834-3.786-5.553-2.196-8.135" fill="#000000" p-id="9787"></path><path d="M504.33261 584.495h-0.967c-63.568 0.752-140.646-7.504-215.286-21.92-6.391 36.262-10.25 81.838-6.936 136.196 8.37 137.384 91.62 223.736 220.118 224.996H506.48461c128.498-1.26 211.748-87.612 220.12-224.996 3.314-54.362-0.547-99.938-6.94-136.203-74.654 14.423-151.745 22.684-215.332 21.927" fill="#FFFFFF" p-id="9788"></path><path d="M323.27461 577.016v137.468s64.957 12.705 130.031 3.91V591.59c-41.225-2.262-85.688-7.304-130.031-14.574" fill="#EB1C26" p-id="9789"></path><path d="M788.09761 432.536s-121.98 40.387-283.743 41.539h-0.962c-161.497-1.147-283.328-41.401-283.744-41.539l-40.854 106.952c102.186 32.31 228.837 53.135 324.598 51.926l0.96-0.002c95.768 1.216 222.4-19.61 324.6-51.924l-40.855-106.952z" fill="#EB1C26" p-id="9790"></path></svg>`,
    wechat: `<svg t="1770777063094" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="6815" width="200" height="200"><path d="M337.387283 341.82659c-17.757225 0-35.514451 11.83815-35.514451 29.595375s17.757225 29.595376 35.514451 29.595376 29.595376-11.83815 29.595376-29.595376c0-18.49711-11.83815-29.595376-29.595376-29.595375zM577.849711 513.479769c-11.83815 0-22.936416 12.578035-22.936416 23.6763 0 12.578035 11.83815 23.676301 22.936416 23.676301 17.757225 0 29.595376-11.83815 29.595376-23.676301s-11.83815-23.676301-29.595376-23.6763zM501.641618 401.017341c17.757225 0 29.595376-12.578035 29.595376-29.595376 0-17.757225-11.83815-29.595376-29.595376-29.595375s-35.514451 11.83815-35.51445 29.595375 17.757225 29.595376 35.51445 29.595376zM706.589595 513.479769c-11.83815 0-22.936416 12.578035-22.936416 23.6763 0 12.578035 11.83815 23.676301 22.936416 23.676301 17.757225 0 29.595376-11.83815 29.595376-23.676301s-11.83815-23.676301-29.595376-23.6763z" fill="#28C445" p-id="6816"></path><path d="M510.520231 2.959538C228.624277 2.959538 0 231.583815 0 513.479769s228.624277 510.520231 510.520231 510.520231 510.520231-228.624277 510.520231-510.520231-228.624277-510.520231-510.520231-510.520231zM413.595376 644.439306c-29.595376 0-53.271676-5.919075-81.387284-12.578034l-81.387283 41.433526 22.936416-71.768786c-58.450867-41.433526-93.965318-95.445087-93.965317-159.815029 0-113.202312 105.803468-201.988439 233.803468-201.98844 114.682081 0 216.046243 71.028902 236.023121 166.473989-7.398844-0.739884-14.797688-1.479769-22.196532-1.479769-110.982659 1.479769-198.289017 85.086705-198.289017 188.67052 0 17.017341 2.959538 33.294798 7.398844 49.572255-7.398844 0.739884-15.537572 1.479769-22.936416 1.479768z m346.265896 82.867052l17.757225 59.190752-63.630058-35.514451c-22.936416 5.919075-46.612717 11.83815-70.289017 11.83815-111.722543 0-199.768786-76.947977-199.768786-172.393063-0.739884-94.705202 87.306358-171.653179 198.289017-171.65318 105.803468 0 199.028902 77.687861 199.028902 172.393064 0 53.271676-34.774566 100.624277-81.387283 136.138728z" fill="#28C445" p-id="6817"></path></svg>`,
    dingtalk: `<svg t="1770777036743" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="5808" width="200" height="200"><path d="M512.003 79C272.855 79 79 272.855 79 512.003 79 751.145 272.855 945 512.003 945 751.145 945 945 751.145 945 512.003 945 272.855 751.145 79 512.003 79z m200.075 375.014c-0.867 3.764-3.117 9.347-6.234 16.012h0.087l-0.347 0.648c-18.183 38.86-65.631 115.108-65.631 115.108l-0.215-0.52-13.856 24.147h66.8L565.063 779l29.002-115.368h-52.598l18.27-76.29c-14.76 3.55-32.253 8.436-52.945 15.1 0 0-27.967 16.36-80.607-31.5 0 0-35.501-31.29-14.891-39.078 8.744-3.33 42.466-7.573 69.004-11.122 35.93-4.845 57.965-7.441 57.965-7.441s-110.607 1.643-136.841-2.468c-26.237-4.11-59.525-47.905-66.626-86.377 0 0-10.953-21.117 23.595-11.122 34.547 10 177.535 38.95 177.535 38.95s-185.933-56.992-198.36-70.929c-12.381-13.846-36.406-75.902-33.289-113.981 0 0 1.343-9.521 11.127-6.926 0 0 137.49 62.75 231.475 97.152 94.028 34.403 175.76 51.885 165.2 96.414z" fill="#3AA2EB" p-id="5809"></path></svg>`,
    feishu: `<svg t="1770776989358" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="4830" width="200" height="200"><path d="M512 0c282.76736 0 512 229.23264 512 512s-229.23264 512-512 512S0 794.76736 0 512 229.23264 0 512 0zM224.03072 421.59104l-0.03072 7.08096 0.4096 186.0096-0.23552 37.09952 0.26624 15.8976 0.29184 5.43232 0.41984 3.74272 0.08192 0.4608c0.0512 0.29184 0.11264 0.54784 0.17408 0.77824 1.1776 4.42368 3.72224 8.2432 7.64416 11.79136 3.47648 3.14368 7.74144 5.91872 14.21824 9.48736 31.46752 17.26976 61.6448 29.952 92.3904 38.62016 31.83616 8.97536 64.68608 13.77792 100.12672 14.54592 36.62336 0.7936 70.79936-3.02592 104.2176-11.50464 32-8.12032 63.69792-20.61312 97.18272-38.02624 24.92928-12.96896 52.0704-33.23392 76.96896-57.216l8.82688-8.76032 8.48896-8.94464 3.44576-3.88096-1.95584 1.1264-7.22432 3.67616-2.62656 1.24416c-28.04736 12.99456-57.18528 16.68096-89.65632 12.78464l-9.90208-1.37216-9.82528-1.7408-2.4832-0.512-2.5088-0.53248-10.3936-2.4576-2.71872-0.70144-2.77504-0.73728-11.80672-3.35872-2.09408-0.62464c-1.408-0.41984-2.8416-0.85504-4.31104-1.3056l-21.78048-6.95296-10.61888-3.5328-31.03744-11.21792-15.2576-5.7344-13.03552-5.07904-6.9632-2.85696-7.40864-3.34336-0.70144-0.35328a22.59968 22.59968 0 0 1-2.09408-1.19296l-10.0352-5.01248-26.25536-12.30336-16.32768-8.07424-5.85728-3.05152c-29.27616-15.44192-58.2144-33.7152-86.9888-54.71744-27.76576-20.26496-55.21408-42.94656-82.79552-68.16256l-13.80864-12.82048-3.64032-3.69664z m553.72288-7.5008l-10.3936 0.21504-3.97824 0.2048a230.64576 230.64576 0 0 0-46.27456 7.36768 215.62368 215.62368 0 0 0-40.13568 15.24736 229.7856 229.7856 0 0 0-37.248 23.31136l-6.50752 5.11488-1.5872 1.28-1.57696 1.3056-6.36928 5.43232-6.72768 6.0416-7.45472 6.96832-34.86208 33.85344-2.32448 2.21184c-16.8704 15.9744-29.45536 26.55232-43.93472 36.51584l-5.71904 3.84-15.09376 9.76896-2.17088 1.36704c-2.85184 1.792-5.5552 3.45088-8.11008 4.98176l-7.53152 4.34176 11.02336 4.3776 32.4352 12.1088 20.10112 7.1424 22.68672 7.38816 12.85632 3.95264 11.45856 3.26656 2.688 0.7168c2.65728 0.70656 5.2224 1.35168 7.72608 1.9456l9.72288 2.12992 2.36544 0.4608 2.34496 0.4352 9.35424 1.4848 2.3552 0.3072 2.37056 0.30208c30.6432 3.68128 57.8304 0.02048 83.98336-12.66176 33.47968-16.24064 49.3056-32.82944 71.41376-73.24672l7.2192-13.58336 11.38176-22.23104 4.99712-9.61536 1.536-2.93376c15.29344-28.96896 26.82368-46.68416 42.68032-63.05792l1.54624-1.5872-3.71712-1.42848-4.5568-1.63328-9.50784-3.1488-8.13056-2.42176-3.66592-0.96256a229.76512 229.76512 0 0 0-46.30016-6.656l-10.368-0.22016zM332.4672 272.64l9.1136 6.56384 12.90752 9.48224 5.1712 3.88096a809.55392 809.55392 0 0 1 42.68544 34.47808 730.65984 730.65984 0 0 1 55.808 53.9648c16.384 17.55136 30.5664 33.78176 43.63776 50.0224 10.24 12.71808 19.968 25.64096 29.50656 39.22432l11.19232 16.44032 18.08384 28.75904 11.2896-10.47552 17.11616-16.39424 9.8304-9.22112 12.94336-11.84256 3.00032-2.6624a403.51744 403.51744 0 0 1 25.61536-20.9408c7.12704-5.33504 15.616-10.56768 25.02656-15.50848a268.47744 268.47744 0 0 1 20.0192-9.4208l11.42272-4.51584 6.1952-2.05312-0.1536-0.91136-0.33792-1.37728c-1.42336-5.63712-3.82464-12.7744-7.00416-20.92032l-4.55168-11.1104-1.05472-2.4576c-7.1168-16.3584-15.64672-33.2544-22.03648-43.776l-12.83584-19.85536-7.08096-10.35264-1.2032-1.6896c-9.5488-13.27104-17.11616-21.36064-23.57248-24.32-4.35712-2.00192-8.14592-2.7648-14.73024-2.93888h-7.64416l-5.51936 0.08192-260.74624-0.03584-2.09408-0.11776z" fill="#3370FF" p-id="4831"></path></svg>`,
  }
  return icons[channelId] || icons.telegram
}

const getChannelComponent = (channelId: string) => {
  const components: Record<string, any> = {
    telegram: TelegramConfig,
    discord: DiscordConfig,
    qq: QQConfig,
    wechat: WeChatConfig,
    dingtalk: DingTalkConfig,
    feishu: FeishuConfig
  }
  return components[channelId] || null
}

const handleConfigUpdate = async (channelId: string, config: Record<string, any>) => {
  const success = await channelsStore.updateChannelConfig(channelId, config)
  if (success) {
    configChanged.value = true
    console.log('Configuration updated successfully')
  }
}

const handleTest = async (channelId: string, config?: Record<string, any>) => {
  testResult.value = await channelsStore.testChannel(channelId, config)
}

channelsStore.init()
</script>

<style scoped>
.channels-config {
  padding: 0;
}

/* 头部样式 */
.channels-header {
  margin-bottom: 24px;
  padding: 20px;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 12px;
}

.header-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 16px;
  flex-wrap: wrap; /* 允许换行 */
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1 1 auto; /* 允许伸缩 */
  min-width: 200px; /* 确保最小宽度，防止文字竖排 */
  max-width: 100%; /* 不超过容器宽度 */
  overflow: hidden;
}

.header-icon {
  width: 40px;
  height: 40px;
  background: linear-gradient(135deg, var(--primary-color) 0%, #4f46e5 100%);
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  flex-shrink: 0;
}

.header-text {
  flex: 1;
  min-width: 150px; /* 确保最小宽度 */
  display: flex;
  flex-direction: column;
  gap: 4px;
  overflow: hidden;
}

.channels-header h3 {
  font-size: 18px;
  font-weight: 600;
  margin: 0;
  color: var(--text-primary);
  line-height: 1.3;
  display: block;
  width: 100%;
  word-break: keep-all; /* 防止中文字符断开 */
  overflow-wrap: break-word; /* 允许长单词换行 */
  white-space: normal; /* 允许正常换行 */
}

.channels-description {
  font-size: 13px;
  margin: 0;
  color: var(--text-secondary);
  line-height: 1.4;
  display: block;
  width: 100%;
  word-break: keep-all; /* 防止中文字符断开 */
  overflow-wrap: break-word; /* 允许长单词换行 */
  white-space: normal; /* 允许正常换行 */
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
  flex-wrap: nowrap; /* 防止内部元素换行 */
  min-width: fit-content; /* 根据内容自适应 */
}

.status-summary {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 14px;
  background: var(--bg-secondary);
  border-radius: 8px;
  border: 1px solid var(--border-color);
  flex-wrap: nowrap; /* 防止换行 */
  white-space: nowrap; /* 防止文字换行 */
}

.status-item {
  display: flex;
  align-items: center;
  gap: 6px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-dot.running {
  background: #10b981;
  box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.2);
  animation: pulse-dot 2s ease-in-out infinite;
}

.status-dot.enabled {
  background: var(--primary-color);
}

@keyframes pulse-dot {
  0%, 100% { 
    box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.2);
  }
  50% { 
    box-shadow: 0 0 0 5px rgba(16, 185, 129, 0.1);
  }
}

.status-text {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
}

.status-divider {
  width: 1px;
  height: 16px;
  background: var(--border-color);
}

.refresh-button {
  width: 36px;
  height: 36px;
  padding: 0;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  cursor: pointer;
  color: var(--text-secondary);
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.refresh-button:hover {
  background: var(--bg-hover);
  color: var(--primary-color);
  border-color: var(--primary-color);
}

.refresh-button:active svg {
  animation: spin 0.5s ease-out;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.implementation-status {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px solid var(--border-color);
}

.status-badge {
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  line-height: 1;
}

.status-badge svg {
  flex-shrink: 0;
}

.status-badge.implemented {
  background: rgba(16, 185, 129, 0.1);
  color: #059669;
  border: 1px solid rgba(16, 185, 129, 0.2);
}

.status-badge.planned {
  background: rgba(107, 114, 128, 0.1);
  color: #6b7280;
  border: 1px solid rgba(107, 114, 128, 0.2);
}

/* 重启提示 */
.restart-notice {
  margin-top: 16px;
  padding: 16px 20px;
  background: linear-gradient(135deg, rgba(251, 191, 36, 0.1) 0%, rgba(245, 158, 11, 0.1) 100%);
  border: 1px solid rgba(251, 191, 36, 0.3);
  border-radius: 12px;
  display: flex;
  align-items: flex-start;
  gap: 14px;
  position: relative;
  overflow: hidden;
}

.restart-notice::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(90deg, #f59e0b, #fbbf24);
}

.notice-icon {
  width: 40px;
  height: 40px;
  background: rgba(251, 191, 36, 0.15);
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #f59e0b;
  flex-shrink: 0;
}

.notice-content {
  flex: 1;
  min-width: 0;
}

.notice-content strong {
  display: block;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.notice-content p {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0;
  line-height: 1.5;
}

.notice-close {
  width: 32px;
  height: 32px;
  background: rgba(0, 0, 0, 0.05);
  border: none;
  border-radius: 8px;
  cursor: pointer;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
  flex-shrink: 0;
}

.notice-close:hover {
  background: rgba(0, 0, 0, 0.1);
  color: var(--text-primary);
}

.loading-state,
.error-state {
  text-align: center;
  padding: 80px 20px;
}

.spinner {
  width: 48px;
  height: 48px;
  border: 4px solid var(--border-color);
  border-top-color: var(--primary-color);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin: 0 auto 20px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.error-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.retry-button {
  margin-top: 16px;
  padding: 10px 24px;
  background: var(--primary-color);
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 500;
  transition: all 0.2s;
}

.retry-button:hover {
  opacity: 0.9;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

/* 网格布局 */
.channels-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}

/* 卡片样式 */
.channel-card {
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  overflow: hidden;
  transition: all 0.2s ease;
  position: relative;
}

.channel-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: transparent;
  transition: all 0.2s;
}

.channel-card.is-running::before {
  background: linear-gradient(90deg, #10b981, #059669);
}

.channel-card.is-enabled::before {
  background: linear-gradient(90deg, var(--primary-color), #4f46e5);
}

.channel-card:hover {
  border-color: var(--primary-color);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}

.channel-card.is-expanded {
  border-color: var(--primary-color);
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.1);
}

.channel-card.is-recommended::after {
  content: '✓';
  position: absolute;
  top: 10px;
  right: 10px;
  width: 24px;
  height: 24px;
  background: linear-gradient(135deg, #10b981 0%, #059669 100%);
  color: white;
  font-size: 12px;
  font-weight: 700;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 6px rgba(16, 185, 129, 0.3);
  z-index: 1;
}

.channel-card.is-planned {
  opacity: 0.65;
}

.channel-card.is-planned::before {
  background: linear-gradient(90deg, #9ca3af, #6b7280);
}

.channel-card.is-planned:hover {
  opacity: 0.8;
}

/* 卡片头部 */
.card-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  cursor: pointer;
  user-select: none;
}

.channel-icon-box {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: transform 0.2s;
}

.channel-card:hover .channel-icon-box {
  transform: scale(1.05);
}

.icon-inner {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.icon-inner svg {
  width: 100%;
  height: 100%;
  filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.1));
}

/* 渠道图标背景 - 使用中性色 */
.icon-telegram { background: var(--bg-tertiary); }
.icon-discord { background: var(--bg-tertiary); }
.icon-qq { background: var(--bg-tertiary); }
.icon-wechat { background: var(--bg-tertiary); }
.icon-dingtalk { background: var(--bg-tertiary); }
.icon-feishu { background: var(--bg-tertiary); }

/* 渠道元信息 */
.channel-meta {
  flex: 1;
  min-width: 0;
}

.channel-name {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.channel-name h4 {
  font-size: 15px;
  font-weight: 600;
  margin: 0;
  color: var(--text-primary);
}

.channel-desc {
  font-size: 12px;
  color: var(--text-secondary);
  margin: 0;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* 徽章样式 */
.badge {
  padding: 3px 8px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  line-height: 1;
}

.badge-success {
  background: rgba(16, 185, 129, 0.12);
  color: #059669;
}

.badge-primary {
  background: rgba(59, 130, 246, 0.12);
  color: var(--primary-color);
}

.badge-secondary {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.pulse-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #10b981;
  animation: pulse 2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { 
    opacity: 1;
  }
  50% { 
    opacity: 0.5;
  }
}

/* 展开按钮 */
.expand-btn {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  border: none;
  background: var(--bg-secondary);
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
}

.expand-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.expand-btn svg {
  transition: transform 0.2s;
}

.expand-btn.is-expanded svg {
  transform: rotate(180deg);
}

/* 卡片主体 */
.card-body {
  border-top: 1px solid var(--border-color);
  background: var(--bg-secondary);
  overflow: hidden;
}

.card-body-inner {
  padding: 16px;
}

/* 计划中渠道提示 */
.planned-notice {
  padding: 32px 20px;
  text-align: center;
}

.planned-icon {
  width: 64px;
  height: 64px;
  margin: 0 auto 16px;
  background: var(--bg-tertiary);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
}

.planned-notice h4 {
  font-size: 16px;
  font-weight: 600;
  margin: 0 0 6px 0;
  color: var(--text-primary);
}

.planned-notice p {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0;
  line-height: 1.5;
}

/* 滑动动画 */
.slide-down-enter-active {
  transition: max-height 0.3s ease-out, opacity 0.2s ease-out 0.1s;
  overflow: hidden;
}

.slide-down-leave-active {
  transition: max-height 0.25s ease-in, opacity 0.15s ease-in;
  overflow: hidden;
}

.slide-down-enter-from {
  max-height: 0;
  opacity: 0;
}

.slide-down-enter-to {
  max-height: 800px;
  opacity: 1;
}

.slide-down-leave-from {
  max-height: 800px;
  opacity: 1;
}

.slide-down-leave-to {
  max-height: 0;
  opacity: 0;
}

/* 测试结果对话框 */
.test-result-modal {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 20px;
}

.test-result-content {
  background: var(--bg-primary);
  border-radius: 20px;
  max-width: 540px;
  width: 100%;
  max-height: 80vh;
  overflow: auto;
  box-shadow: 0 24px 64px rgba(0, 0, 0, 0.4);
}

.test-result-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 24px;
  border-bottom: 1px solid var(--border-color);
}

.header-icon-wrapper {
  width: 48px;
  height: 48px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.header-icon-wrapper.success {
  background: rgba(16, 185, 129, 0.1);
  color: #10b981;
}

.header-icon-wrapper.error {
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
}

.test-result-header h4 {
  font-size: 17px;
  font-weight: 600;
  margin: 0 0 4px 0;
  color: var(--text-primary);
}

.header-text {
  flex: 1;
  min-width: 0;
}

.test-message {
  font-size: 14px;
  color: var(--text-secondary);
  margin: 0;
}

.close-button {
  margin-left: auto;
  background: var(--bg-tertiary);
  border: none;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  cursor: pointer;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
  flex-shrink: 0;
}

.close-button:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.test-result-body {
  padding: 24px;
}

.result-info {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.info-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
}

.info-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  min-width: 60px;
}

.info-value {
  font-size: 14px;
  color: var(--text-primary);
  font-family: 'Monaco', 'Menlo', 'Consolas', monospace;
}

.status-badge {
  padding: 4px 12px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  font-family: inherit;
}

.status-badge.connected {
  background: rgba(16, 185, 129, 0.12);
  color: #059669;
}

.status-badge.configured {
  background: rgba(59, 130, 246, 0.12);
  color: var(--primary-color);
}

.info-note {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 16px;
  background: rgba(59, 130, 246, 0.08);
  border: 1px solid rgba(59, 130, 246, 0.2);
  border-radius: 8px;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.5;
}

.info-note svg {
  flex-shrink: 0;
  margin-top: 2px;
  color: var(--primary-color);
}

.test-result-body pre {
  margin: 0;
  padding: 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  font-size: 13px;
  color: var(--text-secondary);
  overflow-x: auto;
  font-family: 'Monaco', 'Menlo', 'Consolas', monospace;
  line-height: 1.6;
}

.modal-enter-active,
.modal-leave-active {
  transition: all 0.3s ease;
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}

.modal-enter-from .test-result-content,
.modal-leave-to .test-result-content {
  transform: scale(0.95) translateY(20px);
}

/* 响应式 - 使用更小的断点来适应侧边栏变化 */
@media (max-width: 1200px) {
  .header-top {
    gap: 16px;
  }
  
  .status-summary {
    padding: 6px 10px;
    gap: 8px;
  }
  
  .status-text {
    font-size: 12px;
  }
}

@media (max-width: 900px) {
  .header-top {
    flex-wrap: wrap;
    gap: 12px;
  }
  
  .header-left {
    flex: 1 1 100%;
    min-width: 100%;
  }
  
  .header-right {
    flex: 1 1 100%;
    width: 100%;
    justify-content: space-between;
  }
  
  .status-summary {
    flex: 1;
    min-width: 0;
  }
}

@media (max-width: 768px) {
  .channels-grid {
    grid-template-columns: 1fr;
    gap: 12px;
  }
  
  .channels-header {
    padding: 16px;
    margin-bottom: 16px;
  }
  
  .header-top {
    flex-direction: column;
    align-items: stretch;
    gap: 12px;
  }
  
  .header-left {
    gap: 10px;
    min-width: 100%; /* 小屏幕下占满宽度 */
  }
  
  .header-text {
    min-width: 0; /* 小屏幕下允许收缩 */
    flex: 1;
  }
  
  .header-icon {
    width: 36px;
    height: 36px;
    flex-shrink: 0; /* 防止图标被压缩 */
  }
  
  .header-text h3 {
    font-size: 16px;
  }
  
  .channels-description {
    display: none; /* 小屏幕隐藏描述 */
  }
  
  .header-right {
    display: flex; /* 确保flex布局 */
    align-items: center; /* 垂直居中 */
    width: 100%; /* 占满宽度 */
    justify-content: space-between;
    flex-wrap: nowrap; /* 防止换行 */
    gap: 12px; /* 保持间距 */
  }
  
  .status-summary {
    flex: 1;
    min-width: 0; /* 允许收缩 */
    padding: 8px 12px; /* 减小内边距 */
    gap: 10px; /* 减小间距 */
    display: flex; /* 确保flex布局 */
    align-items: center; /* 垂直居中 */
    flex-wrap: nowrap; /* 防止换行 */
  }
  
  .status-item {
    gap: 5px; /* 减小间距 */
    min-width: 0; /* 允许收缩 */
    display: flex; /* 确保flex布局 */
    align-items: center; /* 垂直居中 */
    flex-shrink: 1; /* 允许收缩 */
  }
  
  .status-text {
    font-size: 12px; /* 减小字体 */
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  
  .status-divider {
    flex-shrink: 0; /* 防止分隔线被压缩 */
  }
  
  .refresh-button {
    flex-shrink: 0; /* 防止按钮被压缩 */
  }

  .card-header {
    padding: 14px;
    gap: 10px;
  }

  .channel-icon-box {
    width: 44px;
    height: 44px;
  }

  .icon-inner {
    width: 26px;
    height: 26px;
  }
}

@media (max-width: 480px) {
  .channels-header h3 {
    font-size: 15px;
  }
  
  .channels-description {
    display: none; /* 确保隐藏 */
  }
  
  .header-right {
    display: flex; /* 确保flex布局 */
    align-items: center; /* 垂直居中 */
    gap: 8px; /* 进一步减小间距 */
    flex-wrap: nowrap; /* 防止换行 */
  }
  
  .status-summary {
    padding: 6px 10px; /* 进一步减小内边距 */
    gap: 8px;
    display: flex; /* 确保flex布局 */
    align-items: center; /* 垂直居中 */
    flex-wrap: nowrap; /* 防止换行 */
  }
  
  .status-item {
    gap: 4px;
    display: flex; /* 确保flex布局 */
    align-items: center; /* 垂直居中 */
    flex-shrink: 1; /* 允许收缩 */
  }
  
  .status-text {
    font-size: 11px; /* 进一步减小字体 */
    white-space: nowrap;
  }
  
  .status-dot {
    width: 6px; /* 减小圆点尺寸 */
    height: 6px;
    flex-shrink: 0; /* 防止圆点被压缩 */
  }
  
  .refresh-button {
    width: 32px; /* 减小按钮尺寸 */
    height: 32px;
    flex-shrink: 0; /* 防止按钮被压缩 */
  }
  
  .refresh-button svg {
    width: 14px;
    height: 14px;
  }
  
  .implementation-status {
    flex-direction: column;
    gap: 6px;
  }
  
  .status-badge {
    font-size: 11px;
    padding: 5px 10px;
  }

  .channel-card {
    border-radius: 10px;
  }

  .card-header {
    padding: 12px;
  }

  .channel-icon-box {
    width: 40px;
    height: 40px;
    border-radius: 10px;
  }

  .icon-inner {
    width: 24px;
    height: 24px;
  }

  .channel-name h4 {
    font-size: 14px;
  }

  .channel-desc {
    font-size: 11px;
  }
  
  .badge {
    font-size: 10px;
    padding: 2px 6px;
  }
}
</style>
