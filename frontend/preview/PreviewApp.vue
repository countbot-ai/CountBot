<template>
  <div class="preview-root">
    <div class="chat-window">
      <ChatHeader
        :actions="headerActions"
        @toggle-sidebar="noop"
        @clear-chat="noop"
      />

      <main class="main">
        <MessageList :messages="messages" :auto-scroll="false" />
      </main>

      <ChatInput
        :input-message="draft"
        :textarea-ref="undefined"
        :is-streaming="true"
        :can-send="false"
        :show-team-picker="false"
        :filtered-teams="[]"
        :team-picker-index="0"
        :is-mac="() => true"
        :attachments="[]"
        :is-uploading-attachments="false"
        @input="(v) => (draft = v)"
        @send="noop"
        @stop="noop"
        @keydown="noop"
        @team-select="noop"
        @files-selected="noop"
        @remove-attachment="noop"
      />
    </div>

    <aside class="preview-switch">
      <button
        class="preview-switch-btn"
        @click="showWfModal = true"
      >
        全屏弹窗
      </button>
      <button
        class="preview-switch-btn"
        @click="showWiki = !showWiki"
      >
        Wiki 面板
      </button>
      <button
        class="preview-switch-btn"
        @click="showCron = !showCron"
      >
        定时任务
      </button>
      <button
        v-for="option in densityOptions"
        :key="option.id"
        class="preview-switch-btn"
        :class="{ active: density === option.id }"
        @click="density = option.id"
      >
        {{ option.label }}
      </button>
    </aside>

    <!-- 侧栏面板（复刻 ChatWindow 的 panel 容器，用于检查内嵌面板样式） -->
    <template v-if="showWiki || showCron">
      <div class="preview-overlay" @click="showWiki = false; showCron = false" />
      <aside class="preview-panel">
        <header class="preview-panel-head">
          <strong>{{ showCron ? '定时任务' : 'Wiki' }}</strong>
          <button class="preview-panel-close" @click="showWiki = false; showCron = false">✕</button>
        </header>
        <div class="preview-panel-body">
          <CronManager v-if="showCron" />
          <WikiPanel v-else />
        </div>
      </aside>
    </template>

    <WorkflowFullscreenModal
      v-model="showWfModal"
      :workflow-agents="workflowAgentsForModal"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  PanelLeftOpen,
  BrainCircuit,
  Blocks,
  AlarmClock,
  SlidersHorizontal,
  Route,
  BookOpen,
} from 'lucide-vue-next'
import ChatHeader from '@/components/chat/ChatHeader.vue'
import ChatInput from '@/components/chat/ChatInput.vue'
import MessageList from '@/modules/chat/MessageList.vue'
import WorkflowFullscreenModal from '@/components/chat/WorkflowFullscreenModal.vue'
import WikiPanel from '@/modules/wiki/WikiPanel.vue'
import CronManager from '@/modules/scheduler/CronManager.vue'
import type { ChatMessage } from '@/types/chat'

const noop = () => {}
const showWfModal = ref(false)
const showWiki = ref(false)
const showCron = ref(false)
const workflowAgentsForModal = computed(
  () => (messages.value[2]?.toolCalls?.[0]?.workflowAgents as Record<string, any>) || {}
)

// 预览固定中文，避免无头浏览器按 en-US 语言环境渲染成英文
const { locale } = useI18n()
locale.value = 'zh-CN'

// ?theme=dark 用来检查暗色下的层级与对比度；?modal=1 直接打开全屏工作流弹窗
const params = new URLSearchParams(window.location.search)
if (params.get('theme') === 'dark') {
  document.documentElement.setAttribute('data-theme', 'dark')
  document.body.classList.add('dark')
}
if (params.get('modal') === '1') {
  showWfModal.value = true
}
if (params.get('wiki') === '1') {
  showWiki.value = true
}
if (params.get('cron') === '1') {
  showCron.value = true
}

onMounted(async () => {
  await nextTick()
  // MessageList 挂载后会锚到底部，预览需要从第一条看起
  window.setTimeout(() => {
    const container = document.querySelector('.message-list-container')
    if (container) container.scrollTop = 0
  }, 500)
})


const draft = ref('')
const density = ref<'comfortable' | 'compact'>('comfortable')
const densityOptions = [
  { id: 'comfortable' as const, label: '标准' },
  { id: 'compact' as const, label: '紧凑' },
]

const headerActions = [
  { id: 'sessions', icon: PanelLeftOpen, label: 'nav.sessions', tooltip: 'nav.sessionsTooltip', onClick: noop },
  { id: 'multiagent', icon: BrainCircuit, label: 'nav.multiagent', tooltip: 'nav.multiagentTooltip', onClick: noop },
  { id: 'skills', icon: Blocks, label: 'nav.skills', tooltip: 'nav.skillsTooltip', onClick: noop },
  { id: 'wiki', icon: BookOpen, label: 'nav.wiki', tooltip: 'nav.wikiTooltip', onClick: noop },
  { id: 'cron', icon: AlarmClock, label: 'nav.cron', tooltip: 'nav.cronTooltip', onClick: noop },
  { id: 'timeline', icon: Route, label: 'nav.timeline', tooltip: 'nav.timelineTooltip', onClick: noop },
  { id: 'settings', icon: SlidersHorizontal, label: 'settings.title', tooltip: 'nav.settingsTooltip', onClick: noop },
]

const OUTLINE = `我会根据受众分析报告，设计一份可直接交给创作者使用的结构化大纲，并说明每一部分的设计意图和要点。

## 内容架构设计稿

**主题：** 给上班族的「每天 15 分钟减压小习惯」

**设计依据：** 受众分析报告（痛点：时间焦虑、行动门槛高、效果不可见；场景：通勤、午休、睡前；注意力窗口 30–90 秒；语气底线：不施压、不说教）

**目标篇幅：** 600–800 字

### 整体结构

1. **钩子（前 3 秒）**：把「减压」换成「回血」，降低心理门槛
2. **场景锚定**：通勤地铁、午休工位、睡前 5 分钟三个高确定性窗口
3. **动作清单**：每个场景只给一个动作，且都在 15 分钟内可完成
4. **效果可见化**：用一句可自评的体感描述收尾`

const messages = ref<ChatMessage[]>([
  {
    id: '1',
    role: 'user',
    content: '帮我想 5 天的内容排期，面向上班族，主题是每天 15 分钟减压小习惯。不要那种「坚持就是胜利」的说教。',
    timestamp: new Date(Date.now() - 1000 * 60 * 12),
  },
  {
    id: '2',
    role: 'assistant',
    content: OUTLINE,
    timestamp: new Date(Date.now() - 1000 * 60 * 11),
    reasoningContent:
      '先确认受众约束：上班族最缺的是整块时间，所以标题里「15 分钟」比「每天坚持」更有说服力。\n再看语气底线，用户明确排斥说教，那钩子必须落在具体场景而不是口号上。\n结构上先给场景再给动作，最后用一句可自评的体感描述收口，这样读者读完就能判断自己做到没有。',
    toolCalls: [
      {
        id: 'tc-1',
        name: 'write_file',
        arguments: { path: 'content_outline.md', content: '…' },
        result: '已写入 content_outline.md（1,284 字节）',
        status: 'success',
        duration: 380,
      },
      {
        id: 'tc-2',
        name: 'read_file',
        arguments: { path: 'audience_report.md' },
        result: '…',
        status: 'success',
        duration: 120,
      },
      {
        id: 'tc-3',
        name: 'web_search',
        arguments: { query: '上班族 减压 微习惯 2026' },
        error: '上游搜索服务返回 429，已跳过该步骤',
        status: 'error',
        duration: 2400,
      },
    ],
  },
  {
    id: '3',
    role: 'assistant',
    content: '两位成员已经完成分工：受众分析师负责给出场景与语气约束，内容架构师据此产出可直接拍摄的脚本骨架。',
    timestamp: new Date(Date.now() - 1000 * 60 * 6),
    toolCalls: [
      {
        id: 'wf-1',
        name: 'workflow_run',
        arguments: { mode: 'pipeline', team: '内容团队' },
        status: 'running',
        duration: 18400,
        workflowAgents: {
          analyst: {
            id: 'analyst',
            label: '受众分析师',
            status: 'complete',
            toolCalls: [
              {
                id: 'wf-1-a',
                tool: 'read_file',
                arguments: { path: 'audience_brief.md' },
                status: 'success',
                result: '…',
              },
            ],
            agentResult: '受众锁定 25–32 岁通勤上班族，注意力窗口 30–90 秒，排斥励志口吻。',
          },
          writer: {
            id: 'writer',
            label: '内容创作者',
            status: 'complete',
            toolCalls: [
              {
                id: 'wf-1-c',
                tool: 'web_search',
                arguments: { query: '上班族 微习惯 案例' },
                status: 'success',
                result: '…',
              },
            ],
            agentResult: '已产出 5 天的成稿脚本，每天一个动作、一句体感自评。',
          },
          editor: {
            id: 'editor',
            label: '内容编辑',
            status: 'complete',
          },
          architect: {
            id: 'architect',
            label: '内容架构师',
            status: 'running',
            toolCalls: [
              {
                id: 'wf-1-b',
                tool: 'write_file',
                arguments: { path: 'content_outline.md' },
                status: 'running',
              },
            ],
            streamingText: '正在把场景清单压成 5 天的拍摄顺序，先确保每天只出现一个动作。',
          },
        },
      },
    ],
  },
])

if (density.value === 'compact') {
  document.documentElement.dataset.density = 'compact'
}
</script>

<style>
.preview-root {
  position: relative;
  height: 100vh;
  height: 100dvh;
  overflow: hidden;
}

.preview-switch {
  position: fixed;
  bottom: 16px;
  left: 16px;
  z-index: 200;
  display: flex;
  gap: 2px;
  padding: 3px;
  border: 1px solid var(--color-border-primary);
  border-radius: 999px;
  background: var(--color-bg-elevated);
  box-shadow: var(--shadow-sm);
}

.preview-switch-btn {
  border: none;
  border-radius: 999px;
  background: transparent;
  padding: 3px 10px;
  color: var(--color-text-tertiary);
  font-size: 11px;
  cursor: pointer;
}

.preview-switch-btn.active {
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
}

.preview-overlay {
  position: fixed;
  inset: 0;
  z-index: 98;
  background: var(--color-bg-overlay);
}

.preview-panel {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  z-index: 100;
  display: flex;
  flex-direction: column;
  width: min(760px, 100vw);
  background: var(--color-bg-elevated);
  border-left: 1px solid var(--color-border-primary);
}

.preview-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 52px;
  padding: 0 16px;
  border-bottom: 1px solid var(--color-border-primary);
  color: var(--color-text-primary);
  font-size: 15px;
}

.preview-panel-close {
  border: 0;
  background: transparent;
  color: var(--color-text-tertiary);
  font-size: 14px;
  cursor: pointer;
}

.preview-panel-body {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
</style>
