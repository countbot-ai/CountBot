<template>
  <div class="multiagent-config">
    <!-- 团队列表视图：详情改为抽屉，保留列表上下文与滚动位置 -->
    <div class="teams-list-view">
      <div class="team-toolbar">
        <div class="team-stats">
          <span class="team-stat">
            <b>{{ activeTeamCount }}</b>
            {{ $t('settings.multiagent.activeCount') }}
          </span>
          <span class="team-stat-sep" aria-hidden="true" />
          <span class="team-stat">
            {{ $t('settings.multiagent.totalCount') }}
            <b>{{ teams.length }}</b>
          </span>
        </div>
        <div class="team-actions">
          <button class="co-btn co-btn--secondary" @click="triggerImport">
            <component :is="UploadIcon" :size="14" />
            导入
          </button>
          <button class="co-btn co-btn--secondary" :disabled="!teams.length" @click="exportTeams">
            <component :is="DownloadIcon" :size="14" />
            导出
          </button>
          <button class="co-btn co-btn--secondary" @click="showTemplateDialog = true">
            <component :is="LayoutTemplateIcon" :size="14" />
            {{ $t('settings.multiagent.fromTemplate') }}
          </button>
          <button class="co-btn co-btn--primary" @click="showCreateDialog = true">
            <component :is="PlusIcon" :size="14" />
            {{ $t('settings.multiagent.newTeam') }}
          </button>
          <input
            ref="importInput"
            type="file"
            accept="application/json,.json"
            class="import-file-input"
            @change="handleImportChange"
          >
        </div>
      </div>

      <div v-if="teams.length > 0" class="team-filters">
        <div class="team-search">
          <component :is="SearchIcon" :size="14" class="team-search-icon" />
          <input
            v-model="searchQuery"
            class="team-search-input"
            type="text"
            :placeholder="$t('settings.multiagent.searchPlaceholder')"
          >
          <button v-if="searchQuery" class="team-search-clear" @click="searchQuery = ''">
            <component :is="XIcon" :size="13" />
          </button>
        </div>
        <select v-model="filterMode" class="co-select team-filter">
          <option value="">{{ $t('settings.multiagent.allModes') }}</option>
          <option value="pipeline">流水线</option>
          <option value="graph">依赖图</option>
          <option value="council">多视角</option>
        </select>
        <select v-model="filterStatus" class="co-select team-filter">
          <option value="">{{ $t('settings.multiagent.allStatus') }}</option>
          <option value="active">已激活</option>
          <option value="inactive">未激活</option>
        </select>
      </div>

      <div v-if="loading" class="team-state">
        <LoadingState />
      </div>

      <div v-else-if="error" class="team-state">
        <p class="team-state-desc">{{ error }}</p>
        <button class="co-btn co-btn--secondary" @click="loadTeams">{{ $t('common.retry') }}</button>
      </div>

      <!-- 默认页：没有任何团队时给出「模板 / 手动」两条起手路径 -->
      <div v-else-if="teams.length === 0" class="team-empty">
        <div class="team-empty-icon">
          <component :is="UsersIcon" :size="22" />
        </div>
        <h3 class="team-empty-title">{{ $t('settings.multiagent.empty') }}</h3>
        <p class="team-empty-desc">{{ $t('settings.multiagent.emptyDesc') }}</p>
        <div class="team-empty-actions">
          <button class="co-btn co-btn--secondary" @click="showTemplateDialog = true">
            <component :is="LayoutTemplateIcon" :size="14" />
            {{ $t('settings.multiagent.fromTemplate') }}
          </button>
          <button class="co-btn co-btn--primary" @click="showCreateDialog = true">
            {{ $t('settings.multiagent.newTeam') }}
          </button>
        </div>
      </div>

      <!-- 列表：一行一个团队，只保留扫读需要的信息，成员明细进详情看 -->
      <div v-else-if="filteredTeams.length > 0" class="team-list">
        <div
          v-for="(team, index) in filteredTeams"
          :key="team.id"
          class="team-row"
          :class="{ 'is-inactive': !team.is_active }"
          @click="viewTeamDetail(team)"
        >
          <span class="team-index">{{ String(index + 1).padStart(2, '0') }}</span>

          <div class="team-name-line">
            <span class="team-name">{{ team.name }}</span>
            <span class="team-badge">{{ modeLabelMap[team.mode] }}</span>
            <span v-if="team.mode === 'council'" class="team-badge">
              {{ team.cross_review ? '交叉模式' : '独立模式' }}
            </span>
            <span v-if="!team.is_active" class="team-badge team-badge--muted">未启用</span>
          </div>

          <span class="team-member-count">
            <component :is="UsersIcon" :size="12" />
            {{ team.agents.length }} {{ $t('settings.multiagent.agentUnit') }}
          </span>

          <div class="team-row-actions">
            <button class="icon-btn" :title="$t('settings.multiagent.copyPayload')" @click.stop="copyPayload(team)">
              <component :is="CopyIcon" :size="15" />
            </button>
            <button class="icon-btn icon-btn--danger" :title="$t('common.delete')" @click.stop="confirmDelete(team)">
              <component :is="TrashIcon" :size="15" />
            </button>
          </div>

          <component :is="ChevronRightIcon" :size="15" class="team-chevron" />
        </div>
      </div>

      <div v-else class="team-state">
        <component :is="SearchIcon" :size="22" class="team-state-icon" />
        <p class="team-state-title">{{ $t('settings.multiagent.noResults') }}</p>
        <p class="team-state-desc">{{ $t('settings.multiagent.noResultsDesc') }}</p>
        <button class="co-btn co-btn--secondary" @click="clearFilters">
          {{ $t('settings.multiagent.clearFilters') }}
        </button>
      </div>

      <!-- 模板选择对话框 -->
      <Modal :model-value="showTemplateDialog" @close="showTemplateDialog = false" size="large">
        <div class="dialog-content">
          <h3>从模板创建团队</h3>
          <p class="template-hint">选择一个预定义模板快速创建团队，您可以在创建后修改配置</p>

          <!-- 分类过滤 -->
          <div class="template-categories">
            <button
              v-for="category in templateCategories"
              :key="category"
              class="category-btn"
              :class="{ active: selectedCategory === category }"
              @click="selectedCategory = category"
            >
              {{ category }}
            </button>
          </div>

          <!-- 模板列表 -->
          <div class="templates-grid">
            <div
              v-for="template in filteredTemplates"
              :key="template.id"
              class="template-card"
              @click="selectTemplate(template)"
            >
              <div class="template-header">
                <h4>{{ template.name }}</h4>
                <span class="template-badge">{{ modeLabelMap[template.mode] }}</span>
              </div>
              <p class="template-description">{{ template.description }}</p>
              <div class="template-footer">
                <span class="template-agents">
                  <component :is="UsersIcon" :size="14" />
                  {{ template.agents.length }} 个成员
                </span>
                <span class="template-category">{{ template.category }}</span>
              </div>
            </div>
          </div>
        </div>
      </Modal>

      <!-- 创建团队对话框 -->
      <Modal
        :model-value="showCreateDialog"
        :title="$t('settings.multiagent.form.createTitle')"
        size="medium"
        @close="closeDialog"
      >
        <div class="agent-form">
          <div class="af-field">
            <label class="af-label" for="team-form-name">
              {{ $t('settings.multiagent.form.name') }}
              <span class="af-required">*</span>
            </label>
            <input
              id="team-form-name"
              v-model="formData.name"
              type="text"
              class="co-input"
              :placeholder="$t('settings.multiagent.form.namePlaceholder')"
            />
          </div>

          <div class="af-field">
            <label class="af-label" for="team-form-desc">
              {{ $t('settings.multiagent.form.description') }}
            </label>
            <textarea
              id="team-form-desc"
              v-model="formData.description"
              class="co-textarea"
              rows="3"
              :placeholder="$t('settings.multiagent.form.descriptionPlaceholder')"
            />
          </div>

          <div class="af-field">
            <span class="af-label">
              {{ $t('settings.multiagent.form.mode') }}
              <span class="af-required">*</span>
            </span>
            <div class="mode-selector">
              <label
                v-for="mode in modes"
                :key="mode.id"
                class="mode-option"
                :class="{ selected: formData.mode === mode.id }"
              >
                <input v-model="formData.mode" type="radio" :value="mode.id" class="mode-input" />
                <span class="mode-radio" aria-hidden="true" />
                <span class="mode-content">
                  <strong>{{ mode.name }}</strong>
                  <span>{{ mode.desc }}</span>
                </span>
              </label>
            </div>
          </div>

          <div class="af-switches">
            <div v-if="formData.mode === 'council'" class="af-switch-row">
              <div class="af-switch-text">
                <span class="af-switch-title">{{ $t('settings.multiagent.form.crossReview') }}</span>
                <span class="af-switch-hint">{{ $t('settings.multiagent.form.crossReviewHint') }}</span>
              </div>
              <SwitchToggle
                v-model="formData.cross_review"
                :width="40"
                :height="22"
                :aria-label="$t('settings.multiagent.form.crossReview')"
              />
            </div>

            <div class="af-switch-row">
              <div class="af-switch-text">
                <span class="af-switch-title">{{ $t('settings.multiagent.form.enableSkills') }}</span>
                <span class="af-switch-hint">{{ $t('settings.multiagent.form.enableSkillsHint') }}</span>
              </div>
              <SwitchToggle
                v-model="formData.enable_skills"
                :width="40"
                :height="22"
                :aria-label="$t('settings.multiagent.form.enableSkills')"
              />
            </div>
          </div>
        </div>

        <template #footer>
          <button class="co-btn co-btn--secondary" @click="closeDialog">
            {{ $t('common.cancel') }}
          </button>
          <button class="co-btn co-btn--primary" :disabled="!formData.name.trim()" @click="saveTeam">
            {{ $t('settings.multiagent.form.createAndAddMembers') }}
          </button>
        </template>
      </Modal>
    </div>

    <!-- 团队详情抽屉：点击抽屉外的空白区域即可关闭 -->
    <Drawer
      :model-value="!!selectedTeam"
      size="wide"
      :show-header="false"
      :mask-closable="true"
      @update:model-value="handleDetailVisible"
    >
      <TeamDetail
        v-if="selectedTeam"
        :team="selectedTeam"
        @back="selectedTeam = null"
        @updated="handleTeamUpdated"
      />
    </Drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Plus as PlusIcon, Trash as TrashIcon, Copy as CopyIcon, Users as UsersIcon, Search as SearchIcon, X as XIcon, LayoutTemplate as LayoutTemplateIcon, ChevronRight as ChevronRightIcon, Upload as UploadIcon, Download as DownloadIcon } from 'lucide-vue-next'
import { useAgentTeamsStore, type AgentTeam } from '@/store/agentTeams'
import type { AgentTeamCreate } from '@/api/agentTeams'
import { useToast } from '@/composables/useToast'
import { useConfirm } from '@/composables/useConfirm'
import { useI18n } from 'vue-i18n'
import { Drawer, LoadingState, Modal } from '@/components/ui'
import SwitchToggle from '@/components/ui/SwitchToggle.vue'
import TeamDetail from '@/modules/teams/TeamDetail.vue'
import { agentTeamTemplates, templateCategories, type AgentTeamTemplate } from '@/data/agentTeamTemplates'

const { t } = useI18n()
const teamsStore = useAgentTeamsStore()
const toast = useToast()
const { confirm } = useConfirm()

const teams = computed(() => teamsStore.teams)
const activeTeamCount = computed(() => teams.value.filter((team) => team.is_active).length)
const loading = computed(() => teamsStore.loading)
const error = computed(() => teamsStore.error)

const showCreateDialog = ref(false)
const showTemplateDialog = ref(false)
const selectedTeam = ref<AgentTeam | null>(null)
const importInput = ref<HTMLInputElement>()

// 搜索和过滤
const searchQuery = ref('')
const filterMode = ref('')
const filterStatus = ref('')

// 模板相关
const selectedCategory = ref('全部')

const filteredTemplates = computed(() => {
  if (selectedCategory.value === '全部') {
    return agentTeamTemplates
  }
  return agentTeamTemplates.filter(t => t.category === selectedCategory.value)
})

const filteredTeams = computed(() => {
  let result = teams.value

  // 搜索过滤
  if (searchQuery.value.trim()) {
    const query = searchQuery.value.toLowerCase()
    result = result.filter(team =>
      team.name.toLowerCase().includes(query) ||
      (team.description && team.description.toLowerCase().includes(query))
    )
  }

  // 模式过滤
  if (filterMode.value) {
    result = result.filter(team => team.mode === filterMode.value)
  }

  // 状态过滤
  if (filterStatus.value) {
    const isActive = filterStatus.value === 'active'
    result = result.filter(team => team.is_active === isActive)
  }

  return result
})

const clearFilters = () => {
  searchQuery.value = ''
  filterMode.value = ''
  filterStatus.value = ''
}

const selectTemplate = (template: AgentTeamTemplate) => {
  // 基于模板填充表单
  formData.value = {
    name: template.name,
    description: template.description,
    mode: template.mode,
    cross_review: template.cross_review,
    enable_skills: template.enable_skills,
    agents: JSON.parse(JSON.stringify(template.agents)), // 深拷贝
    is_active: true,
  }
  showTemplateDialog.value = false
  showCreateDialog.value = true
}

const formData = ref({
  name: '',
  description: '',
  mode: 'council' as 'pipeline' | 'graph' | 'council',
  cross_review: true,
  enable_skills: false,
  agents: [],
  is_active: true,
})

const modeLabelMap: Record<string, string> = {
  pipeline: '流水线',
  graph: '依赖图',
  council: '多视角',
}

const modes = [
  { id: 'pipeline', name: '流水线 (Pipeline)', desc: '顺序执行，每步接收前序输出' },
  { id: 'graph', name: '依赖图 (Graph)', desc: '无依赖项并行执行' },
  { id: 'council', name: '多视角 (Council)', desc: '全员并行分析 → 交叉互评' },
]

onMounted(async () => {
  await loadTeams()
})

/** 导入/导出只包含团队定义，不涉及管理员模型配置 */
function triggerImport() {
  importInput.value?.click()
}

function exportTeams() {
  const payload = {
    version: '1.0.0',
    exported_at: new Date().toISOString(),
    teams: teams.value.map(team => ({
      name: team.name,
      description: team.description || '',
      mode: team.mode,
      agents: team.agents,
      is_active: team.is_active,
      cross_review: team.cross_review,
      enable_skills: team.enable_skills,
    })),
  }
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' }),
  )
  const link = document.createElement('a')
  link.href = url
  link.download = `agent-teams-${new Date().toISOString().slice(0, 10)}.json`
  link.click()
  URL.revokeObjectURL(url)
}

function normalizeImportedTeam(raw: any): AgentTeamCreate | null {
  const name = String(raw?.name || '').trim()
  if (!name) return null
  const mode = ['pipeline', 'graph', 'council'].includes(raw?.mode)
    ? raw.mode
    : 'pipeline'
  return {
    name,
    description: String(raw?.description || ''),
    mode,
    agents: (Array.isArray(raw?.agents) ? raw.agents : [])
      .filter((agent: any) => agent && String(agent.id || '').trim())
      .map((agent: any) => ({
        id: String(agent.id),
        role: String(agent.role || ''),
        system_prompt: agent.system_prompt ? String(agent.system_prompt) : null,
        task: String(agent.task || ''),
        perspective: agent.perspective ? String(agent.perspective) : null,
        depends_on: Array.isArray(agent.depends_on) ? agent.depends_on.map(String) : [],
        condition: agent.condition ?? null,
      })),
    is_active: raw?.is_active !== false,
    cross_review: raw?.cross_review !== false,
    enable_skills: Boolean(raw?.enable_skills),
  }
}

async function handleImportChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return

  try {
    const parsed = JSON.parse(await file.text())
    const rows = Array.isArray(parsed) ? parsed : parsed?.teams
    if (!Array.isArray(rows) || rows.length === 0) {
      throw new Error('文件里没有团队数据')
    }
    const normalized = rows.map(normalizeImportedTeam).filter(Boolean) as AgentTeamCreate[]
    if (!normalized.length) {
      throw new Error('没有可导入的团队')
    }
    const names = new Set<string>()
    for (const team of normalized) {
      if (names.has(team.name)) {
        throw new Error(`导入文件里存在重复团队名：${team.name}`)
      }
      names.add(team.name)
    }

    const existing = new Map(teams.value.map(team => [team.name, team]))
    for (const payload of normalized) {
      const current = existing.get(payload.name)
      if (current) await teamsStore.updateTeam(current.id, payload)
      else await teamsStore.createTeam(payload)
    }
    await loadTeams()
    toast.success(`已导入 ${normalized.length} 个团队`)
  } catch (err: any) {
    toast.error(err?.message || '导入失败')
  }
}

const loadTeams = async () => {
  await teamsStore.loadTeams()
}

const viewTeamDetail = (team: AgentTeam) => {
  selectedTeam.value = team
}

// 抽屉关闭（Esc / 遮罩）时清空选中，列表状态保持不变
const handleDetailVisible = (visible: boolean) => {
  if (!visible) selectedTeam.value = null
}

const handleTeamUpdated = async () => {
  await teamsStore.loadTeams()
  // 更新选中的团队数据
  if (selectedTeam.value) {
    const updated = teams.value.find(t => t.id === selectedTeam.value!.id)
    if (updated) {
      selectedTeam.value = updated
    }
  }
}

const confirmDelete = async (team: AgentTeam) => {
  await confirm({
    title: t('common.confirmDelete'),
    message: t('settings.multiagent.confirmDelete', { name: team.name }),
    type: 'danger',
    confirmText: t('common.delete'),
    confirmVariant: 'danger',
    onConfirm: async () => {
      try {
        await teamsStore.deleteTeam(team.id)
        toast.success(t('common.success'))
      } catch (err: any) {
        toast.error(err.message || t('common.error'))
      }
    }
  })
}

const copyPayload = (team: AgentTeam) => {
  const payload = {
    mode: team.mode,
    goal: "在这里描述你的目标...",
    cross_review: team.cross_review,
    agents: team.agents.map(a => ({
      id: a.id,
      role: a.role,
      perspective: a.perspective,
      task: a.task,
      depends_on: a.depends_on,
      system_prompt: a.system_prompt,
    })),
  }
  
  navigator.clipboard.writeText(JSON.stringify(payload, null, 2))
  toast.success(t('common.copied'))
}

const closeDialog = () => {
  showCreateDialog.value = false
  formData.value = {
    name: '',
    description: '',
    mode: 'council',
    cross_review: true,
    enable_skills: false,
    agents: [],
    is_active: true,
  }
}

const saveTeam = async () => {
  if (!formData.value.name.trim()) {
    toast.error(t('settings.multiagent.form.nameRequired'))
    return
  }

  try {
    const newTeam = await teamsStore.createTeam(formData.value)
    toast.success(t('settings.multiagent.form.createSuccess'))
    closeDialog()
    // 自动进入详情页添加成员
    selectedTeam.value = newTeam
  } catch (err: any) {
    toast.error(err.message || t('settings.multiagent.form.createError'))
  }
}
</script>
<style scoped>
@import './styles/MultiAgentConfig.css';

/* ---------- 列表视图对齐设置页骨架 ---------- */

.list-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 6px;
}

.toolbar-sep {
  color: var(--color-text-disabled);
}

.toolbar-right {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.import-file-input {
  display: none;
}

.filter-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.search-box {
  position: relative;
  display: flex;
  align-items: center;
  flex: 1;
  min-width: 0;
  max-width: 320px;
}

.search-icon {
  position: absolute;
  left: 9px;
  color: var(--color-text-tertiary);
  pointer-events: none;
}

.search-input {
  padding-left: 28px;
  padding-right: 26px;
}

.search-clear {
  position: absolute;
  right: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-text-tertiary);
  cursor: pointer;
}

.search-clear:hover {
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
}

.filter-select {
  width: auto;
  min-width: 112px;
}

/* 行整体可点开详情，右侧图标按钮各自 stop 冒泡 */
.team-row {
  cursor: pointer;
}

.team-row:hover {
  background: var(--color-bg-secondary);
}

.team-row.is-inactive .co-row-title {
  color: var(--color-text-secondary);
}

.row-chevron {
  flex-shrink: 0;
  color: var(--color-text-disabled);
}

.icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  flex-shrink: 0;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-text-tertiary);
  cursor: pointer;
}

.icon-btn:hover {
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
}

.icon-btn--danger:hover {
  background: var(--color-error-light);
  color: var(--color-error);
}

.agent-line {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.agent-count {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--color-text-tertiary);
}

.agent-chip {
  padding: 1px 7px;
  border-radius: var(--radius-sm);
  background: var(--color-bg-tertiary);
  font-size: 11px;
  line-height: 18px;
  color: var(--color-text-secondary);
}

.agent-chip.is-more {
  color: var(--color-text-tertiary);
}

.state-block {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 56px 16px;
  border: 1px dashed var(--color-border-primary);
  border-radius: var(--radius-lg);
  text-align: center;
}

.state-icon {
  color: var(--color-text-disabled);
}

.state-title {
  margin: 4px 0 0;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
}

.state-desc {
  margin: 0 0 8px;
  max-width: 52ch;
  font-size: var(--font-size-xs);
  line-height: 1.6;
  color: var(--color-text-tertiary);
}

@media (max-width: 680px) {
  .filter-bar {
    flex-wrap: wrap;
  }

  .search-box {
    max-width: none;
    flex-basis: 100%;
  }
}
</style>
