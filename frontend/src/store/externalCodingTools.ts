import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  settingsAPI,
  type ExternalCodingToolCheckResponse,
  type ExternalCodingToolProfile,
  type ExternalCodingToolsConfig
} from '@/api'

const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value))

export const useExternalCodingToolsStore = defineStore('externalCodingTools', () => {
  const config = ref<ExternalCodingToolsConfig | null>(null)
  const loading = ref(false)
  const saving = ref(false)
  const checking = ref<string | null>(null)
  const error = ref<string | null>(null)

  async function loadConfig(force = false) {
    if (config.value && !force) {
      return config.value
    }

    loading.value = true
    error.value = null
    try {
      const response = await settingsAPI.getExternalCodingTools()
      config.value = clone(response)
      return config.value
    } catch (err: any) {
      error.value = err.message || 'Failed to load external coding tools config'
      throw err
    } finally {
      loading.value = false
    }
  }

  async function saveConfig() {
    if (!config.value) {
      await loadConfig()
    }

    if (!config.value) {
      throw new Error('External coding tools config is empty')
    }

    saving.value = true
    error.value = null
    try {
      const response = await settingsAPI.updateExternalCodingTools(clone(config.value))
      config.value = clone(response)
      return config.value
    } catch (err: any) {
      error.value = err.message || 'Failed to save external coding tools config'
      throw err
    } finally {
      saving.value = false
    }
  }

  async function checkProfile(profile: ExternalCodingToolProfile): Promise<ExternalCodingToolCheckResponse> {
    checking.value = profile.name || 'profile'
    error.value = null
    try {
      return await settingsAPI.checkExternalCodingTool(clone(profile))
    } catch (err: any) {
      error.value = err.message || 'Failed to check external coding tool profile'
      throw err
    } finally {
      checking.value = null
    }
  }

  function createEmptyProfile(): ExternalCodingToolProfile {
    return {
      name: '',
      aliases: [],
      type: 'cli',
      icon_svg: '',
      enabled: false,
      description: '',
      command: '',
      args: [],
      working_dir: '',
      stdin_template: null,
      env: {},
      inherit_env: [],
      session_mode: 'history',
      history_message_count: 10,
      timeout: 900,
      success_exit_codes: [0]
    }
  }

  function addProfile() {
    if (!config.value) {
      config.value = { version: 1, profiles: [] }
    }
    config.value.profiles.push(createEmptyProfile())
  }

  function removeProfile(index: number) {
    config.value?.profiles.splice(index, 1)
  }

  return {
    config,
    loading,
    saving,
    checking,
    error,
    loadConfig,
    saveConfig,
    checkProfile,
    createEmptyProfile,
    addProfile,
    removeProfile
  }
})
