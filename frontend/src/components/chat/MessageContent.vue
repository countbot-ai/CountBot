<template>
  <div
    v-if="!isThinking"
    class="message-content"
    :class="{ 
      'markdown-content': role === 'assistant',
      'typewriter-active': isReplaying 
    }"
  >
    <!-- eslint-disable-next-line vue/no-v-html -->
    <div v-if="role === 'assistant'" v-html="content" />
    <div v-else>{{ content }}</div>
  </div>
  <div v-else class="message-content thinking-indicator">
    <span class="thinking-dots">
      <span class="dot" />
      <span class="dot" />
      <span class="dot" />
    </span>
  </div>
</template>

<script setup lang="ts">
interface Props {
  content: string
  role: 'user' | 'assistant'
  isThinking?: boolean
  isReplaying?: boolean
}

defineProps<Props>()
</script>

<style scoped>
.message-content {
  padding: 12px 16px;
  background: transparent;
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 14px;
  line-height: 1.6;
  word-wrap: break-word;
  overflow-wrap: break-word;
  word-break: break-word;
  max-width: 100%;
  overflow-x: auto;
}

.message-content.markdown-content {
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border-primary);
}

.message-content:not(.markdown-content) {
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-primary);
  white-space: pre-wrap;
}

.thinking-indicator {
  display: flex;
  align-items: center;
  min-height: 40px;
}

.thinking-dots {
  display: flex;
  gap: 4px;
  align-items: center;
}

.thinking-dots .dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-tertiary);
  animation: thinking-bounce 1.4s ease-in-out infinite;
}

.thinking-dots .dot:nth-child(2) {
  animation-delay: 0.16s;
}

.thinking-dots .dot:nth-child(3) {
  animation-delay: 0.32s;
}

@keyframes thinking-bounce {
  0%, 80%, 100% {
    transform: scale(0.6);
    opacity: 0.4;
  }
  40% {
    transform: scale(1);
    opacity: 1;
  }
}

.typewriter-active :deep(*:last-child)::after {
  content: '|';
  animation: blink-cursor 0.7s step-end infinite;
  color: var(--text-tertiary);
  font-weight: 100;
}

@keyframes blink-cursor {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}




</style>
