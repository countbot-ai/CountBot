<template>
  <div ref="rootEl" class="wf-compare-panel">
    <div
      v-for="agent in parsedAgentList"
      :key="agent.id"
      class="wf-compare-col"
      :class="{ 'wf-compare-col--collapsed': collapsed[agent.id] }"
    >
      <!-- 列头：点击折叠/展开 -->
      <div class="wf-compare-col-header" @click="toggleCollapse(agent.id)">
        <div class="wf-agent-dot" :class="agent.status === 'running' ? 'wf-dot-running' : 'wf-dot-done'">
          <Bot :size="15" class="wf-agent-bot" />
        </div>
        <span class="wf-compare-chip">agent</span>
        <span class="wf-compare-label">{{ agent.label }}</span>
        <span v-if="agent.status === 'running'" class="wf-compare-status-text">{{ t('chat.workflowPanel.thinking') }}</span>
        <span v-else class="wf-compare-status-done">✓</span>
        <!-- 工具调用数量徽章 -->
        <span v-if="agent.toolCalls && agent.toolCalls.length > 0" class="wf-tool-badge">
          {{ agent.toolCalls.length }}
        </span>
        <!-- 折叠箭头：展开时朝下，折叠后朝右 -->
        <ChevronDown
          :size="12"
          class="wf-compare-chevron"
          :class="{ 'wf-compare-chevron--collapsed': collapsed[agent.id] }"
        />
      </div>
      <!-- 内容区：折叠时隐藏 -->
      <div v-show="!collapsed[agent.id]" class="wf-compare-col-body">
        <!-- 工具调用区域 -->
        <div v-if="agent.toolCalls && agent.toolCalls.length > 0" class="wf-agent-tools">
          <!-- 工具调用头部 -->
          <div class="wf-tools-header" @click.stop="toggleAgentTools(agent.id)">
            <component :is="WrenchIcon" :size="14" class="wf-tools-icon" />
            <span class="wf-tools-title">工具调用</span>
            <span class="wf-tools-count">{{ agent.toolCalls.length }}</span>
            <component :is="ChevronDownIcon" :size="14" class="wf-tools-chevron" :class="{ expanded: isAgentToolsOpen(agent.id) }" />
          </div>
          <!-- 工具调用列表 -->
          <transition name="slide">
            <div v-show="isAgentToolsOpen(agent.id)" class="wf-tools-list">
              <ToolCallCard
                v-for="(toolCall, idx) in agent.toolCalls"
                :key="idx"
                :tool-name="toolCall.tool"
                :arguments="toolCall.arguments"
                :status="toolCall.status === 'running' ? 'running' : 'success'"
                :result="toolCall.result"
                :default-collapsed="true"
                context-kind="agent"
                :context-label="agent.label"
              />
            </div>
          </transition>
        </div>
        <ReasoningBlock
          v-if="agent.sections.reasoning"
          :content="agent.sections.reasoning"
          :is-thinking="agent.status === 'running' && !agent.sections.content"
          :default-expanded="false"
        />
        
        <!-- 输出内容区域 -->
        <div class="wf-output-section">
          <!-- 流式输出中 -->
          <!-- eslint-disable-next-line vue/no-v-html -->
          <div
            v-if="agent.status === 'running' && agent.sections.content"
            class="markdown-content wf-compare-content"
            v-html="renderMarkdown(agent.sections.content || '')"
          />
          <!-- 思考中（无流式内容） -->
          <div v-else-if="agent.status === 'running'" class="wf-compare-thinking">
            <Loader2 :size="12" class="spin" />
            <span>{{ t('chat.workflowPanel.thinking') }}</span>
          </div>
          <!-- 完成，显示结论 -->
          <!-- eslint-disable-next-line vue/no-v-html -->
          <div
            v-else-if="agent.sections.content"
            class="markdown-content wf-compare-content"
            v-html="renderMarkdown(agent.sections.content || '')"
          />
          <div v-else class="wf-compare-empty">—</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Loader2, ChevronDown, Bot, Wrench as WrenchIcon, ChevronDown as ChevronDownIcon } from 'lucide-vue-next'
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

// 每张卡的折叠状态（id → 是否折叠）
const collapsed = ref<Record<string, boolean>>({})
const toggleCollapse = (id: string) => {
  collapsed.value[id] = !collapsed.value[id]
}

// 每个 agent 的工具调用展开状态
const agentToolsExpanded = ref<Record<string, boolean>>({})

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
@import './styles/WorkflowComparePanel.css';
</style>
