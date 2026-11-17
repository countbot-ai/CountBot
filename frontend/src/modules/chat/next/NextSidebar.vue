<template>
  <aside class="nc-sidebar" :class="{ 'is-open': open }">
    <div class="nc-sidebar-head">
      <div class="nc-brand">
        <img class="nc-brand-logo" src="@/assets/countbot-logo.svg" alt="" />
        <span class="nc-brand-name">CountBot</span>
      </div>
      <button
        class="nc-icon-button nc-sidebar-close"
        :title="$t('chat.next.collapseSidebar')"
        :aria-label="$t('chat.next.collapseSidebar')"
        @click="$emit('toggle')"
      >
        <component :is="PanelLeftCloseIcon" :size="16" />
      </button>
      <button
        class="nc-icon-button nc-sidebar-mobile-close"
        :title="$t('common.close')"
        :aria-label="$t('common.close')"
        @click="$emit('close')"
      >
        <component :is="XIcon" :size="16" />
      </button>
    </div>

    <nav class="nc-nav">
      <button class="nc-nav-item nc-nav-item--primary" @click="$emit('create')">
        <component :is="PlusIcon" :size="16" />
        <span class="nc-nav-label">{{ $t('chat.newSession') }}</span>
        <kbd class="nc-kbd">{{ modKey }}N</kbd>
      </button>

      <button class="nc-nav-item" :class="{ 'is-active': searchOpen }" @click="toggleSearch">
        <component :is="SearchIcon" :size="16" />
        <span class="nc-nav-label">{{ $t('common.search') }}</span>
        <kbd class="nc-kbd">{{ modKey }}K</kbd>
      </button>

      <button class="nc-nav-item" @click="$emit('open-panel', 'cron')">
        <component :is="AlarmClockIcon" :size="16" />
        <span class="nc-nav-label">{{ $t('nav.cron') }}</span>
      </button>

      <button class="nc-nav-item" @click="$emit('open-panel', 'skills')">
        <component :is="BlocksIcon" :size="16" />
        <span class="nc-nav-label">{{ $t('nav.skills') }}</span>
      </button>

      <button class="nc-nav-item" @click="$emit('open-panel', 'wiki')">
        <component :is="BookOpenIcon" :size="16" />
        <span class="nc-nav-label">{{ $t('nav.wiki') }}</span>
      </button>

      <button class="nc-nav-item" @click="$emit('open-settings', 'multiagent')">
        <component :is="UsersIcon" :size="16" />
        <span class="nc-nav-label">{{ $t('nav.multiagent') }}</span>
      </button>

      <button class="nc-nav-item" @click="$emit('open-settings', 'channels')">
        <component :is="RadioIcon" :size="16" />
        <span class="nc-nav-label">{{ $t('nav.remoteConnection') }}</span>
      </button>
    </nav>

    <div v-if="searchOpen" class="nc-search">
      <component :is="SearchIcon" :size="14" class="nc-search-icon" />
      <input
        ref="searchInputRef"
        v-model="query"
        class="nc-search-input"
        type="text"
        :placeholder="$t('chat.next.searchSessions')"
        :aria-label="$t('chat.next.searchSessions')"
        @keydown.esc="closeSearch"
      />
      <button
        class="nc-search-clear"
        :title="$t('common.clear')"
        :aria-label="$t('common.clear')"
        @click="closeSearch"
      >
        <component :is="XIcon" :size="13" />
      </button>
    </div>

    <div class="nc-sessions">
      <div class="nc-section-head">
        <span class="nc-section-title">
          {{ query ? $t('common.search') : $t('nav.recent') }}
        </span>
        <span class="nc-section-count">{{ filteredSessions.length }}</span>
        <button class="nc-section-action" @click="$emit('open-panel', 'sessions')">
          {{ $t('chat.next.allSessions') }}
        </button>
      </div>

      <div v-if="loading && sessions.length === 0" class="nc-session-loading">
        {{ $t('common.loading') }}
      </div>

      <div v-else class="nc-session-list">
        <div
          v-for="session in visibleSessions"
          :key="session.id"
          class="nc-session-row"
          :class="{ 'is-active': session.id === currentSessionId }"
        >
          <input
            v-if="renamingId === session.id"
            :ref="setRenameInput"
            v-model="renameDraft"
            class="nc-session-rename-input"
            type="text"
            :aria-label="$t('chat.next.renameSession')"
            @keydown.enter.prevent="commitRename(session)"
            @keydown.esc.prevent="cancelRename"
            @blur="commitRename(session)"
          />
          <template v-else>
            <button
              class="nc-session-item"
              :class="{ 'is-active': session.id === currentSessionId }"
              :title="session.name"
              @click="$emit('select', session.id)"
            >
              <span class="nc-session-name">{{ session.name || $t('chat.newSession') }}</span>
              <span class="nc-session-time">{{ formatRelative(session.updatedAt) }}</span>
            </button>
            <div class="nc-session-actions">
              <button
                class="nc-session-action"
                :title="$t('chat.next.sessionSettings')"
                :aria-label="$t('chat.next.sessionSettings')"
                @click.stop="$emit('config', session.id)"
              >
                <component :is="SettingsIcon" :size="14" />
              </button>
              <button
                class="nc-session-action"
                :title="$t('chat.next.renameSession')"
                :aria-label="$t('chat.next.renameSession')"
                @click.stop="startRename(session)"
              >
                <component :is="PencilIcon" :size="14" />
              </button>
              <button
                class="nc-session-action nc-session-action--danger"
                :title="$t('chat.next.deleteSession')"
                :aria-label="$t('chat.next.deleteSession')"
                @click.stop="$emit('delete', session.id)"
              >
                <component :is="TrashIcon" :size="14" />
              </button>
            </div>
          </template>
        </div>

        <p v-if="filteredSessions.length === 0" class="nc-session-empty">
          {{ query ? $t('common.noResults') : $t('sessions.empty') }}
        </p>
      </div>

      <button
        v-if="filteredSessions.length > INITIAL_VISIBLE"
        class="nc-show-more"
        @click="showAll = !showAll"
      >
        <component :is="showAll ? ChevronUpIcon : ChevronDownIcon" :size="14" />
        <span>{{ showAll ? $t('chat.next.showLess') : $t('chat.next.showMore') }}</span>
      </button>
    </div>

    <div class="nc-sidebar-foot">
      <button class="nc-nav-item" @click="$emit('open-settings', 'general')">
        <component :is="SettingsIcon" :size="16" />
        <span class="nc-nav-label">{{ $t('settings.title') }}</span>
      </button>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import type { ComponentPublicInstance } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  AlarmClock as AlarmClockIcon,
  Blocks as BlocksIcon,
  BookOpen as BookOpenIcon,
  ChevronDown as ChevronDownIcon,
  ChevronUp as ChevronUpIcon,
  PanelLeftClose as PanelLeftCloseIcon,
  Pencil as PencilIcon,
  Plus as PlusIcon,
  Radio as RadioIcon,
  Search as SearchIcon,
  Settings as SettingsIcon,
  Trash2 as TrashIcon,
  Users as UsersIcon,
  X as XIcon,
} from 'lucide-vue-next'
import type { Session } from '@/store/chat'
import type { SettingsTab } from '@/types/settings'
import { parseTimestamp } from '@/utils/time'

interface Props {
  sessions: Session[]
  currentSessionId: string | null
  loading?: boolean
  open?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  open: true,
})

const emit = defineEmits<{
  create: []
  select: [sessionId: string]
  config: [sessionId: string]
  rename: [payload: { sessionId: string; name: string }]
  delete: [sessionId: string]
  'open-panel': [panel: 'sessions' | 'skills' | 'cron' | 'wiki']
  'open-settings': [tab: SettingsTab]
  toggle: []
  close: []
}>()

const { t } = useI18n()

const INITIAL_VISIBLE = 8

const query = ref('')
const searchOpen = ref(false)
const showAll = ref(false)
const searchInputRef = ref<HTMLInputElement>()

const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)
const modKey = isMac ? '⌘' : 'Ctrl+'

const filteredSessions = computed(() => {
  const keyword = query.value.trim().toLowerCase()
  const list = keyword
    ? props.sessions.filter(session => (session.name || '').toLowerCase().includes(keyword))
    : props.sessions

  return [...list].sort(
    (a, b) => parseTimestamp(b.updatedAt).getTime() - parseTimestamp(a.updatedAt).getTime(),
  )
})

const visibleSessions = computed(() =>
  showAll.value ? filteredSessions.value : filteredSessions.value.slice(0, INITIAL_VISIBLE),
)

const toggleSearch = async () => {
  searchOpen.value = !searchOpen.value
  if (searchOpen.value) {
    await nextTick()
    searchInputRef.value?.focus()
  } else {
    query.value = ''
  }
}

const closeSearch = () => {
  searchOpen.value = false
  query.value = ''
}

// 会话行内重命名：仅一个输入框存在，用函数 ref 取元素（v-for 内字符串 ref 会变成数组）
const renamingId = ref<string | null>(null)
const renameDraft = ref('')
const renameInput = ref<HTMLInputElement | null>(null)

const setRenameInput = (el: Element | ComponentPublicInstance | null) => {
  renameInput.value = (el as HTMLInputElement | null) ?? null
}

const startRename = async (session: Session) => {
  renamingId.value = session.id
  renameDraft.value = session.name || ''
  await nextTick()
  renameInput.value?.focus()
  renameInput.value?.select()
}

const cancelRename = () => {
  renamingId.value = null
  renameDraft.value = ''
}

const commitRename = (session: Session) => {
  // Esc 取消时输入框会被移除并触发 blur，这里用 id 判定避免重复提交
  if (renamingId.value !== session.id) return
  const name = renameDraft.value.trim()
  renamingId.value = null
  renameDraft.value = ''
  if (!name || name === (session.name || '')) return
  emit('rename', { sessionId: session.id, name })
}

const formatRelative = (value: string): string => {
  const date = parseTimestamp(value)
  if (Number.isNaN(date.getTime())) return ''
  const diffMinutes = Math.floor((Date.now() - date.getTime()) / 60000)
  if (diffMinutes < 1) return t('time.justNow')
  if (diffMinutes < 60) return t('time.minutesAgo', { count: diffMinutes })
  const diffHours = Math.floor(diffMinutes / 60)
  if (diffHours < 24) return t('time.hoursAgo', { count: diffHours })
  return t('time.daysAgo', { count: Math.floor(diffHours / 24) })
}

defineExpose({ focusSearch: toggleSearch })
</script>

<style scoped>
@import './styles/NextSidebar.css';
</style>
