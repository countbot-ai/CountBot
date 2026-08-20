<template>
  <div class="team-detail">
    <!-- 返回按钮和团队信息 -->
    <div class="detail-header">
      <button class="btn-back" @click="$emit('back')">
        <component :is="ArrowLeftIcon" :size="16" />
        返回团队列表
      </button>
      
      <div class="team-info-section">
        <div class="team-title-row">
          <h2>{{ team.name }}</h2>
          <div class="team-badges">
            <span class="badge badge-mode">{{ modeLabelMap[team.mode] }}</span>
            <span v-if="team.mode === 'council'" class="badge badge-review" :class="team.cross_review ? 'badge-cross' : 'badge-independent'">
              {{ team.cross_review ? '交叉模式' : '独立模式' }}
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
        <h3>团队成员 ({{ localAgents.length }})</h3>
        <div class="section-actions">
          <button v-if="team.mode === 'graph' && localAgents.length > 0" class="btn-secondary" @click="showGraph = !showGraph">
            <component :is="NetworkIcon" :size="16" />
            {{ showGraph ? '隐藏依赖图' : '查看依赖图' }}
          </button>
          <button class="btn-primary" @click="addMember">
            <component :is="PlusIcon" :size="16" />
            添加成员
          </button>
        </div>
      </div>

      <!-- 依赖关系图 (Graph模式) -->
      <div v-if="team.mode === 'graph' && showGraph && localAgents.length > 0" class="graph-section">
        <DependencyGraph :agents="localAgents" />
      </div>

      <div v-if="localAgents.length === 0" class="empty-members">
        <component :is="UsersIcon" :size="48" class="empty-icon" />
        <p>暂无成员，点击上方按钮添加</p>
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
              <span class="detail-label">视角:</span>
              <span class="detail-value">{{ agent.perspective || '-' }}</span>
            </div>
            <div v-else class="detail-item">
              <span class="detail-label">任务:</span>
              <span class="detail-value">{{ agent.task || '-' }}</span>
            </div>
            <div v-if="team.mode === 'graph' && agent.depends_on?.length" class="detail-item">
              <span class="detail-label">依赖:</span>
              <span class="detail-value">{{ agent.depends_on.join(', ') }}</span>
            </div>
            <div v-if="agent.condition" class="detail-item full-width">
              <span class="detail-label">执行条件:</span>
              <div class="condition-badge">
                <span class="condition-type">{{ agent.condition.type === 'output_contains' ? '包含' : '不包含' }}</span>
                <span class="condition-node">{{ agent.condition.node }}</span>
                <span class="condition-text">"{{ agent.condition.text }}"</span>
              </div>
            </div>
            <div v-if="agent.system_prompt" class="detail-item full-width">
              <span class="detail-label">系统提示词:</span>
              <div class="prompt-preview">{{ agent.system_prompt }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 编辑团队信息对话框 - 标签页形式 -->
    <Modal :model-value="showEditTeamDialog" @close="closeEditTeamDialog" size="large">
      <div class="dialog-content">
        <h3>编辑团队信息</h3>

        <!-- 标签页导航 -->
        <div class="tabs-nav">
          <button
            class="tab-btn"
            :class="{ active: activeTab === 'basic' }"
            @click="activeTab = 'basic'"
          >
            <component :is="InfoIcon" :size="16" />
            <span>基本信息</span>
          </button>
          <button
            class="tab-btn"
            :class="{ active: activeTab === 'model' }"
            @click="activeTab = 'model'"
          >
            <component :is="CpuIcon" :size="16" />
            <span>模型配置</span>
          </button>
        </div>

        <!-- 标签页内容 -->
        <div class="tabs-content">
          <!-- 基本信息标签页 -->
          <div v-show="activeTab === 'basic'" class="tab-panel">
            <div class="form-group">
              <label>团队名称 <span class="required">*</span></label>
              <input v-model="teamForm.name" type="text" class="form-input" />
            </div>

            <div class="form-group">
              <label>团队描述</label>
              <textarea v-model="teamForm.description" class="form-textarea" rows="3" />
            </div>

            <div class="form-group">
              <label>协作模式 <span class="required">*</span></label>
              <select v-model="teamForm.mode" class="form-select">
                <option value="pipeline">流水线 (Pipeline)</option>
                <option value="graph">依赖图 (Graph)</option>
                <option value="council">多视角 (Council)</option>
              </select>
            </div>

            <div v-if="teamForm.mode === 'council'" class="form-group">
              <div class="toggle-wrapper">
                <div class="toggle-content">
                  <span class="toggle-title">启用交叉评审</span>
                  <p class="toggle-hint">关闭后，成员将独立分析，不互相评审</p>
                </div>
                <SwitchToggle
                  v-model="teamForm.cross_review"
                  :width="44"
                  :height="24"
                  aria-label="启用交叉评审"
                />
              </div>
            </div>

            <div class="form-group">
              <div class="toggle-wrapper">
                <div class="toggle-content">
                  <span class="toggle-title">启用技能系统</span>
                  <p class="toggle-hint">开启后，子 Agent 可以使用技能（如图片生成、天气查询等）</p>
                </div>
                <SwitchToggle
                  v-model="teamForm.enable_skills"
                  :width="44"
                  :height="24"
                  aria-label="启用技能系统"
                />
              </div>
            </div>
          </div>

          <!-- 模型配置标签页 -->
          <div v-show="activeTab === 'model'" class="tab-panel">
            <!-- 使用自定义配置开关 -->
            <div class="config-toggle" :class="{ active: useCustomModel }">
              <div class="toggle-header">
                <label class="toggle-label">
                  <SwitchToggle
                    v-model="useCustomModel"
                    :width="48"
                    :height="28"
                    aria-label="为此团队使用自定义模型"
                    @change="onToggleCustomModel"
                  />
                  <div class="toggle-content-large">
                    <span class="toggle-text">为此团队使用自定义模型</span>
                    <span class="toggle-hint">团队成员将使用此配置的模型和 API</span>
                  </div>
                </label>
                <div v-if="useCustomModel" class="config-badge">
                  <component :is="SparklesIcon" :size="14" />
                  <span>自定义</span>
                </div>
              </div>
            </div>

            <div v-if="useCustomModel" class="model-config-section">
              <div class="model-config-toolbar">
                <div class="model-config-copy">
                  <h4>模型设置</h4>
                  <p>支持从模型预设快速填充团队专属配置</p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  :icon="LayoutGridIcon"
                  @click="openPresetPanel"
                >
                  模型预设
                </Button>
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
                  <input v-model="modelConfig.model" type="text" class="form-input" placeholder="glm-5" />
                </div>

              </div>

              <ModelParameterFields
                :temperature="modelConfig.temperature ?? 0"
                :max-tokens="modelConfig.max_tokens ?? 0"
                :max-iterations="modelConfig.max_iterations ?? 25"
                :thinking-enabled="modelConfig.thinking_enabled ?? true"
                @update:temperature="modelConfig.temperature = $event"
                @update:maxTokens="modelConfig.max_tokens = $event"
                @update:maxIterations="modelConfig.max_iterations = $event"
                @update:thinkingEnabled="modelConfig.thinking_enabled = $event"
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
                <h4>使用全局默认配置</h4>
                <p>启用自定义配置以为此团队设置专属的模型和 API</p>
                <Button
                  variant="outline"
                  size="sm"
                  :icon="LayoutGridIcon"
                  @click="openPresetPanel"
                >
                  使用模型预设
                </Button>
              </div>
            </div>
          </div>
        </div>

        <div class="dialog-actions">
          <button class="btn-secondary" @click="closeEditTeamDialog">取消</button>
          <button class="btn-primary" @click="saveTeamInfo">保存</button>
        </div>
      </div>
    </Modal>

    <ProviderPresetPanel
      v-model="showPresetPanel"
      :current-config="currentDraftConfig"
      :available-providers="providers"
      @apply-config="handleApplyPresetConfig"
    />

    <!-- 编辑成员对话框 -->
    <Modal :model-value="showEditMemberDialog" @close="closeMemberDialog" size="large">
      <div class="dialog-content">
        <h3>{{ editingMemberIndex === null ? '添加成员' : '编辑成员' }}</h3>

        <div class="form-group">
          <label>成员 ID <span class="required">*</span></label>
          <input v-model="memberForm.id" type="text" class="form-input" placeholder="例如：analyst" />
          <p class="form-hint">唯一标识符，用于依赖关系引用</p>
        </div>

        <div v-if="team.mode === 'council'" class="form-group">
          <label>视角 (Perspective) <span class="required">*</span></label>
          <input v-model="memberForm.perspective" type="text" class="form-input" placeholder="例如：技术架构师，关注可扩展性" />
          <p class="form-hint">描述这个成员的分析视角</p>
        </div>

        <div v-else class="form-group">
          <label>角色 (Role) <span class="required">*</span></label>
          <input v-model="memberForm.role" type="text" class="form-input" placeholder="例如：需求分析师" />
        </div>

        <div v-if="team.mode !== 'council'" class="form-group">
          <label>任务 (Task)</label>
          <textarea v-model="memberForm.task" class="form-textarea" rows="3" placeholder="描述这个成员的具体任务..." />
          <p class="form-hint">`task` 会作为实际执行任务传给子 Agent；如果未填写系统提示词，系统也会基于角色和任务自动生成默认系统提示。</p>
        </div>

        <div v-if="team.mode === 'graph'" class="form-group">
          <label>依赖 (Depends On)</label>
          
          <div class="dependency-selector">
            <div v-if="getSelectedDependencies().length > 0" class="selected-tags">
              <span v-for="dep in getSelectedDependencies()" :key="dep" class="dependency-tag">
                {{ dep }}
                <button type="button" class="tag-remove" @click="removeDependency(dep)">×</button>
              </span>
            </div>
            <select class="form-select" @change="addDependency($event)" :disabled="getAvailableDependencies().length === 0">
              <option value="">{{ getAvailableDependencies().length === 0 ? '没有可选的依赖节点' : '选择依赖节点...' }}</option>
              <option v-for="agent in getAvailableDependencies()" :key="agent.id" :value="agent.id">
                {{ agent.id }} - {{ agent.role || agent.perspective || '未命名' }}
              </option>
            </select>
          </div>
          <p class="form-hint">选择此成员需要等待哪些成员完成后才能执行</p>
        </div>

        <!-- 条件配置（Graph模式下始终显示） -->
        <div v-if="team.mode === 'graph'" class="form-group">
          <label>执行条件（可选）</label>
          
          <!-- 没有依赖时显示提示 -->
          <div v-if="!memberForm.depends_on_str.trim()" class="condition-disabled-hint">
            <component :is="InfoIcon" :size="16" />
            <span>请先选择依赖节点，然后可以配置基于依赖输出的执行条件</span>
          </div>
          
          <!-- 有依赖时显示配置 -->
          <div v-else class="condition-config">
            <div class="toggle-wrapper">
              <div class="toggle-content">
                <span class="toggle-title">启用条件执行</span>
                <p class="toggle-hint">根据依赖节点的输出决定是否执行此节点</p>
              </div>
              <SwitchToggle
                v-model="memberForm.enable_condition"
                :width="44"
                :height="24"
                aria-label="启用条件执行"
              />
            </div>

            <div v-if="memberForm.enable_condition" class="condition-form">
              <div class="form-row">
                <div class="form-col">
                  <label>条件类型</label>
                  <select v-model="memberForm.condition_type" class="form-select">
                    <option value="output_contains">输出包含</option>
                    <option value="output_not_contains">输出不包含</option>
                  </select>
                </div>
                <div class="form-col">
                  <label>检查节点</label>
                  <select v-model="memberForm.condition_node" class="form-select">
                    <option value="">选择节点...</option>
                    <option v-for="nodeId in getAllUpstreamNodes()" :key="nodeId" :value="nodeId">
                      {{ nodeId }} - {{ getAgentById(nodeId)?.role || getAgentById(nodeId)?.perspective || '未命名' }}
                    </option>
                  </select>
                  <p class="form-hint">可以选择任何上游节点（包括间接依赖）</p>
                </div>
              </div>
              <div class="form-row">
                <div class="form-col full">
                  <label>匹配文本</label>
                  <input 
                    v-model="memberForm.condition_text" 
                    type="text" 
                    class="form-input" 
                    placeholder="例如：测试通过、成功、无问题" 
                  />
                  <p class="form-hint">
                    {{ memberForm.condition_type === 'output_contains' 
                      ? '当依赖节点输出包含此文本时，执行当前节点' 
                      : '当依赖节点输出不包含此文本时，执行当前节点' }}
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="form-group">
          <label>系统提示词 (System Prompt)</label>
          <textarea 
            v-model="memberForm.system_prompt" 
            class="form-textarea prompt-textarea" 
            rows="8" 
            placeholder="为这个智能体定义持久的系统级指令，例如：&#10;&#10;你是一位资深的技术架构师，拥有15年的大型系统设计经验。你的职责是：&#10;1. 评估技术方案的可行性和可扩展性&#10;2. 识别潜在的技术风险和瓶颈&#10;3. 提供具体的技术建议和最佳实践&#10;&#10;请始终保持专业、客观，并提供可操作的建议。"
          />
          <p class="form-hint">
            `system_prompt` 会直接作为系统消息注入；如果这里留空，系统会自动用角色和任务生成默认系统提示。填写后会覆盖默认系统提示，但不会替代上面的 `task`。
          </p>
        </div>

        <div class="dialog-actions">
          <button class="btn-secondary" @click="closeMemberDialog">取消</button>
          <button class="btn-primary" @click="saveMember" :disabled="!canSaveMember">保存</button>
        </div>
      </div>
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
  LayoutGrid as LayoutGridIcon,
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
import { useToast } from '@/composables/useToast'
import { Modal } from '@/components/ui'
import Button from '@/components/ui/Button.vue'
import SwitchToggle from '@/components/ui/SwitchToggle.vue'
import ModelParameterFields from '@/components/ui/ModelParameterFields.vue'
import ProviderPresetPanel from '@/modules/settings/ProviderPresetPanel.vue'
import Select from '@/components/ui/Select.vue'
import DependencyGraph from './DependencyGraph.vue'
import { settingsAPI } from '@/api'
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

interface PresetApplyPayload {
  provider: string
  model: string
  apiKey: string
  baseUrl?: string
  enabled: boolean
  temperature?: number
  maxTokens?: number
  maxIterations?: number
  source: 'preset' | 'codingplan'
  label: string
}

const props = defineProps<Props>()
const emit = defineEmits(['back', 'updated'])
const { t } = useI18n()

const teamsStore = useAgentTeamsStore()
const toast = useToast()

const modeLabelMap: Record<string, string> = {
  pipeline: '流水线',
  graph: '依赖图',
  council: '多视角',
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
const showPresetPanel = ref(false)

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
const currentDraftConfig = computed(() => ({
  provider: modelConfig.value.provider || '',
  model: modelConfig.value.model || '',
  apiKey: modelConfig.value.api_key || '',
  baseUrl: modelConfig.value.api_base || '',
  enabled: true,
  temperature: modelConfig.value.temperature,
  maxTokens: modelConfig.value.max_tokens,
  maxIterations: modelConfig.value.max_iterations,
}))

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
    // 如果是新建模式，排除与当前 ID 相同的成员（虽然不太可能）
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

const removeMember = (index: number) => {
  if (!confirm('确定要删除这个成员吗？')) return
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
    const providersData = await settingsAPI.getProviders()
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
  if (!props.team.id) return
  
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

function openPresetPanel() {
  testResult.value = null
  showPresetPanel.value = true
}

function handleApplyPresetConfig(payload: PresetApplyPayload) {
  isHydratingConfig.value = true
  try {
    useCustomModel.value = true
    modelConfig.value = buildEffectiveModelConfig<TeamModelConfig>(
      globalModelDefaults.value,
      {
        ...modelConfig.value,
        provider: payload.provider,
        model: payload.model,
        api_mode: 'chat_completions',
        api_key: payload.apiKey,
        api_base: payload.baseUrl || '',
        temperature: payload.temperature ?? modelConfig.value.temperature,
        max_tokens: payload.maxTokens ?? modelConfig.value.max_tokens,
        max_iterations: payload.maxIterations ?? modelConfig.value.max_iterations,
      },
    )
    testResult.value = null
    ensureValidTeamProviderSelection()
  } finally {
    isHydratingConfig.value = false
  }
}

// 切换自定义模型
function onToggleCustomModel() {
  // 只是切换开关状态，不立即保存
  // 实际的保存会在用户点击"保存"按钮时进行
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
    const response = await settingsAPI.testConnection({
      provider: modelConfig.value.provider || 'zhipu',
      api_key: modelConfig.value.api_key || undefined,
      api_base: modelConfig.value.api_base || undefined,
      model: modelConfig.value.model || 'glm-5',
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
    
    // 保存模型配置
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
    
    toast.success('团队信息已更新')
    closeEditTeamDialog()
    emit('updated')
  } catch (err: any) {
    toast.error(err.message || '保存失败')
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
    toast.success('成员已更新')
    emit('updated')
  } catch (err: any) {
    toast.error(err.message || '保存失败')
  }
}
</script>
<style scoped>
@import './styles/TeamDetail.css';
</style>


