<template>
  <div ref="rootEl" class="wf-agents-list">
    <div
      v-for="agent in parsedAgentList"
      :key="agent.id"
      class="wf-agent-item"
    >
      <!-- Agent 头部 -->
      <div class="wf-agent-header" @click="toggleAgentPanel(agent.id, agent.status)">
        <div class="wf-agent-dot" :class="agent.status === 'running' ? 'wf-dot-running' : 'wf-dot-done'">
          <component :is="BotIcon" :size="15" class="wf-agent-bot" />
        </div>
        <span class="wf-agent-chip">agent</span>
        <span class="wf-agent-label">{{ agent.label }}</span>
        <span v-if="agent.toolCalls?.length" class="wf-agent-tc-count">
          {{ agent.toolCalls.length }}
        </span>
        <component
          :is="ChevronRightIcon"
          :size="12"
          class="wf-agent-chevron"
          :class="{ expanded: isAgentOpen(agent.id, agent.status) }"
        />
      </div>
      <!-- Agent 工具调用 -->
      <transition name="slide">
        <div v-show="isAgentOpen(agent.id, agent.status)" class="wf-agent-tools">
          <!-- 工具调用头部 -->
          <div v-if="agent.toolCalls?.length" class="wf-tools-header" @click.stop="toggleAgentTools(agent.id)">
            <component :is="WrenchIcon" :size="14" class="wf-tools-icon" />
            <span class="wf-tools-title">工具调用</span>
            <span class="wf-tools-count">{{ agent.toolCalls.length }}</span>
            <component :is="ChevronDownIcon" :size="14" class="wf-tools-chevron" :class="{ expanded: isAgentToolsOpen(agent.id) }" />
          </div>
          <!-- 工具调用列表 -->
          <transition name="slide">
            <div v-show="isAgentToolsOpen(agent.id)" class="wf-tools-list">
              <ToolCallCard
                v-for="(tc, tci) in agent.toolCalls"
                :key="tc.id || tci"
                :tool-name="tc.tool"
                :arguments="tc.arguments"
                :status="tc.status === 'running' ? 'running' : 'success'"
                :result="tc.result"
                :default-collapsed="true"
                context-kind="agent"
                :context-label="agent.label"
              />
            </div>
          </transition>
          <ReasoningBlock
            v-if="agent.sections.reasoning"
            :content="agent.sections.reasoning"
            :is-thinking="agent.status === 'running' && !agent.sections.content"
            :default-expanded="false"
          />
          <!-- 运行中：有流式输出时展示实时内容，否则显示思考中 -->
          <template v-if="agent.status === 'running'">
            <!-- eslint-disable-next-line vue/no-v-html -->
            <div
              v-if="agent.sections.content"
              class="wf-agent-result-text markdown-content"
              v-html="renderMarkdown(agent.sections.content || '')"
            />
            <div v-else-if="!agent.toolCalls?.length" class="wf-agent-thinking">
              <component :is="Loader2Icon" :size="11" class="spin" />
              <span>{{ t('chat.workflowPanel.thinking') }}</span>
            </div>
          </template>
          <!-- Agent 完成时渲染结论（Markdown 格式，无字数限制） -->
          <!-- eslint-disable-next-line vue/no-v-html -->
          <div
            v-if="agent.status === 'complete' && agent.sections.content"
            class="wf-agent-result-text markdown-content"
            v-html="renderMarkdown(agent.sections.content || '')"
          />
        </div>
      </transition>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Loader2 as Loader2Icon, ChevronRight as ChevronRightIcon, Bot as BotIcon, Wrench as WrenchIcon, ChevronDown as ChevronDownIcon } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { useMarkdown } from '@/composables/useMarkdown'
import { useMermaid } from '@/composables/useMermaid'
import ToolCallCard from '@/components/chat/ToolCallCard.vue'
import ReasoningBlock from '@/components/chat/ReasoningBlock.vue'
import { splitReasoningSections } from '@/utils/reasoningSections'

interface Props {
  workflowAgents: Record<string, any>
}

const props = defineProps<Props>()
const { t } = useI18n()
const { renderMarkdown } = useMarkdown()
const rootEl = ref<HTMLElement | null>(null)

const agentList = computed(() => Object.values(props.workflowAgents || {}))
const parsedAgentList = computed(() =>
  agentList.value.map((agent: any) => {
    const sourceText = agent.status === 'running'
      ? (agent.streamingText || '')
      : (agent.agentResult || agent.result || '')

    return {
      ...agent,
      sections: splitReasoningSections(sourceText),
    }
  })
)

useMermaid(rootEl, [() => props.workflowAgents], { deep: true })

// 存储每个 agent 的展开状态
const agentExpanded = ref<Record<string, boolean>>({})
// 存储每个 agent 的工具调用展开状态
const agentToolsExpanded = ref<Record<string, boolean>>({})

/**
 * 判断某个 agent 是否展开
 */
const isAgentOpen = (agentId: string, status?: string): boolean => {
  if (agentExpanded.value[agentId] !== undefined) return agentExpanded.value[agentId]
  return status === 'running' // 运行中默认展开，完成后折叠
}

const toggleAgentPanel = (agentId: string, status?: string) => {
  const cur = isAgentOpen(agentId, status)
  agentExpanded.value = { ...agentExpanded.value, [agentId]: !cur }
}

/**
 * 判断某个 agent 的工具调用是否展开
 */
const isAgentToolsOpen = (agentId: string): boolean => {
  if (agentToolsExpanded.value[agentId] !== undefined) return agentToolsExpanded.value[agentId]
  return true // 默认展开
}

const toggleAgentTools = (agentId: string) => {
  const cur = isAgentToolsOpen(agentId)
  agentToolsExpanded.value = { ...agentToolsExpanded.value, [agentId]: !cur }
}
</script>
<style scoped>
@import './styles/WorkflowListPanel.css';
</style>
