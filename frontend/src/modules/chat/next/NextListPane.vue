<template>
  <aside class="nc-list-pane" :class="{ 'is-open': open }">
    <div v-if="open" class="nc-list-inner">
      <header class="nc-list-head">
        <h2 class="nc-list-title">{{ $t('nav.chat') }}</h2>
        <div class="nc-list-head-actions">
          <button
            class="nc-list-icon"
            :title="$t('chat.next.collapseSidebar')"
            :aria-label="$t('chat.next.collapseSidebar')"
            @click="$emit('close')"
          >
            <component :is="PanelLeftCloseIcon" :size="16" />
          </button>
        </div>
      </header>

      <div class="nc-list-content">
        <div class="nc-search">
          <component :is="SearchIcon" :size="14" class="nc-search-icon" />
          <input
            ref="searchInputRef"
            v-model="query"
            class="nc-search-input"
            type="text"
            :placeholder="$t('chat.next.searchSessions')"
            :aria-label="$t('chat.next.searchSessions')"
            @keydown.esc="query = ''"
          />
          <button
            v-if="query"
            class="nc-search-clear"
            :title="$t('common.clear')"
            :aria-label="$t('common.clear')"
            @click="query = ''"
          >
            <component :is="XIcon" :size="13" />
          </button>
          <span class="nc-search-divider" aria-hidden="true" />
          <button
            class="nc-search-action"
            :title="$t('chat.newSession')"
            :aria-label="$t('chat.newSession')"
            @click="$emit('create')"
          >
            <component :is="PlusIcon" :size="15" />
          </button>
        </div>

        <div v-if="loading && sessions.length === 0" class="nc-session-loading">
          {{ $t('common.loading') }}
        </div>

        <div v-else class="nc-session-list">
          <div
            v-for="session in filteredSessions"
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
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import type { ComponentPublicInstance } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  PanelLeftClose as PanelLeftCloseIcon,
  Pencil as PencilIcon,
  Plus as PlusIcon,
  Search as SearchIcon,
  Settings as SettingsIcon,
  Trash2 as TrashIcon,
  X as XIcon,
} from 'lucide-vue-next'
import type { Session } from '@/store/chat'
import { parseTimestamp } from '@/utils/time'

const props = withDefaults(
  defineProps<{
    open?: boolean
    sessions?: Session[]
    currentSessionId?: string | null
    loading?: boolean
  }>(),
  {
    open: true,
    sessions: () => [],
    currentSessionId: null,
    loading: false,
  },
)

const emit = defineEmits<{
  create: []
  select: [sessionId: string]
  config: [sessionId: string]
  rename: [payload: { sessionId: string; name: string }]
  delete: [sessionId: string]
  close: []
}>()

const { t } = useI18n()

const query = ref('')
const searchInputRef = ref<HTMLInputElement>()

const filteredSessions = computed(() => {
  const keyword = query.value.trim().toLowerCase()
  const list = keyword
    ? props.sessions.filter(session => (session.name || '').toLowerCase().includes(keyword))
    : props.sessions

  return [...list].sort(
    (a, b) => parseTimestamp(b.updatedAt).getTime() - parseTimestamp(a.updatedAt).getTime(),
  )
})

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

const focusSearch = async () => {
  await nextTick()
  searchInputRef.value?.focus()
}

defineExpose({ focusSearch })
</script>

<style scoped>
@import './styles/NextListPane.css';
</style>
