<template>
  <div
    class="spawn-card"
    :class="`spawn-status-${spawnTask.status}`"
    :data-tool-call-id="toolCallId"
  >
    <!-- 头部 -->
    <div class="spawn-card-header" @click="togglePanel">
      <!-- 状态圆点 -->
      <div class="spawn-status-dot">
        <component
          v-if="spawnTask.status === 'running' || spawnTask.status === 'pending'"
          :is="Loader2Icon"
          :size="12"
          class="spin"
        />
      </div>
      <!-- Bot 图标 -->
      <component :is="BotIcon" :size="14" class="spawn-tool-icon" />
      <!-- 任务标签 -->
      <span class="spawn-tool-name">{{ spawnTask.label || $t('spawn.task') }}</span>
      <span class="spawn-status-chip">{{ statusLabel }}</span>
      <span v-if="progressValue > 0 && spawnTask.status !== 'failed'" class="spawn-progress-pill">{{ progressValue }}%</span>
      <!-- 工具调用数 -->
      <span
        v-if="toolCallRecords.length > 0"
        class="spawn-tc-count"
      >{{ $t('spawn.toolCount', { n: toolCallRecords.length }) }}</span>
      <!-- 展开箭头 -->
      <component
        :is="ChevronRightIcon"
        :size="14"
        class="spawn-chevron"
        :class="{ expanded: isOpen }"
      />
    </div>

    <!-- 可折叠内容区 -->
    <transition name="slide">
      <div v-if="isOpen" class="spawn-card-body">
        <div class="spawn-meta-strip">
          <span class="spawn-meta-label">{{ $t('spawn.meta.task') }}</span>
          <span class="spawn-meta-value">{{ taskShortId }}</span>
          <span v-if="spawnTask.message" class="spawn-meta-message">{{ spawnTask.message }}</span>
        </div>

        <!-- 嵌套工具调用列表 -->
        <div v-if="toolCallRecords.length > 0" class="spawn-nested-tools">
          <div class="spawn-nested-label">{{ $t('spawn.subagentTools') }}</div>
          <div class="spawn-nested-rail">
            <ToolCallCard
              v-for="(record, index) in toolCallRecords"
              :key="record.tool_call_id || index"
              :tool-name="record.name"
              :arguments="record.arguments"
              :status="getRecordStatus(record.status)"
              :result="record.result ?? undefined"
              :duration="record.duration_ms"
              :default-collapsed="true"
              context-kind="subagent"
              :context-label="spawnTask.label || $t('tools.card.contextLabel.subagent')"
              :context-meta="taskShortId"
            />
          </div>
        </div>

        <!-- 无工具调用时的等待提示 -->
        <div
          v-else-if="spawnTask.status === 'running' || spawnTask.status === 'pending'"
          class="spawn-waiting"
        >
          <component :is="Loader2Icon" :size="11" class="spin" />
          <span>{{ $t('spawn.running') }}</span>
        </div>

        <!-- 完成结果 -->
        <div v-if="spawnTask.status === 'completed' && hasResultContent" class="spawn-result-section">
          <ReasoningBlock
            v-if="visibleReasoning"
            :content="visibleReasoning"
            :default-expanded="false"
          />

          <div v-if="visibleResultContent" class="spawn-result-epilogue">
            <div class="spawn-section-label">{{ $t('spawn.result') }}</div>
            <!-- eslint-disable-next-line vue/no-v-html -->
            <div class="spawn-result-content markdown-content" v-html="renderMarkdown(visibleResultContent)" />
          </div>
        </div>

        <!-- 失败错误 -->
        <div v-if="spawnTask.status === 'failed' && spawnTask.error" class="spawn-error-section">
          <div class="spawn-section-label spawn-error-label">{{ $t('spawn.error') }}</div>
          <pre class="spawn-error-content">{{ spawnTask.error }}</pre>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { TaskToolCallRecord } from '@/api/endpoints'
import {
  Bot as BotIcon,
  ChevronRight as ChevronRightIcon,
  Loader2 as Loader2Icon,
} from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import ToolCallCard from './ToolCallCard.vue'
import ReasoningBlock from './ReasoningBlock.vue'
import { useMarkdown } from '@/composables/useMarkdown'
import { splitReasoningSections } from '@/utils/reasoningSections'

type ToolCardStatus = 'pending' | 'running' | 'success' | 'error' | 'cancelled'

interface SpawnTask {
  task_id: string | null
  label: string
  status: string
  progress: number
  result: string | null
  error: string | null
  tool_call_records?: TaskToolCallRecord[]
  message?: string
  session_id?: string | null
  created_at?: string
  started_at?: string | null
  completed_at?: string | null
}

interface Props {
  spawnTask: SpawnTask
  toolCallId: string
  isReplaying?: boolean
  replayVisibleCount?: number
}

const props = withDefaults(defineProps<Props>(), {
  isReplaying: false,
  replayVisibleCount: undefined
})

const { t } = useI18n()
const { renderMarkdown } = useMarkdown()

// 面板展开状态
const panelExpanded = ref<boolean | undefined>(undefined)

const isOpen = computed(() => {
  // 如果用户手动设置过，使用用户设置
  if (panelExpanded.value !== undefined) {
    return panelExpanded.value
  }
  // 默认展开：运行中、等待中、或者已完成且有工具调用记录
  if (props.spawnTask.status === 'running' || props.spawnTask.status === 'pending') {
    return true
  }
  // 已完成的任务：如果有工具调用记录，默认展开以显示详情
  if (props.spawnTask.status === 'completed' && props.spawnTask.tool_call_records && props.spawnTask.tool_call_records.length > 0) {
    return true
  }
  // 失败的任务默认折叠
  return false
})

const toolCallRecords = computed(() => {
  const all = props.spawnTask.tool_call_records || []
  // 重放时按可见计数截取
  if (props.isReplaying && props.replayVisibleCount !== undefined) {
    return all.slice(0, props.replayVisibleCount)
  }
  return all
})

const progressValue = computed(() => Math.max(0, Math.min(100, Math.round(props.spawnTask.progress || 0))))

const statusLabel = computed(() => {
  const key = `spawn.status.${props.spawnTask.status}`
  const value = t(key)
  return value && value !== key ? value : props.spawnTask.status
})

const taskShortId = computed(() => {
  if (!props.spawnTask.task_id) return t('spawn.meta.awaitingTaskId')
  return props.spawnTask.task_id.slice(0, 12)
})

const parsedSections = computed(() => splitReasoningSections(props.spawnTask.result))

/**
 * 重放时是否显示总结部分（所有工具调用显示完毕后才显示）
 */
const showEpilogue = computed(() => {
  if (!props.isReplaying) return true // 非重放时始终显示
  
  const totalToolCalls = props.spawnTask.tool_call_records?.length || 0
  const visibleCount = props.replayVisibleCount || 0
  
  // 所有工具调用都已显示时才显示总结
  return visibleCount >= totalToolCalls
})

const visibleResultContent = computed(() => {
  if (!showEpilogue.value) return null
  return parsedSections.value.content
})

const visibleReasoning = computed(() => {
  if (!showEpilogue.value) return null
  return parsedSections.value.reasoning
})

// 是否有结果内容需要显示
const hasResultContent = computed(() => {
  return !!(visibleReasoning.value || visibleResultContent.value)
})

const togglePanel = () => {
  panelExpanded.value = !isOpen.value
}

const getRecordStatus = (status: string): ToolCardStatus => {
  if (status === 'pending') return 'pending'
  if (status === 'running') return 'running'
  if (status === 'error') return 'error'
  if (status === 'cancelled') return 'cancelled'
  return 'success'
}
</script>
<style scoped>
@import './styles/SpawnTaskPanel.css';
</style>
