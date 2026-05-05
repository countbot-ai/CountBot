<template>
  <div
    ref="rootEl"
    class="message"
    :class="`message-${message.role}`"
  >
    <div class="message-avatar" @click="handleAvatarClick" :title="message.role === 'user' ? $t('avatar.clickToSetUser') : $t('avatar.clickToSetAI')">
      <img
        v-if="avatarImageUrl"
        :src="avatarImageUrl"
        alt="Avatar"
        class="avatar-image"
      />
      <component
        v-else
        :is="avatarIcon"
        :size="16"
      />
    </div>
    <div class="message-body">
      <!-- 交织模式：文字和工具调用交织显示 -->
      <div
        v-if="useInterleavedMode && !message.isThinking"
        key="interleaved-mode"
        class="assistant-response-shell assistant-response-shell-interleaved"
      >
        <ReasoningBlock
          v-if="message.reasoningContent && message.role === 'assistant'"
          :content="message.reasoningContent"
          :is-thinking="Boolean(message.isThinking && message.reasoningContent)"
          :default-expanded="false"
          embedded
        />
        <InterleavedMessage
          :content="interleavedContent"
          :tool-calls="inlineToolCalls"
          :is-replaying="isReplaying"
          :replay-segment-count="replayInterleavedSegments"
          shell-mode
        />
      </div>

      <!-- 传统模式：工具调用在上，文字在下 -->
      <div v-else key="traditional-mode" class="message-main">
        <!-- 普通工具调用显示 -->
        <div
          v-if="shouldShowToolCallsSection"
          class="tool-calls-container"
        >
          <div class="tool-calls-header" @click="toggleToolCalls">
            <component :is="WrenchIcon" :size="14" class="tool-calls-icon" />
            <span class="tool-calls-title">{{ $t('tools.toolCalls') || 'Tool Calls' }}</span>
            <span class="tool-calls-count">{{ totalToolCallCount }}</span>
            <component :is="ChevronDownIcon" :size="14" class="tool-calls-chevron" :class="{ expanded: toolCallsExpanded }" />
          </div>
          <transition name="slide-list">
            <div v-if="toolCallsExpanded" class="tool-calls-list">
              <div
                v-if="shouldFetchHistoryToolCalls && !historyToolCallsLoaded && !historyToolCallsLoading"
                class="tool-calls-note"
              >
                为避免历史消息卡顿，工具调用按需加载。
              </div>
              <div v-if="historyToolCallsLoading" class="tool-calls-loading">
                <component :is="Loader2Icon" :size="14" class="spin" />
                <span>工具调用加载中...</span>
              </div>
              <div v-if="historyToolCallsError" class="tool-calls-error">
                {{ historyToolCallsError }}
              </div>
              <template v-for="(toolCall, index) in regularToolCalls" :key="toolCall.id || index">
                <!-- 普通工具调用 -->
                <ToolCallCard
                  :tool-id="toolCall.id"
                  :tool-name="toolCall.name"
                  :arguments="toolCall.arguments"
                  :status="toolCall.status || 'success'"
                  :result="toolCall.result"
                  :error="toolCall.error"
                  :duration="toolCall.duration"
                  :detail-available="toolCall.detailAvailable"
                  :detail-loaded="toolCall.detailLoaded"
                  :result-truncated="toolCall.resultTruncated"
                  :error-truncated="toolCall.errorTruncated"
                  :progress="toolCall.progress"
                  :progress-message="toolCall.progressMessage"
                  :progress-details="toolCall.progressDetails"
                  :timestamp="message.timestamp"
                  :default-collapsed="true"
                  :is-replaying="isReplaying"
                  :show-result="shouldShowToolResult(toolCall.id)"
                  context-kind="main"
                />
              </template>
              <div
                v-if="historyToolCallsLoaded && regularToolCalls.length === 0 && hasSpecialVisibleToolCalls"
                class="tool-calls-note"
              >
                特殊工具调用已在下方工作流或子代理面板展示。
              </div>
              <button
                v-if="canLoadMoreToolCalls"
                class="tool-calls-load-more-btn"
                :disabled="historyToolCallsLoading"
                @click.stop="loadMoreToolCalls"
              >
                加载更多工具调用 ({{ loadedToolCallCount }}/{{ totalToolCallCount }})
              </button>
            </div>
          </transition>
        </div>

        <!-- 多智能体协作显示（与工具调用同级） -->
        <div
          v-if="workflowToolCalls.length > 0"
          class="workflow-container"
        >
          <template v-for="toolCall in workflowToolCalls" :key="toolCall.id">
            <div class="wf-run-panel" :data-tc-id="toolCall.id">
              <!-- 面板头部 -->
              <div class="wf-run-header" @click="toggleWorkflowPanel(toolCall.id, toolCall.status)">
                <div class="wf-run-lead">
                  <div class="wf-run-sigil">
                    <component :is="UsersIcon" :size="14" class="wf-run-icon" />
                  </div>
                  <div class="wf-run-copy">
                    <div class="wf-run-title-row">
                      <span class="wf-run-kicker">multi-agent</span>
                      <span class="wf-run-name">{{ t('chat.workflowPanel.title') }}</span>
                    </div>
                    <div class="wf-run-meta-row">
                      <span v-if="toolCall.arguments?.mode" class="wf-run-mode">{{ wfModeLabel(toolCall.arguments.mode) }}</span>
                      <span class="wf-agent-count">
                        {{ t('chat.workflowPanel.agentCount', { n: Object.keys(toolCall.workflowAgents || {}).length }) }}
                      </span>
                    </div>
                  </div>
                </div>
                <span class="wf-run-status-chip" :class="`wf-run-status-${toolCall.status || 'success'}`">
                  <component v-if="toolCall.status === 'running'" :is="Loader2Icon" :size="12" class="spin wf-status-loader" />
                  <span>{{ toolCall.status === 'running' ? 'Running' : 'Complete' }}</span>
                </span>
                <!-- 视图控制按钮组 -->
                <div v-if="Object.keys(toolCall.workflowAgents || {}).length > 1" class="wf-view-controls">
                  <!-- 并排对比切换按钮 -->
                  <button
                    class="wf-view-btn"
                    :title="wfCompareMode[toolCall.id] ? '切换为列表视图' : '切换为并排视图'"
                    @click.stop="wfCompareMode[toolCall.id] = !wfCompareMode[toolCall.id]"
                  >
                    <component :is="wfCompareMode[toolCall.id] ? ListIcon : LayoutGridIcon" :size="14" />
                    <span class="wf-btn-text">{{ wfCompareMode[toolCall.id] ? '列表' : '并排' }}</span>
                  </button>
                  <!-- 全屏按钮 -->
                  <button
                    class="wf-view-btn wf-fullscreen-btn"
                    title="全屏查看"
                    @click.stop="openFullscreen(toolCall)"
                  >
                    <component :is="MaximizeIcon" :size="14" />
                    <span class="wf-btn-text">全屏</span>
                  </button>
                </div>
                <component
                  :is="ChevronRightIcon"
                  :size="14"
                  class="wf-run-chevron"
                  :class="{ expanded: isWfPanelOpen(toolCall.id, toolCall.status) }"
                />
              </div>
              <!-- Agent 列表 / 并排对比视图 -->
              <transition name="slide">
                <div v-if="isWfPanelOpen(toolCall.id, toolCall.status)" class="wf-agents-list">
                  <!-- 并排对比模式 -->
                  <WorkflowComparePanel
                    v-if="wfCompareMode[toolCall.id] && Object.keys(toolCall.workflowAgents || {}).length"
                    :key="`${toolCall.id}-compare`"
                    :workflow-agents="toolCall.workflowAgents || {}"
                  />
                  
                  <!-- 列表模式 -->
                  <WorkflowListPanel
                    v-else-if="!wfCompareMode[toolCall.id] && Object.keys(toolCall.workflowAgents || {}).length"
                    :key="`${toolCall.id}-list`"
                    :workflow-agents="toolCall.workflowAgents || {}"
                  />
                  <template v-else>
                    <div
                      v-for="agent in visibleAgents(toolCall)"
                      :key="(agent as any).id"
                      class="wf-agent-item"
                    >
                      <!-- Agent 头部 -->
                      <div class="wf-agent-header" @click="toggleAgentPanel(toolCall.id, (agent as any).id, (agent as any).status)">
                        <div class="wf-agent-dot" :class="(agent as any).status === 'running' ? 'wf-dot-running' : 'wf-dot-done'">
                          <component :is="BotIcon" :size="15" class="wf-agent-bot" />
                        </div>
                        <span class="wf-agent-label">{{ (agent as any).label }}</span>
                        <span v-if="(agent as any).toolCalls?.length" class="wf-agent-tc-count">
                          {{ (agent as any).toolCalls.length }}
                        </span>
                        <component
                          :is="ChevronRightIcon"
                          :size="12"
                          class="wf-agent-chevron"
                          :class="{ expanded: isAgentOpen(toolCall.id, (agent as any).id, (agent as any).status) }"
                        />
                      </div>
                      <!-- Agent 工具调用 -->
                      <transition name="slide">
                        <div v-if="isAgentOpen(toolCall.id, (agent as any).id, (agent as any).status)" class="wf-agent-tools">
                          <!-- 工具调用头部 -->
                          <div v-if="(agent as any).toolCalls?.length" class="wf-tools-header" @click.stop="toggleAgentTools(toolCall.id, (agent as any).id)">
                            <component :is="WrenchIcon" :size="14" class="wf-tools-icon" />
                            <span class="wf-tools-title">工具调用</span>
                            <span class="wf-tools-count">{{ (agent as any).toolCalls.length }}</span>
                            <component :is="ChevronDownIcon" :size="14" class="wf-tools-chevron" :class="{ expanded: isAgentToolsOpen(toolCall.id, (agent as any).id) }" />
                          </div>
                          <!-- 工具调用列表 -->
                          <transition name="slide">
                            <div v-if="isAgentToolsOpen(toolCall.id, (agent as any).id)" class="wf-tools-list">
                              <ToolCallCard
                                v-for="(tc, tci) in (agent as any).toolCalls"
                                :key="(tc as any).id || tci"
                                :tool-name="(tc as any).tool"
                                :arguments="(tc as any).arguments"
                                :status="(tc as any).status === 'running' ? 'running' : 'success'"
                                :result="(tc as any).result"
                                :progress="(tc as any).progress"
                                :progress-message="(tc as any).progressMessage"
                                :progress-details="(tc as any).progressDetails"
                                :default-collapsed="true"
                                context-kind="agent"
                                :context-label="(agent as any).label"
                              />
                            </div>
                          </transition>
                          <!-- 运行中：有流式输出时展示实时内容，否则显示思考中 -->
                          <template v-if="(agent as any).status === 'running'">
                            <!-- eslint-disable-next-line vue/no-v-html -->
                            <div v-if="(agent as any).streamingText" class="wf-agent-result-text markdown-content" v-html="renderMarkdown((agent as any).streamingText)" />
                            <div v-else-if="!(agent as any).toolCalls?.length" class="wf-agent-thinking">
                              <component :is="Loader2Icon" :size="11" class="spin" />
                              <span>{{ t('chat.workflowPanel.thinking') }}</span>
                            </div>
                          </template>
                          <!-- Agent 完成时渲染结论（Markdown 格式，无字数限制） -->
                          <!-- eslint-disable-next-line vue/no-v-html -->
                          <div v-if="(agent as any).status === 'complete' && (agent as any).agentResult" class="wf-agent-result-text markdown-content" v-html="renderMarkdown((agent as any).agentResult)" />
                        </div>
                      </transition>
                    </div>
                  </template>
                  <!-- 无 agent 时的提示：运行中显示旋转等待，已完成则显示静态说明 -->
                  <div v-if="!wfCompareMode[toolCall.id] && !Object.keys(toolCall.workflowAgents || {}).length" class="wf-agents-empty">
                    <template v-if="toolCall.status === 'running'">
                      <component :is="Loader2Icon" :size="12" class="spin" />
                      <span>{{ t('chat.workflowPanel.waitingForAgents') }}</span>
                    </template>
                    <span v-else class="wf-history-note">{{ t('chat.workflowPanel.historyNotAvailable') }}</span>
                  </div>
                </div>
              </transition>
            </div>
          </template>
        </div>

        <!-- Spawn 子代理任务面板 -->
        <div
          v-if="spawnToolCalls.length > 0"
          class="spawn-container"
        >
          <template v-for="toolCall in spawnToolCalls" :key="toolCall.id">
            <SpawnTaskPanel
              v-if="toolCall.spawn_task"
              :spawn-task="toolCall.spawn_task"
              :tool-call-id="toolCall.id"
              :is-replaying="isReplaying"
              :replay-visible-count="getSpawnVisibleCount(toolCall.id)"
            />
          </template>
        </div>

      <div v-if="message.attachmentItems && message.attachmentItems.length > 0" class="message-attachments">
        <MessageAttachment
          v-for="attachment in message.attachmentItems"
          :key="attachment.path"
          :attachment="attachment"
          :session-id="resolvedSessionId"
        />
      </div>

      <!-- 思考中状态 -->
      <div v-if="message.isThinking && !message.reasoningContent" class="message-content thinking-indicator">
        <span class="thinking-dots">
          <span class="dot" />
          <span class="dot" />
          <span class="dot" />
        </span>
      </div>

      <!-- 消息内容（传统模式） -->
      <!-- eslint-disable-next-line vue/no-v-html -->
      <div
        v-else-if="shouldFuseReasoningReply"
        class="assistant-response-shell"
      >
        <ReasoningBlock
          :content="message.reasoningContent || ''"
          :is-thinking="Boolean(message.isThinking && message.reasoningContent)"
          :default-expanded="false"
          embedded
        />
        <div
          v-if="displayContent && (!isReplaying || replayContent !== null)"
          class="message-content assistant-response-body markdown-content"
          :class="{ 'typewriter-active': isReplaying }"
          v-html="replayContent !== null ? replayContent : renderedContent"
        />
      </div>
      <div 
        v-else-if="message.role === 'assistant' && displayContent && (!isReplaying || replayContent !== null)"
        class="message-content markdown-content"
        :class="{ 'typewriter-active': isReplaying }"
        v-html="replayContent !== null ? replayContent : renderedContent"
      />
      <div 
        v-else-if="message.role !== 'assistant' && message.content"
        class="message-content"
      >
        {{ message.content }}
      </div>
      </div>
      <div class="message-footer">
        <div class="message-time">
          {{ formattedTime }}
        </div>
        <div
          class="message-actions"
        >
          <button
            v-if="message.role === 'assistant'"
            class="action-btn"
            :title="$t('chat.replay') || '重放'"
            @click="handleReplay"
          >
            <component
              :is="isReplaying ? SquareIcon : PlayIcon"
              :size="14"
            />
          </button>
          <button
            v-if="message.role === 'assistant'"
            class="action-btn"
            :title="$t('chat.regenerate')"
            @click="handleRegenerate"
          >
            <component
              :is="RefreshIcon"
              :size="14"
            />
          </button>
          <button
            v-if="message.role === 'assistant'"
            class="action-btn"
            :title="$t('chat.copy')"
            @click="handleCopy"
          >
            <component
              :is="copied ? CheckIcon : CopyIcon"
              :size="14"
            />
          </button>
          <button
            class="action-btn action-btn-delete"
            :title="$t('chat.deleteMessage') || '删除消息'"
            @click="handleDelete"
          >
            <component
              :is="TrashIcon"
              :size="14"
            />
          </button>
        </div>
      </div>
    </div>
  </div>
  
  <!-- 头像设置对话框 - 使用 Teleport 传送到 body -->
  <Teleport to="body">
    <AvatarSettingDialog
      v-model:show="showAvatarDialog"
      :title="avatarDialogTitle"
      :current-url="avatarImageUrl"
      @save="handleAvatarSave"
      @clear="handleAvatarClear"
    />
  </Teleport>
  
  <!-- 多智能体全屏模态框 -->
  <WorkflowFullscreenModal
    v-model="showFullscreenModal"
    :workflow-agents="fullscreenWorkflowAgents"
  />
</template>

<script setup lang="ts">
import { computed, ref, nextTick, onMounted, onBeforeUnmount, watch } from 'vue'
import {
  User as UserIcon,
  Bot as BotIcon,
  RefreshCw as RefreshIcon,
  Copy as CopyIcon,
  Check as CheckIcon,
  Wrench as WrenchIcon,
  ChevronDown as ChevronDownIcon,
  ChevronRight as ChevronRightIcon,
  Play as PlayIcon,
  Square as SquareIcon,
  Trash2 as TrashIcon,
  Users as UsersIcon,
  Loader2 as Loader2Icon,
  LayoutGrid as LayoutGridIcon,
  List as ListIcon,
  Maximize as MaximizeIcon
} from 'lucide-vue-next'
import { useMarkdown } from '@/composables/useMarkdown'
import { useMermaid } from '@/composables/useMermaid'
import { useI18n } from 'vue-i18n'
import { useToast } from '@/composables/useToast'
import { copyTextToClipboard } from '@/utils/clipboard'
import { chatAPI } from '@/api'
import ToolCallCard from '@/components/chat/ToolCallCard.vue'
import ReasoningBlock from '@/components/chat/ReasoningBlock.vue'
import WorkflowComparePanel from '@/components/chat/WorkflowComparePanel.vue'
import WorkflowListPanel from '@/components/chat/WorkflowListPanel.vue'
import WorkflowFullscreenModal from '@/components/chat/WorkflowFullscreenModal.vue'
import SpawnTaskPanel from '@/components/chat/SpawnTaskPanel.vue'
import InterleavedMessage from '@/components/chat/InterleavedMessage.vue'
import MessageAttachment from '@/components/chat/MessageAttachment.vue'
import { normalizeHistoryToolCall } from '@/modules/chat/utils/historyMessages'
import { useChatStore } from '@/store/chat'
import type { ChatMessage, ChatToolCall } from '@/types/chat'

interface Props {
  message: ChatMessage
}

interface Emits {
  (e: 'regenerate', messageId: string): void
  (e: 'replay-start', messageId: string): void
  (e: 'delete', messageId: string): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const { renderMarkdown } = useMarkdown()
const { t } = useI18n()
const toast = useToast()
const chatStore = useChatStore()

const HISTORY_TOOL_PAGE_SIZE = 20
const HISTORY_TOOL_PREVIEW_LIMIT = 1200

const copied = ref(false)
const toolCallsExpanded = ref(false)
const isReplaying = ref(false)
const replayContent = ref<string | null>(null)
const replayToolIndex = ref(0)
// 重放时每个 workflow_run 面板的可见 agent 数量（tcId → count）
const replayWorkflowVisibleCounts = ref<Record<string, number>>({})
// 重放时每个 spawn 面板的可见工具调用数量（tcId → count）
const replaySpawnVisibleCounts = ref<Record<string, number>>({})
// 重放时每个普通工具调用是否显示结果（tcId → boolean）
const replayToolResultVisible = ref<Record<string, boolean>>({})
// 重放时交织消息的可见段落数量
const replayInterleavedSegments = ref(0)
let replayTimer: number | null = null

// 消息根元素引用，用于重放时定位 DOM 元素
const rootEl = ref<HTMLElement>()
const historyToolCalls = ref<ChatToolCall[]>([])
const historyToolCallsLoaded = ref(false)
const historyToolCallsLoading = ref(false)
const historyToolCallsError = ref('')

const inlineToolCalls = computed(() => props.message.toolCalls || [])

const effectiveToolCalls = computed(() => {
  if (historyToolCallsLoaded.value) {
    return historyToolCalls.value
  }
  return inlineToolCalls.value
})

const loadedToolCallCount = computed(() => effectiveToolCalls.value.length)

const totalToolCallCount = computed(() => {
  return Math.max(
    props.message.toolCallCount || 0,
    inlineToolCalls.value.length,
    historyToolCallsLoaded.value ? historyToolCalls.value.length : 0
  )
})

const shouldFetchHistoryToolCalls = computed(() => {
  return totalToolCallCount.value > 0 && inlineToolCalls.value.length === 0
})

const shouldAutoLoadSpecialHistoryToolCalls = computed(() => {
  if (!shouldFetchHistoryToolCalls.value) return false
  if (props.message.role !== 'assistant') return false

  const specialToolNames = props.message.specialToolCallNames || []
  if (specialToolNames.length > 0) return true

  const content = props.message.content || ''
  return content.includes('<!--WORKFLOW_EXEC:')
})

const hasHistoryWorkflowTool = computed(() => {
  return (props.message.specialToolCallNames || []).includes('workflow_run')
})

const shouldShowToolCallsSection = computed(() => {
  return totalToolCallCount.value > 0 && (!isReplaying.value || replayToolIndex.value > 0)
})

const resolvedSessionId = computed(() => props.message.sessionId || chatStore.currentSessionId || '')

const canLoadMoreToolCalls = computed(() => {
  return historyToolCallsLoaded.value && loadedToolCallCount.value < totalToolCallCount.value
})

const mergeUniqueToolCalls = (existing: ChatToolCall[], incoming: ChatToolCall[]): ChatToolCall[] => {
  const deduped = new Map<string, ChatToolCall>()
  for (const toolCall of existing) {
    deduped.set(toolCall.id, toolCall)
  }
  for (const toolCall of incoming) {
    deduped.set(toolCall.id, toolCall)
  }
  return Array.from(deduped.values())
}

const loadHistoryToolCalls = async (append = false) => {
  if (!shouldFetchHistoryToolCalls.value || !resolvedSessionId.value || historyToolCallsLoading.value) {
    return
  }

  historyToolCallsLoading.value = true
  historyToolCallsError.value = ''

  try {
    const response = await chatAPI.getMessageToolCalls(
      resolvedSessionId.value,
      Number(props.message.id),
      {
        limit: HISTORY_TOOL_PAGE_SIZE,
        offset: append ? historyToolCalls.value.length : 0,
        tool_mode: 'summary',
        tool_preview_limit: HISTORY_TOOL_PREVIEW_LIMIT,
      }
    )

    const normalized = response.items.map((toolCall) => normalizeHistoryToolCall(toolCall))
    historyToolCalls.value = append
      ? mergeUniqueToolCalls(historyToolCalls.value, normalized)
      : normalized
    historyToolCallsLoaded.value = true
  } catch (error) {
    console.error('[MessageItem] 加载工具调用失败:', error)
    historyToolCallsError.value = '工具调用加载失败，请重试'
    toast.error(historyToolCallsError.value)
  } finally {
    historyToolCallsLoading.value = false
  }
}

const loadMoreToolCalls = async () => {
  await loadHistoryToolCalls(true)
}

const toggleToolCalls = async () => {
  toolCallsExpanded.value = !toolCallsExpanded.value
  if (toolCallsExpanded.value && shouldFetchHistoryToolCalls.value && !historyToolCallsLoaded.value) {
    await loadHistoryToolCalls(false)
  }
}

watch(
  () => props.message.id,
  () => {
    historyToolCalls.value = []
    historyToolCallsLoaded.value = false
    historyToolCallsLoading.value = false
    historyToolCallsError.value = ''
    toolCallsExpanded.value = false
  }
)

watch(
  shouldAutoLoadSpecialHistoryToolCalls,
  (shouldAutoLoadSpecialTools) => {
    if (
      shouldAutoLoadSpecialTools &&
      !historyToolCallsLoaded.value &&
      !historyToolCallsLoading.value
    ) {
      void loadHistoryToolCalls(false)
    }
  },
  { immediate: true }
)

// ---- Workflow Run Panel State ----
// 存储每个 workflow_run toolCall 的面板展开状态（undefined = 自动，true/false = 用户手动）
const wfPanelExpanded = ref<Record<string, boolean>>({})
// 存储每个 agent 的展开状态
const wfAgentExpanded = ref<Record<string, boolean>>({})
// 存储每个 agent 的工具调用展开状态
const wfAgentToolsExpanded = ref<Record<string, boolean>>({})
// 存储每个 workflow_run 面板的并排对比模式状态
const wfCompareMode = ref<Record<string, boolean>>({})
// 全屏模态框状态
const showFullscreenModal = ref(false)
const fullscreenWorkflowAgents = ref<Record<string, any>>({})

// ---- Spawn Panel State ----
// 存储每个 spawn toolCall 的面板展开状态
const spawnPanelExpanded = ref<Record<string, boolean>>({})

/**
 * 判断 workflow 面板是否展开
 * - 用户手动切换过：使用手动状态
 * - 否则：运行中自动展开，完成后折叠
 */
const isWfPanelOpen = (tcId: string, status?: string): boolean => {
  if (wfPanelExpanded.value[tcId] !== undefined) return wfPanelExpanded.value[tcId]
  if (historyToolCallsLoaded.value && inlineToolCalls.value.length === 0 && hasHistoryWorkflowTool.value) {
    return true
  }
  return status === 'running'
}

const toggleWorkflowPanel = (tcId: string, status?: string) => {
  const cur = isWfPanelOpen(tcId, status)
  wfPanelExpanded.value = { ...wfPanelExpanded.value, [tcId]: !cur }
}

/**
 * 打开全屏模态框
 */
const openFullscreen = (toolCall: ChatToolCall) => {
  fullscreenWorkflowAgents.value = toolCall.workflowAgents || {}
  showFullscreenModal.value = true
}

const wfModeLabel = (mode: string): string => {
  const key = `chat.workflowPanel.modes.${mode}`
  const translated = t(key)
  // t() returns the key itself when no translation is found
  return translated === key ? mode : translated
}

/** 判断某个 agent 是否展开 */
const isAgentOpen = (tcId: string, agentId: string, status?: string): boolean => {
  const key = `${tcId}:${agentId}`
  if (wfAgentExpanded.value[key] !== undefined) return wfAgentExpanded.value[key]
  return status === 'running' // 运行中默认展开，完成后折叠
}

const toggleAgentPanel = (tcId: string, agentId: string, status?: string) => {
  const key = `${tcId}:${agentId}`
  const cur = isAgentOpen(tcId, agentId, status)
  wfAgentExpanded.value = { ...wfAgentExpanded.value, [key]: !cur }
}

/** 判断某个 agent 的工具调用是否展开 */
const isAgentToolsOpen = (tcId: string, agentId: string): boolean => {
  const key = `${tcId}:${agentId}:tools`
  if (wfAgentToolsExpanded.value[key] !== undefined) return wfAgentToolsExpanded.value[key]
  return true // 默认展开
}

const toggleAgentTools = (tcId: string, agentId: string) => {
  const key = `${tcId}:${agentId}:tools`
  const cur = isAgentToolsOpen(tcId, agentId)
  wfAgentToolsExpanded.value = { ...wfAgentToolsExpanded.value, [key]: !cur }
}

// 头像相关
import { useAvatar } from '@/composables/useAvatar'
import AvatarSettingDialog from '@/components/chat/AvatarSettingDialog.vue'

const { userAvatarUrl, aiAvatarUrl, setUserAvatar, setAiAvatar, clearUserAvatar, clearAiAvatar, initAvatars } = useAvatar()
const showAvatarDialog = ref(false)
const avatarDialogTitle = computed(() => props.message.role === 'user' ? t('avatar.setUserAvatar') : t('avatar.setAIAvatar'))

const avatarIcon = computed(() => (props.message.role === 'user' ? UserIcon : BotIcon))
const avatarImageUrl = computed(() => props.message.role === 'user' ? userAvatarUrl.value : aiAvatarUrl.value)

const handleAvatarClick = () => {
  showAvatarDialog.value = true
}

const handleAvatarSave = (url: string) => {
  if (props.message.role === 'user') {
    setUserAvatar(url)
  } else {
    setAiAvatar(url)
  }
}

const handleAvatarClear = () => {
  if (props.message.role === 'user') {
    clearUserAvatar()
  } else {
    clearAiAvatar()
  }
}

// 初始化头像
onMounted(() => {
  initAvatars()
})

const WORKFLOW_META_RE = /\n?\n?<!--WORKFLOW_EXEC:[\s\S]*?:WORKFLOW_EXEC-->$/u
const PIPELINE_WORKFLOW_HEADER = '# Pipeline Workflow Results'

const stripWorkflowMeta = (content: string | null | undefined): string => {
  return (content || '').replace(WORKFLOW_META_RE, '').trim()
}

const extractWorkflowDisplayText = (
  content: string | null | undefined,
  toolCalls?: ChatToolCall[]
): string => {
  const stripped = stripWorkflowMeta(content)
  if (!stripped) return ''

  const hasWorkflowRun = (toolCalls || []).some(tc => tc.name === 'workflow_run')
  if (!hasWorkflowRun) return stripped

  if (stripped.startsWith(PIPELINE_WORKFLOW_HEADER)) {
    const blocks = stripped
      .split(/\n\n---\n\n/)
      .map(block => block.trim())
      .filter(Boolean)

    if (blocks.length > 1) {
      const lastBlock = blocks[blocks.length - 1]
      const stageContent = lastBlock.replace(/^##\s+[^\n]+\n+/u, '').trim()
      if (stageContent) return stageContent
    }
  }

  return stripped
}

const workflowResultFallback = computed(() => {
  const workflowCall = effectiveToolCalls.value
    .filter(tc => tc.name === 'workflow_run')
    .slice()
    .reverse()
    .find(tc => tc.result && String(tc.result).trim())

  if (!workflowCall?.result) return ''
  return extractWorkflowDisplayText(String(workflowCall.result), effectiveToolCalls.value)
})

const shouldHideRawWorkflowWrapper = computed(() => {
  if (!hasHistoryWorkflowTool.value) return false
  if (!shouldAutoLoadSpecialHistoryToolCalls.value) return false
  if (historyToolCallsLoaded.value) return false

  return stripWorkflowMeta(props.message.content).startsWith(PIPELINE_WORKFLOW_HEADER)
})

const displayContent = computed(() => {
  if (shouldHideRawWorkflowWrapper.value) {
    return ''
  }

  const directContent = extractWorkflowDisplayText(props.message.content, effectiveToolCalls.value)
  if (directContent) return directContent
  if (props.message.role === 'assistant') {
    return workflowResultFallback.value
  }
  return props.message.content || ''
})

const renderedContent = computed(() => {
  const content = displayContent.value
  if (props.message.role === 'assistant') {
    return renderMarkdown(content)
  }
  return content
})

useMermaid(rootEl, [renderedContent, replayContent, () => effectiveToolCalls.value], { deep: true })

/**
 * 判断是否使用交织模式展示
 * 条件：有内容、有工具调用、且没有 workflow_run 或 spawn
 */
const useInterleavedMode = computed(() => {
  if (!displayContent.value || inlineToolCalls.value.length === 0) {
    return false
  }
  
  // 如果有 workflow_run 或 spawn，不使用交织模式
  const hasSpecialTools = inlineToolCalls.value.some(
    tc => tc.name === 'workflow_run' || tc.name === 'spawn'
  )
  
  return !hasSpecialTools
})

const interleavedContent = computed(() => {
  if (!isReplaying.value) {
    return renderedContent.value
  }

  return replayContent.value ?? ''
})

const visibleToolCalls = computed(() => {
  const all = effectiveToolCalls.value
  if (!isReplaying.value) return all
  return all.slice(0, replayToolIndex.value)
})

/**
 * 分离出 workflow_run 工具调用
 */
const workflowToolCalls = computed(() => {
  return visibleToolCalls.value.filter(tc => tc.name === 'workflow_run')
})

/**
 * 分离出普通工具调用（排除 workflow_run 和 spawn）
 */
const regularToolCalls = computed(() => {
  return visibleToolCalls.value.filter(tc => tc.name !== 'workflow_run' && tc.name !== 'spawn')
})

/**
 * 分离出 spawn 工具调用
 */
const spawnToolCalls = computed(() => {
  return visibleToolCalls.value.filter(tc => tc.name === 'spawn')
})

const hasSpecialVisibleToolCalls = computed(() => {
  return workflowToolCalls.value.length > 0 || spawnToolCalls.value.length > 0
})

const shouldFuseReasoningReply = computed(() => {
  return (
    props.message.role === 'assistant' &&
    Boolean(props.message.reasoningContent) &&
    !useInterleavedMode.value
  )
})

/**
 * 重放时按可见计数截取 agent 列表；非重放时返回全部。
 */
const visibleAgents = (toolCall: any): any[] => {
  const all = Object.values(toolCall.workflowAgents || {})
  if (!isReplaying.value) return all
  const count = replayWorkflowVisibleCounts.value[toolCall.id]
  if (count === undefined) return []
  return all.slice(0, count)
}

/**
 * 获取普通工具调用是否显示结果（用于重放）
 */
const shouldShowToolResult = (toolCallId: string): boolean => {
  if (!isReplaying.value) return true // 非重放时始终显示
  return replayToolResultVisible.value[toolCallId] ?? false
}

/**
 * 获取 spawn 面板中可见的工具调用数量（用于重放）
 */
const getSpawnVisibleCount = (toolCallId: string): number | undefined => {
  if (!isReplaying.value) return undefined
  return replaySpawnVisibleCounts.value[toolCallId]
}

import { formatTime } from '@/utils/time'

const formattedTime = computed(() => {
  return formatTime(props.message.timestamp)
})

const handleRegenerate = () => {
  emit('regenerate', props.message.id)
}

const handleDelete = () => {
  if (confirm(t('chat.confirmDeleteMessage') || '确定要删除这条消息吗？')) {
    emit('delete', props.message.id)
  }
}

const handleCopy = async () => {
  try {
    await copyTextToClipboard(displayContent.value)
    copied.value = true
    toast.success(t('chat.copied'))
    
    setTimeout(() => {
      copied.value = false
    }, 2000)
  } catch (error) {
    console.error('Failed to copy:', error)
    toast.error(t('chat.copyFailed'))
  }
}

const handleReplay = () => {
  if (isReplaying.value) {
    stopReplay()
    return
  }
  
  const hasContent = displayContent.value
  const hasToolCalls = effectiveToolCalls.value.length > 0
  if (!hasContent && !hasToolCalls) return
  
  // 先清空所有内容（blank slate）
  isReplaying.value = true
  replayContent.value = null  // null = 隐藏文字区域
  replayToolIndex.value = 0   // 0 = 隐藏所有工具调用
  replayInterleavedSegments.value = 0  // 0 = 隐藏所有交织段落
  toolCallsExpanded.value = true
  
  // 通知父组件滚动到此消息
  emit('replay-start', props.message.id)
  
  // 延迟后开始重放，让用户看到清空效果
  replayTimer = window.setTimeout(() => {
    // 如果使用交织模式，使用新的重放逻辑
    if (useInterleavedMode.value) {
      startInterleavedReplay()
    } else if (hasToolCalls) {
      showToolCallsSequentially()
    } else {
      startTextReplay()
    }
  }, 300)
}

const showToolCallsSequentially = () => {
  if (!isReplaying.value) return

  const toolCalls = effectiveToolCalls.value
  if (replayToolIndex.value < toolCalls.length) {
    replayToolIndex.value++
    const justRevealed = toolCalls[replayToolIndex.value - 1]

    // workflow_run 面板：先强制展开面板，再逐个展示子 agent，最后继续后续工具调用
    if (justRevealed?.name === 'workflow_run') {
      // 强制展开面板，确保 agent 动画在展开状态下进行
      wfPanelExpanded.value = { ...wfPanelExpanded.value, [justRevealed.id]: true }
      replayWorkflowVisibleCounts.value[justRevealed.id] = 0
      // 等待面板展开动画完成后再开始逐个出现
      replayTimer = window.setTimeout(() => {
        animateWorkflowAgents(justRevealed, () => {
          replayTimer = window.setTimeout(showToolCallsSequentially, 400)
        })
      }, 300)
    } 
    // spawn 面板：先强制展开面板，再逐个展示子代理工具调用
    else if (justRevealed?.name === 'spawn' && justRevealed.spawn_task) {
      // 强制展开面板
      spawnPanelExpanded.value = { ...spawnPanelExpanded.value, [justRevealed.id]: true }
      replaySpawnVisibleCounts.value[justRevealed.id] = 0
      // 等待面板展开动画完成后再开始逐个出现
      replayTimer = window.setTimeout(() => {
        animateSpawnToolCalls(justRevealed, () => {
          replayTimer = window.setTimeout(showToolCallsSequentially, 400)
        })
      }, 300)
    }
    // 普通工具调用：先显示卡片（不含结果），延迟后显示结果
    else {
      // 先显示工具调用卡片（参数部分）
      replayToolResultVisible.value[justRevealed.id] = false
      
      // 延迟显示结果部分（模拟执行过程）
      replayTimer = window.setTimeout(() => {
        if (isReplaying.value && justRevealed.result) {
          replayToolResultVisible.value[justRevealed.id] = true
        }
        // 继续下一个工具调用
        replayTimer = window.setTimeout(showToolCallsSequentially, 300)
      }, 500)
    }
  } else {
    // 工具调用全部展示完毕，进入文字阶段
    if (displayContent.value) {
      replayTimer = window.setTimeout(startTextReplay, 300)
    } else {
      stopReplay()
    }
  }
}

/**
 * 查找最近的可滚动祖先元素（message-list-container）。
 */
const findScrollContainer = (): HTMLElement | null => {
  let el: HTMLElement | null = rootEl.value ?? null
  while (el) {
    if (el.classList.contains('message-list-container')) return el
    el = el.parentElement
  }
  return null
}

/**
 * 将目标元素滚动到可滚动容器的视口内。
 */
const scrollElementIntoContainer = (target: HTMLElement) => {
  const container = findScrollContainer()
  if (!container) {
    // 降级使用浏览器原生滚动
    target.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    return
  }
  const containerRect = container.getBoundingClientRect()
  const targetRect = target.getBoundingClientRect()
  const targetBottom = targetRect.bottom - containerRect.top + container.scrollTop
  const targetTop = targetRect.top - containerRect.top + container.scrollTop
  const visibleBottom = container.scrollTop + container.clientHeight

  // 仅当元素底部超出可视区域时才滚动
  if (targetBottom > visibleBottom) {
    container.scrollTo({ top: targetBottom - container.clientHeight + 16, behavior: 'smooth' })
  } else if (targetTop < container.scrollTop) {
    container.scrollTo({ top: targetTop - 16, behavior: 'smooth' })
  }
}

/**
 * 逐个展示 workflow_run 面板中的子 Agent（每 500ms 一个），完成后调用 onComplete。
 * 每次新 Agent 出现后自动追踪滚动到最新条目。
 */
const animateWorkflowAgents = (tc: any, onComplete: () => void) => {
  if (!isReplaying.value) return
  const agents = Object.values(tc.workflowAgents || {})
  const current = replayWorkflowVisibleCounts.value[tc.id] ?? 0
  if (current < agents.length) {
    replayWorkflowVisibleCounts.value[tc.id] = current + 1
    // 等待 DOM 更新后，将最新出现的 agent 条目滚动到视口内
    nextTick(() => {
      const panel = rootEl.value?.querySelector<HTMLElement>(`.wf-run-panel[data-tc-id="${tc.id}"]`)
      const items = panel?.querySelectorAll<HTMLElement>('.wf-agent-item')
      if (items && items.length > 0) {
        scrollElementIntoContainer(items[items.length - 1])
      }
    })
    replayTimer = window.setTimeout(() => animateWorkflowAgents(tc, onComplete), 500)
  } else {
    onComplete()
  }
}

/**
 * 逐个展示 spawn 面板中的子代理工具调用（每 400ms 一个），完成后调用 onComplete。
 * 前言部分始终显示，工具调用逐个出现，所有工具调用完成后显示总结部分
 */
const animateSpawnToolCalls = (tc: any, onComplete: () => void) => {
  if (!isReplaying.value) return
  const toolCalls = tc.spawn_task?.tool_call_records || []
  const current = replaySpawnVisibleCounts.value[tc.id] ?? 0
  
  if (current < toolCalls.length) {
    replaySpawnVisibleCounts.value[tc.id] = current + 1
    // 等待 DOM 更新后滚动
    nextTick(() => {
      const panel = rootEl.value?.querySelector<HTMLElement>(`.spawn-card[data-tool-call-id="${tc.id}"]`)
      if (panel) {
        scrollElementIntoContainer(panel)
      }
    })
    replayTimer = window.setTimeout(() => animateSpawnToolCalls(tc, onComplete), 400)
  } else {
    // 所有工具调用显示完毕，继续下一个工具调用
    // 总结部分会通过 showEpilogue computed 自动显示
    onComplete()
  }
}

const startTextReplay = () => {
  if (!isReplaying.value || !displayContent.value) return
  
  // 设置为空字符串，使内容区域可见（null = 隐藏）
  replayContent.value = ''
  const rawText = displayContent.value
  let charIndex = 0
  const speed = 15
  
  const tick = () => {
    if (!isReplaying.value) return
    
    const step = Math.min(3, rawText.length - charIndex)
    charIndex += step
    
    const partial = rawText.slice(0, charIndex)
    replayContent.value = renderMarkdown(partial)
    
    if (charIndex >= rawText.length) {
      stopReplay()
      return
    }
    
    replayTimer = window.setTimeout(tick, speed)
  }
  
  replayTimer = window.setTimeout(tick, speed)
}

const stopReplay = () => {
  isReplaying.value = false
  replayContent.value = null
  replayToolIndex.value = 0
  replayWorkflowVisibleCounts.value = {}
  replaySpawnVisibleCounts.value = {}
  replayToolResultVisible.value = {}
  replayInterleavedSegments.value = 0
  if (replayTimer) {
    clearTimeout(replayTimer)
    replayTimer = null
  }
}

/**
 * 交织模式重放：先逐个显示工具调用，然后显示文字内容
 */
const startInterleavedReplay = () => {
  if (!isReplaying.value) return
  
  const toolCalls = effectiveToolCalls.value
  
  // 如果有工具调用，先显示工具调用
  if (toolCalls.length > 0) {
    showInterleavedTools()
  } else {
    // 没有工具调用，直接显示文字
    startTextReplay()
  }
}

/**
 * 交织模式：逐个显示工具调用
 */
const showInterleavedTools = () => {
  if (!isReplaying.value) return
  
  const toolCalls = effectiveToolCalls.value
  if (replayInterleavedSegments.value < toolCalls.length) {
    replayInterleavedSegments.value++
    replayTimer = window.setTimeout(showInterleavedTools, 500)
  } else {
    // 所有工具调用显示完毕，显示文字内容
    if (displayContent.value) {
      replayTimer = window.setTimeout(startTextReplay, 500)
    } else {
      stopReplay()
    }
  }
}

onBeforeUnmount(() => {
  stopReplay()
})
</script>
<style scoped>
@import './styles/MessageItem.css';
</style>


