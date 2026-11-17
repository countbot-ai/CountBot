<template>
  <div class="wiki-panel">
    <div class="wiki-header">
      <div class="top-tabs">
        <button
          class="top-tab"
          :class="{ active: activeTab === 'entries' }"
          @click="activeTab = 'entries'"
        >
          <component :is="BookOpenIcon" :size="16" />
          {{ $t('wiki.panel.library') }}
        </button>
        <button
          class="top-tab"
          :class="{ active: activeTab === 'guide' }"
          @click="activeTab = 'guide'"
        >
          <component :is="LightbulbIcon" :size="16" />
          {{ $t('wiki.panel.guide') }}
        </button>
      </div>

      <div class="header-actions">
        <button
          v-if="activeTab === 'entries'"
          class="create-btn"
          @click="handleCreate"
        >
          <component :is="PlusIcon" :size="16" />
          {{ $t('wiki.panel.newEntry') }}
        </button>
        <button
          v-if="activeTab === 'entries'"
          class="compile-btn"
          @click="showCompileDialog = true"
        >
          <component :is="SparklesIcon" :size="16" />
          {{ $t('wiki.panel.aiCompile') }}
        </button>
        <button
          class="refresh-btn"
          :disabled="loading"
          @click="handleRefresh"
        >
          <component
            :is="RefreshIcon"
            :size="16"
            :class="{ 'spin': loading }"
          />
        </button>
      </div>
    </div>

    <template v-if="activeTab === 'entries'">
      <!-- Stats Bar -->
      <div
        v-if="!loading && entries.length > 0"
        class="stats-bar"
      >
        <div class="stat">
          <component :is="BookOpenIcon" :size="16" />
          {{ $t('wiki.panel.totalEntries', { n: entries.length }) }}
        </div>
        <div class="stat">
          <component :is="TagIcon" :size="16" />
          {{ $t('wiki.panel.tags', { n: uniqueTags.length }) }}
        </div>
        <div class="stat">
          <component :is="ClockIcon" :size="16" />
          {{ $t('wiki.panel.recentlyUpdated', { time: latestUpdate }) }}
        </div>
      </div>

      <!-- Filter Bar -->
      <div
        v-if="!loading && entries.length > 0"
        class="filter-bar"
      >
        <div class="filter-controls">
          <div class="filter-tabs">
            <button
              class="filter-tab"
              :class="{ active: filterTag === 'all' }"
              @click="filterTag = 'all'"
            >
              <component :is="BookOpenIcon" :size="16" />
              {{ $t('wiki.panel.allWithCount', { n: entries.length }) }}
            </button>
            <button
              v-for="tag in uniqueTags.slice(0, 4)"
              :key="tag"
              class="filter-tab"
              :class="{ active: filterTag === tag }"
              @click="filterTag = tag"
            >
              <component :is="TagIcon" :size="16" />
              {{ tag }} ({{ tagCounts[tag] }})
            </button>
          </div>

          <div class="search-box">
            <component :is="SearchIcon" :size="16" />
            <input
              v-model="searchQuery"
              class="search-input"
              type="search"
              :placeholder="$t('wiki.panel.searchPlaceholder')"
              :aria-label="$t('wiki.panel.searchAria')"
              @keyup.escape="searchQuery = ''"
            >
            <button
              v-if="searchQuery"
              type="button"
              class="search-clear-btn"
              @click="searchQuery = ''"
            >
              {{ $t('wiki.panel.clear') }}
            </button>
          </div>
        </div>

        <p class="filter-summary">
          {{ filteredSummary }}
        </p>
      </div>

      <!-- Loading State -->
      <div
        v-if="loading"
        class="loading-state"
      >
        <component :is="LoaderIcon" :size="32" class="spin" />
        <p>{{ $t('wiki.panel.loading') }}</p>
      </div>

      <!-- Error State -->
      <div
        v-else-if="error"
        class="error-state"
      >
        <component :is="AlertCircleIcon" :size="32" />
        <p>{{ error }}</p>
        <button class="retry-btn" @click="handleRefresh">{{ $t('wiki.panel.retry') }}</button>
      </div>

      <!-- Entries Grid -->
      <div
        v-else-if="filteredEntries.length > 0"
        class="entries-grid"
      >
        <div
          v-for="entry in filteredEntries"
          :key="entry.slug"
          class="entry-card"
        >
          <!-- Card Header -->
          <div class="card-header">
            <div class="entry-info">
              <component :is="FileTextIcon" :size="20" class="entry-icon" />
              <h3 class="entry-title">{{ entry.title }}</h3>
            </div>
          </div>

          <!-- Card Body -->
          <div class="card-body">
            <p class="entry-preview">{{ getPreview(entry.content) }}</p>

            <!-- Tags -->
            <div
              v-if="entry.tags && entry.tags.length > 0"
              class="tags"
            >
              <span
                v-for="tag in entry.tags"
                :key="tag"
                class="tag"
              >
                <component :is="TagIcon" :size="12" />
                {{ tag }}
              </span>
            </div>
          </div>

          <!-- Card Footer -->
          <div class="card-footer">
            <button
              class="view-btn"
              @click.stop="handleView(entry)"
            >
              <component :is="EyeIcon" :size="16" />
              {{ $t('wiki.panel.view') }}
            </button>
            <button
              class="edit-btn"
              @click.stop="handleEdit(entry)"
            >
              <component :is="EditIcon" :size="16" />
            </button>
            <button
              class="delete-btn"
              @click.stop="confirmDelete(entry)"
            >
              <component :is="TrashIcon" :size="16" />
            </button>
          </div>

          <!-- Card Meta -->
          <div class="card-meta">
            <span class="meta-time">
              <component :is="ClockIcon" :size="12" />
              {{ formatTime(entry.updated_at) }}
            </span>
            <span class="meta-slug">{{ entry.slug }}</span>
          </div>
        </div>
      </div>

      <!-- Empty State -->
      <div
        v-else
        class="empty-state"
      >
        <component
          :is="entries.length > 0 ? SearchIcon : BookOpenIcon"
          :size="48"
        />
        <h3>{{ emptyStateTitle }}</h3>
        <p>{{ emptyStateDescription }}</p>
        <div
          v-if="hasActiveFilters"
          class="empty-state-actions"
        >
          <button type="button" class="retry-btn" @click="resetFilters">
            {{ $t('wiki.panel.resetFilters') }}
          </button>
        </div>
      </div>
    </template>

    <!-- Guide Tab -->
    <WikiGuide v-else />

    <!-- Create/Edit Modal -->
    <WikiEditor
      v-model="showEditorModal"
      :entry="editingEntry"
      @save="handleSave"
      @cancel="closeEditor"
    />

    <!-- View Detail Modal -->
    <WikiViewer
      v-model="showViewModal"
      :entry="viewingEntry"
      @edit="handleEdit"
      @close="closeViewer"
    />

    <!-- Compile Modal -->
    <WikiCompiler
      v-model="showCompileDialog"
      @result="useCompileResult"
    />

    <!-- Delete Confirmation -->
    <ConfirmDialog
      v-if="deletingEntry"
      :show="true"
      :title="$t('wiki.panel.deleteTitle')"
      :message="$t('wiki.panel.deleteMessage', { title: deletingEntry.title })"
      @confirm="handleDelete"
      @cancel="deletingEntry = null"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useToast } from '@/composables/useToast'
import { useWiki } from './composables/useWiki'
import {
  RefreshCw as RefreshIcon,
  Loader2 as LoaderIcon,
  AlertCircle as AlertCircleIcon,
  BookOpen as BookOpenIcon,
  Search as SearchIcon,
  Plus as PlusIcon,
  Trash as TrashIcon,
  Edit as EditIcon,
  Eye as EyeIcon,
  Tag as TagIcon,
  Clock as ClockIcon,
  FileText as FileTextIcon,
  Sparkles as SparklesIcon,
  Lightbulb as LightbulbIcon
} from 'lucide-vue-next'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'
import WikiGuide from './components/WikiGuide.vue'
import WikiEditor from './components/WikiEditor.vue'
import WikiViewer from './components/WikiViewer.vue'
import WikiCompiler from './components/WikiCompiler.vue'

const { t } = useI18n()
const toast = useToast()

// 使用组合式函数
const wiki = useWiki()
const {
  entries,
  loading,
  error,
  searchQuery,
  filterTag,
  uniqueTags,
  tagCounts,
  hasActiveFilters,
  filteredEntries,
  latestUpdate,
  loadEntries,
  createEntry,
  updateEntry,
  deleteEntry,
  resetFilters,
  formatTime,
  getPreview,
} = wiki

// 本地状态
const activeTab = ref<'entries' | 'guide'>('entries')
const showEditorModal = ref(false)
const showViewModal = ref(false)
const showCompileDialog = ref(false)
const editingEntry = ref<any>(null)
const viewingEntry = ref<any>(null)
const deletingEntry = ref<any>(null)

// 计算属性
const filteredSummary = computed(() => {
  if (!hasActiveFilters.value) {
    return t('wiki.panel.showAll', { n: entries.value.length })
  }
  return t('wiki.panel.showFiltered', { n: filteredEntries.value.length, total: entries.value.length })
})

const emptyStateTitle = computed(() =>
  entries.value.length > 0 ? t('wiki.panel.noMatch') : t('wiki.panel.noEntries')
)

const emptyStateDescription = computed(() => {
  if (entries.value.length === 0) {
    return t('wiki.panel.createFirst')
  }
  if (searchQuery.value.trim()) {
    return t('wiki.panel.noSearchMatch', { query: searchQuery.value })
  }
  return t('wiki.panel.noTagEntries')
})

// 方法
const handleRefresh = async () => {
  await loadEntries()
  toast.success(t('wiki.panel.refreshSuccess'))
}

const handleCreate = () => {
  editingEntry.value = null
  showEditorModal.value = true
}

const handleEdit = (entry: any) => {
  editingEntry.value = entry
  showViewModal.value = false
  showEditorModal.value = true
}

const handleView = async (entry: any) => {
  try {
    const { wikiApi } = await import('./services/wikiApi')
    viewingEntry.value = await wikiApi.getEntry(entry.slug)
    showViewModal.value = true
  } catch (err: any) {
    toast.error(t('wiki.panel.loadDetailFailed'))
  }
}

const closeEditor = () => {
  showEditorModal.value = false
  editingEntry.value = null
}

const closeViewer = () => {
  showViewModal.value = false
  viewingEntry.value = null
}

const handleSave = async (form: any) => {
  try {
    if (editingEntry.value) {
      await updateEntry(editingEntry.value.slug, form)
      toast.success(t('wiki.panel.updated', { title: form.title }))
    } else {
      await createEntry(form)
      toast.success(t('wiki.panel.created', { title: form.title }))
    }
    closeEditor()
  } catch (err: any) {
    toast.error(err.message || t('wiki.panel.saveFailed'))
  }
}

const confirmDelete = (entry: any) => {
  deletingEntry.value = entry
}

const handleDelete = async () => {
  if (!deletingEntry.value) return
  try {
    await deleteEntry(deletingEntry.value.slug)
    toast.success(t('wiki.panel.deleted', { title: deletingEntry.value.title }))
    deletingEntry.value = null
  } catch (err: any) {
    toast.error(err.message || t('wiki.panel.deleteFailed'))
  }
}

const useCompileResult = () => {
  editingEntry.value = null
  showCompileDialog.value = false
  showEditorModal.value = true
  toast.success(t('wiki.panel.compileFilled'))
}
</script>
<style scoped>
@import './styles/WikiPanel.css';
</style>
