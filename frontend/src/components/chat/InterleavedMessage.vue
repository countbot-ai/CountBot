<template>
  <div ref="rootEl" class="interleaved-message">
    <!-- 完整消息内容 -->
    <!-- eslint-disable-next-line vue/no-v-html -->
    <div
      v-if="content"
      class="interleaved-content markdown-content"
      v-html="content"
    />

    <!-- 工具调用：逐行排开，不做外框；顺序本身就是执行叙事 -->
    <div v-if="visibleToolCalls.length > 0" class="interleaved-tools">
      <ToolCallCard
        v-for="(toolCall, index) in visibleToolCalls"
        :key="toolCall.id || index"
        :tool-name="toolCall.name"
        :arguments="toolCall.arguments"
        :status="toolCall.status || 'success'"
        :result="toolCall.result"
        :error="toolCall.error"
        :duration="toolCall.duration"
        :progress="toolCall.progress"
        :progress-message="toolCall.progressMessage"
        :progress-details="toolCall.progressDetails"
        :default-collapsed="true"
        :is-replaying="isReplaying"
        :show-result="shouldShowResult(index)"
        context-kind="main"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useMermaid } from '@/composables/useMermaid'
import ToolCallCard from './ToolCallCard.vue'
import type { ChatToolCall } from '@/types/chat'

interface Props {
  content: string
  toolCalls: ChatToolCall[]
  isReplaying?: boolean
  replaySegmentCount?: number
  /** 兼容旧调用点：外壳模式不再改变排版，保留入参避免上层改动 */
  shellMode?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  isReplaying: false,
  replaySegmentCount: undefined,
  shellMode: false
})

const rootEl = ref<HTMLElement | null>(null)

useMermaid(rootEl, [() => props.content, () => props.isReplaying, () => props.replaySegmentCount])

const visibleToolCalls = computed(() => {
  if (!props.isReplaying) return props.toolCalls
  return props.toolCalls.slice(0, props.replaySegmentCount || 0)
})

const shouldShowResult = (index: number): boolean => {
  if (!props.isReplaying) return true
  return index < (props.replaySegmentCount || 0)
}
</script>

<style scoped>
.interleaved-message {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}

.interleaved-content {
  min-width: 0;
  color: var(--color-text-primary);
  font-size: 14px;
  line-height: 1.75;
  word-wrap: break-word;
  overflow-wrap: break-word;
  word-break: break-word;
  text-wrap: pretty;
}

/* 工具行左侧收 0：与正文左对齐，靠图标列形成视觉竖线 */
.interleaved-tools {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
  margin-left: -6px;
}
</style>
