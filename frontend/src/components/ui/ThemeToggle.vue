<template>
  <div class="theme-toggle">
    <button
      class="toggle-btn"
      :class="{ 'is-dark': theme === 'dark' }"
      :title="$t('settings.toggleTheme')"
      @click="toggleTheme"
    >
      <transition name="theme-icon" mode="out-in">
        <component :is="themeIcon" :size="18" :key="theme" class="icon" />
      </transition>
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Sun, Moon } from 'lucide-vue-next'
import { useTheme } from '@/composables/useTheme'

const { theme, toggleTheme } = useTheme()

const themeIcon = computed(() => theme.value === 'light' ? Moon : Sun)
</script>

<style scoped>
.theme-toggle {
  display: flex;
  align-items: center;
}

.toggle-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  padding: 0;
  border: 1px solid transparent;
  border-radius: var(--radius-md, 8px);
  background: transparent;
  color: var(--text-secondary, #6b7280);
  cursor: pointer;
  transition: all 0.15s ease;
  position: relative;
  overflow: hidden;
}

.toggle-btn:hover {
  background: var(--hover-bg, #f3f4f6);
  border-color: var(--border-color, #e5e7eb);
  color: var(--text-primary, #1f2937);
}

.toggle-btn:active {
  transform: scale(0.92);
}

.icon {
  transition: transform 0.2s ease;
}

.toggle-btn:hover .icon {
  transform: rotate(15deg) scale(1.1);
}

/* 深色模式 */
:root[data-theme="dark"] .toggle-btn {
  color: var(--text-secondary, #9ca3af);
}

:root[data-theme="dark"] .toggle-btn:hover {
  background: rgba(0, 240, 255, 0.1);
  border-color: rgba(0, 240, 255, 0.2);
  color: #00f0ff;
}

/* 主题图标切换动画 */
.theme-icon-enter-active,
.theme-icon-leave-active {
  transition: all 0.2s ease;
}

.theme-icon-enter-from {
  opacity: 0;
  transform: rotate(-90deg) scale(0.5);
}

.theme-icon-leave-to {
  opacity: 0;
  transform: rotate(90deg) scale(0.5);
}

.theme-icon-enter-to,
.theme-icon-leave-from {
  opacity: 1;
  transform: rotate(0deg) scale(1);
}
</style>
