<template>
  <div class="welcome-guide">
    <div class="welcome-hero">
      <div class="welcome-icon">
        <!-- 自定义图标：传入 iconSvg prop 即可替换，否则显示默认图标 -->
        <span v-if="iconSvg" class="welcome-icon-custom" v-html="iconSvg" />
<svg t="1773210500269" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="1799" width="200" height="200"><path d="M595.6 87.4C585.8 51.3 552.9 25 513.5 25s-72.2 22.9-82.1 59c-9.8 39.4 6.5 72.3 49.2 95.3 6.5 3.3 19.7 9.8 19.7 16.4v75.5h26.3v-68.9c0-9.8 9.8-19.7 19.7-23 42.7-19.7 59.1-52.6 49.3-91.9z m112.7 185.5c40.1 0 78.6 15.9 107 44.3 28.4 28.4 44.3 66.9 44.3 107v259.5c0 40.1-16 78.6-44.3 107s-66.9 44.3-107 44.3H319.6c-40.1 0-78.6-15.9-107-44.3s-44.3-66.9-44.3-107V424.2c0-40.1 16-78.6 44.3-107 28.4-28.4 66.9-44.3 107-44.3h388.7z m0 72H319.6c-21 0-41.2 8.3-56.1 23.2-14.9 14.9-23.2 35.1-23.2 56.1v249.5c0 21 8.4 41.2 23.2 56.1 14.9 14.9 35 23.2 56.1 23.2h388.7c21 0 41.2-8.3 56.1-23.2 14.9-14.9 23.2-35.1 23.2-56.1V424.2c0-21-8.4-41.2-23.2-56.1-14.9-14.9-35-23.2-56.1-23.2z m-62.7 169.5c17.5 0 31.2 14.8 29.9 32.2L667.9 649c-1.2 15.7-14.2 27.8-29.9 27.8h-2.8c-8.4 0-16.3-3.5-22-9.6s-8.6-14.3-7.9-22.7l7.6-102.4c1.2-15.7 14.2-27.8 30-27.8h2.8z m-157.2-78.3c18 0 33.7 12 38.6 29.3l50.8 183c1.7 6 0.4 12.5-3.4 17.4-3.8 5-9.7 7.9-15.9 7.9h-18.8c-8.8 0-16.6-5.8-19.1-14.3l-43-141.8c-0.6-2-2.3-3.5-4.4-3.6-2.1-0.2-4.1 1-4.9 2.9l-45.1 95.5c-1.6 3.3 0.8 7.1 4.5 7.1h38.6c7.5 0 12.3 8 8.8 14.7l-8 15.1c-6.9 13.1-20.5 21.3-35.3 21.3h-52.6c-10.2 0-19.7-5.1-25.2-13.7-5.5-8.5-6.4-19.3-2.2-28.6l75.6-168.7c6.5-14.4 20.7-23.6 36.5-23.6h24.7z m171.5-15c16 2 24 16.1 24 42.1V481c0.1 5.2-3.9 9.6-9.1 9.9-20.9 1.1-34.9-0.1-41.9-3.6-12-6-21-21.1-18-36.1 3-15.1 21-33.1 45-30.1z m252.4 228.3c59.1 3.3 111.7-49.2 111.7-108.2S971.4 436 912.3 439.3v210.1z m-800.6 0.1V439.3C46 442.6 0 488.6 0 547.6c3.3 55.8 52.6 101.8 111.7 101.8z m165.5 261.4h469.5c29.7 0 44.5 12 44.5 36s-14.8 36-44.5 36H277.2c-29.7 0-44.5-12-44.5-36s14.8-36 44.5-36z" p-id="1800" fill="#8a8a8a"></path></svg>
      </div>
      <h1 class="welcome-title">欢迎使用 CountBot</h1>
      <p class="welcome-subtitle">开始与 AI 助手对话，或点击下方快速配置</p>
    </div>

    <div class="quick-actions">
      <button class="action-card" @click="$emit('open-settings', 'provider')">
        <div class="action-icon">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <rect width="20" height="8" x="2" y="2" rx="2" ry="2" />
            <rect width="20" height="8" x="2" y="14" rx="2" ry="2" />
            <line x1="6" x2="6.01" y1="6" y2="6" />
            <line x1="6" x2="6.01" y1="18" y2="18" />
          </svg>
        </div>
        <div class="action-content">
          <h3 class="action-title">配置模型 API</h3>
          <p class="action-desc">设置 OpenAI、Claude 等 AI 模型</p>
        </div>
        <div class="action-arrow">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="m9 18 6-6-6-6" />
          </svg>
        </div>
      </button>

      <button class="action-card" @click="$emit('open-settings', 'channels')">
        <div class="action-icon">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <rect width="7" height="7" x="3" y="3" rx="1" />
            <rect width="7" height="7" x="14" y="3" rx="1" />
            <rect width="7" height="7" x="14" y="14" rx="1" />
            <rect width="7" height="7" x="3" y="14" rx="1" />
          </svg>
        </div>
        <div class="action-content">
          <h3 class="action-title">配置渠道</h3>
          <p class="action-desc">连接微博、钉钉、飞书等平台</p>
        </div>
        <div class="action-arrow">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="m9 18 6-6-6-6" />
          </svg>
        </div>
      </button>

      <button class="action-card" @click="$emit('open-settings', 'personality')">
        <div class="action-icon">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" />
            <circle cx="12" cy="7" r="4" />
          </svg>
        </div>
        <div class="action-content">
          <h3 class="action-title">配置性格</h3>
          <p class="action-desc">自定义 AI 助手的个性和行为</p>
        </div>
        <div class="action-arrow">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="m9 18 6-6-6-6" />
          </svg>
        </div>
      </button>

      <button class="action-card" @click="$emit('open-settings', 'teams')">
        <div class="action-icon">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
            <circle cx="9" cy="7" r="4" />
            <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
            <path d="M16 3.13a4 4 0 0 1 0 7.75" />
          </svg>
        </div>
        <div class="action-content">
          <h3 class="action-title">多智能体</h3>
          <p class="action-desc">配置多个 AI 协作完成任务</p>
        </div>
        <div class="action-arrow">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="m9 18 6-6-6-6" />
          </svg>
        </div>
      </button>
    </div>

    <div class="welcome-footer">
      <p class="footer-text">在下方输入框开始对话</p>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  /** 传入自定义 SVG 字符串，留空则显示默认图标 */
  iconSvg?: string
}>()

defineEmits<{
  'open-settings': [section: string]
}>()
</script>
<style scoped>
@import './styles/WelcomeGuide.css';
</style>