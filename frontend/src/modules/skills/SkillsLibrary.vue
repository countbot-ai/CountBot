<template>
  <div class="skills-library">
    <!-- Header -->
    <div class="skills-header">
      <div class="header-content">
        <h2 class="title">
          {{ $t('skills.title') }}
        </h2>
        <p class="description">
          {{ $t('skills.description') }}
        </p>
      </div>
      <div class="header-actions">
        <button
          class="create-btn"
          @click="handleCreateSkill"
        >
          <component
            :is="PlusIcon"
            :size="16"
          />
          {{ $t('skills.createSkill') }}
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

    <!-- Filter Bar -->
    <div
      v-if="!loading && skills.length > 0"
      class="filter-bar"
    >
      <div class="filter-tabs">
        <button
          class="filter-tab"
          :class="{ active: filterStatus === 'all' }"
          @click="filterStatus = 'all'"
        >
          <component
            :is="PackageIcon"
            :size="16"
          />
          {{ $t('skills.all') }} ({{ skills.length }})
        </button>
        <button
          class="filter-tab"
          :class="{ active: filterStatus === 'enabled' }"
          @click="filterStatus = 'enabled'"
        >
          <component
            :is="CheckCircleIcon"
            :size="16"
          />
          {{ $t('skills.enabled') }} ({{ enabledCount }})
        </button>
        <button
          class="filter-tab"
          :class="{ active: filterStatus === 'disabled' }"
          @click="filterStatus = 'disabled'"
        >
          <component
            :is="XCircleIcon"
            :size="16"
          />
          {{ $t('skills.disabled') }} ({{ disabledCount }})
        </button>
        <button
          class="filter-tab"
          :class="{ active: filterStatus === 'autoLoad' }"
          @click="filterStatus = 'autoLoad'"
        >
          <component
            :is="ZapIcon"
            :size="16"
          />
          {{ $t('skills.autoLoad') }} ({{ autoLoadCount }})
        </button>
      </div>
    </div>

    <!-- Loading State -->
    <div
      v-if="loading"
      class="loading-state"
    >
      <component
        :is="LoaderIcon"
        :size="32"
        class="spin"
      />
      <p>{{ $t('common.loading') }}</p>
    </div>

    <!-- Error State -->
    <div
      v-else-if="error"
      class="error-state"
    >
      <component
        :is="AlertCircleIcon"
        :size="32"
      />
      <p>{{ error }}</p>
      <button
        class="retry-btn"
        @click="handleRefresh"
      >
        {{ $t('common.retry') }}
      </button>
    </div>

    <!-- Skills Grid -->
    <div
      v-else-if="filteredSkills.length > 0"
      class="skills-grid"
    >
      <div
        v-for="skill in filteredSkills"
        :key="skill.name"
        class="skill-card"
        :class="{ 'disabled': !skill.enabled }"
      >
        <!-- Card Header -->
        <div class="card-header">
          <div class="skill-info">
            <component
              :is="BookOpenIcon"
              :size="20"
              class="skill-icon"
            />
            <h3 class="skill-name">
              {{ skill.name }}
            </h3>
          </div>
          <div class="skill-badges">
            <span
              v-if="skill.autoLoad"
              class="badge auto-load"
              :title="$t('skills.autoLoadTooltip')"
            >
              <component
                :is="ZapIcon"
                :size="12"
              />
              {{ $t('skills.autoLoad') }}
            </span>
          </div>
        </div>

        <!-- Card Body -->
        <div class="card-body">
          <p class="skill-description">
            {{ skill.description || $t('skills.noDescription') }}
          </p>

          <!-- Requirements -->
          <div
            v-if="skill.requirements && skill.requirements.length > 0"
            class="requirements"
          >
            <component
              :is="AlertCircleIcon"
              :size="14"
            />
            <span class="requirements-label">{{ $t('skills.requirements') }}:</span>
            <div class="requirements-list">
              <span
                v-for="req in skill.requirements"
                :key="req"
                class="requirement-tag"
              >
                {{ req }}
              </span>
            </div>
          </div>
        </div>

        <!-- Card Footer -->
        <div class="card-footer">
          <button
            class="view-btn"
            @click="handleViewSkill(skill.name)"
          >
            <component
              :is="EyeIcon"
              :size="16"
            />
            {{ $t('skills.viewDetails') }}
          </button>
          <button
            class="toggle-btn"
            :class="{ 'enabled': skill.enabled }"
            @click="handleToggleSkill(skill.name, !skill.enabled)"
          >
            <component
              :is="skill.enabled ? ToggleRightIcon : ToggleLeftIcon"
              :size="16"
            />
            {{ skill.enabled ? $t('skills.disable') : $t('skills.enable') }}
          </button>
        </div>
      </div>
    </div>

    <!-- Empty State -->
    <div
      v-else
      class="empty-state"
    >
      <component
        :is="PackageIcon"
        :size="48"
      />
      <h3>{{ $t('skills.noSkills') }}</h3>
      <p>{{ $t('skills.noSkillsDesc') }}</p>
    </div>

    <!-- Skill Detail Modal -->
    <Modal
      :model-value="!!selectedSkill"
      :title="selectedSkill?.name"
      @update:model-value="(val) => !val && handleCloseModal()"
    >
      <div v-if="selectedSkill" class="skill-detail">
        <!-- Skill Info -->
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
                <span
                  class="source-badge"
                  :class="selectedSkill.source"
                >
                  {{ selectedSkill.source === 'builtin' ? $t('skills.builtin') : $t('skills.workspace') }}
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
              <span
                class="info-value"
                :class="{ 'highlight': selectedSkill.autoLoad }"
              >
                {{ selectedSkill.autoLoad ? $t('common.yes') : $t('common.no') }}
              </span>
            </div>
          </div>
          <div
            v-if="selectedSkill.description"
            class="info-item full-width"
          >
            <span class="info-label">{{ $t('skills.description') }}</span>
            <p class="info-value description-text">
              {{ selectedSkill.description }}
            </p>
          </div>
          <div
            v-if="selectedSkill.requirements && selectedSkill.requirements.length > 0"
            class="info-item full-width"
          >
            <span class="info-label">{{ $t('skills.requirements') }}</span>
            <div class="requirements-list">
              <span
                v-for="req in selectedSkill.requirements"
                :key="req"
                class="requirement-tag"
              >
                <component
                  :is="PackageIcon"
                  :size="12"
                />
                {{ req }}
              </span>
            </div>
          </div>
        </div>

        <!-- Skill Content -->
        <div class="detail-section">
          <h4 class="section-title">
            {{ $t('skills.content') }}
          </h4>
          <div class="skill-content">
            <pre class="skill-markdown">{{ renderedContent }}</pre>
          </div>
        </div>

        <!-- Actions -->
        <div class="detail-actions">
          <button
            v-if="selectedSkill.source === 'workspace'"
            class="action-btn"
            @click="handleEditSkill"
          >
            <component
              :is="EditIcon"
              :size="16"
            />
            {{ $t('common.edit') }}
          </button>
          <button
            v-if="selectedSkill.source === 'workspace'"
            class="action-btn danger"
            @click="handleDeleteSkill"
          >
            <component
              :is="TrashIcon"
              :size="16"
            />
            {{ $t('common.delete') }}
          </button>
          <button
            class="action-btn primary"
            @click="handleToggleSkillFromModal(!selectedSkill.enabled)"
          >
            {{ selectedSkill.enabled ? $t('skills.disable') : $t('skills.enable') }}
          </button>
          <button
            class="action-btn"
            @click="handleCloseModal"
          >
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
        :skill="editorSkill"
        @close="handleCloseEditor"
        @save="handleSaveSkill"
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
  BookOpen as BookOpenIcon,
  CheckCircle as CheckCircleIcon,
  XCircle as XCircleIcon,
  Zap as ZapIcon,
  Eye as EyeIcon,
  ToggleLeft as ToggleLeftIcon,
  ToggleRight as ToggleRightIcon,
  Plus as PlusIcon,
  Trash as TrashIcon,
  Edit as EditIcon
} from 'lucide-vue-next'
import { useSkillsStore, type SkillDetail } from '@/store/skills'
import { useToast } from '@/composables/useToast'
import { useMarkdown } from '@/composables/useMarkdown'
import Modal from '@/components/ui/Modal.vue'
import SkillEditor from './SkillEditor.vue'
import type { CreateSkillRequest, UpdateSkillRequest } from '@/api'

const { t } = useI18n()
const skillsStore = useSkillsStore()
const toast = useToast()
const { renderMarkdown } = useMarkdown()

// State
const selectedSkill = ref<SkillDetail | null>(null)
const loadingSkillDetail = ref(false)
const showEditor = ref(false)
const editorSkill = ref<SkillDetail | null>(null)
const filterStatus = ref<'all' | 'enabled' | 'disabled' | 'autoLoad'>('all')

// Computed
const skills = computed(() => skillsStore.skills)
const loading = computed(() => skillsStore.loading)
const error = computed(() => skillsStore.error)

const enabledCount = computed(() => 
  skills.value.filter(s => s.enabled).length
)

const disabledCount = computed(() => 
  skills.value.filter(s => !s.enabled).length
)

const autoLoadCount = computed(() => 
  skills.value.filter(s => s.autoLoad).length
)

const filteredSkills = computed(() => {
  switch (filterStatus.value) {
    case 'enabled':
      return skills.value.filter(s => s.enabled)
    case 'disabled':
      return skills.value.filter(s => !s.enabled)
    case 'autoLoad':
      return skills.value.filter(s => s.autoLoad)
    default:
      return skills.value
  }
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

// Methods
const handleRefresh = async () => {
  try {
    await skillsStore.loadSkills()
  } catch (err: any) {
    toast.error(t('skills.loadError'))
  }
}

const handleViewSkill = async (name: string) => {
  loadingSkillDetail.value = true
  try {
    selectedSkill.value = await skillsStore.getSkill(name)
  } catch (err: any) {
    toast.error(t('skills.loadDetailError'))
  } finally {
    loadingSkillDetail.value = false
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
  
  // 不允许删除内置技能
  if (selectedSkill.value.source === 'builtin') {
    toast.warning(t('skills.cannotDeleteBuiltin'))
    return
  }
  
  if (!confirm(t('skills.deleteConfirm', { name }))) {
    return
  }
  
  try {
    await skillsStore.deleteSkill(name)
    toast.success(t('skills.deleteSuccess', { name }))
    selectedSkill.value = null
    await handleRefresh()
  } catch (err: any) {
    toast.error(t('skills.deleteError'))
  }
}

const handleCloseEditor = () => {
  showEditor.value = false
  editorSkill.value = null
}

const handleToggleSkill = async (name: string, enabled: boolean) => {
  try {
    await skillsStore.toggleSkill(name, enabled)
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
  
  // Update modal state
  selectedSkill.value.enabled = enabled
}

const handleCloseModal = () => {
  selectedSkill.value = null
}

// Lifecycle
onMounted(() => {
  handleRefresh()
})
</script>

<style scoped>
.skills-library {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-secondary, #f9fafb);
}

/* Header */
.skills-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: var(--spacing-xl);
  border-bottom: 1px solid var(--border-color, #e5e7eb);
  background: var(--bg-primary, #ffffff);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}

.header-content {
  flex: 1;
}

.title {
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary, #1f2937);
  margin: 0 0 var(--spacing-xs) 0;
}

.description {
  font-size: var(--font-size-sm);
  color: var(--text-secondary, #6b7280);
  margin: 0;
}

.header-actions {
  display: flex;
  gap: var(--spacing-sm);
}

.refresh-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: var(--radius-md);
  background: var(--bg-primary, #ffffff);
  color: var(--text-secondary, #6b7280);
  cursor: pointer;
  transition: all var(--transition-base);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

.refresh-btn:hover:not(:disabled) {
  background: var(--hover-bg, #f3f4f6);
  color: var(--text-primary, #1f2937);
  border-color: var(--color-primary, #3b82f6);
}

.refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.create-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--color-primary, #3b82f6);
  border-radius: var(--radius-md);
  background: var(--color-primary, #3b82f6);
  color: white;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: all var(--transition-base);
  box-shadow: 0 2px 4px rgba(59, 130, 246, 0.3);
}

.create-btn:hover {
  background: var(--color-primary-hover, #2563eb);
  box-shadow: 0 4px 6px rgba(59, 130, 246, 0.4);
  transform: translateY(-1px);
}

/* Stats Bar */
.stats-bar {
  display: flex;
  gap: var(--spacing-xl);
  padding: var(--spacing-md) var(--spacing-xl);
  border-bottom: 1px solid var(--border-color, #e5e7eb);
  background: var(--bg-primary, #ffffff);
}

.stat {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--font-size-sm);
  color: var(--text-secondary, #6b7280);
}

.stat svg {
  color: var(--color-primary, #3b82f6);
}

/* Filter Bar */
.filter-bar {
  padding: var(--spacing-md) var(--spacing-xl);
  border-bottom: 1px solid var(--border-color, #e5e7eb);
  background: var(--bg-primary, #ffffff);
}

.filter-tabs {
  display: flex;
  gap: var(--spacing-sm);
}

.filter-tab {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: var(--radius-md);
  background: var(--bg-primary, #ffffff);
  color: var(--text-secondary, #6b7280);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: all 0.15s ease;
}

.filter-tab:hover {
  background: var(--bg-tertiary, #f3f4f6);
  border-color: var(--text-tertiary, #9ca3af);
  color: var(--text-primary, #1f2937);
}

.filter-tab.active {
  background: var(--color-primary-light, #eff6ff);
  border-color: var(--color-primary, #3b82f6);
  color: var(--color-primary, #3b82f6);
  font-weight: var(--font-weight-semibold);
}

.filter-tab svg {
  flex-shrink: 0;
}

/* States */
.loading-state,
.error-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-md);
  flex: 1;
  padding: var(--spacing-3xl);
  color: var(--text-secondary);
  text-align: center;
}

.error-state {
  color: var(--color-error);
}

.empty-state h3 {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  margin: 0;
}

.empty-state p {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  margin: 0;
}

.retry-btn {
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-size: var(--font-size-sm);
  cursor: pointer;
  transition: all var(--transition-base);
}

.retry-btn:hover {
  background: var(--hover-bg);
}

/* Skills Grid */
.skills-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: var(--spacing-lg);
  padding: var(--spacing-xl);
  overflow-y: auto;
}

.skill-card {
  display: flex;
  flex-direction: column;
  padding: var(--spacing-lg);
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: var(--radius-lg);
  background: var(--bg-primary, #ffffff);
  transition: all var(--transition-base);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}

.skill-card:hover {
  border-color: var(--color-primary, #3b82f6);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  transform: translateY(-2px);
}

.skill-card.disabled {
  opacity: 0.6;
  background: var(--bg-tertiary, #f3f4f6);
}

.card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: var(--spacing-md);
  padding-bottom: var(--spacing-sm);
  border-bottom: 1px solid var(--border-color, #e5e7eb);
}

.skill-info {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  flex: 1;
}

.skill-icon {
  color: var(--color-primary, #3b82f6);
  flex-shrink: 0;
}

.skill-name {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary, #1f2937);
  margin: 0;
  word-break: break-word;
}

.skill-badges {
  display: flex;
  gap: var(--spacing-xs);
}

.badge {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
}

.badge.auto-load {
  background: var(--color-warning-light, #fef3c7);
  color: var(--color-warning, #f59e0b);
  border: 1px solid var(--color-warning, #f59e0b);
}

.card-body {
  flex: 1;
  margin-bottom: var(--spacing-md);
}

.skill-description {
  font-size: var(--font-size-sm);
  color: var(--text-secondary, #6b7280);
  margin: 0 0 var(--spacing-md) 0;
  line-height: 1.6;
}

.requirements {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--radius-md);
  background: var(--bg-secondary, #f9fafb);
  border: 1px solid var(--border-color, #e5e7eb);
  font-size: var(--font-size-xs);
  color: var(--text-tertiary, #9ca3af);
}

.requirements svg {
  flex-shrink: 0;
  margin-top: 2px;
}

.requirements-label {
  font-weight: var(--font-weight-medium);
  flex-shrink: 0;
}

.requirements-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.requirement-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  background: var(--bg-primary);
  color: var(--text-secondary);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  border: 1px solid var(--border-color);
}

.card-footer {
  display: flex;
  gap: var(--spacing-sm);
  padding-top: var(--spacing-md);
  border-top: 1px solid var(--border-color, #e5e7eb);
}

.view-btn,
.toggle-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: var(--radius-md);
  background: var(--bg-primary, #ffffff);
  color: var(--text-primary, #1f2937);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: all var(--transition-base);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

.view-btn {
  flex: 1;
}

.view-btn:hover {
  background: var(--bg-secondary, #f9fafb);
  border-color: var(--color-primary, #3b82f6);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.toggle-btn:hover {
  background: var(--bg-secondary, #f9fafb);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.toggle-btn.enabled {
  background: var(--color-success-light, #d1fae5);
  border-color: var(--color-success, #10b981);
  color: var(--color-success, #10b981);
}

/* Skill Detail Modal */
.skill-detail {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xl);
}

.detail-section {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.section-title {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  margin: 0;
  padding-bottom: var(--spacing-sm);
  border-bottom: 1px solid var(--border-color);
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--spacing-md);
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.info-item.full-width {
  grid-column: 1 / -1;
}

.info-label {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--text-secondary);
  margin-bottom: 4px;
}

.info-value {
  font-size: var(--font-size-sm);
  color: var(--text-primary);
  line-height: 1.5;
}

.skill-name-value {
  font-weight: var(--font-weight-semibold);
  color: var(--color-primary);
  font-size: var(--font-size-base);
}

.description-text {
  margin: 0;
  padding: var(--spacing-sm);
  background: var(--bg-tertiary);
  border-radius: var(--radius-sm);
  border-left: 3px solid var(--color-primary);
}

.status-badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 12px;
  border-radius: var(--radius-full);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
}

.status-badge.enabled {
  background: var(--color-success-light, #d1fae5);
  color: var(--color-success, #10b981);
  border: 1px solid var(--color-success, #10b981);
}

.status-badge.disabled {
  background: var(--bg-tertiary);
  color: var(--text-tertiary);
  border: 1px solid var(--border-color);
}

.source-badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 12px;
  border-radius: var(--radius-full);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
}

.source-badge.workspace {
  background: var(--color-primary-light, #dbeafe);
  color: var(--color-primary, #3b82f6);
  border: 1px solid var(--color-primary, #3b82f6);
}

.source-badge.builtin {
  background: var(--color-warning-light, #fef3c7);
  color: var(--color-warning, #f59e0b);
  border: 1px solid var(--color-warning, #f59e0b);
}

.info-value.highlight {
  color: var(--color-success);
  font-weight: var(--font-weight-semibold);
}

.info-value.enabled {
  color: var(--color-success);
  font-weight: var(--font-weight-medium);
}

.skill-content {
  padding: var(--spacing-md);
  border-radius: var(--radius-md);
  background: var(--bg-tertiary);
  font-size: var(--font-size-sm);
  line-height: 1.6;
  max-height: 500px;
  overflow-y: auto;
  border: 1px solid var(--border-color);
}

.skill-markdown {
  margin: 0;
  padding: 0;
  font-family: 'JetBrains Mono', 'Consolas', monospace;
  font-size: var(--font-size-sm);
  line-height: 1.6;
  color: var(--text-primary);
  white-space: pre-wrap;
  word-wrap: break-word;
}

.detail-actions {
  display: flex;
  gap: var(--spacing-sm);
  justify-content: flex-end;
  padding-top: var(--spacing-md);
  border-top: 1px solid var(--border-color);
}

.action-btn {
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: all var(--transition-base);
}

.action-btn:hover {
  background: var(--hover-bg);
}

.action-btn.primary {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: white;
}

.action-btn.primary:hover {
  background: var(--color-primary-dark);
}

.action-btn.danger {
  background: var(--color-error);
  border-color: var(--color-error);
  color: white;
}

.action-btn.danger:hover {
  background: var(--color-error-dark);
}

/* Animations */
.spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

/* 深色模式 */
:root[data-theme="dark"] .skills-library {
  background: var(--bg-secondary, #0e1422);
}

:root[data-theme="dark"] .skills-header {
  background: var(--bg-primary, #0a0e1a);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.4);
}

:root[data-theme="dark"] .filter-bar {
  background: var(--bg-primary, #0a0e1a);
  border-color: #152035;
}

:root[data-theme="dark"] .filter-tab {
  background: var(--bg-tertiary, #131b2c);
  border-color: #1e2d45;
  color: var(--text-secondary, #7a9ab0);
}

:root[data-theme="dark"] .filter-tab:hover {
  background: #152035;
  border-color: rgba(0, 240, 255, 0.25);
  color: #d0e8f0;
}

:root[data-theme="dark"] .filter-tab.active {
  background: rgba(0, 240, 255, 0.08);
  border-color: rgba(0, 240, 255, 0.4);
  color: #00f0ff;
}

:root[data-theme="dark"] .stats-bar {
  background: var(--bg-primary, #0a0e1a);
}

:root[data-theme="dark"] .skill-card {
  background: var(--bg-primary, #0e1422);
  border-color: #152035;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.3);
}

:root[data-theme="dark"] .skill-card:hover {
  border-color: rgba(0, 240, 255, 0.2);
  box-shadow: 0 0 10px rgba(0, 240, 255, 0.05), 0 2px 8px rgba(0, 0, 0, 0.4);
}

:root[data-theme="dark"] .skill-card.disabled {
  background: #0a0e1a;
  opacity: 0.5;
}

:root[data-theme="dark"] .card-header {
  border-color: #152035;
}

:root[data-theme="dark"] .card-footer {
  border-color: #152035;
}

:root[data-theme="dark"] .view-btn,
:root[data-theme="dark"] .toggle-btn {
  background: #131b2c;
  border-color: #1e2d45;
  color: #7a9ab0;
}

:root[data-theme="dark"] .view-btn:hover {
  background: #152035;
  border-color: rgba(0, 240, 255, 0.3);
  color: #00f0ff;
}

:root[data-theme="dark"] .toggle-btn:hover {
  background: #152035;
  border-color: rgba(0, 240, 255, 0.3);
  color: #00f0ff;
}

:root[data-theme="dark"] .toggle-btn.enabled {
  background: rgba(0, 255, 136, 0.08);
  border-color: rgba(0, 255, 136, 0.3);
  color: #00ff88;
}

:root[data-theme="dark"] .badge.auto-load {
  background: rgba(255, 149, 0, 0.1);
  border-color: rgba(255, 149, 0, 0.3);
  color: #ff9500;
}

:root[data-theme="dark"] .requirements {
  background: #0a0e1a;
  border-color: #152035;
}

:root[data-theme="dark"] .requirement-tag {
  background: #131b2c;
  border-color: #1e2d45;
  color: #7a9ab0;
}

:root[data-theme="dark"] .create-btn {
  background: #131b2c;
  border-color: #00f0ff;
  color: #00f0ff;
  box-shadow: 0 0 8px rgba(0, 240, 255, 0.12);
}

:root[data-theme="dark"] .create-btn:hover {
  background: #152035;
  border-color: #33f5ff;
  color: #33f5ff;
  box-shadow: 0 0 14px rgba(0, 240, 255, 0.2);
}

:root[data-theme="dark"] .refresh-btn {
  background: #0e1422;
  border-color: #1e2d45;
  color: #7a9ab0;
}

:root[data-theme="dark"] .refresh-btn:hover:not(:disabled) {
  background: #131b2c;
  border-color: rgba(0, 240, 255, 0.3);
  color: #00f0ff;
}
</style>
