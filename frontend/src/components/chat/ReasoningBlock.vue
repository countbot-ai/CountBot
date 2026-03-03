<template>
  <div class="reasoning-block" :class="{ 'is-expanded': isExpanded }">
    <!-- 头部：可点击展开/折叠 -->
    <div class="reasoning-header" @click="toggleExpand">
      <div class="reasoning-icon">
        <svg
          class="icon-thinking"
          :class="{ 'is-spinning': isThinking }"
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
        >
          <circle cx="12" cy="12" r="10" />
          <path d="M12 6v6l4 2" />
        </svg>
      </div>
      
      <div class="reasoning-title">
        <span class="title-text">{{ $t('chat.reasoning.title') }}</span>
        <span class="reasoning-length">{{ contentLength }} {{ $t('chat.reasoning.chars') }}</span>
      </div>
      
      <div class="reasoning-toggle">
        <svg
          class="icon-chevron"
          :class="{ 'is-rotated': isExpanded }"
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </div>
    </div>
    
    <!-- 内容：可展开/折叠 -->
    <transition name="reasoning-expand">
      <div v-if="isExpanded" class="reasoning-content">
        <div class="reasoning-text">
          {{ content }}
        </div>
        
        <!-- 底部操作栏 -->
        <div class="reasoning-actions">
          <button
            class="action-button"
            @click.stop="copyContent"
            :title="$t('chat.reasoning.copy')"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
            </svg>
            <span>{{ $t('chat.reasoning.copy') }}</span>
          </button>
          
          <button
            class="action-button"
            @click.stop="toggleExpand"
            :title="$t('chat.reasoning.collapse')"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="18 15 12 9 6 15" />
            </svg>
            <span>{{ $t('chat.reasoning.collapse') }}</span>
          </button>
        </div>
      </div>
    </transition>
    
    <!-- 折叠时的预览 -->
    <div v-if="!isExpanded" class="reasoning-preview">
      {{ previewText }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'

interface Props {
  content: string
  isThinking?: boolean
  defaultExpanded?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  isThinking: false,
  defaultExpanded: false,
})

const { t } = useI18n()

// 状态
const isExpanded = ref(props.defaultExpanded)

// 计算属性
const contentLength = computed(() => {
  return props.content.length
})

const previewText = computed(() => {
  const maxLength = 100
  if (props.content.length <= maxLength) {
    return props.content
  }
  return props.content.substring(0, maxLength) + '...'
})

// 方法
const toggleExpand = () => {
  isExpanded.value = !isExpanded.value
}

const copyContent = async () => {
  try {
    await navigator.clipboard.writeText(props.content)
    // 可以添加一个提示
    console.log('Reasoning content copied to clipboard')
  } catch (err) {
    console.error('Failed to copy reasoning content:', err)
  }
}
</script>

<style scoped>
.reasoning-block {
  margin: 8px 0;
  border-radius: 8px;
  background: linear-gradient(135deg, #667eea15 0%, #764ba215 100%);
  border: 1px solid var(--color-border-light);
  overflow: hidden;
  transition: all 0.3s ease;
}

.reasoning-block:hover {
  border-color: var(--color-primary);
  box-shadow: 0 2px 8px rgba(102, 126, 234, 0.1);
}

.reasoning-block.is-expanded {
  background: linear-gradient(135deg, #667eea20 0%, #764ba220 100%);
}

/* 头部 */
.reasoning-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  cursor: pointer;
  user-select: none;
  transition: background-color 0.2s ease;
}

.reasoning-header:hover {
  background-color: rgba(102, 126, 234, 0.05);
}

.reasoning-icon {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.icon-thinking {
  transition: transform 0.3s ease;
}

.icon-thinking.is-spinning {
  animation: spin 2s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.reasoning-title {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-primary);
}

.title-text {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  font-weight: 600;
}

.reasoning-length {
  font-size: 11px;
  color: var(--color-text-tertiary);
  padding: 2px 6px;
  background-color: rgba(102, 126, 234, 0.1);
  border-radius: 4px;
}

.reasoning-toggle {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  color: var(--color-text-secondary);
}

.icon-chevron {
  transition: transform 0.3s ease;
}

.icon-chevron.is-rotated {
  transform: rotate(180deg);
}

/* 预览 */
.reasoning-preview {
  padding: 0 12px 10px 44px;
  font-size: 12px;
  color: var(--color-text-secondary);
  line-height: 1.5;
  font-style: italic;
}

/* 内容 */
.reasoning-content {
  border-top: 1px solid var(--color-border-light);
  background-color: rgba(255, 255, 255, 0.5);
}

.reasoning-text {
  padding: 12px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--color-text-primary);
  white-space: pre-wrap;
  word-wrap: break-word;
  font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
  background-color: rgba(102, 126, 234, 0.03);
  border-radius: 4px;
  margin: 12px;
}

/* 操作栏 */
.reasoning-actions {
  display: flex;
  gap: 8px;
  padding: 8px 12px;
  border-top: 1px solid var(--color-border-light);
  background-color: rgba(255, 255, 255, 0.3);
}

.action-button {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  font-size: 12px;
  color: var(--color-text-secondary);
  background: transparent;
  border: 1px solid var(--color-border-light);
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.action-button:hover {
  color: var(--color-primary);
  border-color: var(--color-primary);
  background-color: rgba(102, 126, 234, 0.05);
}

.action-button svg {
  flex-shrink: 0;
}

/* 展开/折叠动画 */
.reasoning-expand-enter-active,
.reasoning-expand-leave-active {
  transition: all 0.3s ease;
  max-height: 1000px;
  overflow: hidden;
}

.reasoning-expand-enter-from,
.reasoning-expand-leave-to {
  max-height: 0;
  opacity: 0;
}

/* 深色模式 */
:root[data-theme='dark'] .reasoning-block {
  background: linear-gradient(135deg, #667eea20 0%, #764ba220 100%);
  border-color: var(--color-border-dark);
}

:root[data-theme='dark'] .reasoning-block.is-expanded {
  background: linear-gradient(135deg, #667eea25 0%, #764ba225 100%);
}

:root[data-theme='dark'] .reasoning-header:hover {
  background-color: rgba(102, 126, 234, 0.1);
}

:root[data-theme='dark'] .reasoning-content {
  background-color: rgba(0, 0, 0, 0.2);
}

:root[data-theme='dark'] .reasoning-text {
  background-color: rgba(102, 126, 234, 0.05);
}

:root[data-theme='dark'] .reasoning-actions {
  background-color: rgba(0, 0, 0, 0.3);
  border-color: var(--color-border-dark);
}

:root[data-theme='dark'] .action-button:hover {
  background-color: rgba(102, 126, 234, 0.1);
}
</style>
