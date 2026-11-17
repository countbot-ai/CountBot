<template>
  <SettingsCard :title="$t('settings.general.appearanceCard')">
    <SettingsRow
      :label="$t('settings.general.theme')"
      :description="$t('settings.general.themeDesc')"
      layout="block"
    >
      <div class="theme-grid">
        <button
          v-for="theme in themes"
          :key="theme.value"
          class="theme-tile"
          :class="{ 'is-active': themePreset === theme.value }"
          :aria-pressed="themePreset === theme.value"
          @click="setThemePreset(theme.value)"
        >
          <component :is="theme.icon" :size="16" class="theme-tile-icon" />
          <span class="theme-tile-label">{{ $t(theme.label) }}</span>
        </button>
      </div>
    </SettingsRow>

    <SettingsRow
      :label="$t('settings.general.language')"
      :description="$t('settings.general.languageDesc')"
    >
      <div class="co-segmented">
        <button
          v-for="lang in languages"
          :key="lang.value"
          class="co-segmented-item"
          :class="{ 'is-active': currentLocale === lang.value }"
          @click="setLanguage(lang.value)"
        >
          {{ lang.label }}
        </button>
      </div>
    </SettingsRow>

    <SettingsRow
      :label="$t('settings.general.outputLanguage')"
      :description="$t('settings.general.outputLanguageDesc')"
      :hint="$t('settings.general.outputLanguageHint')"
      wide-control
    >
      <OutputLanguageSelect v-model="outputLanguage" />
    </SettingsRow>
  </SettingsCard>

  <ConversationHistorySettings
    v-model:max-history-messages="maxHistoryMessages"
    v-model:enable-short-context-summary="enableShortContextSummary"
  />
</template>

<script setup lang="ts">
import { computed, ref, watch, type Component } from 'vue'
import {
  Sun as SunIcon,
  Moon as MoonIcon,
  Monitor as MonitorIcon,
  Snowflake as SnowflakeIcon,
  Trees as TreesIcon,
  Flower2 as Flower2Icon,
} from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { setLocale } from '@/i18n'
import { useTheme } from '@/composables/useTheme'
import type { ThemePreset } from '@/i18n/utils/detector'
import { useSettingsStore } from '@/store/settings'
import { usePersonaSource } from '@/composables/usePersonaSource'
import { SettingsCard, SettingsRow, OutputLanguageSelect, ConversationHistorySettings } from './ui'

const { locale } = useI18n()
const { themePreset, setThemePreset } = useTheme()
const settingsStore = useSettingsStore()
// 输出语言属于用户人设：管理员改全局配置，普通用户改自己的配置
const personaSource = usePersonaSource()

const currentLocale = computed(() => locale.value)

/** 普通用户的输出语言存在本地（全局配置不可读），管理员沿用全局草稿 */
const localOutputLanguage = ref('中文')
const localMaxHistoryMessages = ref(0)
const localShortContextSummary = ref(false)

const normalizeHistoryLimit = (value?: number | null) => {
  if (typeof value !== 'number' || Number.isNaN(value)) return 0
  return value <= 0 ? 0 : value
}

const maxHistoryMessages = computed({
  get: () =>
    personaSource.isUserScoped.value
      ? localMaxHistoryMessages.value
      : normalizeHistoryLimit(settingsStore.settings?.persona.max_history_messages),
  set: (value: number) => {
    const normalized = normalizeHistoryLimit(value)
    if (personaSource.isUserScoped.value) {
      localMaxHistoryMessages.value = normalized
      return
    }
    if (settingsStore.settings) {
      settingsStore.settings.persona.max_history_messages = normalized
    }
  },
})

const enableShortContextSummary = computed({
  get: () =>
    personaSource.isUserScoped.value
      ? localShortContextSummary.value
      : Boolean(settingsStore.settings?.persona.enable_short_context_summary),
  set: (value: boolean) => {
    if (personaSource.isUserScoped.value) {
      localShortContextSummary.value = value
      return
    }
    if (settingsStore.settings) {
      settingsStore.settings.persona.enable_short_context_summary = value
    }
  },
})

const outputLanguage = computed({
  get: () =>
    personaSource.isUserScoped.value
      ? localOutputLanguage.value
      : settingsStore.settings?.persona.output_language || '中文',
  set: (value: string) => {
    if (personaSource.isUserScoped.value) {
      localOutputLanguage.value = value
      return
    }
    if (settingsStore.settings) {
      settingsStore.settings.persona.output_language = value
    }
  },
})

// 输出语言归属用户人设，身份异步到位，用 watch 跟踪角色确定数据来源
watch(
  () => personaSource.isUserScoped.value,
  async (scoped) => {
    if (!scoped) return
    try {
      const persona = await personaSource.load()
      localOutputLanguage.value = String(persona.output_language || '中文')
      localMaxHistoryMessages.value = normalizeHistoryLimit(
        persona.max_history_messages as number | null | undefined,
      )
      localShortContextSummary.value = Boolean(persona.enable_short_context_summary)
    } catch (error) {
      console.error('Failed to load persona settings:', error)
    }
  },
  { immediate: true },
)

interface ThemeOption {
  value: ThemePreset
  label: string
  icon: Component
}

const themes: ThemeOption[] = [
  { value: 'light', label: 'settings.general.lightTheme', icon: SunIcon },
  { value: 'dark', label: 'settings.general.darkTheme', icon: MoonIcon },
  { value: 'auto', label: 'settings.general.autoTheme', icon: MonitorIcon },
  { value: 'cool', label: 'settings.general.coolTheme', icon: SnowflakeIcon },
  { value: 'forest', label: 'settings.general.forestTheme', icon: TreesIcon },
  { value: 'sakura', label: 'settings.general.sakuraTheme', icon: Flower2Icon },
]

const languages = [
  { value: 'zh-CN', label: '简体中文' },
  { value: 'en-US', label: 'English' },
]

/** 统一走 i18n 入口，同步 locale、localStorage 与 <html lang> */
function setLanguage(lang: string) {
  setLocale(lang === 'zh-CN' ? 'zh-CN' : 'en-US')
}

// 输出语言留空会让注入的提示词带上空字符串，回落到中文
watch(
  () => (personaSource.isUserScoped.value ? localOutputLanguage.value : settingsStore.settings?.persona.output_language),
  (value) => {
    if (personaSource.isUserScoped.value) {
      if (!value?.trim()) localOutputLanguage.value = '中文'
      return
    }
    if (settingsStore.settings?.persona && !value?.trim()) {
      settingsStore.settings.persona.output_language = '中文'
    }
  },
  { immediate: true },
)
/** 保存通用设置：普通用户的输出语言与历史条数在此落库，管理员已写入全局草稿 */
async function saveConfig(): Promise<boolean> {
  if (personaSource.isUserScoped.value) {
    await personaSource.save({
      output_language: localOutputLanguage.value || '中文',
      max_history_messages: normalizeHistoryLimit(localMaxHistoryMessages.value),
      enable_short_context_summary: localShortContextSummary.value,
    })
  }
  return true
}

defineExpose({ saveConfig })
</script>

<style scoped>
.theme-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(132px, 1fr));
  gap: 8px;
}

.theme-tile {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 36px;
  padding: 0 12px;
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-md);
  background: var(--color-bg-secondary);
  color: var(--color-text-secondary);
  font-family: inherit;
  font-size: var(--font-size-sm);
  text-align: left;
  cursor: pointer;
  transition:
    border-color var(--transition-fast),
    background var(--transition-fast),
    color var(--transition-fast);
}

.theme-tile:hover {
  border-color: var(--color-border-secondary);
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
}

/* 选中态只用边框与文字层级表达，不加彩色填充 */
.theme-tile.is-active {
  border-color: var(--color-border-strong);
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
  font-weight: var(--font-weight-medium);
}

.theme-tile-icon {
  flex-shrink: 0;
}

.theme-tile-label {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
