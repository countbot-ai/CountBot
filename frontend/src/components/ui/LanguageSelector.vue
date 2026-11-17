<template>
  <div class="language-selector">
    <button
      class="selector-btn"
      :title="$t('settings.changeLanguage')"
      @click="toggleLanguage"
    >
      <component :is="Globe2Icon" :size="18" class="icon" />
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Globe2 as Globe2Icon } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'

const { locale } = useI18n()

const currentLanguageLabel = computed(() => locale.value === 'zh-CN' ? '中文' : 'EN')

const toggleLanguage = () => {
  locale.value = locale.value === 'zh-CN' ? 'en-US' : 'zh-CN'
  localStorage.setItem('CountBot-language', locale.value)
}
</script>

<style scoped>
.language-selector {
  display: flex;
  align-items: center;
}

.selector-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  padding: 0;
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s ease;
}

.selector-btn:hover {
  background: var(--hover-bg);
  border-color: var(--border-color);
  color: var(--text-primary);
}

.selector-btn:active {
  transform: scale(0.92);
}

.icon {
  flex-shrink: 0;
  transition: transform 0.2s ease;
}

.selector-btn:hover .icon {
  transform: rotate(15deg) scale(1.1);
}

/* 深色模式 */



</style>
