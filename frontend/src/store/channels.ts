/**
 * 渠道管理 Store
 * 
 * Channels Management Store
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Ref } from 'vue'

export interface ChannelConfig {
  name: string
  description: string
  icon: string
  enabled: boolean
  configured: boolean
  config: Record<string, any>
}

export interface ChannelStatus {
  enabled: boolean
  running: boolean
  display_name: string
}

export const useChannelsStore = defineStore('channels', () => {
  // 状态
  const channels: Ref<Record<string, ChannelConfig>> = ref({})
  const status: Ref<Record<string, ChannelStatus>> = ref({})
  const loading = ref(false)
  const error: Ref<string | null> = ref(null)

  // 计算属性
  const enabledChannels = computed(() => {
    return Object.entries(channels.value)
      .filter(([_, channel]) => channel.enabled)
      .map(([id, channel]) => ({ id, ...channel }))
  })

  const configuredChannels = computed(() => {
    return Object.entries(channels.value)
      .filter(([_, channel]) => channel.configured)
      .map(([id, channel]) => ({ id, ...channel }))
  })

  const runningChannels = computed(() => {
    return Object.entries(status.value)
      .filter(([_, s]) => s.running)
      .map(([id, s]) => ({ id, ...s }))
  })

  // 方法
  async function fetchChannels() {
    loading.value = true
    error.value = null

    try {
      const response = await fetch('/api/channels/list')
      const data = await response.json()

      if (data.success) {
        channels.value = data.channels
        
        // 为每个渠道获取完整配置（替换截断的数据）
        const channelIds = Object.keys(data.channels)
        await Promise.all(
          channelIds.map(async (channelId) => {
            try {
              const configResponse = await fetch(`/api/channels/${channelId}/config`)
              const configData = await configResponse.json()
              
              if (configData.success && configData.config) {
                // 用完整配置替换截断的配置
                channels.value[channelId].config = configData.config
              }
            } catch (e) {
              console.error(`Failed to fetch full config for ${channelId}:`, e)
              // 保留截断的配置，不影响其他渠道
            }
          })
        )
      } else {
        error.value = data.error || 'Failed to fetch channels'
      }
    } catch (e: any) {
      error.value = e.message || 'Network error'
      console.error('Error fetching channels:', e)
    } finally {
      loading.value = false
    }
  }

  async function fetchStatus() {
    try {
      const response = await fetch('/api/channels/status')
      const data = await response.json()

      if (data.success) {
        status.value = data.status
      }
    } catch (e: any) {
      console.error('Error fetching channel status:', e)
    }
  }

  async function testChannel(channelId: string, config?: Record<string, any>): Promise<{ success: boolean; message: string; data?: any }> {
    loading.value = true
    error.value = null

    try {
      const response = await fetch('/api/channels/test', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ 
          channel: channelId,
          config: config // 传递用户输入的配置
        })
      })

      const data = await response.json()
      return data
    } catch (e: any) {
      error.value = e.message || 'Test failed'
      return {
        success: false,
        message: e.message || 'Network error'
      }
    } finally {
      loading.value = false
    }
  }

  async function updateChannelConfig(channelId: string, config: Record<string, any>): Promise<boolean> {
    loading.value = true
    error.value = null

    try {
      const response = await fetch('/api/channels/update', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          channel: channelId,
          config
        })
      })

      const data = await response.json()

      if (data.success) {
        // 重新获取渠道列表
        await fetchChannels()
        return true
      } else {
        error.value = data.message || 'Update failed'
        return false
      }
    } catch (e: any) {
      error.value = e.message || 'Network error'
      console.error('Error updating channel config:', e)
      return false
    } finally {
      loading.value = false
    }
  }

  async function getChannelConfig(channelId: string): Promise<Record<string, any> | null> {
    try {
      const response = await fetch(`/api/channels/${channelId}/config`)
      const data = await response.json()

      if (data.success) {
        return data.config
      }
      return null
    } catch (e: any) {
      console.error('Error getting channel config:', e)
      return null
    }
  }

  // 初始化
  function init() {
    fetchChannels()
    fetchStatus()

    // 定期更新状态
    setInterval(() => {
      fetchStatus()
    }, 10000) // 每 10 秒更新一次
  }

  return {
    // 状态
    channels,
    status,
    loading,
    error,

    // 计算属性
    enabledChannels,
    configuredChannels,
    runningChannels,

    // 方法
    fetchChannels,
    fetchStatus,
    testChannel,
    updateChannelConfig,
    getChannelConfig,
    init
  }
})
