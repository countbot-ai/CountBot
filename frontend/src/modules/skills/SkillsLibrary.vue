<template>
  <div class="skills-library">
    <div class="skills-toolbar">
      <div class="filter-tabs">
        <button
          class="filter-tab"
          :class="{ active: filterStatus === 'all' }"
          @click="filterStatus = 'all'"
        >
          {{ $t('skills.all') }}
          <span class="filter-count">{{ skills.length }}</span>
        </button>
        <button
          class="filter-tab"
          :class="{ active: filterStatus === 'enabled' }"
          @click="filterStatus = 'enabled'"
        >
          {{ $t('skills.enabled') }}
          <span class="filter-count">{{ enabledCount }}</span>
        </button>
        <button
          class="filter-tab"
          :class="{ active: filterStatus === 'disabled' }"
          @click="filterStatus = 'disabled'"
        >
          {{ $t('skills.disabled') }}
          <span class="filter-count">{{ disabledCount }}</span>
        </button>
        <button
          class="filter-tab"
          :class="{ active: filterStatus === 'autoLoad' }"
          @click="filterStatus = 'autoLoad'"
        >
          {{ $t('skills.autoLoad') }}
          <span class="filter-count">{{ autoLoadCount }}</span>
        </button>
      </div>

      <div class="toolbar-actions">
        <div class="search-box">
          <component :is="SearchIcon" :size="14" class="search-icon" />
          <input
            v-model="searchQuery"
            class="search-input"
            type="text"
            :placeholder="$t('skills.searchPlaceholder')"
            :aria-label="$t('skills.searchLabel')"
            @keyup.escape="searchQuery = ''"
          />
          <button
            v-if="searchQuery"
            type="button"
            class="search-clear-btn"
            :title="$t('skills.clearSearch')"
            :aria-label="$t('skills.clearSearch')"
            @click="searchQuery = ''"
          >
            <component :is="XIcon" :size="13" />
          </button>
        </div>

        <div class="view-toggle" role="group" :aria-label="$t('skills.viewMode')">
          <button
            class="view-toggle-btn"
            :class="{ active: viewMode === 'card' }"
            :title="$t('skills.cardView')"
            :aria-label="$t('skills.cardView')"
            @click="setViewMode('card')"
          >
            <component :is="LayoutGridIcon" :size="15" />
          </button>
          <button
            class="view-toggle-btn"
            :class="{ active: viewMode === 'list' }"
            :title="$t('skills.listView')"
            :aria-label="$t('skills.listView')"
            @click="setViewMode('list')"
          >
            <component :is="ListIcon" :size="15" />
          </button>
        </div>

        <button
          class="icon-btn"
          :disabled="loading"
          :title="$t('common.refresh')"
          :aria-label="$t('common.refresh')"
          @click="handleRefresh"
        >
          <component :is="RefreshIcon" :size="16" :class="{ spin: loading }" />
        </button>

        <button class="primary-btn" @click="handleCreateSkill">
          <component :is="PlusIcon" :size="15" />
          {{ $t('skills.createSkill') }}
        </button>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="loading" class="loading-state">
      <component :is="LoaderIcon" :size="28" class="spin" />
      <p>{{ $t('common.loading') }}</p>
    </div>

    <!-- Error State -->
    <div v-else-if="error" class="error-state">
      <component :is="AlertCircleIcon" :size="28" />
      <p>{{ error }}</p>
      <button class="secondary-btn" @click="handleRefresh">
        {{ $t('common.retry') }}
      </button>
    </div>

    <!-- Skills Grid / List -->
    <div v-else-if="filteredSkills.length > 0" class="skills-scroll">
      <div v-if="viewMode === 'card'" class="skills-grid">
        <article
          v-for="(skill, index) in filteredSkills"
          :key="skill.name"
          class="skill-card"
          :class="{ 'is-disabled': !skill.enabled }"
        >
          <header class="card-head">
            <div class="skill-info">
              <span class="card-index">{{ padIndex(index) }}</span>
              <component :is="BookOpenIcon" :size="18" class="skill-icon" />
              <h3 class="skill-name">{{ skill.name }}</h3>
            </div>
            <div class="skill-badges">
              <span class="source-badge" :class="skill.source">
                {{ getSourceLabel(skill.source) }}
              </span>
              <span v-if="skill.autoLoad" class="auto-badge" :title="$t('skills.autoLoadTooltip')">
                <component :is="ZapIcon" :size="11" />
                {{ $t('skills.autoLoad') }}
              </span>
            </div>
          </header>

          <div class="card-body">
            <p class="skill-description">
              {{ skill.description || $t('skills.noDescription') }}
            </p>

            <p v-if="skill.source === 'openclaw'" class="card-note">
              {{ $t('skills.openclawImportHint') }}
            </p>

            <div v-if="skill.requirements && skill.requirements.length > 0" class="requirements">
              <component :is="AlertCircleIcon" :size="13" />
              <span class="requirements-label">{{ $t('skills.requirements') }}</span>
              <span v-for="req in skill.requirements" :key="req" class="requirement-tag">
                {{ req }}
              </span>
            </div>
          </div>

          <footer class="card-foot">
            <button class="text-btn" @click.stop="handleViewSkill(skill.name)">
              <component :is="EyeIcon" :size="15" />
              {{ $t('skills.viewDetails') }}
            </button>
            <div class="card-foot-actions">
              <button
                v-if="skill.hasConfig && skill.source !== 'openclaw' && skill.source !== 'shared'"
                class="icon-btn icon-btn--sm"
                :title="$t('skills.editConfig')"
                :aria-label="$t('skills.editConfig')"
                @click.stop="handleQuickEditConfig(skill.name)"
              >
                <component :is="SettingsIcon" :size="15" />
              </button>
              <button
                v-if="userStore.isAdmin && isShareable(skill)"
                class="icon-btn icon-btn--sm share-toggle-btn"
                :class="{ 'is-shared': isSkillShared(skill.name) }"
                :disabled="sharing"
                :title="isSkillShared(skill.name) ? '取消全局共享' : '设为全局共享，所有普通用户可见'"
                :aria-label="isSkillShared(skill.name) ? '取消全局共享' : '设为全局共享'"
                @click.stop="handleShareSkill(skill)"
              >
                <component :is="isSkillShared(skill.name) ? GlobeIcon : ShareIcon" :size="15" />
              </button>
              <button
                class="toggle-btn"
                :class="{ 'is-on': skill.enabled }"
                @click.stop="handleToggleSkill(skill.name, !skill.enabled)"
              >
                <span class="toggle-track"><span class="toggle-thumb" /></span>
                {{ getToggleLabel(skill) }}
              </button>
            </div>
          </footer>
        </article>
      </div>

      <div v-else class="skills-rows">
        <div
          v-for="(skill, index) in filteredSkills"
          :key="skill.name"
          class="skill-row"
          :class="{ 'is-disabled': !skill.enabled }"
        >
          <span class="row-index">{{ padIndex(index) }}</span>
          <div class="row-name-cell">
            <span class="row-name">{{ skill.name }}</span>
            <span class="source-badge" :class="skill.source">
              {{ getSourceLabel(skill.source) }}
            </span>
            <span v-if="skill.autoLoad" class="auto-badge" :title="$t('skills.autoLoadTooltip')">
              <component :is="ZapIcon" :size="11" />
              {{ $t('skills.autoLoad') }}
            </span>
          </div>
          <p class="row-desc">
            {{ skill.description || $t('skills.noDescription') }}
          </p>
          <div class="row-actions">
            <button class="text-btn" @click.stop="handleViewSkill(skill.name)">
              <component :is="EyeIcon" :size="15" />
              {{ $t('skills.viewDetails') }}
            </button>
            <!-- 配置 / 共享图标都用固定槽位，缺失时用占位保持后续操作对齐 -->
            <button
              v-if="skill.hasConfig && skill.source !== 'openclaw' && skill.source !== 'shared'"
              class="icon-btn icon-btn--sm"
              :title="$t('skills.editConfig')"
              :aria-label="$t('skills.editConfig')"
              @click.stop="handleQuickEditConfig(skill.name)"
            >
              <component :is="SettingsIcon" :size="15" />
            </button>
            <span v-else class="action-slot" aria-hidden="true" />
            <button
              v-if="userStore.isAdmin && isShareable(skill)"
              class="icon-btn icon-btn--sm share-toggle-btn"
              :class="{ 'is-shared': isSkillShared(skill.name) }"
              :disabled="sharing"
              :title="isSkillShared(skill.name) ? '取消全局共享' : '设为全局共享，所有普通用户可见'"
              :aria-label="isSkillShared(skill.name) ? '取消全局共享' : '设为全局共享'"
              @click.stop="handleShareSkill(skill)"
            >
              <component :is="isSkillShared(skill.name) ? GlobeIcon : ShareIcon" :size="15" />
            </button>
            <span v-else class="action-slot" aria-hidden="true" />
            <button
              class="toggle-btn"
              :class="{ 'is-on': skill.enabled }"
              @click.stop="handleToggleSkill(skill.name, !skill.enabled)"
            >
              <span class="toggle-track"><span class="toggle-thumb" /></span>
              {{ getToggleLabel(skill) }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Empty State -->
    <div v-else class="empty-state">
      <component :is="hasSkills ? SearchIcon : PackageIcon" :size="36" />
      <h3>{{ emptyStateTitle }}</h3>
      <p>{{ emptyStateDescription }}</p>
      <button v-if="hasActiveFilters" type="button" class="secondary-btn" @click="resetFilters">
        {{ $t('skills.resetFilters') }}
      </button>
    </div>

    <!-- Skill Detail Modal -->
    <Modal
      :model-value="showDetailModal"
      :title="selectedSkill?.name"
      @update:model-value="(val) => !val && handleCloseModal()"
    >
      <div v-if="selectedSkill" class="skill-detail">
        <div class="detail-section">
          <h4 class="section-title">
            {{ $t('skills.information') }}
          </h4>
          <div class="info-grid">
            <div class="info-item">
              <span class="info-label">{{ $t('skills.skillName') }}</span>
              <span class="info-value skill-name-value">{{ selectedSkill.name }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">{{ $t('skills.source') }}</span>
              <span class="info-value">
                <span class="source-badge" :class="selectedSkill.source">
                  {{ getSourceLabel(selectedSkill.source) }}
                </span>
              </span>
            </div>
            <div class="info-item">
              <span class="info-label">{{ $t('skills.status') }}</span>
              <span
                class="info-value status-badge"
                :class="{ 'enabled': selectedSkill.enabled, 'disabled': !selectedSkill.enabled }"
              >
                {{ selectedSkill.enabled ? $t('skills.enabled') : $t('skills.disabled') }}
              </span>
            </div>
            <div class="info-item">
              <span class="info-label">{{ $t('skills.autoLoad') }}</span>
              <span class="info-value" :class="{ 'highlight': selectedSkill.autoLoad }">
                {{ selectedSkill.autoLoad ? $t('common.yes') : $t('common.no') }}
              </span>
            </div>
          </div>
          <div v-if="selectedSkill.description" class="info-item full-width">
            <span class="info-label">{{ $t('skills.description') }}</span>
            <p class="info-value description-text">
              {{ selectedSkill.description }}
            </p>
          </div>
          <p v-if="selectedSkill.source === 'openclaw'" class="guide-note inline-guide-note">
            {{ $t('skills.openclawDetailHint') }}
          </p>
          <div
            v-if="selectedSkill.requirements && selectedSkill.requirements.length > 0"
            class="info-item full-width"
          >
            <span class="info-label">{{ $t('skills.requirements') }}</span>
            <div class="requirements-list">
              <span v-for="req in selectedSkill.requirements" :key="req" class="requirement-tag">
                <component :is="PackageIcon" :size="12" />
                {{ req }}
              </span>
            </div>
          </div>
        </div>

        <div class="detail-section">
          <h4 class="section-title">
            {{ $t('skills.content') }}
          </h4>
          <div class="skill-content">
            <pre class="skill-markdown">{{ renderedContent }}</pre>
          </div>
        </div>

        <div class="detail-actions">
          <button
            v-if="hasConfig && selectedSkill.source !== 'openclaw' && selectedSkill.source !== 'shared'"
            class="secondary-btn"
            @click="handleEditConfig"
          >
            <component :is="SettingsIcon" :size="15" />
            {{ $t('skills.editConfig') }}
          </button>
          <button
            v-if="selectedSkill.source === 'workspace'"
            class="secondary-btn"
            @click="handleEditSkill"
          >
            <component :is="EditIcon" :size="15" />
            {{ $t('common.edit') }}
          </button>
          <button
            v-if="canShareSelected"
            class="secondary-btn share-btn"
            :class="{ 'is-shared': isSkillShared(selectedSkill.name) }"
            :disabled="sharing"
            @click="handleShareSkill(selectedSkill)"
          >
            <component :is="isSkillShared(selectedSkill.name) ? GlobeIcon : ShareIcon" :size="15" />
            {{ sharing ? '处理中…' : (isSkillShared(selectedSkill.name) ? '取消全局共享' : '设为全局共享') }}
          </button>
          <button
            v-if="selectedSkill.source === 'workspace'"
            class="secondary-btn secondary-btn--danger"
            @click="handleDeleteSkill"
          >
            <component :is="TrashIcon" :size="15" />
            {{ $t('common.delete') }}
          </button>
          <button class="primary-btn" @click="handleToggleSkillFromModal(!selectedSkill.enabled)">
            {{ getToggleLabel(selectedSkill) }}
          </button>
          <button class="secondary-btn" @click="handleCloseModal">
            {{ $t('common.close') }}
          </button>
        </div>
      </div>
    </Modal>

    <!-- 技能编辑器模态框 -->
    <Modal
      :model-value="showEditor"
      :title="editorSkill ? $t('skills.editSkill') : $t('skills.createSkill')"
      size="large"
      @update:model-value="(val) => !val && handleCloseEditor()"
    >
      <SkillEditor
        :skill="editorSkill ?? undefined"
        @close="handleCloseEditor"
        @save="handleSaveSkill"
      />
    </Modal>

    <!-- 配置编辑器模态框 -->
    <Modal
      :model-value="showConfigEditor"
      :title="$t('skills.skillConfig')"
      size="large"
      @update:model-value="(val) => !val && handleCloseConfigEditor()"
    >
      <SkillConfigEditor
        v-if="selectedSkill"
        :skill-name="selectedSkill.name"
        @close="handleCloseConfigEditor"
        @saved="handleConfigSaved"
      />
    </Modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  RefreshCw as RefreshIcon,
  Loader2 as LoaderIcon,
  AlertCircle as AlertCircleIcon,
  Package as PackageIcon,
  Search as SearchIcon,
  BookOpen as BookOpenIcon,
  Zap as ZapIcon,
  Eye as EyeIcon,
  Plus as PlusIcon,
  Trash as TrashIcon,
  Edit as EditIcon,
  Settings as SettingsIcon,
  Share2 as ShareIcon,
  Globe as GlobeIcon,
  LayoutGrid as LayoutGridIcon,
  List as ListIcon,
  X as XIcon,
} from 'lucide-vue-next'
import { useSkillsStore, type Skill, type SkillDetail } from '@/store/skills'
import { useUserStore } from '@/store/user'
import { sharedSkillsAPI } from '@/api'
import { useToast } from '@/composables/useToast'
import { useConfirm } from '@/composables/useConfirm'
import Modal from '@/components/ui/Modal.vue'
import SkillEditor from './SkillEditor.vue'
import SkillConfigEditor from './SkillConfigEditor.vue'
import { filterSkills, type SkillFilterStatus } from './skillFilters'
import type { CreateSkillRequest, UpdateSkillRequest } from '@/api'

const { t } = useI18n()
const skillsStore = useSkillsStore()
const userStore = useUserStore()
const toast = useToast()
const { confirm } = useConfirm()

// State
const sharing = ref(false)
/** 共享技能的启停走登记接口，不能用只接受 workspace 来源的技能开关。 */
const sharedSkillIds = ref<Record<string, string>>({})
/** 管理员视角：技能名 -> 当前共享登记（approved 表示已全局共享） */
const sharedRegistry = ref<Record<string, { id: string; status: string }>>({})
const selectedSkill = ref<SkillDetail | null>(null)
const showEditor = ref(false)
const showDetailModal = ref(false)
const showConfigEditor = ref(false)
const editorSkill = ref<SkillDetail | null>(null)
const filterStatus = ref<SkillFilterStatus>('all')
const searchQuery = ref('')

/** 视图偏好：卡片 / 列表，按浏览器记忆 */
const VIEW_KEY = 'skillsViewMode'
const viewMode = ref<'card' | 'list'>(
  typeof localStorage !== 'undefined' && localStorage.getItem(VIEW_KEY) === 'card' ? 'card' : 'list',
)

const setViewMode = (mode: 'card' | 'list') => {
  viewMode.value = mode
  localStorage.setItem(VIEW_KEY, mode)
}

/** 序号统一两位，列表看起来更整齐 */
const padIndex = (index: number) => String(index + 1).padStart(2, '0')

// Computed
const skills = computed(() => skillsStore.skills)
const loading = computed(() => skillsStore.loading)
const error = computed(() => skillsStore.error)
const hasConfig = computed(() => Boolean(selectedSkill.value?.hasConfig))

/** 共享只能由管理员发起；工作区与内置技能都可发布为全局共享。 */
const canShareSelected = computed(
  () =>
    userStore.isAdmin &&
    (selectedSkill.value?.source === 'workspace' ||
      selectedSkill.value?.source === 'builtin'),
)

function isShareable(skill: Pick<Skill, 'source'>): boolean {
  return skill.source === 'workspace' || skill.source === 'builtin'
}

function isSkillShared(name: string): boolean {
  return sharedRegistry.value[name]?.status === 'approved'
}

async function handleShareSkill(skill: Pick<Skill, 'name'> | null) {
  if (!skill) return
  sharing.value = true
  try {
    if (isSkillShared(skill.name)) {
      const row = sharedRegistry.value[skill.name]
      await sharedSkillsAPI.revoke(row.id, '')
      toast.success(`「${skill.name}」已取消共享`)
    } else {
      await sharedSkillsAPI.publish({ name: skill.name, audience: null })
      toast.success(`「${skill.name}」已全局共享`)
    }
    await loadSharedRegistry()
  } catch (err: any) {
    toast.error(err?.message || '操作失败')
  } finally {
    sharing.value = false
  }
}

const enabledCount = computed(() =>
  skills.value.filter(s => s.enabled).length
)

const disabledCount = computed(() =>
  skills.value.filter(s => !s.enabled).length
)

const autoLoadCount = computed(() =>
  skills.value.filter(s => s.autoLoad).length
)

const normalizedSearchQuery = computed(() => searchQuery.value.trim())

const filteredSkills = computed(() =>
  filterSkills(skills.value, filterStatus.value, normalizedSearchQuery.value)
)

const hasSkills = computed(() => skills.value.length > 0)

const hasActiveFilters = computed(() =>
  filterStatus.value !== 'all' || normalizedSearchQuery.value.length > 0
)

const emptyStateTitle = computed(() =>
  hasSkills.value ? t('skills.noSearchResults') : t('skills.noSkills')
)

const emptyStateDescription = computed(() => {
  if (!hasSkills.value) {
    return t('skills.noSkillsDesc')
  }

  if (normalizedSearchQuery.value.length > 0) {
    return t('skills.noSearchResultsDesc')
  }

  return t('skills.noFilterResultsDesc')
})

const renderedContent = computed(() => {
  if (!selectedSkill.value?.content) return ''
  // 移除 frontmatter
  let content = selectedSkill.value.content
  if (content.startsWith('---')) {
    const match = content.match(/^---\n.*?\n---\n/s)
    if (match) {
      content = content.substring(match[0].length)
    }
  }
  return content.trim()
})

const getSourceLabel = (source?: Skill['source']) => {
  switch (source) {
    case 'builtin':
      return t('skills.builtin')
    case 'openclaw':
      return t('skills.openclaw')
    case 'shared':
      return '共享'
    default:
      return t('skills.workspace')
  }
}

const getToggleLabel = (skill: Pick<Skill, 'source' | 'enabled'>) => {
  if (skill.source === 'openclaw' && !skill.enabled) {
    return t('skills.importAndEnable')
  }

  return skill.enabled ? t('skills.disable') : t('skills.enable')
}

const refreshSelectedSkill = async (name: string) => {
  try {
    selectedSkill.value = await skillsStore.getSkill(name)
  } catch (error) {
    handleCloseModal()
  }
}

// Methods
const resetFilters = () => {
  filterStatus.value = 'all'
  searchQuery.value = ''
}

async function loadSharedSkillIds() {
  if (userStore.isAdmin) return
  try {
    const rows = await sharedSkillsAPI.list()
    sharedSkillIds.value = Object.fromEntries(
      rows
        .filter((row) => row.status === 'approved')
        .map((row) => [row.name, row.id]),
    )
  } catch {
    sharedSkillIds.value = {}
  }
}

async function loadPublishableNames() {
  if (!userStore.isAdmin) return
  await loadSharedRegistry()
}

async function loadSharedRegistry() {
  if (!userStore.isAdmin) return
  try {
    const rows = await sharedSkillsAPI.list()
    const map: Record<string, { id: string; status: string }> = {}
    for (const row of rows) {
      // 同名多次发布只保留最新记录，已批准优先，避免撤回后仍显示为共享
      const existing = map[row.name]
      if (!existing || row.status === 'approved') {
        map[row.name] = { id: row.id, status: row.status }
      }
    }
    sharedRegistry.value = map
  } catch {
    sharedRegistry.value = {}
  }
}

const handleRefresh = async () => {
  try {
    // 先执行热重载，然后刷新列表
    await skillsStore.reloadSkills()
    await Promise.all([loadSharedSkillIds(), loadPublishableNames()])
    toast.success(t('skills.reloadSuccess'))
  } catch (err: any) {
    toast.error(t('skills.loadError'))
  }
}

const handleViewSkill = async (name: string) => {
  try {
    selectedSkill.value = await skillsStore.getSkill(name)
    showDetailModal.value = true
  } catch (err: any) {
    toast.error(t('skills.loadDetailError'))
  }
}

const handleCreateSkill = () => {
  editorSkill.value = null
  showEditor.value = true
}

const handleEditSkill = () => {
  if (!selectedSkill.value) return
  editorSkill.value = selectedSkill.value
  showEditor.value = true
}

const handleSaveSkill = async (data: CreateSkillRequest | UpdateSkillRequest) => {
  try {
    if (editorSkill.value) {
      // 更新现有技能
      const updateData = data as UpdateSkillRequest
      await skillsStore.updateSkill(editorSkill.value.name, updateData)
      toast.success(t('skills.updateSuccess', { name: editorSkill.value.name }))

      // 如果当前正在查看这个技能，更新详情
      if (selectedSkill.value && selectedSkill.value.name === editorSkill.value.name) {
        selectedSkill.value = await skillsStore.getSkill(editorSkill.value.name)
      }
    } else {
      // 创建新技能
      const createData = data as CreateSkillRequest
      await skillsStore.createSkill(createData)
      toast.success(t('skills.createSuccess', { name: createData.name }))
    }

    showEditor.value = false
    await handleRefresh()
  } catch (err: any) {
    toast.error(t('skills.saveError'))
  }
}

const handleDeleteSkill = async () => {
  if (!selectedSkill.value) return

  const name = selectedSkill.value.name

  // 只允许删除工作空间技能
  if (selectedSkill.value.source === 'builtin') {
    toast.warning(t('skills.cannotDeleteBuiltin'))
    return
  }

  if (selectedSkill.value.source === 'openclaw') {
    toast.warning(t('skills.cannotDeleteOpenclaw'))
    return
  }

  await confirm({
    title: t('common.confirmDelete'),
    message: t('skills.deleteConfirm', { name }),
    type: 'danger',
    confirmText: t('common.delete'),
    confirmVariant: 'danger',
    onConfirm: async () => {
      try {
        await skillsStore.deleteSkill(name)
        toast.success(t('skills.deleteSuccess', { name }))
        selectedSkill.value = null
        await handleRefresh()
      } catch (err: any) {
        toast.error(t('skills.deleteError'))
      }
    }
  })
}

const handleCloseEditor = () => {
  showEditor.value = false
  editorSkill.value = null
}

const handleToggleSkill = async (name: string, enabled: boolean) => {
  const isShared = skills.value.find((skill) => skill.name === name)?.source === 'shared'
  const sharedId = sharedSkillIds.value[name]
  if (isShared && !sharedId) {
    toast.error(t('skills.toggleError'))
    return
  }
  try {
    if (isShared) {
      await sharedSkillsAPI.setState(sharedId, enabled)
      await skillsStore.reloadSkills()
    } else {
      await skillsStore.toggleSkill(name, enabled)
    }
    if (selectedSkill.value?.name === name) {
      await refreshSelectedSkill(name)
    }
    toast.success(
      enabled
        ? t('skills.enableSuccess', { name })
        : t('skills.disableSuccess', { name })
    )
  } catch (err: any) {
    toast.error(t('skills.toggleError'))
  }
}

const handleToggleSkillFromModal = async (enabled: boolean) => {
  if (!selectedSkill.value) return

  const name = selectedSkill.value.name
  await handleToggleSkill(name, enabled)
}

const handleCloseModal = () => {
  showDetailModal.value = false
  selectedSkill.value = null
}

// 快速编辑配置（从卡片直接打开）
const handleQuickEditConfig = async (skillName: string) => {
  try {
    // 加载技能详情
    selectedSkill.value = await skillsStore.getSkill(skillName)

    // 只打开配置编辑器，不打开详情模态框
    showDetailModal.value = false
    showConfigEditor.value = true
  } catch (err: any) {
    toast.error(t('skills.loadConfigError'))
  }
}

// Open config editor
const handleEditConfig = () => {
  showConfigEditor.value = true
}

// Close config editor
const handleCloseConfigEditor = () => {
  showConfigEditor.value = false
}

// Handle config saved
const handleConfigSaved = () => {
  toast.success(t('skills.configSaved'))
  showConfigEditor.value = false
}

// Lifecycle
onMounted(() => {
  handleRefresh()
})
</script>

<style scoped>
@import './styles/SkillsLibrary.css';
</style>
