<template>
  <div class="multiagent-config">
    <!-- 团队列表视图 -->
    <div v-if="!selectedTeam" class="teams-list-view">
      <div class="section-header">
        <div class="header-top">
          <h3 class="section-title">
            {{ $t('settings.multiagent.title') }}
          </h3>
          <div class="header-actions">
            <button class="action-btn btn-secondary" @click="showTemplateDialog = true">
              <component :is="LayoutTemplateIcon" :size="16" />
              <span>从模板创建</span>
            </button>
            <button class="action-btn btn-primary" @click="showCreateDialog = true">
              <component :is="PlusIcon" :size="16" />
              <span>{{ $t('settings.multiagent.newTeam') }}</span>
            </button>
          </div>
        </div>
        <p class="section-desc">
          {{ $t('settings.multiagent.description') }}
        </p>
        <div class="status-summary">
          <div class="status-item">
            <span class="status-dot active"></span>
            <span class="status-text">{{ teams.filter(t => t.is_active).length }} 已激活</span>
          </div>
          <div class="status-divider"></div>
          <div class="status-item">
            <span class="status-dot total"></span>
            <span class="status-text">{{ teams.length }} 总计</span>
          </div>
        </div>
      </div>

      <!-- 搜索和过滤栏 -->
      <div v-if="teams.length > 0" class="search-filter-bar">
        <div class="search-box">
          <component :is="SearchIcon" :size="16" class="search-icon" />
          <input
            v-model="searchQuery"
            type="text"
            class="search-input"
            placeholder="搜索团队名称或描述..."
          />
          <button v-if="searchQuery" class="clear-btn" @click="searchQuery = ''">
            <component :is="XIcon" :size="14" />
          </button>
        </div>
        <div class="filter-group">
          <select v-model="filterMode" class="filter-select">
            <option value="">所有模式</option>
            <option value="pipeline">流水线</option>
            <option value="graph">依赖图</option>
            <option value="council">多视角</option>
          </select>
          <select v-model="filterStatus" class="filter-select">
            <option value="">所有状态</option>
            <option value="active">已激活</option>
            <option value="inactive">未激活</option>
          </select>
        </div>
      </div>

      <!-- 加载状态 -->
      <div v-if="loading" class="loading-state">
        <LoadingState />
      </div>

      <!-- 错误状态 -->
      <div v-else-if="error" class="error-state">
        <p>{{ error }}</p>
        <button class="btn-secondary" @click="loadTeams">
          {{ $t('common.retry') }}
        </button>
      </div>

      <!-- 空状态 -->
      <div v-else-if="teams.length === 0" class="empty-state">
        <component :is="UsersIcon" :size="48" class="empty-icon" />
        <h3>{{ $t('settings.multiagent.empty') }}</h3>
        <p>{{ $t('settings.multiagent.emptyDesc') }}</p>
        <button class="btn-primary" @click="showCreateDialog = true">
          <component :is="PlusIcon" :size="16" />
          {{ $t('settings.multiagent.newTeam') }}
        </button>
      </div>

      <!-- 团队列表 -->
      <div v-else-if="filteredTeams.length > 0" class="teams-grid">
        <div
          v-for="team in filteredTeams"
          :key="team.id"
          class="team-card"
          :class="{ inactive: !team.is_active }"
          @click="viewTeamDetail(team)"
        >
          <div class="team-card-header">
            <div class="team-info">
              <h3>{{ team.name }}</h3>
              <div class="team-badges">
                <span class="badge badge-mode">{{ modeLabelMap[team.mode] }}</span>
                <span v-if="team.mode === 'council'" class="badge badge-review" :class="team.cross_review ? 'badge-cross' : 'badge-independent'">
                  {{ team.cross_review ? '交叉模式' : '独立模式' }}
                </span>
              </div>
            </div>
            <div class="team-actions" @click.stop>
              <button class="icon-btn" :title="$t('settings.multiagent.copyPayload')" @click="copyPayload(team)">
                <component :is="CopyIcon" :size="16" />
              </button>
              <button class="icon-btn danger" :title="$t('common.delete')" @click="confirmDelete(team)">
                <component :is="TrashIcon" :size="16" />
              </button>
            </div>
          </div>

          <p v-if="team.description" class="team-description">{{ team.description }}</p>

          <div class="team-agents">
            <span class="agent-count">
              <component :is="UsersIcon" :size="14" />
              {{ team.agents.length }} {{ $t('settings.multiagent.agentUnit') }}
            </span>
            <div class="agent-chips">
              <span v-for="agent in team.agents.slice(0, 3)" :key="agent.id" class="agent-chip">
                {{ agent.role || agent.perspective || agent.id }}
              </span>
              <span v-if="team.agents.length > 3" class="agent-chip more">
                +{{ team.agents.length - 3 }}
              </span>
            </div>
          </div>

          <div class="team-footer">
            <span class="view-detail">{{ $t('settings.multiagent.viewDetail') }}</span>
          </div>
        </div>
      </div>

      <!-- 无搜索结果 -->
      <div v-else class="no-results">
        <component :is="SearchIcon" :size="48" class="empty-icon" />
        <h3>未找到匹配的团队</h3>
        <p>尝试调整搜索条件或过滤器</p>
        <button class="btn-secondary" @click="clearFilters">
          清除所有过滤条件
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
      <Modal :model-value="showCreateDialog" @close="closeDialog" size="medium">
        <div class="dialog-content">
          <h3>{{ $t('settings.multiagent.form.createTitle') }}</h3>

          <div class="form-section">
            <div class="form-group">
              <label>{{ $t('settings.multiagent.form.name') }} <span class="required">*</span></label>
              <input v-model="formData.name" type="text" class="form-input" :placeholder="$t('settings.multiagent.form.namePlaceholder')" />
            </div>

            <div class="form-group">
              <label>{{ $t('settings.multiagent.form.description') }}</label>
              <textarea v-model="formData.description" class="form-textarea" rows="2" :placeholder="$t('settings.multiagent.form.descriptionPlaceholder')" />
            </div>

            <div class="form-group">
              <label>{{ $t('settings.multiagent.form.mode') }} <span class="required">*</span></label>
              <div class="mode-selector">
                <label v-for="mode in modes" :key="mode.id" class="mode-option" :class="{ selected: formData.mode === mode.id }">
                  <input v-model="formData.mode" type="radio" :value="mode.id" />
                  <div class="mode-content">
                    <strong>{{ mode.name }}</strong>
                    <span>{{ mode.desc }}</span>
                  </div>
                </label>
              </div>
            </div>

            <div v-if="formData.mode === 'council'" class="form-group">
              <div class="toggle-wrapper">
                <div class="toggle-content">
                  <div class="toggle-label-text">
                    <span class="toggle-title">{{ $t('settings.multiagent.form.crossReview') }}</span>
                    <p class="toggle-hint">{{ $t('settings.multiagent.form.crossReviewHint') }}</p>
                  </div>
                </div>
                <SwitchToggle
                  v-model="formData.cross_review"
                  :width="44"
                  :height="24"
                  :aria-label="$t('settings.multiagent.form.crossReview')"
                />
              </div>
            </div>

            <div class="form-group">
              <div class="toggle-wrapper">
                <div class="toggle-content">
                  <div class="toggle-label-text">
                    <span class="toggle-title">{{ $t('settings.multiagent.form.enableSkills') }}</span>
                    <p class="toggle-hint">{{ $t('settings.multiagent.form.enableSkillsHint') }}</p>
                  </div>
                </div>
                <SwitchToggle
                  v-model="formData.enable_skills"
                  :width="44"
                  :height="24"
                  :aria-label="$t('settings.multiagent.form.enableSkills')"
                />
              </div>
            </div>
          </div>

          <div class="dialog-actions">
            <button class="btn-secondary" @click="closeDialog">
              {{ $t('common.cancel') }}
            </button>
            <button class="btn-primary" @click="saveTeam" :disabled="!formData.name.trim()">
              {{ $t('settings.multiagent.form.createAndAddMembers') }}
            </button>
          </div>
        </div>
      </Modal>
    </div>

    <!-- 团队详情视图 -->
    <TeamDetail
      v-else
      :team="selectedTeam"
      @back="selectedTeam = null"
      @updated="handleTeamUpdated"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Plus as PlusIcon, Trash as TrashIcon, Copy as CopyIcon, Users as UsersIcon, Search as SearchIcon, X as XIcon, LayoutTemplate as LayoutTemplateIcon, Network as NetworkIcon } from 'lucide-vue-next'
import { useAgentTeamsStore, type AgentTeam } from '@/store/agentTeams'
import { useToast } from '@/composables/useToast'
import { useI18n } from 'vue-i18n'
import { LoadingState, Modal } from '@/components/ui'
import SwitchToggle from '@/components/ui/SwitchToggle.vue'
import TeamDetail from '@/modules/teams/TeamDetail.vue'
import { agentTeamTemplates, templateCategories, type AgentTeamTemplate } from '@/data/agentTeamTemplates'

const { t } = useI18n()
const teamsStore = useAgentTeamsStore()
const toast = useToast()

const teams = computed(() => teamsStore.teams)
const loading = computed(() => teamsStore.loading)
const error = computed(() => teamsStore.error)

const showCreateDialog = ref(false)
const showTemplateDialog = ref(false)
const selectedTeam = ref<AgentTeam | null>(null)

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

const loadTeams = async () => {
  await teamsStore.loadTeams()
}

const viewTeamDetail = (team: AgentTeam) => {
  selectedTeam.value = team
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
  if (!confirm(t('settings.multiagent.confirmDelete', { name: team.name }))) return
  
  try {
    await teamsStore.deleteTeam(team.id)
    toast.success(t('common.success'))
  } catch (err: any) {
    toast.error(err.message || t('common.error'))
  }
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
</style>
