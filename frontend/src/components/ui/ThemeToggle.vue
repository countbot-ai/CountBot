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
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s ease;
  position: relative;
  overflow: hidden;
}

.toggle-btn:hover {
  background: var(--hover-bg);
  border-color: var(--border-color);
  color: var(--text-primary);
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
