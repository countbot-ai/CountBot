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
        :size="15"
      />
    </div>

    <div class="message-body">
      <!-- 交织模式：思考 → 正文 → 工具行，按发生顺序摊开，不套卡片 -->
      <div
        v-if="useInterleavedMode && !message.isThinking"
        key="interleaved-mode"
        class="assistant-response-shell"
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

      <!-- 传统模式：工具 / 工作流 / 正文依次排列 -->
      <div v-else key="traditional-mode" class="message-main">
        <!-- 普通工具调用：一条时直接排开，多条才给一个可折叠的分组标题 -->
        <div v-if="shouldShowToolCallsSection" class="tool-calls">
          <div v-if="showToolCallsHead" class="tool-calls-head" @click="toggleToolCalls">
            <component :is="WrenchIcon" :size="13" class="tool-calls-glyph" />
            <span class="tool-calls-title">{{ $t('tools.toolCalls') || 'Tool Calls' }}</span>
            <span class="tool-calls-count">· {{ totalToolCallCount }}</span>
            <component :is="ChevronDownIcon" :size="13" class="tool-calls-chevron" :class="{ expanded: toolCallsExpanded }" />
          </div>
          <transition name="slide-list">
            <div v-if="isToolCallsListVisible" class="tool-calls-list">
              <p
                v-if="shouldFetchHistoryToolCalls && !historyToolCallsLoaded && !historyToolCallsLoading"
                class="tool-calls-note"
              >
                为避免历史消息卡顿，工具调用按需加载。
              </p>
              <div v-if="historyToolCallsLoading" class="tool-calls-note">
                <component :is="Loader2Icon" :size="13" class="spin" />
                <span>工具调用加载中...</span>
              </div>
              <p v-if="historyToolCallsError" class="tool-calls-error">{{ historyToolCallsError }}</p>

              <ToolCallCard
                v-for="(toolCall, index) in regularToolCalls"
                :key="toolCall.id || index"
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

              <p
                v-if="historyToolCallsLoaded && regularToolCalls.length === 0 && hasSpecialVisibleToolCalls"
                class="tool-calls-note"
              >
                特殊工具调用已在下方工作流或子代理面板展示。
              </p>
              <button
                v-if="canLoadMoreToolCalls"
                class="tool-calls-more"
                :disabled="historyToolCallsLoading"
                @click.stop="loadMoreToolCalls"
              >
                加载更多工具调用 ({{ loadedToolCallCount }}/{{ totalToolCallCount }})
              </button>
            </div>
          </transition>
        </div>

        <!-- 多智能体：一张卡一行摘要，成员与视图开关都在首屏可见 -->
        <div v-if="workflowToolCalls.length > 0" class="team-run">
          <article
            v-for="toolCall in workflowToolCalls"
            :key="toolCall.id"
            class="team-run-card"
            :data-tc-id="toolCall.id"
          >
            <header class="team-run-head">
              <button
                type="button"
                class="team-run-toggle"
                :aria-expanded="isWfPanelOpen(toolCall.id, toolCall.status)"
                @click="toggleWorkflowPanel(toolCall.id, toolCall.status)"
              >
                <component
                  :is="ChevronRightIcon"
                  :size="13"
                  class="team-run-chevron"
                  :class="{ 'is-open': isWfPanelOpen(toolCall.id, toolCall.status) }"
                />
                <component :is="UsersIcon" :size="14" class="team-run-glyph" />
                <span class="team-run-title">{{ t('chat.workflowPanel.title') }}</span>
                <span v-if="toolCall.arguments?.mode" class="team-run-subject">{{ wfModeLabel(toolCall.arguments.mode) }}</span>
                <component
                  v-if="toolCall.status === 'running'"
                  :is="Loader2Icon"
                  :size="12"
                  class="spin team-run-spinner"
                />
                <span class="team-run-meta">{{ wfStatusSummary(toolCall) }}</span>
                <span v-if="toolCall.duration" class="team-run-meta">{{ wfDurationText(toolCall.duration) }}</span>
              </button>

              <div v-if="workflowAgentList(toolCall).length > 1" class="team-run-toolbar">
                <button
                  type="button"
                  :class="{ 'is-active': !wfCompareMode[toolCall.id] }"
                  @click.stop="wfCompareMode[toolCall.id] = false"
                >
                  <component :is="ListIcon" :size="13" />
                  <span>列表</span>
                </button>
                <button
                  type="button"
                  :class="{ 'is-active': wfCompareMode[toolCall.id] }"
                  @click.stop="wfCompareMode[toolCall.id] = true"
                >
                  <component :is="LayoutGridIcon" :size="13" />
                  <span>并排</span>
                </button>
                <button
                  type="button"
                  class="team-run-toolbar-icon"
                  title="全屏查看"
                  @click.stop="openFullscreen(toolCall)"
                >
                  <component :is="MaximizeIcon" :size="13" />
                </button>
              </div>
            </header>

            <!-- 阵容：收起态也能看出有哪几个成员、各自什么状态 -->
            <div v-if="workflowAgentList(toolCall).length" class="team-run-roster">
              <span
                v-for="agent in workflowAgentList(toolCall)"
                :key="agent.id"
                class="team-run-member"
                :class="agent.status === 'running' ? 'is-running' : 'is-done'"
              >
                <span class="team-run-member-dot" />
                <span class="team-run-member-name">{{ agent.label }}</span>
              </span>
            </div>

            <transition name="slide">
              <div v-if="isWfPanelOpen(toolCall.id, toolCall.status)" class="team-run-body">
                <WorkflowComparePanel
                  v-if="wfCompareMode[toolCall.id] && workflowAgentList(toolCall).length"
                  :key="`${toolCall.id}-compare`"
                  :workflow-agents="toolCall.workflowAgents || {}"
                />
                <WorkflowListPanel
                  v-else-if="workflowAgentList(toolCall).length"
                  :key="`${toolCall.id}-list`"
                  :workflow-agents="toolCall.workflowAgents || {}"
                  :visible-count="wfReplayVisibleCount(toolCall.id)"
                />
                <div v-else class="team-run-empty">
                  <component v-if="toolCall.status === 'running'" :is="Loader2Icon" :size="12" class="spin" />
                  <span>{{ toolCall.status === 'running' ? t('chat.workflowPanel.waitingForAgents') : t('chat.workflowPanel.historyNotAvailable') }}</span>
                </div>
              </div>
            </transition>
          </article>
        </div>

        <!-- Spawn 子代理任务面板 -->
        <div v-if="spawnToolCalls.length > 0" class="spawn-container">
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

        <!-- 思考 + 回复融合 -->
        <div
          v-else-if="shouldFuseReasoningReply"
          class="assistant-response-shell"
        >
          <ReasoningBlock
            :content="embeddedReasoningContent"
            :is-thinking="Boolean(message.isThinking && embeddedReasoningContent)"
            :default-expanded="false"
            embedded
          />
          <div
            v-if="displayContent && (!isReplaying || replayContent !== null)"
            class="message-content assistant-response-body markdown-content"
            :class="{ 'typewriter-active': isReplaying || isStreaming }"
            v-html="replayContent !== null ? replayContent : renderedContent"
          />
        </div>
        <div
          v-else-if="message.role === 'assistant' && displayContent && (!isReplaying || replayContent !== null)"
          class="message-content markdown-content"
          :class="{ 'typewriter-active': isReplaying || isStreaming }"
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
        <div class="message-actions">
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
            :class="{ 'is-copied': copied }"
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
import { splitReasoningSections } from '@/utils/reasoningSections'
import { useChatStore } from '@/store/chat'
import type { ChatMessage, ChatToolCall, WorkflowAgentState } from '@/types/chat'

interface Props {
  message: ChatMessage
  /** 本条消息是否正在实时流式输出（用于逐字晕开动画） */
  isStreaming?: boolean
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
  if (totalToolCallCount.value === 0) return false
  if (isReplaying.value && replayToolIndex.value === 0) return false
  // 只有工作流 / spawn 时，它们的明细在各自面板里，这里不再留一个空分组
  if (regularToolCalls.value.length === 0 && !shouldFetchHistoryToolCalls.value) return false
  return true
})

/**
 * 只有一条工具调用时，分组标题是纯冗余：那一行本身就说明了一切。
 * 需要在历史里按需拉取详情时仍保留标题，因为标题是加载入口。
 */
const showToolCallsHead = computed(() => {
  return totalToolCallCount.value > 1 || shouldFetchHistoryToolCalls.value
})

const isToolCallsListVisible = computed(() => {
  return toolCallsExpanded.value || !showToolCallsHead.value
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

/** 成员列表：模板里多处要用（人数、阵容、空态判断），统一从 workflowAgents 取 */
const workflowAgentList = (toolCall: ChatToolCall): WorkflowAgentState[] => {
  return Object.values(toolCall.workflowAgents || {})
}

/** 头部摘要里的成员状态：只写有内容的档位，避免「0 个失败」这类噪音 */
const wfStatusSummary = (toolCall: ChatToolCall): string => {
  const agents = workflowAgentList(toolCall)
  if (agents.length === 0) {
    return toolCall.status === 'running' ? '' : t('chat.workflowPanel.historyNotAvailable')
  }

  const running = agents.filter(agent => agent.status === 'running').length
  const done = agents.length - running
  const parts: string[] = []
  if (running > 0) parts.push(`${running} 运行中`)
  if (done > 0) parts.push(`${done} 已完成`)
  return parts.join(' · ')
}

const wfDurationText = (duration: number): string => {
  if (duration < 1000) return `${duration}ms`
  const seconds = duration / 1000
  if (seconds < 60) return `${seconds.toFixed(1)}s`
  const minutes = Math.floor(seconds / 60)
  const rest = Math.round(seconds % 60)
  return rest > 0 ? `${minutes}m ${rest}s` : `${minutes}m`
}

/** 重放时按可见计数截取成员；非重放返回 undefined（展示全部） */
const wfReplayVisibleCount = (tcId: string): number | undefined => {
  if (!isReplaying.value) return undefined
  return replayWorkflowVisibleCounts.value[tcId]
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

// 字面量 `<!--` 会被 esbuild 依赖扫描识别为 HTML 注释，故以 \x3C / \x3E 转义，语义等价。
const WORKFLOW_META_RE = /\n?\n?\x3C!--WORKFLOW_EXEC:[\s\S]*?:WORKFLOW_EXEC--\x3E$/u
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

const hasWorkflowResult = computed(() => {
  return hasHistoryWorkflowTool.value || effectiveToolCalls.value.some(
    toolCall => toolCall.name === 'workflow_run'
  )
})

const workflowReasoningSections = computed(() => {
  if (props.message.role !== 'assistant' || !hasWorkflowResult.value) {
    return null
  }

  const sections = splitReasoningSections(displayContent.value)
  return sections.reasoning ? sections : null
})

const embeddedReasoningContent = computed(() => {
  return [
    props.message.reasoningContent,
    workflowReasoningSections.value?.reasoning,
  ]
    .filter((content): content is string => Boolean(content))
    .join('\n\n---\n\n')
})

const renderedContent = computed(() => {
  const content = workflowReasoningSections.value?.content ?? displayContent.value
  if (props.message.role === 'assistant') {
    return renderMarkdown(content)
  }
  return content
})

useMermaid(rootEl, [renderedContent, replayContent, () => effectiveToolCalls.value], { deep: true })

// ---- 规则 4 - 流式打字：对正在输出的尾部字符做逐字晕开 ----
// v-html 是全量重渲染，无法在模板层拆字；这里在 DOM 更新后把最后一个
// 文本节点的尾部 N 个字符包成 span.stream-char，由 CSS 完成
// 90ms blur(6px)→清晰、相邻字 30ms 错开的波浪晕开。
const TYPEWRITER_TAIL = 12

const clearStreamChars = (host: HTMLElement) => {
  host.querySelectorAll('span.stream-char').forEach((span) => {
    const parent = span.parentNode
    if (!parent) return
    parent.replaceChild(document.createTextNode(span.textContent || ''), span)
    parent.normalize()
  })
}

const applyTypewriter = () => {
  const root = rootEl.value
  if (!root) return
  const host = root.querySelector<HTMLElement>('.typewriter-active')
  if (!host) return

  clearStreamChars(host)

  // 找最后一个文本节点（跳过 svg / script / style 内的文本，避免破坏结构）
  const walker = document.createTreeWalker(host, NodeFilter.SHOW_TEXT, {
    acceptNode: (node) => {
      const parent = node.parentElement
      if (!parent) return NodeFilter.FILTER_REJECT
      if (parent.closest('svg, script, style')) return NodeFilter.FILTER_REJECT
      return NodeFilter.FILTER_ACCEPT
    },
  })
  let lastText: Text | null = null
  while (walker.nextNode()) lastText = walker.currentNode as Text
  if (!lastText || !lastText.nodeValue || lastText.nodeValue.length < 2) return

  const text = lastText.nodeValue
  const start = Math.max(0, text.length - TYPEWRITER_TAIL)
  const head = text.slice(0, start)
  const tail = text.slice(start)

  const fragment = document.createDocumentFragment()
  if (head) fragment.appendChild(document.createTextNode(head))
  for (let i = 0; i < tail.length; i += 1) {
    const span = document.createElement('span')
    span.className = 'stream-char'
    span.style.setProperty('--i', String(i))
    span.textContent = tail[i]
    fragment.appendChild(span)
  }
  lastText.parentNode?.replaceChild(fragment, lastText)
}

watch(
  [renderedContent, replayContent, () => props.isStreaming],
  () => {
    if (!props.isStreaming && !isReplaying.value) return
    nextTick(applyTypewriter)
  },
  { flush: 'post' }
)

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
    Boolean(embeddedReasoningContent.value) &&
    !useInterleavedMode.value
  )
})

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

    // 规则 10 - 复制对勾 2.5s 后自熄恢复（CSS 侧同步淡出，切换时无感）
    setTimeout(() => {
      copied.value = false
    }, 2500)
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
