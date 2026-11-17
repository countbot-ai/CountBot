<template>
  <div ref="rootEl" class="interleaved-message">
    <template v-for="group in renderGroups" :key="group.key">
      <!-- 正文段落：直接的阅读面，不加任何容器 -->
      <!-- eslint-disable-next-line vue/no-v-html -->
      <div
        v-if="group.kind === 'text'"
        class="interleaved-content markdown-content"
        v-html="group.html"
      />

      <!-- 连续的工具调用归为一组：一块「执行轨迹」，与正文形成层次对照 -->
      <div v-else class="interleaved-tools">
        <ToolCallCard
          v-for="item in group.items"
          :key="item.key"
          :tool-name="item.toolCall.name"
          :arguments="item.toolCall.arguments"
          :status="item.toolCall.status || 'success'"
          :result="item.toolCall.result"
          :error="item.toolCall.error"
          :duration="item.toolCall.duration"
          :progress="item.toolCall.progress"
          :progress-message="item.toolCall.progressMessage"
          :progress-details="item.toolCall.progressDetails"
          :default-collapsed="true"
          :is-replaying="isReplaying"
          :show-result="item.showResult"
          context-kind="main"
        />
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useMermaid } from '@/composables/useMermaid'
import ToolCallCard from './ToolCallCard.vue'
import type { InterleavedRenderBlock, InterleavedToolBlock } from '@/types/chat'

interface Props {
  /** 已按发生顺序排好的正文 / 工具调用块 */
  blocks: InterleavedRenderBlock[]
  isReplaying?: boolean
}

/**
 * 渲染分组：正文各自成段，连续的工具调用合并成一个工具组，
 * 避免每个工具都挂一层容器，同时让「一次执行」看起来是一次连续动作。
 */
type RenderGroup =
  | { key: string; kind: 'text'; html: string }
  | { key: string; kind: 'tools'; items: InterleavedToolBlock[] }

const props = withDefaults(defineProps<Props>(), {
  isReplaying: false,
})

const rootEl = ref<HTMLElement | null>(null)

const renderGroups = computed<RenderGroup[]>(() => {
  const groups: RenderGroup[] = []

  for (const block of props.blocks) {
    if (block.kind === 'text') {
      // 空正文块不落成空占位，避免工具组之间多出一道空隙
      if (block.html) {
        groups.push({ key: block.key, kind: 'text', html: block.html })
      }
      continue
    }

    const last = groups[groups.length - 1]
    if (last && last.kind === 'tools') {
      last.items.push(block)
    } else {
      groups.push({ key: `tools-${block.key}`, kind: 'tools', items: [block] })
    }
  }

  return groups
})

useMermaid(rootEl, [() => props.blocks.map((block) => block.kind === 'text' ? block.html : '').join('')])
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

/* 工具组：靠背景阶梯分层，左侧收 0 保持与正文同一根竖线 */
.interleaved-tools {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
  margin-left: -6px;
  padding: 4px;
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-lg);
  background: var(--color-bg-secondary);
}
</style>
