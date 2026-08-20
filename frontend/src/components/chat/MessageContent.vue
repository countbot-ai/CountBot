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
  background: #f8fafc;
  border: 1px solid #f1f5f9;
}

.message-content:not(.markdown-content) {
  background: #ffffff;
  border: 1px solid #e2e8f0;
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
  background: var(--text-tertiary, #94a3b8);
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
  color: var(--text-tertiary, #94a3b8);
  font-weight: 100;
}

@keyframes blink-cursor {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

[data-theme='dark'] .message-content.markdown-content {
  background:
    linear-gradient(180deg, rgba(29, 36, 46, 0.96), rgba(22, 28, 37, 0.98));
  border: 1px solid rgba(76, 89, 110, 0.34);
  color: #d6dee8;
}

[data-theme='dark'] .message-content:not(.markdown-content) {
  background:
    linear-gradient(180deg, rgba(36, 44, 55, 0.96), rgba(28, 35, 45, 0.98));
  border: 1px solid rgba(88, 103, 126, 0.3);
  color: #d9e2ed;
}
</style>
