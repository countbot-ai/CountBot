/** 人设数据源：按身份分流到全局配置或用户配置 */

import { computed } from 'vue'
import { meAPI } from '@/api'
import { useSettingsStore } from '@/store/settings'
import { useUserStore } from '@/store/user'

export interface PersonaData {
  [key: string]: unknown
}

export function usePersonaSource() {
  const settingsStore = useSettingsStore()
  const userStore = useUserStore()

  /** 身份是否已就绪；分流必须以 loaded 为前提 */
  const identityReady = computed(() => userStore.loaded)

  /** 普通用户走用户接口；管理员走全局配置（由设置页统一提交） */
  const isUserScoped = computed(() => identityReady.value && !userStore.isAdmin)

  /** 确保身份已加载，供直接调用 load/save 的路径使用。 */
  async function ensureIdentity(): Promise<void> {
    if (!identityReady.value) {
      await userStore.loadProfile()
    }
  }

  /** 读当前生效的人设。 */
  async function load(): Promise<PersonaData> {
    await ensureIdentity()
    if (isUserScoped.value) {
      return (await meAPI.getPersona()) as PersonaData
    }
    return (settingsStore.settings?.persona || {}) as PersonaData
  }

  /** 保存人设：普通用户立即落库，管理员写入 store 待统一提交 */
  async function save(patch: PersonaData): Promise<void> {
    await ensureIdentity()
    if (isUserScoped.value) {
      await meAPI.updatePersona(patch)
      return
    }
    if (settingsStore.settings) {
      settingsStore.settings.persona = {
        ...settingsStore.settings.persona,
        ...patch,
      } as typeof settingsStore.settings.persona
    }
  }

  /** 立即落库，不等设置页保存按钮 */
  async function saveNow(patch: PersonaData): Promise<void> {
    await ensureIdentity()
    if (isUserScoped.value) {
      await meAPI.updatePersona(patch)
      return
    }
    // 全局配置是整体覆盖写入，必须带上现有字段，否则其余人设项会被清空
    const current = settingsStore.settings?.persona
    await settingsStore.saveSettings({
      persona: { ...(current || {}), ...patch },
    } as never)
  }

  return { identityReady, isUserScoped, ensureIdentity, load, save, saveNow }
}
