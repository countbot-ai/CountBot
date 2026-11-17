<template>
  <div class="team-detail">
    <!-- 返回按钮和团队信息 -->
    <div class="detail-header">
      <button class="btn-back" @click="$emit('back')">
        <component :is="ArrowLeftIcon" :size="16" />
        {{ $t('teams.detail.backToList') }}
      </button>
      
      <div class="team-info-section">
        <div class="team-title-row">
          <h2>{{ team.name }}</h2>
          <div class="team-badges">
            <span class="badge badge-mode">{{ modeLabelMap[team.mode] }}</span>
            <span v-if="team.mode === 'council'" class="badge badge-review" :class="team.cross_review ? 'badge-cross' : 'badge-independent'">
              {{ team.cross_review ? $t('teams.detail.crossMode') : $t('teams.detail.independentMode') }}
            </span>
          </div>
          <button class="icon-btn" @click="showEditTeamDialog = true">
            <component :is="EditIcon" :size="16" />
          </button>
        </div>
        <p v-if="team.description" class="team-description">{{ team.description }}</p>
      </div>
    </div>

    <!-- 成员列表 -->
    <div class="members-section">
      <div class="section-header">
        <h3>{{ $t('teams.detail.membersTitle', { n: localAgents.length }) }}</h3>
        <div class="section-actions">
          <button v-if="team.mode === 'graph' && localAgents.length > 0" class="btn-secondary" @click="showGraph = !showGraph">
            <component :is="NetworkIcon" :size="16" />
            {{ showGraph ? $t('teams.detail.hideGraph') : $t('teams.detail.showGraph') }}
          </button>
          <button class="btn-primary" @click="addMember">
            <component :is="PlusIcon" :size="16" />
            {{ $t('teams.detail.addMember') }}
          </button>
        </div>
      </div>

      <!-- 依赖关系图 (Graph模式) -->
      <div v-if="team.mode === 'graph' && showGraph && localAgents.length > 0" class="graph-section">
        <DependencyGraph :agents="localAgents" />
      </div>

      <div v-if="localAgents.length === 0" class="empty-members">
        <component :is="UsersIcon" :size="48" class="empty-icon" />
        <p>{{ $t('teams.detail.emptyMembers') }}</p>
      </div>

      <div v-else class="members-list">
        <div v-for="(agent, index) in localAgents" :key="index" class="member-card">
          <div class="member-header">
            <div class="member-info">
              <span class="member-number">#{{ index + 1 }}</span>
              <h4>{{ agent.role || agent.perspective || agent.id }}</h4>
            </div>
            <div class="member-actions">
              <button class="icon-btn" @click="editMember(index)">
                <component :is="EditIcon" :size="16" />
              </button>
              <button class="icon-btn danger" @click="removeMember(index)">
                <component :is="TrashIcon" :size="16" />
              </button>
            </div>
          </div>

          <div class="member-details">
            <div class="detail-item">
              <span class="detail-label">ID:</span>
              <span class="detail-value">{{ agent.id }}</span>
            </div>
            <div v-if="team.mode === 'council'" class="detail-item">
              <span class="detail-label">{{ $t('teams.detail.perspectiveLabel') }}</span>
              <span class="detail-value">{{ agent.perspective || '-' }}</span>
            </div>
            <div v-else class="detail-item">
              <span class="detail-label">{{ $t('teams.detail.taskLabel') }}</span>
              <span class="detail-value">{{ agent.task || '-' }}</span>
            </div>
            <div v-if="team.mode === 'graph' && agent.depends_on?.length" class="detail-item">
              <span class="detail-label">{{ $t('teams.detail.dependsLabel') }}</span>
              <span class="detail-value">{{ agent.depends_on.join(', ') }}</span>
            </div>
            <div v-if="agent.condition" class="detail-item full-width">
              <span class="detail-label">{{ $t('teams.detail.conditionLabel') }}</span>
              <div class="condition-badge">
                <span class="condition-type">{{ agent.condition.type === 'output_contains' ? $t('teams.detail.conditionContains') : $t('teams.detail.conditionNotContains') }}</span>
                <span class="condition-node">{{ agent.condition.node }}</span>
                <span class="condition-text">"{{ agent.condition.text }}"</span>
              </div>
            </div>
            <div v-if="agent.system_prompt" class="detail-item full-width">
              <span class="detail-label">{{ $t('teams.detail.systemPromptLabel') }}</span>
              <div class="prompt-preview">{{ agent.system_prompt }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 编辑团队信息对话框 - 标签页形式 -->
    <Modal
      :model-value="showEditTeamDialog"
      :title="$t('teams.detail.editTitle')"
      size="large"
      @close="closeEditTeamDialog"
    >
      <div class="dialog-content">
        <!-- 标签页导航 -->
        <div class="tabs-nav">
          <button
            class="tab-btn"
            :class="{ active: activeTab === 'basic' }"
            @click="activeTab = 'basic'"
          >
            <component :is="InfoIcon" :size="16" />
            <span>{{ $t('teams.detail.tabBasic') }}</span>
          </button>
          <button
            v-if="userStore.isAdmin"
            class="tab-btn"
            :class="{ active: activeTab === 'model' }"
            @click="activeTab = 'model'"
          >
            <component :is="CpuIcon" :size="16" />
            <span>{{ $t('teams.detail.tabModel') }}</span>
          </button>
        </div>

        <!-- 标签页内容 -->
        <div class="tabs-content">
          <!-- 基本信息标签页 -->
          <div v-show="activeTab === 'basic'" class="tab-panel">
            <div class="form-group">
              <label>{{ $t('teams.detail.teamName') }} <span class="required">*</span></label>
              <input v-model="teamForm.name" type="text" class="form-input" />
            </div>

            <div class="form-group">
              <label>{{ $t('teams.detail.teamDescription') }}</label>
              <textarea v-model="teamForm.description" class="form-textarea" rows="3" />
            </div>

            <div class="form-group">
              <label>{{ $t('teams.detail.collaborationMode') }} <span class="required">*</span></label>
              <select v-model="teamForm.mode" class="form-select">
                <option value="pipeline">{{ $t('teams.detail.modePipeline') }}</option>
                <option value="graph">{{ $t('teams.detail.modeGraph') }}</option>
                <option value="council">{{ $t('teams.detail.modeCouncil') }}</option>
              </select>
            </div>

            <div v-if="teamForm.mode === 'council'" class="form-group">
              <div class="toggle-wrapper">
                <div class="toggle-content">
                  <span class="toggle-title">{{ $t('teams.detail.crossReview') }}</span>
                  <p class="toggle-hint">{{ $t('teams.detail.crossReviewHint') }}</p>
                </div>
                <SwitchToggle
                  v-model="teamForm.cross_review"
                  :width="44"
                  :height="24"
                  :aria-label="$t('teams.detail.crossReview')"
                />
              </div>
            </div>

            <div class="form-group">
              <div class="toggle-wrapper">
                <div class="toggle-content">
                  <span class="toggle-title">{{ $t('teams.detail.skills') }}</span>
                  <p class="toggle-hint">{{ $t('teams.detail.skillsHint') }}</p>
                </div>
                <SwitchToggle
                  v-model="teamForm.enable_skills"
                  :width="44"
                  :height="24"
                  :aria-label="$t('teams.detail.skills')"
                />
              </div>
            </div>
          </div>

          <!-- 模型配置标签页：团队模型属于管理员能力，普通用户沿用当前对话模型 -->
          <div v-if="userStore.isAdmin" v-show="activeTab === 'model'" class="tab-panel">
            <!-- 使用自定义配置开关 -->
            <div class="config-toggle" :class="{ active: useCustomModel }">
              <div class="toggle-header">
                <label class="toggle-label">
                  <SwitchToggle
                    v-model="useCustomModel"
                    :width="48"
                    :height="28"
                    :aria-label="$t('teams.detail.customModel')"
                    @change="onToggleCustomModel"
                  />
                  <div class="toggle-content-large">
                    <span class="toggle-text">{{ $t('teams.detail.customModel') }}</span>
                    <span class="toggle-hint">{{ $t('teams.detail.customModelHint') }}</span>
                  </div>
                </label>
                <div v-if="useCustomModel" class="config-badge">
                  <component :is="SparklesIcon" :size="14" />
                  <span>{{ $t('teams.detail.custom') }}</span>
                </div>
              </div>
            </div>

            <div v-if="useCustomModel" class="model-config-section">
              <div class="model-config-toolbar">
                <div class="model-config-copy">
                  <h4>{{ $t('teams.detail.modelSettings') }}</h4>
                </div>
              </div>

              <div class="form-grid">
                <div class="form-group">
                  <label>{{ $t('settings.providers.selectProvider') }}</label>
                  <Select
                    v-model="modelConfig.provider"
                    :options="providerOptions"
                    :placeholder="$t('settings.providers.selectProvider')"
                    searchable
                  />
                </div>

                <div class="form-group">
                  <label>{{ $t('settings.providers.model') }}</label>
                  <input v-model="modelConfig.model" type="text" class="form-input" placeholder="deepseek-flash" />
                </div>

              </div>

              <ModelParameterFields
                :temperature="modelConfig.temperature ?? 0"
                :max-tokens="modelConfig.max_tokens ?? 0"
                :max-iterations="modelConfig.max_iterations ?? 0"
                :thinking-enabled="modelConfig.thinking_enabled ?? true"
                :stream-enabled="modelConfig.stream_enabled ?? true"
                @update:temperature="modelConfig.temperature = $event"
                @update:maxTokens="modelConfig.max_tokens = $event"
                @update:maxIterations="modelConfig.max_iterations = $event"
                @update:thinkingEnabled="modelConfig.thinking_enabled = $event"
                @update:streamEnabled="modelConfig.stream_enabled = $event"
              />

              <!-- 高级 API 设置 -->
              <details class="advanced-config">
                <summary>
                  <component :is="LockIcon" :size="16" />
                  <span>{{ $t('chat.sessionConfig.advancedApiSettings') }}</span>
                  <component :is="ChevronDownIcon" :size="16" class="chevron" />
                </summary>

                <div class="advanced-content">
                  <div class="form-group">
                    <label>{{ $t('settings.providers.apiKey') }}</label>
                    <input
                      v-model="modelConfig.api_key"
                      type="password"
                      :placeholder="$t('chat.sessionConfig.leaveEmptyForGlobal')"
                      class="form-input"
                    />
                    <p class="form-hint">{{ $t('chat.sessionConfig.apiKeyHint') }}</p>
                  </div>

                  <div class="form-group">
                    <label>{{ $t('settings.providers.baseUrl') }}</label>
                    <input
                      v-model="modelConfig.api_base"
                      type="text"
                      :placeholder="$t('chat.sessionConfig.leaveEmptyForGlobal')"
                      class="form-input"
                    />
                    <p class="form-hint">{{ $t('chat.sessionConfig.apiBaseHint') }}</p>
                  </div>

                  <!-- 测试连接按钮 -->
                  <div class="form-group">
                    <button
                      @click="handleTestConnection"
                      class="btn-secondary"
                      :disabled="testing"
                    >
                      <component :is="testing ? Loader2Icon : CheckCircleIcon" :size="16" :class="{ spin: testing }" />
                      <span>{{ testing ? $t('settings.providers.testing') : $t('settings.providers.testConnection') }}</span>
                    </button>
                  </div>

                  <!-- 测试结果 -->
                  <div
                    v-if="testResult"
                    class="test-result"
                    :class="testResult.success ? 'success' : 'error'"
                  >
                    <component :is="testResult.success ? CheckCircleIcon : XCircleIcon" :size="16" />
                    <span>{{ testResult.message }}</span>
                  </div>
                </div>
              </details>
            </div>

            <div v-else class="empty-state-inline">
              <component :is="GlobeIcon" :size="32" class="empty-icon" />
              <div class="empty-text">
                <h4>{{ $t('teams.detail.globalDefault') }}</h4>
                <p>{{ $t('teams.detail.globalDefaultHint') }}</p>
              </div>
            </div>
          </div>
        </div>

      </div>

      <template #footer>
        <button class="co-btn co-btn--secondary" @click="closeEditTeamDialog">{{ $t('common.cancel') }}</button>
        <button class="co-btn co-btn--primary" @click="saveTeamInfo">{{ $t('common.save') }}</button>
      </template>
    </Modal>

    <!-- 编辑成员对话框 -->
    <Modal
      :model-value="showEditMemberDialog"
      :title="editingMemberIndex === null ? $t('teams.detail.addMemberTitle') : $t('teams.detail.editMemberTitle')"
      size="large"
      @close="closeMemberDialog"
    >
      <div class="dialog-content">
        <div class="form-group">
          <label>{{ $t('teams.detail.memberId') }} <span class="required">*</span></label>
          <input v-model="memberForm.id" type="text" class="form-input" :placeholder="$t('teams.detail.memberIdPlaceholder')" />
          <p class="form-hint">{{ $t('teams.detail.memberIdHint') }}</p>
        </div>

        <div v-if="team.mode === 'council'" class="form-group">
          <label>{{ $t('teams.detail.perspective') }} <span class="required">*</span></label>
          <input v-model="memberForm.perspective" type="text" class="form-input" :placeholder="$t('teams.detail.perspectivePlaceholder')" />
          <p class="form-hint">{{ $t('teams.detail.perspectiveHint') }}</p>
        </div>

        <div v-else class="form-group">
          <label>{{ $t('teams.detail.role') }} <span class="required">*</span></label>
          <input v-model="memberForm.role" type="text" class="form-input" :placeholder="$t('teams.detail.rolePlaceholder')" />
        </div>

        <div v-if="team.mode !== 'council'" class="form-group">
          <label>{{ $t('teams.detail.task') }}</label>
          <textarea v-model="memberForm.task" class="form-textarea" rows="3" :placeholder="$t('teams.detail.taskPlaceholder')" />
          <p class="form-hint">{{ $t('teams.detail.taskHint') }}</p>
        </div>

        <div v-if="team.mode === 'graph'" class="form-group">
          <label>{{ $t('teams.detail.dependsOn') }}</label>
          
          <div class="dependency-selector">
            <div v-if="getSelectedDependencies().length > 0" class="selected-tags">
              <span v-for="dep in getSelectedDependencies()" :key="dep" class="dependency-tag">
                {{ dep }}
                <button type="button" class="tag-remove" @click="removeDependency(dep)">×</button>
              </span>
            </div>
            <select class="form-select" @change="addDependency($event)" :disabled="getAvailableDependencies().length === 0">
              <option value="">{{ getAvailableDependencies().length === 0 ? $t('teams.detail.noDependencies') : $t('teams.detail.selectDependencies') }}</option>
              <option v-for="agent in getAvailableDependencies()" :key="agent.id" :value="agent.id">
                {{ agent.id }} - {{ agent.role || agent.perspective || $t('teams.detail.unnamed') }}
              </option>
            </select>
          </div>
          <p class="form-hint">{{ $t('teams.detail.dependsHint') }}</p>
        </div>

        <!-- 条件配置（Graph模式下始终显示） -->
        <div v-if="team.mode === 'graph'" class="form-group">
          <label>{{ $t('teams.detail.conditionOptional') }}</label>
          
          <!-- 没有依赖时显示提示 -->
          <div v-if="!memberForm.depends_on_str.trim()" class="condition-disabled-hint">
            <component :is="InfoIcon" :size="16" />
            <span>{{ $t('teams.detail.selectDependenciesFirst') }}</span>
          </div>
          
          <!-- 有依赖时显示配置 -->
          <div v-else class="condition-config">
            <div class="toggle-wrapper">
              <div class="toggle-content">
                <span class="toggle-title">{{ $t('teams.detail.enableCondition') }}</span>
                <p class="toggle-hint">{{ $t('teams.detail.conditionHint') }}</p>
              </div>
              <SwitchToggle
                v-model="memberForm.enable_condition"
                :width="44"
                :height="24"
                :aria-label="$t('teams.detail.enableCondition')"
              />
            </div>

            <div v-if="memberForm.enable_condition" class="condition-form">
              <div class="form-row">
                <div class="form-col">
                  <label>{{ $t('teams.detail.conditionType') }}</label>
                  <select v-model="memberForm.condition_type" class="form-select">
                    <option value="output_contains">{{ $t('teams.detail.outputContains') }}</option>
                    <option value="output_not_contains">{{ $t('teams.detail.outputNotContains') }}</option>
                  </select>
                </div>
                <div class="form-col">
                  <label>{{ $t('teams.detail.checkNode') }}</label>
                  <select v-model="memberForm.condition_node" class="form-select">
                    <option value="">{{ $t('teams.detail.selectNode') }}</option>
                    <option v-for="nodeId in getAllUpstreamNodes()" :key="nodeId" :value="nodeId">
                      {{ nodeId }} - {{ getAgentById(nodeId)?.role || getAgentById(nodeId)?.perspective || $t('teams.detail.unnamed') }}
                    </option>
                  </select>
                  <p class="form-hint">{{ $t('teams.detail.anyUpstream') }}</p>
                </div>
              </div>
              <div class="form-row">
                <div class="form-col full">
                  <label>{{ $t('teams.detail.matchText') }}</label>
                  <input 
                    v-model="memberForm.condition_text" 
                    type="text" 
                    class="form-input" 
                    :placeholder="$t('teams.detail.matchPlaceholder')" 
                  />
                  <p class="form-hint">
                    {{ memberForm.condition_type === 'output_contains' 
                      ? $t('teams.detail.matchContainsHint') 
                      : $t('teams.detail.matchNotContainsHint') }}
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="form-group">
          <label>{{ $t('teams.detail.systemPromptFull') }}</label>
          <textarea 
            v-model="memberForm.system_prompt" 
            class="form-textarea prompt-textarea" 
            rows="8" 
            :placeholder="$t('teams.detail.systemPromptPlaceholder')"
          />
          <p class="form-hint">
            {{ $t('teams.detail.systemPromptHint') }}
          </p>
        </div>

      </div>

      <template #footer>
        <button class="co-btn co-btn--secondary" @click="closeMemberDialog">{{ $t('common.cancel') }}</button>
        <button class="co-btn co-btn--primary" @click="saveMember" :disabled="!canSaveMember">{{ $t('common.save') }}</button>
      </template>
    </Modal>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { 
  ArrowLeft as ArrowLeftIcon, 
  Plus as PlusIcon, 
  Edit as EditIcon, 
  Trash as TrashIcon, 
  Users as UsersIcon, 
  Info as InfoIcon, 
  Network as NetworkIcon, 
  Cpu as CpuIcon,
  Sparkles as SparklesIcon,
  ChevronDown as ChevronDownIcon,
  Lock as LockIcon,
  CheckCircle as CheckCircleIcon,
  XCircle as XCircleIcon,
  Loader2 as Loader2Icon,
  Globe as GlobeIcon
} from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { useAgentTeamsStore, type AgentTeam } from '@/store/agentTeams'
import { useUserStore } from '@/store/user'
import { useToast } from '@/composables/useToast'
import { useConfirm } from '@/composables/useConfirm'
import { Modal } from '@/components/ui'
import SwitchToggle from '@/components/ui/SwitchToggle.vue'
import ModelParameterFields from '@/components/ui/ModelParameterFields.vue'
import Select from '@/components/ui/Select.vue'
import DependencyGraph from './DependencyGraph.vue'
import { useModelCatalog } from '@/composables/useModelCatalog'
import { agentTeamsApi, type TeamModelConfig } from '@/api/agentTeams'
import {
  findFirstSelectableProvider,
  findProviderById,
  resolveProviderDefaultApiBase,
  resolveProviderDefaultModel,
} from '@/utils/providerRuntime'
import {
  buildCustomModelEditorConfig,
  MODEL_CONFIG_FALLBACK,
  buildEffectiveModelConfig,
  buildModelConfigOverrides,
  buildSendableModelConfig,
} from '@/utils/modelConfig'

interface Props {
  team: AgentTeam
}

const props = defineProps<Props>()
const emit = defineEmits(['back', 'updated'])
const { t } = useI18n()

const teamsStore = useAgentTeamsStore()
const userStore = useUserStore()
const toast = useToast()
// 供应商目录与连通性测试按身份分流，普通用户不走管理员接口
const modelCatalog = useModelCatalog()
const { confirm } = useConfirm()

const modeLabelMap: Record<string, string> = {
  pipeline: t('teams.detail.modePipeline'),
  graph: t('teams.detail.modeGraph'),
  council: t('teams.detail.modeCouncil'),
}

// 本地成员列表（可编辑）
const localAgents = ref<any[]>([])

// 显示依赖图
const showGraph = ref(false)

// 团队信息编辑
const showEditTeamDialog = ref(false)
const activeTab = ref<'basic' | 'model'>('basic')
const teamForm = ref({
  name: '',
  description: '',
  mode: 'council' as 'pipeline' | 'graph' | 'council',
  cross_review: true,
  enable_skills: false,
})

// 模型配置相关
const useCustomModel = ref(false)
const testing = ref(false)
const testResult = ref<{ success: boolean; message: string } | null>(null)
const providers = ref<Array<{ id: string; name: string; defaultApiBase?: string; defaultModel?: string }>>([])
const isHydratingConfig = ref(false)

const createDefaultModelConfig = (): TeamModelConfig =>
  buildCustomModelEditorConfig<TeamModelConfig>()

const modelConfig = ref<TeamModelConfig>(createDefaultModelConfig())
const globalModelDefaults = ref<TeamModelConfig>(createDefaultModelConfig())
const providerOptions = computed(() =>
  providers.value.map(provider => ({
    value: provider.id,
    label: provider.name,
  }))
)
// 成员编辑
const showEditMemberDialog = ref(false)
const editingMemberIndex = ref<number | null>(null)
const memberForm = ref({
  id: '',
  role: '',
  perspective: '',
  task: '',
  system_prompt: '',
  depends_on_str: '',
  enable_condition: false,
  condition_type: 'output_contains' as 'output_contains' | 'output_not_contains',
  condition_node: '',
  condition_text: '',
})

const canSaveMember = computed(() => {
  if (!memberForm.value.id.trim()) return false
  if (props.team.mode === 'council') {
    return !!memberForm.value.perspective.trim()
  }
  return !!memberForm.value.role.trim()
})

// 初始化数据
watch(() => props.team, (newTeam) => {
  if (newTeam) {
    localAgents.value = JSON.parse(JSON.stringify(newTeam.agents || []))
    teamForm.value = {
      name: newTeam.name,
      description: newTeam.description || '',
      mode: newTeam.mode,
      cross_review: newTeam.cross_review,
      enable_skills: newTeam.enable_skills || false,
    }
  }
}, { immediate: true })

// 组件挂载时加载数据
onMounted(async () => {
  await loadProviders()
  await loadTeamModelConfig()
})

const addMember = () => {
  editingMemberIndex.value = null
  memberForm.value = {
    id: `agent${localAgents.value.length + 1}`,
    role: '',
    perspective: '',
    task: '',
    system_prompt: '',
    depends_on_str: '',
    enable_condition: false,
    condition_type: 'output_contains',
    condition_node: '',
    condition_text: '',
  }
  showEditMemberDialog.value = true
}

const editMember = (index: number) => {
  editingMemberIndex.value = index
  const agent = localAgents.value[index]
  
  // 解析条件配置
  const hasCondition = !!agent.condition
  memberForm.value = {
    id: agent.id,
    role: agent.role || '',
    perspective: agent.perspective || '',
    task: agent.task || '',
    system_prompt: agent.system_prompt || '',
    depends_on_str: (agent.depends_on || []).join(', '),
    enable_condition: hasCondition,
    condition_type: agent.condition?.type || 'output_contains',
    condition_node: agent.condition?.node || '',
    condition_text: agent.condition?.text || '',
  }
  showEditMemberDialog.value = true
}

const getAllUpstreamNodes = (): string[] => {
  const visited = new Set<string>()
  const queue: string[] = []
  
  // 获取当前成员的直接依赖
  const currentDeps = memberForm.value.depends_on_str
    .split(',')
    .map(s => s.trim())
    .filter(Boolean)
  
  currentDeps.forEach(dep => {
    visited.add(dep)
    queue.push(dep)
  })
  
  // BFS 遍历所有上游节点
  while (queue.length > 0) {
    const currentId = queue.shift()!
    const agent = localAgents.value.find(a => a.id === currentId)
    
    if (agent?.depends_on) {
      agent.depends_on.forEach((depId: string) => {
        if (!visited.has(depId)) {
          visited.add(depId)
          queue.push(depId)
        }
      })
    }
  }
  
  return Array.from(visited)
}

const getAgentById = (id: string) => {
  return localAgents.value.find(a => a.id === id)
}

const getSelectedDependencies = () => {
  return memberForm.value.depends_on_str
    .split(',')
    .map(s => s.trim())
    .filter(Boolean)
}

const getAvailableDependencies = () => {
  const currentId = memberForm.value.id.trim()
  const selected = getSelectedDependencies()
  
  // 过滤掉当前成员和已选择的依赖
  return localAgents.value.filter(agent => {
    // 如果是编辑模式，排除当前成员
    if (editingMemberIndex.value !== null) {
      const currentAgent = localAgents.value[editingMemberIndex.value]
      if (agent.id === currentAgent?.id) {
        return false
      }
    }
    // 新建模式排除与当前 ID 相同的成员
    if (agent.id === currentId) {
      return false
    }
    // 排除已选择的依赖
    return !selected.includes(agent.id)
  })
}

const addDependency = (event: Event) => {
  const select = event.target as HTMLSelectElement
  const depId = select.value
  if (!depId) return
  
  const current = getSelectedDependencies()
  current.push(depId)
  memberForm.value.depends_on_str = current.join(', ')
  
  // 重置选择框
  select.value = ''
}

const removeDependency = (depId: string) => {
  const current = getSelectedDependencies()
  const filtered = current.filter(id => id !== depId)
  memberForm.value.depends_on_str = filtered.join(', ')
  
  // 如果没有依赖了，清空条件配置
  if (filtered.length === 0) {
    memberForm.value.enable_condition = false
    memberForm.value.condition_node = ''
    memberForm.value.condition_text = ''
  }
}

const removeMember = async (index: number) => {
  const confirmed = await confirm({
    title: t('teams.detail.confirmDelete'),
    message: t('teams.detail.confirmDeleteMessage'),
    type: 'danger',
    confirmText: t('common.delete'),
    confirmVariant: 'danger'
  })
  if (!confirmed) return
  localAgents.value.splice(index, 1)
  saveChanges()
}

const closeMemberDialog = () => {
  showEditMemberDialog.value = false
  editingMemberIndex.value = null
}

const saveMember = () => {
  const agent: any = {
    id: memberForm.value.id.trim(),
  }

  if (props.team.mode === 'council') {
    agent.perspective = memberForm.value.perspective.trim()
    const parts = agent.perspective.split(/[，,]/)
    agent.role = parts[0].trim() || agent.id
  } else {
    agent.role = memberForm.value.role.trim()
    agent.task = memberForm.value.task.trim()
  }

  if (memberForm.value.system_prompt.trim()) {
    agent.system_prompt = memberForm.value.system_prompt.trim()
  }

  if (props.team.mode === 'graph') {
    agent.depends_on = memberForm.value.depends_on_str
      .split(',')
      .map(s => s.trim())
      .filter(Boolean)
    
    // 保存条件配置
    if (memberForm.value.enable_condition && 
        memberForm.value.condition_node && 
        memberForm.value.condition_text.trim()) {
      agent.condition = {
        type: memberForm.value.condition_type,
        node: memberForm.value.condition_node,
        text: memberForm.value.condition_text.trim(),
      }
    }
  } else {
    agent.depends_on = []
  }

  if (editingMemberIndex.value !== null) {
    localAgents.value[editingMemberIndex.value] = agent
  } else {
    localAgents.value.push(agent)
  }

  closeMemberDialog()
  saveChanges()
}

// 加载服务商列表
async function loadProviders() {
  try {
    const providersData = await modelCatalog.listProviders()
    providers.value = providersData.map(p => ({
      id: p.id,
      name: p.name,
      defaultApiBase: resolveProviderDefaultApiBase(p),
      defaultModel: resolveProviderDefaultModel(p)
    }))
    ensureValidTeamProviderSelection()
  } catch (error) {
    console.error('Failed to load providers:', error)
  }
}

// 加载团队模型配置
async function loadTeamModelConfig() {
  if (!props.team.id || !userStore.isAdmin) return
  
  try {
    const config = await agentTeamsApi.getConfig(props.team.id)
    globalModelDefaults.value = buildEffectiveModelConfig<TeamModelConfig>(
      undefined,
      config.global_defaults,
    )
    if (config.use_custom_model) {
      applyModelConfig(config.model_settings, true)
    } else {
      applyModelConfig(config.global_defaults, false)
    }
  } catch (error) {
    console.error('Failed to load team config:', error)
  }
}

function applyModelConfig(config: TeamModelConfig, enabled: boolean) {
  isHydratingConfig.value = true
  try {
    useCustomModel.value = enabled
    modelConfig.value = buildCustomModelEditorConfig<TeamModelConfig>(
      globalModelDefaults.value,
      enabled ? config : undefined,
    )
    testResult.value = null
    ensureValidTeamProviderSelection()
  } finally {
    isHydratingConfig.value = false
  }
}

function ensureValidTeamProviderSelection() {
  if (providers.value.length === 0) {
    return
  }

  const currentProvider = findProviderById(providers.value, modelConfig.value.provider)
  if (currentProvider) {
    return
  }

  const fallbackProvider = findFirstSelectableProvider(providers.value)
  const nextProvider = fallbackProvider || providers.value[0]
  if (!nextProvider) {
    return
  }

  modelConfig.value.provider = nextProvider.id
  if (!modelConfig.value.api_base) {
    modelConfig.value.api_base = nextProvider.defaultApiBase || ''
  }
  if (
    !modelConfig.value.model
    || modelConfig.value.model === MODEL_CONFIG_FALLBACK.model
  ) {
    modelConfig.value.model = nextProvider.defaultModel || modelConfig.value.model
  }
}

// 切换自定义模型
function onToggleCustomModel() {
  // 仅切换开关状态，保存由用户点击“保存”按钮触发
  if (!useCustomModel.value) {
    // 关闭时，清空测试结果
    testResult.value = null
    return
  }

  modelConfig.value = buildCustomModelEditorConfig<TeamModelConfig>(
    globalModelDefaults.value,
    modelConfig.value,
  )
  testResult.value = null
}

// 测试连接
async function handleTestConnection() {
  testing.value = true
  testResult.value = null

  try {
    const response = await modelCatalog.testConnection({
      provider: modelConfig.value.provider || 'deepseek',
      api_key: modelConfig.value.api_key || undefined,
      api_base: modelConfig.value.api_base || undefined,
      model: modelConfig.value.model || 'deepseek-flash',
      ...buildSendableModelConfig(modelConfig.value),
    })
    
    testResult.value = {
      success: response.success,
      message: response.success 
        ? (response.message || t('settings.providers.testSuccess'))
        : (response.error || response.message || t('settings.providers.testFailed'))
    }
  } catch (error: any) {
    testResult.value = {
      success: false,
      message: error.response?.data?.error || error.message || t('settings.providers.testFailed')
    }
  } finally {
    testing.value = false
  }
}

// 监听 provider 变化，自动填充默认值
watch(() => modelConfig.value.provider, (newProvider, oldProvider) => {
  if (!newProvider || providers.value.length === 0 || isHydratingConfig.value) {
    return
  }

  const nextProvider = providers.value.find(p => p.id === newProvider)
  const previousProvider = oldProvider ? providers.value.find(p => p.id === oldProvider) : null

  if (!nextProvider) {
    return
  }

  const shouldUpdateApiBase = !modelConfig.value.api_base || (
    !!previousProvider?.defaultApiBase && modelConfig.value.api_base === previousProvider.defaultApiBase
  )
  if (shouldUpdateApiBase) {
    modelConfig.value.api_base = nextProvider.defaultApiBase || ''
  }

  const shouldUpdateModel = !modelConfig.value.model || (
    !!previousProvider?.defaultModel && modelConfig.value.model === previousProvider.defaultModel
  )
  if (shouldUpdateModel && nextProvider.defaultModel) {
    modelConfig.value.model = nextProvider.defaultModel
  }
})

const closeEditTeamDialog = () => {
  showEditTeamDialog.value = false
  activeTab.value = 'basic'
}

const saveTeamInfo = async () => {
  try {
    // 保存基本信息
    await teamsStore.updateTeam(props.team.id, {
      name: teamForm.value.name,
      description: teamForm.value.description,
      mode: teamForm.value.mode,
      cross_review: teamForm.value.cross_review,
      enable_skills: teamForm.value.enable_skills,
      agents: localAgents.value,
      is_active: props.team.is_active,
    })
    
    // 保存模型配置（仅管理员）
    if (userStore.isAdmin) {
      if (useCustomModel.value) {
        await agentTeamsApi.updateConfig(
          props.team.id,
          buildModelConfigOverrides<TeamModelConfig>(
            modelConfig.value,
            globalModelDefaults.value,
          ),
        )
      } else if (props.team.use_custom_model) {
        // 如果之前启用了自定义模型，现在关闭了，需要重置
        await agentTeamsApi.resetConfig(props.team.id)
      }
    }
    
    toast.success(t('teams.detail.teamUpdated'))
    closeEditTeamDialog()
    emit('updated')
  } catch (err: any) {
    toast.error(err.message || t('teams.detail.saveFailed'))
  }
}

const saveChanges = async () => {
  try {
    await teamsStore.updateTeam(props.team.id, {
      name: props.team.name,
      description: props.team.description,
      mode: props.team.mode,
      cross_review: props.team.cross_review,
      enable_skills: props.team.enable_skills || false,
      agents: localAgents.value,
      is_active: props.team.is_active,
    })
    toast.success(t('teams.detail.memberUpdated'))
    emit('updated')
  } catch (err: any) {
    toast.error(err.message || t('teams.detail.saveFailed'))
  }
}
</script>
<style scoped>
@import './styles/TeamDetail.css';
</style>

