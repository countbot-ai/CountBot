<template>
  <div
    v-if="visibleToolCalls.length > 0"
    class="tool-calls-container"
  >
    <div class="tool-calls-header" @click="$emit('toggle')">
      <component :is="WrenchIcon" :size="14" class="tool-calls-icon" />
      <span class="tool-calls-title">{{ $t('tools.toolCalls') || 'Tool Calls' }}</span>
      <span class="tool-calls-count">{{ visibleToolCalls.length }}</span>
      <component
        :is="ChevronDownIcon"
        :size="14"
        class="tool-calls-chevron"
        :class="{ expanded }"
      />
    </div>
    <transition name="slide-list">
      <div v-show="expanded" class="tool-calls-list">
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
          context-kind="main"
        />
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ChevronDown as ChevronDownIcon, Wrench as WrenchIcon } from 'lucide-vue-next'
import ToolCallCard from './ToolCallCard.vue'
import type { ChatToolCall } from '@/types/chat'

interface Props {
  toolCalls: ChatToolCall[]
  isReplaying?: boolean
  visibleCount?: number
  expanded?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  isReplaying: false,
  visibleCount: undefined,
  expanded: true
})

defineEmits<{
  (e: 'toggle'): void
}>()

const visibleToolCalls = computed(() => {
  if (!props.isReplaying || props.visibleCount === undefined) {
    return props.toolCalls
  }

  return props.toolCalls.slice(0, props.visibleCount)
})
</script>
