<template>
  <div class="general-config">
    <div class="section-header">
      <h3 class="section-title">
        {{ $t('settings.general.title') }}
      </h3>
      <p class="section-desc">
        {{ $t('settings.general.description') }}
      </p>
    </div>

    <div class="config-options">
      <!-- 主题设置 -->
      <div class="config-card">
        <div class="card-header">
          <div class="header-left">
            <component
              :is="currentTheme === 'dark' ? MoonIcon : SunIcon"
              :size="20"
              class="icon"
            />
            <div class="header-text">
              <h4 class="card-title">{{ $t('settings.general.theme') }}</h4>
              <p class="card-desc">{{ $t('settings.general.themeDesc') }}</p>
            </div>
          </div>
        </div>
        <div class="card-body">
          <div class="theme-options">
            <button
              v-for="theme in themes"
              :key="theme.value"
              class="theme-btn"
              :class="{ active: currentTheme === theme.value }"
              @click="setTheme(theme.value)"
            >
              <component :is="theme.icon" :size="18" />
              <span>{{ $t(theme.label) }}</span>
            </button>
          </div>
        </div>
      </div>

      <!-- 语言设置 -->
      <div class="config-card">
        <div class="card-header">
          <div class="header-left">
            <component
              :is="LanguagesIcon"
              :size="20"
              class="icon"
            />
            <div class="header-text">
              <h4 class="card-title">{{ $t('settings.general.language') }}</h4>
              <p class="card-desc">{{ $t('settings.general.languageDesc') }}</p>
            </div>
          </div>
        </div>
        <div class="card-body">
          <div class="language-options">
            <button
              v-for="lang in languages"
              :key="lang.value"
              class="language-btn"
              :class="{ active: currentLocale === lang.value }"
              @click="setLanguage(lang.value)"
            >
              <span class="language-flag">{{ lang.flag }}</span>
              <span class="language-name">{{ lang.label }}</span>
            </button>
          </div>
        </div>
      </div>

      <div class="config-card">
        <div class="card-header">
          <div class="header-left">
            <component
              :is="LanguagesIcon"
              :size="20"
              class="icon"
            />
            <div class="header-text">
              <h4 class="card-title">{{ $t('settings.general.outputLanguage') }}</h4>
              <p class="card-desc">{{ $t('settings.general.outputLanguageDesc') }}</p>
            </div>
          </div>
        </div>
        <div class="card-body">
          <Input
            v-model="outputLanguage"
            type="text"
            :placeholder="$t('settings.general.outputLanguagePlaceholder')"
            :hint="$t('settings.general.outputLanguageHint')"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, watch, type Component } from 'vue'
import {
  Sun as SunIcon,
  Moon as MoonIcon,
  Monitor as MonitorIcon,
  Languages as LanguagesIcon
} from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import Input from '@/components/ui/Input.vue'
import { useTheme } from '@/composables/useTheme'
import { useSettingsStore } from '@/store/settings'

const { locale } = useI18n()
const { themeMode, setThemeMode } = useTheme()
const settingsStore = useSettingsStore()

const currentTheme = computed(() => themeMode.value)
const currentLocale = computed(() => locale.value)
const outputLanguage = computed({
  get: () => settingsStore.settings?.persona.output_language || '中文',
  set: (value: string) => {
    if (settingsStore.settings) {
      settingsStore.settings.persona.output_language = value
    }
  }
})

type ThemeOption = {
  value: 'light' | 'dark' | 'auto'
  label: string
  icon: Component
}

const themes: ThemeOption[] = [
  { value: 'light', label: 'settings.general.lightTheme', icon: SunIcon },
  { value: 'dark', label: 'settings.general.darkTheme', icon: MoonIcon },
  { value: 'auto', label: 'settings.general.autoTheme', icon: MonitorIcon }
]

const languages = [
  { value: 'zh-CN', label: '简体中文', flag: '🇨🇳' },
  { value: 'en', label: 'English', flag: '🇺🇸' }
]

function setTheme(theme: 'light' | 'dark' | 'auto') {
  setThemeMode(theme)
}

function setLanguage(lang: string) {
  locale.value = lang
  localStorage.setItem('locale', lang)
}

watch(
  () => settingsStore.settings?.persona.output_language,
  (value) => {
    if (settingsStore.settings?.persona && !value?.trim()) {
      settingsStore.settings.persona.output_language = '中文'
    }
  },
  { immediate: true }
)
</script>

<style scoped>
.general-config {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xl);
  padding: var(--spacing-md);
}

.section-header {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.section-title {
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin: 0;
}

.section-desc {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  margin: 0;
  line-height: var(--line-height-relaxed);
}

.config-options {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.config-card {
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-lg);
  overflow: hidden;
  transition: all var(--transition-base);
}

.config-card:hover {
  border-color: var(--color-border-secondary);
  box-shadow: var(--shadow-sm);
}

.card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: var(--spacing-lg);
  gap: var(--spacing-md);
}

.header-left {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-md);
  flex: 1;
  min-width: 0;
}

.icon {
  flex-shrink: 0;
  color: var(--color-primary);
  margin-top: 2px;
}

.header-text {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
  flex: 1;
  min-width: 0;
}

.card-title {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
  margin: 0;
}

.card-desc {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  margin: 0;
  line-height: var(--line-height-normal);
}

.card-body {
  border-top: 1px solid var(--color-border-primary);
  padding: var(--spacing-lg);
  background: var(--color-bg-secondary);
}

/* 主题选项 */
.theme-options {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: var(--spacing-sm);
}

.theme-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-md);
  background: var(--color-bg-primary);
  border: 2px solid var(--color-border-primary);
  border-radius: var(--radius-md);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--transition-base);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
}

.theme-btn:hover {
  border-color: var(--color-border-secondary);
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
  transform: translateY(-2px);
  box-shadow: var(--shadow-sm);
}

.theme-btn.active {
  border-color: var(--color-primary);
  background: var(--color-primary-light);
  color: var(--color-primary);
}

.theme-btn.active:hover {
  transform: translateY(-2px);
}

/* 语言选项 */
.language-options {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: var(--spacing-sm);
}

.language-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-md);
  background: var(--color-bg-primary);
  border: 2px solid var(--color-border-primary);
  border-radius: var(--radius-md);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--transition-base);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
}

.language-btn:hover {
  border-color: var(--color-border-secondary);
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
  transform: translateY(-2px);
  box-shadow: var(--shadow-sm);
}

.language-btn.active {
  border-color: var(--color-primary);
  background: var(--color-primary-light);
  color: var(--color-primary);
}

.language-btn.active:hover {
  transform: translateY(-2px);
}

.language-flag {
  font-size: 24px;
  line-height: 1;
}

.language-name {
  flex: 1;
  text-align: left;
}

/* 响应式 */
@media (max-width: 768px) {
  .theme-options,
  .language-options {
    grid-template-columns: 1fr;
  }
}
</style>
