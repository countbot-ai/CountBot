<template>
  <div v-if="cards.length > 0 || sources.length > 0 || refusal" class="native-activity">
    <div v-if="cards.length > 0 || sources.length > 0" class="native-group">
      <button type="button" class="native-group-head" @click="groupExpanded = !groupExpanded">
        <Sparkles :size="13" class="native-group-icon" />
        <span class="native-group-title">{{ $t('chat.native.groupTitle') }}</span>
        <span class="native-group-count">{{ cards.length || sources.length }}</span>
        <span v-if="hasRunning" class="native-group-status">
          {{ $t('chat.native.running') }}
        </span>
        <span v-else-if="groupSummary" class="native-group-summary">{{ groupSummary }}</span>
        <ChevronDown
          :size="13"
          class="native-group-chevron"
          :class="{ expanded: groupExpanded }"
        />
      </button>

      <div v-if="groupExpanded" class="native-group-body">
        <div
          v-for="item in cards"
          :key="item.key"
          class="native-row"
          :class="{ 'is-error': item.error }"
        >
          <button
            type="button"
            class="native-row-head"
            @click="toggleRow(item.key)"
          >
            <span class="native-row-icon" :class="{ 'is-spinning': item.status === 'running' }">
              <component :is="item.icon" :size="12" />
            </span>
            <span class="native-row-title">{{ item.title }}</span>
            <span class="native-row-sub">{{ rowSubtitle(item) }}</span>
            <span v-if="item.status === 'running'" class="native-row-status">
              {{ $t('chat.native.running') }}
            </span>
            <span v-else-if="item.error" class="native-row-status is-error">
              {{ item.error }}
            </span>
            <span v-if="item.results.length" class="native-row-count">
              {{ item.results.length }}
            </span>
            <ChevronDown
              :size="11"
              class="native-row-chevron"
              :class="{ expanded: isExpanded(item.key) }"
            />
          </button>

          <div v-if="isExpanded(item.key)" class="native-row-detail">
            <div v-if="item.queries.length" class="native-queries">
              <span v-for="query in item.queries" :key="query" class="native-query">
                {{ query }}
              </span>
            </div>

            <a
              v-if="item.url"
              :href="item.url"
              target="_blank"
              rel="noopener noreferrer"
              class="native-link"
            >
              {{ item.titleText || item.url }}
            </a>

            <div v-if="item.results.length" class="native-results">
              <a
                v-for="result in item.results"
                :key="result.url || result.title"
                :href="result.url"
                target="_blank"
                rel="noopener noreferrer"
                class="native-result"
              >
                <img
                  v-if="result.site_icon"
                  :src="result.site_icon"
                  alt=""
                  class="native-result-icon"
                  loading="lazy"
                  @error="hideIcon"
                />
                <span class="native-result-body">
                  <span class="native-result-title">{{ result.title }}</span>
                  <span v-if="result.snippet" class="native-result-snippet">
                    {{ result.snippet }}
                  </span>
                  <span v-if="result.site_name" class="native-result-site">
                    {{ result.site_name }}
                  </span>
                </span>
              </a>
            </div>
          </div>
        </div>

        <div v-if="sources.length" class="native-sources">
          <span class="native-sources-label">{{ $t('chat.native.sources') }}</span>
          <a
            v-for="source in sources"
            :key="source.url"
            :href="source.url"
            target="_blank"
            rel="noopener noreferrer"
            class="native-source"
            :title="source.title || source.url"
          >
            <span class="native-source-index">{{ source.index }}</span>
            <span class="native-source-title">{{ source.title || hostOf(source.url) }}</span>
          </a>
        </div>
      </div>
    </div>

    <div v-if="refusal" class="native-refusal">
      <AlertTriangle :size="13" />
      <span>{{ refusal }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  AlertTriangle,
  ChevronDown,
  Globe,
  Link2,
  Search,
  Sparkles,
} from 'lucide-vue-next'
import type { NativeChatEvent, NativeSearchResult } from '@/types/nativeCaps'

interface Props {
  events: NativeChatEvent[]
}

const props = defineProps<Props>()
const { t } = useI18n()

const AUTO_COLLAPSE_MS = 10_000
const groupExpanded = ref(false)
const expandedKeys = ref<Set<string>>(new Set())
const collapseTimers = new Map<string, number>()

interface ActivityCard {
  key: string
  icon: typeof Search
  title: string
  titleText: string
  status: 'running' | 'done'
  error: string | null
  queries: string[]
  url: string
  results: NativeSearchResult[]
}

function hostOf(url: string): string {
  try {
    return new URL(url).host
  } catch {
    return url
  }
}

function hideIcon(event: Event): void {
  const target = event.target as HTMLImageElement | null
  if (target) target.style.display = 'none'
}

const visibleEvents = computed(() =>
  (props.events || []).filter(event => event?.kind && event.kind !== 'history_blocks'),
)

const refusal = computed(() => {
  const event = visibleEvents.value.find(item => item.kind === 'refusal')
  return event?.message || ''
})

const cards = computed<ActivityCard[]>(() => {
  const result: ActivityCard[] = []
  const byId = new Map<string, ActivityCard>()

  for (const event of visibleEvents.value) {
    if (event.kind === 'search_start') {
      const card: ActivityCard = {
        key: event.id || `search-${result.length}`,
        icon: Search,
        title: event.deep ? t('chat.native.deepSearch') : t('chat.native.webSearch'),
        titleText: '',
        status: 'running',
        error: null,
        queries: event.queries || [],
        url: '',
        results: [],
      }
      result.push(card)
      if (event.id) byId.set(event.id, card)
      continue
    }

    if (event.kind === 'search_results') {
      const card = event.id ? byId.get(event.id) : undefined
      const target = card || {
        key: `results-${result.length}`,
        icon: Search,
        title: t('chat.native.webSearch'),
        titleText: '',
        status: 'done',
        error: null,
        queries: [],
        url: '',
        results: [],
      }
      target.status = 'done'
      target.results = (event.results || []).filter(item => item.url || item.error)
      const failure = target.results.find(item => item.error)
      target.error = failure?.error || null
      if (!card) result.push(target)
      continue
    }

    if (event.kind === 'read_url_start') {
      const url = event.url || ''
      const card: ActivityCard = {
        key: event.id || `read-${result.length}`,
        icon: Link2,
        title: t('chat.native.readUrl'),
        titleText: hostOf(url),
        status: 'running',
        error: null,
        queries: [],
        url,
        results: [],
      }
      result.push(card)
      if (event.id) byId.set(event.id, card)
      continue
    }

    if (event.kind === 'fetch_result') {
      const card = event.id ? byId.get(event.id) : undefined
      const target = card || {
        key: `fetch-${result.length}`,
        icon: Globe,
        title: t('chat.native.readUrl'),
        titleText: '',
        status: 'done',
        error: null,
        queries: [],
        url: event.url || '',
        results: [],
      }
      target.status = 'done'
      target.url = event.url || target.url
      target.titleText = event.title || hostOf(target.url)
      target.error = event.ok === false ? (event.error || t('chat.native.readFailed')) : null
      if (!card) result.push(target)
      continue
    }

    if (event.kind === 'citation' && event.url) {
      const matched = result.find(item => item.url && item.url === event.url)
      if (matched) matched.status = 'done'
    }
  }

  const hasCitation = visibleEvents.value.some(item => item.kind === 'citation')
  return result.map(card => ({
    ...card,
    status:
      card.status === 'running' && (card.results.length > 0 || (hasCitation && card.icon === Search))
        ? 'done'
        : card.status,
  }))
})

const hasRunning = computed(() => cards.value.some(item => item.status === 'running'))

const groupSummary = computed(() => {
  const first = cards.value.find(item => item.queries.length > 0 || item.titleText)
  if (!first) return ''
  return first.queries[0] || first.titleText
})

function rowSubtitle(item: ActivityCard): string {
  return item.queries[0] || item.titleText || item.url
}

function isExpanded(key: string): boolean {
  return expandedKeys.value.has(key)
}

function clearCollapseTimer(key: string): void {
  const timer = collapseTimers.get(key)
  if (timer !== undefined) {
    window.clearTimeout(timer)
    collapseTimers.delete(key)
  }
}

function setExpanded(key: string, next: boolean): void {
  clearCollapseTimer(key)
  const keys = new Set(expandedKeys.value)
  if (next) {
    keys.add(key)
  } else {
    keys.delete(key)
  }
  expandedKeys.value = keys
  if (next) {
    const timer = window.setTimeout(() => {
      collapseTimers.delete(key)
      const current = new Set(expandedKeys.value)
      current.delete(key)
      expandedKeys.value = current
    }, AUTO_COLLAPSE_MS)
    collapseTimers.set(key, timer)
  }
}

function toggleRow(key: string): void {
  setExpanded(key, !isExpanded(key))
}

const sources = computed(() => {
  const seen = new Set<string>()
  const items: Array<{ index: number; url: string; title: string }> = []
  for (const event of visibleEvents.value) {
    if (event.kind !== 'citation' || !event.url || seen.has(event.url)) continue
    seen.add(event.url)
    items.push({
      index: items.length + 1,
      url: event.url,
      title: event.title || '',
    })
  }
  return items
})

onBeforeUnmount(() => {
  for (const key of collapseTimers.keys()) clearCollapseTimer(key)
})
</script>

<style scoped>
@import './styles/NativeActivity.css';
</style>
