<template>
  <div ref="rootEl" class="team-members">
    <div
      v-for="agent in parsedAgentList"
      :key="agent.id"
      class="team-member"
      :class="agent.status === 'running' ? 'is-running' : 'is-done'"
    >
      <!-- 成员行：机器人头像 + 状态点 + 名称 + 步骤数，展开箭头靠 hover -->
      <button
        type="button"
        class="team-member-head"
        :aria-expanded="isAgentOpen(agent.id, agent.status)"
        @click="toggleAgentPanel(agent.id, agent.status)"
      >
        <span class="team-member-avatar" aria-hidden="true">
          <component :is="BotIcon" :size="11" />
          <span class="team-member-status-dot" />
        </span>
        <span class="team-member-name">{{ agent.label }}</span>
        <span v-if="agent.toolCalls?.length" class="team-member-meta">{{ agent.toolCalls.length }} 个步骤</span>
        <component
          :is="ChevronRightIcon"
          :size="12"
          class="team-member-chevron"
          :class="{ 'is-open': isAgentOpen(agent.id, agent.status) }"
        />
      </button>

      <transition name="slide">
        <div v-show="isAgentOpen(agent.id, agent.status)" class="team-member-body">
          <!-- 步骤直接排开，不再套一层「工具调用 N」折叠 -->
          <div v-if="agent.toolCalls?.length" class="team-member-tools">
            <ToolCallCard
              v-for="(tc, tci) in agent.toolCalls"
              :key="tc.id || tci"
              :tool-name="tc.tool"
              :arguments="tc.arguments"
              :status="tc.status === 'running' ? 'running' : 'success'"
              :result="tc.result"
              :error="tc.error"
              :duration="tc.duration"
              :default-collapsed="true"
              context-kind="agent"
              :context-label="agent.label"
            />
          </div>

          <ReasoningBlock
            v-if="agent.sections.reasoning"
            :content="agent.sections.reasoning"
            :is-thinking="agent.status === 'running' && !agent.sections.content"
            :default-expanded="false"
          />

          <!-- eslint-disable-next-line vue/no-v-html -->
          <div
            v-if="agent.sections.content"
            class="team-member-result markdown-content"
            v-html="renderMarkdown(agent.sections.content)"
          />
          <div v-else-if="agent.status === 'running' && !agent.toolCalls?.length" class="team-member-thinking">
            <component :is="Loader2Icon" :size="11" class="spin" />
            <span>{{ t('chat.workflowPanel.thinking') }}</span>
          </div>
        </div>
      </transition>
    </div>

    <p v-if="parsedAgentList.length === 0" class="team-members-empty">
      {{ t('chat.workflowPanel.historyNotAvailable') }}
    </p>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  Bot as BotIcon,
  Loader2 as Loader2Icon,
  ChevronRight as ChevronRightIcon,
} from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { useMarkdown } from '@/composables/useMarkdown'
import { useMermaid } from '@/composables/useMermaid'
import ToolCallCard from '@/components/chat/ToolCallCard.vue'
import ReasoningBlock from '@/components/chat/ReasoningBlock.vue'
import { splitReasoningSections } from '@/utils/reasoningSections'

interface Props {
  workflowAgents: Record<string, any>
  /** 重放用：只显示前 N 个成员，undefined 表示全部 */
  visibleCount?: number
  /** 全屏查看等独立场景：成员默认展开，步骤直接可见 */
  defaultOpen?: boolean
}

const props = defineProps<Props>()
const { t } = useI18n()
const { renderMarkdown } = useMarkdown()
const rootEl = ref<HTMLElement | null>(null)

const agentList = computed(() => Object.values(props.workflowAgents || {}))
const parsedAgentList = computed(() => {
  const sliced = props.visibleCount === undefined
    ? agentList.value
    : agentList.value.slice(0, props.visibleCount)

  return sliced.map((agent: any) => {
    const sourceText = agent.status === 'running'
      ? (agent.streamingText || '')
      : (agent.agentResult || agent.result || '')

    return {
      ...agent,
      sections: splitReasoningSections(sourceText),
    }
  })
})

useMermaid(rootEl, [() => props.workflowAgents], { deep: true })

// 存储每个 agent 的展开状态
const agentExpanded = ref<Record<string, boolean>>({})

/**
 * 运行中默认展开；defaultOpen 场景（全屏查看）全部展开，让步骤和结论直接可读。
 */
const isAgentOpen = (agentId: string, status?: string): boolean => {
  if (agentExpanded.value[agentId] !== undefined) return agentExpanded.value[agentId]
  if (props.defaultOpen) return true
  return status === 'running'
}

const toggleAgentPanel = (agentId: string, status?: string) => {
  const cur = isAgentOpen(agentId, status)
  agentExpanded.value = { ...agentExpanded.value, [agentId]: !cur }
}
</script>
<style scoped>
@import './styles/WorkflowListPanel.css';
</style>
